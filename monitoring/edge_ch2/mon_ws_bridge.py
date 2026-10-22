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
NBINS = 256                 # spectrum points sent to the UI
PUSH_HZ = 5.0               # per-channel UI update rate (lowered to cut CPU)
MAX_FFT_SEG = 8             # cap averaging segments per push (was unbounded -> 100% CPU)
ACTIVE_MARGIN_DB = 8.0      # rms this far above the rolling floor = ACTIVE

CLIENTS = set()
# latest per-channel state the ws server pushes
STATE = {ch: {"ch": ch, "band": "", "freq_mhz": 0.0, "samp_rate": 0.0,
              "spectrum": [], "time": [], "iq": [], "rms_dbfs": -120.0,
              "floor_dbfs": -120.0, "active": False, "t": 0.0}
         for ch in range(1, NCH + 1)}
FLOOR = {ch: -120.0 for ch in range(1, NCH + 1)}


def spectrum_db(x, nbins=NBINS):
    """Average |FFT|^2 of x into nbins points, in dBFS (0 dB = full scale)."""
    n = len(x)
    if n < nbins:
        return None
    fftlen = nbins
    acc = np.zeros(fftlen)
    w = np.hanning(fftlen)
    k = 0
    # cap the number of averaged segments so a big IQ block can't spike CPU
    nseg = min(MAX_FFT_SEG, (n - fftlen) // fftlen)
    for s in range(max(1, nseg)):
        i = s * fftlen
        seg = x[i:i + fftlen] * w
        acc += np.abs(np.fft.fftshift(np.fft.fft(seg))) ** 2
        k += 1
    if k == 0:
        return None
    acc /= k
    db = 10 * np.log10(acc / fftlen + 1e-12)   # rough dBFS
    return db


async def chan_reader(ch):
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVHWM, 16)
    sub.connect("tcp://127.0.0.1:%d" % (BASE_PORT + ch - 1))
    last_push = 0.0
    while True:
        try:
            hdr_b, iq_b = await sub.recv_multipart()
        except Exception:
            await asyncio.sleep(0.05); continue
        try:
            h = json.loads(hdr_b.decode())
        except Exception:
            continue
        x = np.frombuffer(iq_b, dtype=np.complex64)
        if x.size == 0:
            continue
        rms = float(10 * np.log10(np.mean(np.abs(x) ** 2) + 1e-12))
        # rolling noise floor (slow) when not clearly a signal
        f = FLOOR[ch]
        if rms < f + ACTIVE_MARGIN_DB:
            f = 0.98 * f + 0.02 * rms
        FLOOR[ch] = f
        active = rms > f + ACTIVE_MARGIN_DB
        now = time.time()
        if now - last_push >= 1.0 / PUSH_HZ:
            db = spectrum_db(x)
            spec = [round(float(v), 1) for v in db[::max(1, len(db)//NBINS)][:NBINS]] if db is not None else STATE[ch]["spectrum"]
            # REAL time-domain envelope: |IQ| block-averaged into 256 points (dBFS)
            tpts = 256
            a = np.abs(x)
            if a.size >= tpts:
                env = a[:a.size//tpts*tpts].reshape(tpts, -1).mean(axis=1)
                tenv = [round(float(v), 3) for v in (20*np.log10(env + 1e-9))]
            else:
                tenv = STATE[ch]["time"]
            # REAL IQ scatter: 160 subsampled samples, normalised to the block peak
            step = max(1, x.size // 160)
            samp = x[::step][:160]
            mx = float(np.abs(samp).max()) or 1.0
            iq = []
            for v in samp:
                iq.append(round(float(v.real)/mx, 3)); iq.append(round(float(v.imag)/mx, 3))
            STATE[ch] = {
                "ch": ch, "band": h.get("band", ""),
                "freq_mhz": float(h.get("freq", 0.0)) / 1e6,
                "samp_rate": float(h.get("samp_rate", 2e6)),
                "spectrum": spec, "time": tenv, "iq": iq,
                "rms_dbfs": round(rms, 1),
                "floor_dbfs": round(f, 1), "active": bool(active), "t": now,
            }
            last_push = now
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
