#!/usr/bin/env python3
"""mon_ws_bridge - monitoring -> UI WebSocket bridge (ws://127.0.0.1:8780).

Subscribes to the scanner's per-channel IQ (ZeroMQ 5201-5204) and detections (5210) and
serves the UI. Real data only.

  * status (JSON, all channels, 2 Hz):  {type:"stat", ch, band, freq_mhz, samp_rate,
        rms_dbfs (DC removed), floor_dbfs, dc_dbfs, dc_i, dc_q, active, t}
  * full graph data (BINARY, only the channel a client is viewing, 10 Hz):
        b"MON1" + uint32 LE header length + header JSON (the status fields + nfft, window,
        ntime) + float32 spectrum[nfft] (dBFS per bin) + float32 I[ntime] + float32 Q[ntime]
    Binary + one channel at a time keeps the CPU low (JSON text of 4 channels x 10k numbers
    was a big part of the load).
  * detections (JSON, per dwell), the scan plan, band locks, CH2 mode.
UI -> bridge: {cmd:"view",ch}, {cmd:"pin",ch,band}, {cmd:"fftcfg",ch,nfft,window}, {cmd:"ch2_mode",mode}.
"""
import argparse
import asyncio
import json
import os
import struct
import time

import collections
import sys

import numpy as np
import zmq
import zmq.asyncio
import websockets

NCH = 4
BASE_PORT = 5201
DET_PORT = 5210             # detection verdicts from mon_server (one JSON per dwell)
NFFT = 1024                 # FFT size sent to the UI (like the GNU Radio frequency sink default)
FFT_SEGS = 8                # average up to this many 1024-point segments (8192 samples)
TIME_N = 4096               # raw I/Q samples sent for the time plot (the UI picks how many to show)
RING = 8192                 # samples kept per channel for the current look
MIN_PUSH = 4096             # push only when the look has this many settled samples (4 ms at 1 MS/s)
VIEW_HZ = 10.0              # full graph data rate for the channel being viewed
STATUS_HZ = 2.0             # status rate for every channel
SETTLE_S = 0.014            # drop the first 14 ms of a look: 10 ms switch + retune transient (measured) + chunk
ACTIVE_MARGIN_DB = 8.0      # rms (DC removed) this far above that band's own floor = ACTIVE

CLIENTS = set()
VIEW = {}                   # websocket -> channel it shows (gets the binary graph data)
STATUS = {}                 # ch -> last status dict (sent to new clients)
FLOOR = {}                  # (ch, band) -> lowest rms seen for that band (dBFS)
FFT_SIZES = (256, 512, 1024, 2048, 4096, 8192)
FFTCFG = {ch: {"nfft": NFFT, "window": "hann"} for ch in range(1, NCH + 1)}   # set from the UI
PIN_FILE = os.path.expanduser("~/radar2/edge_ch2/pin_ch%d.txt")               # read by mon_server
GAIN_FILE = os.path.expanduser("~/radar2/edge_ch2/gain_ch%d.txt")             # read by mon_server (live RX gain)

# the real scan plan (scan_plan.py, the scanner's source of truth) -> the UI's band lists
sys.path.insert(0, os.path.expanduser("~/radar2/guru_mon_scan"))
try:
    import scan_plan
except Exception as e:                       # no plan -> the UI shows no band list (never a made-up one)
    scan_plan = None
    print("[mon_ws] scan_plan not importable: %s" % e, flush=True)


def build_plan():
    if scan_plan is None:
        return {}
    out = {}
    for i, fr in enumerate(scan_plan.build_frames(0.0)):
        seen = collections.OrderedDict()
        for name, fc, dw in fr:
            d = seen.setdefault(name, {"name": name, "freq_mhz": fc / 1e6, "dwell_ms": dw, "count": 0})
            d["count"] += 1
        out[i + 1] = {"bands": list(seen.values()), "looks": len(fr),
                      "frame_ms": scan_plan.frame_ms(fr), "switch_ms": scan_plan.SWITCH_MS}
    return out


