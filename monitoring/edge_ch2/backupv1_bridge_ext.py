#!/usr/bin/env python3
"""backupv1_bridge_ext - the terrestrial console bridge (ws 8787) on the X310 monitoring pipeline.

The console + bridge come from the terrestrial repo (backupv1/secuecom-version1/gui), built for ONE
USRP B210 driven by its own Module 1 and a decoder (allinone.py) the bridge starts itself. Here the
radio is the USRP-2945 (X310 31082D8) and CH2 (TwinRX A/RX2) is shared with the MON scan:

    mon_server (CH2 scan / auto-lock) -> ZMQ 5202 -> ch2_header_router -> TCP 7001-7004
        -> allinone.py (started by the watchdog) -> decoded audio ZMQ 9101-9104, TETRA events 9105
    mon_server detector verdicts -> ZMQ 5210

This wrapper imports the repo bridge UNCHANGED and replaces only what does not fit this hardware:
  - Module 1 ("Start hardware")   -> no process: the console connects to the router ports.
  - Module 2 ("Start decoder")    -> no 2nd allinone.py (the watchdog runs one; a 2nd one cannot bind
                                     9101-9105 and doubles the CPU): attach the audio taps + TETRA events.
  - band ACTIVE / recording gate  -> the detector's verdict for that band (narrowband line), not the repo's
                                     -60 dBFS level: the level also fired on the retune transient and on
                                     the other bands' noise.
  - band frequencies              -> the real port centres (scan plan RF centre, or the decoder centre the
                                     router shifts to, e.g. DMR 446.11875).
  - RX gain                        -> live CH2 gain via edge_ch2/gain_ch2.txt (mon_server applies it, no restart).
  - status                         -> real values: CH2 gain, TwinRX LO lock, MON frame #, CH2 mode / lock.
Both "modules" start automatically: the pipeline is always running.

Run under the SYSTEM python (GR 3.10), from run_monitor.py.
"""
import asyncio
import importlib.util
import json
import os
import socket
import sys
import time

import numpy as np
import zmq
import zmq.asyncio

ROOT = os.path.expanduser("~/radar2")
EDGE = os.path.join(ROOT, "edge_ch2")
REPO_BRIDGE = os.path.join(ROOT, "backupv1", "secuecom-version1", "gui", "bridge_server.py")
CONSOLE_DIR = os.path.join(EDGE, "ch2_console")
GAIN_FILE = os.path.join(EDGE, "gain_ch2.txt")
CH2_MODE_FILE = os.path.join(EDGE, "ch2_mode.txt")
CH2_LOCK_FILE = os.path.join(EDGE, "ch2_lock.txt")
DET_ADDR = "tcp://127.0.0.1:5210"
DEVICE = "USRP-2945 (X310 31082D8) · TwinRX A/RX2 = CH2"
LINK = "1 GbE · 192.168.10.2"
VERDICT_FRESH_S = 1.2      # a band's verdict counts this long (hold dwell 150 ms .. search cycle ~1 s)

spec = importlib.util.spec_from_file_location("bv1_bridge", REPO_BRIDGE)
bs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bs)

sys.path.insert(0, os.path.join(ROOT, "guru_mon_scan"))
sys.path.insert(0, EDGE)
import scan_plan                                   # noqa: E402
from ch2_header import proto_for_band              # noqa: E402

_rs = importlib.util.spec_from_file_location("ch2_router", os.path.join(EDGE, "ch2_header_router.py"))
_router = importlib.util.module_from_spec(_rs)
_rs.loader.exec_module(_router)

# ---------------------------------------------------------------- real band table (scan plan + router)
PLAN = {}            # proto key -> {rf, centre, dwell_ms, band}
for name, freq, dwell in scan_plan.FRAMES[1]():
    k = proto_for_band(name)
    if k in ("dmr", "nxdn", "p25", "tetra") and k not in PLAN:
        c = _router.DECODE_CENTRE_HZ.get(k, freq)
        if abs(c - freq) >= 0.4 * _router.OUT_RATE:
            c = freq
        PLAN[k] = {"rf": freq, "centre": c, "dwell_ms": dwell, "band": name}
for b in bs.BANDS:
    if b["key"] in PLAN:
        b["freq"] = round(PLAN[b["key"]]["centre"] / 1e6, 6)

# recordings live next to the console copy (served by console_http at /recordings/)
bs.RECORDINGS_DIR = os.path.join(CONSOLE_DIR, "recordings")
os.makedirs(bs.RECORDINGS_DIR, exist_ok=True)

DET = {k: {"active": False, "t": 0.0} for k in ("dmr", "nxdn", "p25", "tetra")}
PORT_REAL_T = {k: 0.0 for k in DET}       # last time the router port carried real IQ (not zero-fill)
bs.STATE.update({"device": DEVICE, "link": LINK, "gain_min": None, "gain_max": None,
                 "ch2_mode": None, "ch2_lock": None, "bands": PLAN})


