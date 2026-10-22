#!/usr/bin/env python3
"""mon_ws_bridge - monitoring -> UI WebSocket bridge.

mon_server scans the 4 USRP channels and PUBlishes per-channel IQ (+header) on
ZeroMQ 5201-5204. This bridge subscribes to all four, turns each channel's IQ
into a spectrum (FFT) + RMS + active/idle detection, and serves it over a
WebSocket so the 5-panel web UI can draw REAL per-channel graphs and detections
for CH1 (drone), CH3 (radar), CH4 (cellular). CH2 (terrestrial) has its own
decoder console; this bridge still carries CH2's spectrum for the overview.

  mon_server --channels ... --pub   (publishes 5201-5204)
  python3 mon_ws_bridge.py           (serves ws://127.0.0.1:8780)

Message to the UI (JSON), ~8 Hz per channel:
  {type:"mon", ch, band, freq_mhz, samp_rate, spectrum:[N dB], rms_dbfs,
   floor_dbfs, active, t}
"""
import argparse
import asyncio
import json
import os
import time

import numpy as np
import zmq
import zmq.asyncio
import websockets

NCH = 4
BASE_PORT = 5201
NFFT = 1024                 # FFT size sent to the UI (like the GNU Radio frequency sink default)
FFT_SEGS = 8                # average up to this many 1024-point segments (8192 samples)
TIME_N = 2048               # raw I/Q samples sent for the time plot
RING = 8192                 # samples kept per channel for the current look
MIN_PUSH = 4096             # push only when the look has this many settled samples (4 ms at 1 MS/s)
PUSH_HZ = 5.0               # per-channel UI update rate
SETTLE_S = 0.012            # drop the first 12 ms of a look: 10 ms retune/switch + margin
ACTIVE_MARGIN_DB = 8.0      # rms this far above that band's own floor = ACTIVE (same rule as mon_server)

CLIENTS = set()
# latest per-channel state the ws server pushes (empty until a look has real samples)
STATE = {ch: {"ch": ch, "band": "", "freq_mhz": 0.0, "samp_rate": 0.0,
              "spectrum": [], "i": [], "q": [], "rms_dbfs": -120.0,
              "floor_dbfs": -120.0, "active": False, "t": 0.0}
         for ch in range(1, NCH + 1)}
FLOOR = {}                  # (ch, band) -> lowest rms seen for that band (dBFS)