PLAN = build_plan()


def window(name, n):
    """FFT windows offered by the GNU Radio frequency sink."""
    k = np.arange(n)
    x = 2 * np.pi * k / (n - 1)
    if name == "rect":
        return np.ones(n)
    if name == "hamming":
        return np.hamming(n)
    if name == "blackman":
        return np.blackman(n)
    if name == "blackmanharris":
        return 0.35875 - 0.48829 * np.cos(x) + 0.14128 * np.cos(2 * x) - 0.01168 * np.cos(3 * x)
    if name == "flattop":
        return (0.21557895 - 0.41663158 * np.cos(x) + 0.277263158 * np.cos(2 * x)
                - 0.083578947 * np.cos(3 * x) + 0.006947368 * np.cos(4 * x))
    if name == "kaiser":
        return np.kaiser(n, 8.6)
    return np.hanning(n)


def read_gain_req(ch):
    try:
        return float(open(GAIN_FILE % ch).read().strip())
    except Exception:
        return None


def read_pin(ch):
    try:
        return open(PIN_FILE % ch).read().strip()
    except Exception:
        return ""


def spectrum_db(x, nfft=NFFT, segs=FFT_SEGS, win="hann"):
    """Averaged power spectrum, dBFS per bin (a full-scale complex tone reads 0 dBFS),
    FFT-shifted so bin 0 = fc - fs/2. Needs at least nfft samples, else None."""
    n = len(x)
    if n < nfft:
        return None
    w = window(win, nfft)
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
    last_full = last_stat = 0.0
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
        cfg = FFTCFG[ch]
        viewers = [w for w, c in list(VIEW.items()) if c == ch]
        want_full = bool(viewers) and now - last_full >= 1.0 / VIEW_HZ
        want_stat = now - last_stat >= 1.0 / STATUS_HZ
        if not (want_full or want_stat) or have < max(MIN_PUSH, cfg["nfft"]):
            continue
        buf = np.concatenate(chunks)[-RING:]
        tail = buf[-4096:]
        dc = complex(tail.mean())                       # what is left of the DC offset (should be tiny)
        rms = float(10 * np.log10(np.mean(np.abs(tail - dc) ** 2) + 1e-15))   # signal level without DC
        band = hdr.get("band", "")
        fk = (ch, band)
        fl = FLOOR.get(fk)
        if fl is None or rms < fl:
            fl = FLOOR[fk] = rms
        st = {"type": "stat", "ch": ch, "band": band, "freq_mhz": float(hdr.get("freq", 0.0)) / 1e6,
              "samp_rate": fs, "nsamp": int(buf.size),
              "dc_i": round(dc.real, 4), "dc_q": round(dc.imag, 4),
              "dc_dbfs": round(float(20 * np.log10(abs(dc) + 1e-9)), 1),
              "rms_dbfs": round(rms, 1), "floor_dbfs": round(fl, 1),
              "active": bool(rms > fl + ACTIVE_MARGIN_DB), "t": now}
        if want_stat:
            last_stat = now
            STATUS[ch] = st
            await broadcast_raw(json.dumps(st))
        if want_full:
            last_full = now
            db = spectrum_db(buf, cfg["nfft"], FFT_SEGS, cfg["window"])
            if db is None:
                continue
            seg = buf[-TIME_N:]
            h2 = dict(st, type="mon", nfft=int(cfg["nfft"]), window=cfg["window"], ntime=int(seg.size))
            hj = json.dumps(h2).encode()
            payload = (b"MON1" + struct.pack("<I", len(hj)) + hj + db.astype(np.float32).tobytes()
                       + seg.real.astype(np.float32).tobytes() + seg.imag.astype(np.float32).tobytes())
            for w in viewers:
                try:
                    await w.send(payload)
                except Exception:
                    CLIENTS.discard(w); VIEW.pop(w, None)