def _read(fn):
    try:
        with open(fn) as f:
            return f.read().strip()
    except OSError:
        return None


async def det_reader():
    """CH2 detector verdicts (ZMQ 5210): band ACTIVE, gain, LO lock, frame number."""
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.connect(DET_ADDR)
    while True:
        try:
            v = json.loads(await sub.recv_string())
        except Exception:
            await asyncio.sleep(0.2)
            continue
        if v.get("ch") != 2:
            continue
        k = proto_for_band(v.get("band", ""))
        now = time.time()
        if v.get("gain_db") is not None:
            bs.STATE["rx_gain_actual"] = v["gain_db"]
        bs.STATE["gain_min"], bs.STATE["gain_max"] = v.get("gain_min"), v.get("gain_max")
        lo = v.get("lo_locked")
        bs.STATE["lo_lock"] = None if lo is None else ("OK" if lo else "UNLOCKED")
        bs.STATE["cycle"] = int(v.get("frame", 0))
        if k in DET:
            act = bool(v.get("active"))
            DET[k] = {"active": act, "t": now, "peak": v.get("peak_dbfs"), "nb_mhz": v.get("nb_mhz"),
                      "nb_db": v.get("nb_db")}
            if act:
                bs.STATE["active_band"] = k
                if now - PORT_REAL_T[k] < 0.4:
                    bs.BAND_RF_LAST[k] = now          # keep recording through the dwell's decode tail


async def status_pusher():
    while True:
        bs.STATE["ch2_mode"] = _read(CH2_MODE_FILE) or "scan"
        bs.STATE["ch2_lock"] = _read(CH2_LOCK_FILE)
        bs.STATE["clients"] = {b["key"]: _port_clients(b["port"]) for b in bs.BANDS}
        if bs.STATE["active_band"] and time.time() - DET[bs.STATE["active_band"]]["t"] > 3 * VERDICT_FRESH_S:
            bs.STATE["active_band"] = None
        await bs.broadcast({"type": "status", **bs.STATE})
        await asyncio.sleep(1.0)


def _port_clients(port):
    """1 when the decoder (allinone.py) holds a connection to this router port, else 0."""
    try:
        out = os.popen("ss -tnpH state established '( dport = :%d )' 2>/dev/null" % port).read()
    except Exception:
        return 0
    for pid in set(int(p) for p in __import__("re").findall(r"pid=(\d+)", out)):
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as f:
                if b"allinone.py" in f.read():
                    return 1
        except OSError:
            pass
    return 0


async def iq_reader(band):
    """Repo iq_reader with ONE change: 'active' = the detector's fresh verdict for this band AND the port
    carrying real IQ right now. Same message format, spectrum, channel table and recording gate."""
    key, port = band["key"], band["port"]
    chunk_bytes = bs.FFT_N * 8
    while bs.STATE["running"]:
        try:
            reader, _writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.5)
            continue
        buf = b""
        last_send = 0.0
        try:
            while bs.STATE["running"]:
                data = await reader.read(65536)
                if not data:
                    break
                buf += data
                while len(buf) >= chunk_bytes:
                    chunk, buf = buf[:chunk_bytes], buf[chunk_bytes:]
                    now = time.time()
                    samples = np.frombuffer(chunk, dtype=np.complex64)
                    real = bool(np.any(samples))
                    if real:
                        PORT_REAL_T[key] = now
                    d = DET[key]
                    active = real and d["active"] and now - d["t"] < VERDICT_FRESH_S
                    bs.BAND_RF_ACTIVE[key] = active
                    if active:
                        bs.BAND_RF_LAST[key] = now
                    if now - last_send < 0.09:
                        continue
                    last_send = now
                    mag2 = np.abs(samples) ** 2
                    rms = float(np.sqrt(np.mean(mag2)))
                    rms_db = 20 * np.log10(rms) if rms > 1e-12 else -120.0
                    win = samples * np.hanning(len(samples))
                    spec_pow = np.abs(np.fft.fftshift(np.fft.fft(win, bs.FFT_N))) ** 2
                    spec_db = 10 * np.log10(np.maximum(spec_pow, 1e-18))
                    chans = bs.channel_powers(spec_pow, key)
                    best = max(range(len(chans)), key=lambda i: chans[i]) if chans else -1
                    noise = float(np.median(chans)) if chans else 0.0
                    occupied = [i for i, p in enumerate(chans) if p - noise > bs.CHAN_SNR_DB] if active else []
                    await bs.broadcast({
                        "type": "iq", "band": key, "active": bool(active), "rms_db": round(rms_db, 1),
                        "spectrum": [round(float(x), 1) for x in spec_db[::2]],
                        "time": [round(float(x), 4) for x in samples.real[::4]][:64],
                        "chan_db": [round(float(p), 1) for p in chans],
                        "chan_best": best if active else -1,
                        "chan_best_db": round(float(chans[best] - noise), 1) if (active and chans) else None,
                        "chan_occupied": occupied,
                        "chan_bw_hz": int(bs.SAMP_RATE / bs.CHANNELS_PER_BAND[key]),
                        "det_nb_mhz": d.get("nb_mhz") if active else None,
                    })
        except (ConnectionResetError, OSError):
            pass
        finally:
            try:
                _writer.close()
            except Exception:
                pass
        await asyncio.sleep(0.5)