def spectrum_db(x, nfft=NFFT, segs=FFT_SEGS):
    """Averaged power spectrum, dBFS per bin (a full-scale complex tone reads 0 dBFS),
    FFT-shifted so bin 0 = fc - fs/2. Needs at least nfft samples, else None."""
    n = len(x)
    if n < nfft:
        return None
    w = np.hanning(nfft)
    nseg = max(1, min(segs, n // nfft))
    acc = np.zeros(nfft)
    for s in range(nseg):
        seg = x[n - (s + 1) * nfft: n - s * nfft] * w      # newest segments first
        acc += np.abs(np.fft.fftshift(np.fft.fft(seg))) ** 2
    acc /= nseg
    return 10 * np.log10(acc / (w.sum() ** 2) + 1e-15)


async def chan_reader(ch):
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVHWM, 16)
    sub.connect("tcp://127.0.0.1:%d" % (BASE_PORT + ch - 1))
    last_push = 0.0
    key = None              # (band, look, frame) of the look being buffered
    chunks, have, skip = [], 0, 0
    hdr = {}
    while True:
        try:
            hdr_b, iq_b = await sub.recv_multipart()
        except Exception:
            await asyncio.sleep(0.05); continue
        try:
            h = json.loads(hdr_b.decode())
        except Exception:
            continue
        fs = float(h.get("samp_rate", 0.0) or 0.0)
        if fs <= 0:
            continue                       # no sample rate in the feed: nothing honest to draw
        k = (h.get("band", ""), h.get("look", 0), h.get("frame", 0))
        if k != key:                       # new look -> new buffer, skip the retune/settle samples
            key, chunks, have, hdr = k, [], 0, h
            skip = int(SETTLE_S * fs)
        x = np.frombuffer(iq_b, dtype=np.complex64)
        if skip:
            d = min(skip, x.size); x = x[d:]; skip -= d
        if x.size == 0:
            continue
        chunks.append(x); have += x.size
        while len(chunks) > 1 and have - chunks[0].size >= RING:
            have -= chunks[0].size; chunks.pop(0)
        now = time.time()
        if now - last_push < 1.0 / PUSH_HZ or have < MIN_PUSH:
            continue
        last_push = now
        buf = np.concatenate(chunks)[-RING:]
        db = spectrum_db(buf)
        if db is None:
            continue
        seg = buf[-TIME_N:]
        rms = float(10 * np.log10(np.mean(np.abs(buf[-4096:]) ** 2) + 1e-15))
        band = hdr.get("band", "")
        fk = (ch, band)
        fl = FLOOR.get(fk)
        if fl is None or rms < fl:
            fl = FLOOR[fk] = rms
        STATE[ch] = {
            "ch": ch, "band": band, "freq_mhz": float(hdr.get("freq", 0.0)) / 1e6,
            "samp_rate": fs, "nfft": NFFT, "nsamp": int(buf.size),
            "spectrum": [round(float(v), 1) for v in db],
            "i": [round(float(v), 5) for v in seg.real],
            "q": [round(float(v), 5) for v in seg.imag],
            "rms_dbfs": round(rms, 1), "floor_dbfs": round(fl, 1),
            "active": bool(rms > fl + ACTIVE_MARGIN_DB), "t": now,
        }
        await broadcast(STATE[ch])


async def broadcast(msg):
    if not CLIENTS:
        return
    data = json.dumps({"type": "mon", **msg})
    for ws in list(CLIENTS):
        try:
            await ws.send(data)
        except Exception:
            CLIENTS.discard(ws)


CH2_MODE_FILE = os.path.expanduser("~/radar2/edge_ch2/ch2_mode.txt")
CH2_LOCK_FILE = os.path.expanduser("~/radar2/edge_ch2/ch2_lock.txt")


def read_ch2_lock():
    """CH2 Mode-2 live state written by mon_server: 'scan', 'search', or
    'lock|<band>|<MHz>'. Returned as a dict for the UI."""
    try:
        s = open(CH2_LOCK_FILE).read().strip()
    except Exception:
        s = ""
    if s.startswith("lock|"):
        parts = s.split("|")
        band = parts[1] if len(parts) > 1 else ""
        mhz = float(parts[2]) if len(parts) > 2 else 0.0
        return {"state": "lock", "band": band, "freq_mhz": mhz}
    if s in ("scan", "search"):
        return {"state": s, "band": "", "freq_mhz": 0.0}
    return {"state": "scan", "band": "", "freq_mhz": 0.0}


async def broadcast_raw(data):
    for ws in list(CLIENTS):
        try:
            await ws.send(data)
        except Exception:
            CLIENTS.discard(ws)


async def ch2_lock_poller():
    """Watch the CH2 lock-status file and push every change to the UI."""
    last = None
    while True:
        st = read_ch2_lock()
        key = (st["state"], st["band"], round(st["freq_mhz"], 4))
        if key != last:
            last = key
            await broadcast_raw(json.dumps({"type": "ch2_lock", **st}))
        await asyncio.sleep(0.3)


def set_ch2_mode(mode):
    """Write the CH2 terrestrial mode the UI picked; mon_server polls this file.
    'scan' = Mode 1 (scan all bands), 'auto' = Mode 2 (detect & hold strongest)."""
    mode = "auto" if mode == "auto" else "scan"
    try:
        with open(CH2_MODE_FILE, "w") as f:
            f.write(mode)
    except Exception as e:
        print("[mon_ws] ch2_mode write failed:", e, flush=True)
    return mode


async def handler(ws):
    CLIENTS.add(ws)
    try:
        # send current snapshot immediately, plus the current CH2 mode
        for ch in range(1, NCH + 1):
            await ws.send(json.dumps({"type": "mon", **STATE[ch]}))
        try:
            cur = open(CH2_MODE_FILE).read().strip() or "scan"
        except Exception:
            cur = "scan"
        await ws.send(json.dumps({"type": "ch2_mode", "mode": cur}))
        await ws.send(json.dumps({"type": "ch2_lock", **read_ch2_lock()}))
        async for raw in ws:
            # UI -> backend control: set CH2 terrestrial mode
            try:
                m = json.loads(raw)
            except Exception:
                continue
            if m.get("cmd") == "ch2_mode":
                mode = set_ch2_mode(m.get("mode"))
                print("[mon_ws] CH2 mode -> %s" % mode, flush=True)
                data = json.dumps({"type": "ch2_mode", "mode": mode})
                for c in list(CLIENTS):
                    try: await c.send(data)
                    except Exception: CLIENTS.discard(c)
    finally:
        CLIENTS.discard(ws)


async def main_async(port):
    tasks = [asyncio.create_task(chan_reader(ch)) for ch in range(1, NCH + 1)]
    tasks.append(asyncio.create_task(ch2_lock_poller()))
    print("[mon_ws] monitoring 5201-5204 -> ws://127.0.0.1:%d" % port, flush=True)
    async with websockets.serve(handler, "127.0.0.1", port):
        await asyncio.gather(*tasks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    a = ap.parse_args()
    try:
        asyncio.run(main_async(a.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