async def det_reader():
    """Forward the scanner's per-dwell detection verdicts (band, peak, floor, active) to the UI."""
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVHWM, 256)
    sub.connect("tcp://127.0.0.1:%d" % DET_PORT)
    while True:
        try:
            m = json.loads(await sub.recv_string())
        except Exception:
            await asyncio.sleep(0.05); continue
        m["type"] = "det"
        await broadcast_raw(json.dumps(m))


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
            if ch in STATUS:
                await ws.send(json.dumps(STATUS[ch]))
        try:
            cur = open(CH2_MODE_FILE).read().strip() or "scan"
        except Exception:
            cur = "scan"
        await ws.send(json.dumps({"type": "ch2_mode", "mode": cur}))
        await ws.send(json.dumps({"type": "plan", "plan": PLAN}))
        for c in range(1, NCH + 1):
            await ws.send(json.dumps({"type": "pin", "ch": c, "band": read_pin(c)}))
            await ws.send(json.dumps({"type": "gain", "ch": c, "req": read_gain_req(c)}))
        await ws.send(json.dumps({"type": "ch2_lock", **read_ch2_lock()}))
        async for raw in ws:
            # UI -> backend control: set CH2 terrestrial mode
            try:
                m = json.loads(raw)
            except Exception:
                continue
            if m.get("cmd") == "view":
                c = int(m.get("ch", 0) or 0)
                if c in range(1, NCH + 1):
                    VIEW[ws] = c
                else:
                    VIEW.pop(ws, None)
                continue
            if m.get("cmd") == "pin":
                # UI band lock: '' = MON plan, else a band of that channel's plan
                c = int(m.get("ch", 0)); band = str(m.get("band") or "")
                names = [b["name"] for b in PLAN.get(c, {}).get("bands", [])]
                if c in range(1, NCH + 1) and (band == "" or band in names):
                    with open(PIN_FILE % c, "w") as f:
                        f.write(band)
                    print("[mon_ws] CH%d %s" % (c, ("LOCK -> " + band) if band else "MON plan"), flush=True)
                    data = json.dumps({"type": "pin", "ch": c, "band": band})
                    for cl in list(CLIENTS):
                        try: await cl.send(data)
                        except Exception: CLIENTS.discard(cl)
                continue
            if m.get("cmd") == "gain":
                # UI RX gain for one channel -> mon_server applies it live (clamped to the radio's range)
                c = int(m.get("ch", 0))
                try:
                    db = float(m.get("db"))
                except Exception:
                    continue
                if c in range(1, NCH + 1) and 0.0 <= db <= 100.0:
                    with open(GAIN_FILE % c, "w") as f:
                        f.write("%.1f" % db)
                    for k in [k for k in FLOOR if k[0] == c]:     # floors were measured at the old gain
                        del FLOOR[k]
                    print("[mon_ws] CH%d RX gain request -> %.1f dB" % (c, db), flush=True)
                    data = json.dumps({"type": "gain", "ch": c, "req": db})
                    for cl in list(CLIENTS):
                        try: await cl.send(data)
                        except Exception: CLIENTS.discard(cl)
                continue
            if m.get("cmd") == "fftcfg":
                c = int(m.get("ch", 0))
                if c in FFTCFG:
                    n = int(m.get("nfft", NFFT)); w = str(m.get("window", "hann"))
                    if n in FFT_SIZES:
                        FFTCFG[c]["nfft"] = n
                    if w in ("hann", "hamming", "blackman", "blackmanharris", "flattop", "kaiser", "rect"):
                        FFTCFG[c]["window"] = w
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
        VIEW.pop(ws, None)


async def main_async(port):
    tasks = [asyncio.create_task(chan_reader(ch)) for ch in range(1, NCH + 1)]
    tasks.append(asyncio.create_task(ch2_lock_poller()))
    tasks.append(asyncio.create_task(det_reader()))
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