async def start_module1_ext():
    """'Start hardware': the X310 is already streaming (mon_server); connect the console to CH2's ports."""
    if bs.STATE["running"]:
        return
    bs.STATE["running"] = True
    bs.STATE["pid"] = None
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] console connected to CH2 of the %s (router ports 7001-7004)" % DEVICE})
    await bs.broadcast({"type": "status", **bs.STATE})
    for b in bs.BANDS:
        bs.spawn(iq_reader(b))


async def stop_module1_ext():
    """'Stop': disconnect the console's spectrum feed only. The radio keeps scanning for the other channels."""
    bs.STATE["running"] = False
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] console feed stopped (the X310 keeps running: it serves all 4 channels)"})
    await bs.broadcast({"type": "status", **bs.STATE})


class _ExternalDecoder:
    """Stands in for the repo's Module 2 Popen: allinone.py is run (and restarted) by the watchdog."""
    pid = None

    def poll(self):
        return None if _decoder_up() else 1


def _decoder_up():
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", 9101)) == 0
    finally:
        s.close()


async def start_module2_ext():
    """'Start decoder': attach to the running allinone.py (audio taps 9101-9104, TETRA events 9105)."""
    if bs.proc2 is not None:
        return
    if not _decoder_up():
        await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                            "text": "[BRIDGE] decoder (allinone.py) is not up yet - the watchdog starts it; retrying"})
        await bs.broadcast({"type": "decoder_status", "running": False})
        return
    bs.proc2 = _ExternalDecoder()
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] attached to the running decoder allinone.py: real decoded audio + TETRA events"})
    await bs.broadcast({"type": "decoder_status", "running": True})
    for k in ("dmr", "nxdn", "p25", "tetra"):
        bs.spawn(bs.audio_tap_reader(k))
    bs.spawn(bs.tetra_event_reader())


async def stop_module2_ext():
    """'Stop decoder': detach the console from the audio taps (the decoder itself keeps running)."""
    bs.proc2 = None
    for band in list(bs.recorders):
        bs.close_recording(band)
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] console detached from the decoder audio (allinone.py keeps running)"})
    await bs.broadcast({"type": "decoder_status", "running": False})


async def apply_gain_ext(gain_db):
    """Live CH2 RX gain: mon_server applies gain_ch2.txt on its next CH2 dwell (no restart)."""
    try:
        g = float(gain_db)
    except (TypeError, ValueError):
        return
    lo, hi = bs.STATE.get("gain_min"), bs.STATE.get("gain_max")
    if lo is not None and hi is not None:
        g = max(lo, min(hi, g))
    tmp = GAIN_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write("%.1f\n" % g)
    os.replace(tmp, GAIN_FILE)
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] CH2 RX gain -> %.1f dB (live; CH2 band floors re-learn)" % g})


async def apply_schedule_ext(new_dwell):
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] CH2 dwell times come from the MON scan plan (scan_plan.py): "
                                + ", ".join("%s %.0f ms" % (k.upper(), v["dwell_ms"]) for k, v in PLAN.items())
                                + " - not changed from the console"})


async def decoder_watch():
    """Keep the console attached: (re)attach when allinone.py is up, report when it goes down."""
    while True:
        up = _decoder_up()
        if up and bs.proc2 is None:
            await start_module2_ext()
        elif not up and bs.proc2 is not None:
            bs.proc2 = None
            await bs.broadcast({"type": "decoder_status", "running": False})
        await asyncio.sleep(2.0)


bs.iq_reader = iq_reader
bs.start_module1 = start_module1_ext
bs.stop_module1 = stop_module1_ext
bs.start_module2 = start_module2_ext
bs.stop_module2 = stop_module2_ext
bs.apply_gain = apply_gain_ext
bs.apply_schedule = apply_schedule_ext


async def main():
    import websockets
    print("SecureCOM console bridge (X310 CH2) - ws://127.0.0.1:8787", flush=True)
    print("bands: " + ", ".join("%s RF %.4f MHz port centre %.5f MHz dwell %.0f ms"
                                % (k, v["rf"] / 1e6, v["centre"] / 1e6, v["dwell_ms"]) for k, v in PLAN.items()),
          flush=True)
    async with websockets.serve(bs.handler, "127.0.0.1", 8787):
        bs.spawn(det_reader())
        bs.spawn(status_pusher())
        await start_module1_ext()
        bs.spawn(decoder_watch())
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
