#!/usr/bin/env python3
"""airmar_bridge_ext - the old repo's air/maritime bridge (terrestrial_src/airmaritime_bridge.py, ws 8887)
on the X310 CH2 feed.

The repo bridge is imported UNCHANGED (AIS/ADS-B decode listeners on ZMQ 9201/9202, AIVDM parsing, vessel and
aircraft tables, websocket protocol). Replaced only where the B210 Module 1 setup does not exist here:
  - band table: AIS port centre 162.000 MHz at 250 kS/s, ADS-B 1090 MHz at the real CH2 rate (200 kS/s);
  - spectrum 'active': the CH2 detector verdict for that band (ZMQ 5210) instead of the repo's -60 dBFS level;
  - 'status' (which the console took from the B210 Module 1 log via ws 8787): which band CH2 is dwelling on now
    (its port carries real IQ only during the dwell), the scan-plan dwell / frequency, CH2 gain, TwinRX LO lock;
  - decoder: run (and restarted) by the watchdog -> Start/Stop do not spawn a second airmaritime_decoder_live.
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
REPO_BRIDGE = os.path.join(ROOT, "terrestrial_src", "airmaritime_bridge.py")
DET_ADDR = "tcp://127.0.0.1:5210"
DEVICE = "USRP-2945 (X310 31082D8) · TwinRX A/RX2 = CH2"
LINK = "1 GbE · 192.168.10.2"
VERDICT_FRESH_S = 12.0     # AIS / ADS-B are visited once per CH2 MON frame (~9 s)

spec = importlib.util.spec_from_file_location("airmaritime_bridge", REPO_BRIDGE)
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)

sys.path.insert(0, os.path.join(ROOT, "guru_mon_scan"))
import scan_plan                                    # noqa: E402

PLAN = {}
for name, freq, dwell in scan_plan.FRAMES[1]():
    k = "ais" if name.upper().startswith("AIS") else ("adsb" if "ADS-B" in name.upper() else None)
    if k and k not in PLAN:
        PLAN[k] = {"band": name, "rf": freq, "dwell_ms": dwell}

ab.AIRMAR_BANDS[0].update({"freq_mhz": 162.000, "samp_rate_hz": 250000.0})       # router: 162.000 MHz at 0 Hz
ab.AIRMAR_BANDS[1].update({"freq_mhz": 1090.000, "samp_rate_hz": 200000.0})      # real CH2 rate

DET = {"ais": {"active": False, "t": 0.0}, "adsb": {"active": False, "t": 0.0}}
PORT_REAL_T = {"ais": 0.0, "adsb": 0.0}
HW = {"gain_db": None, "gain_min": None, "gain_max": None, "lo_locked": None, "frame": None}


def _decoder_up():
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", ab.ZMQ_AIS_PORT)) == 0
    finally:
        s.close()


class _ExternalDecoder:
    """Stands in for the repo's Popen: the decoder is run by the watchdog."""
    def poll(self):
        return None if _decoder_up() else 1

    def terminate(self):
        pass


ab.proc_flowgraph = _ExternalDecoder()


async def det_reader():
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
        HW.update({"gain_db": v.get("gain_db"), "gain_min": v.get("gain_min"), "gain_max": v.get("gain_max"),
                   "lo_locked": v.get("lo_locked"), "frame": v.get("frame")})
        name = (v.get("band") or "").upper()
        k = "ais" if name.startswith("AIS") else ("adsb" if "ADS-B" in name else None)
        if k:
            DET[k] = {"active": bool(v.get("active")), "t": time.time(), "peak": v.get("peak_dbfs"),
                      "nb_mhz": v.get("nb_mhz")}


def status_msg():
    now = time.time()
    dw = [k for k in PORT_REAL_T if now - PORT_REAL_T[k] < 0.3]
    return {"type": "status", "flowgraph_running": _decoder_up(),
            "active_band_am": dw[0] if dw else None,
            "dwell": {k: round(v["dwell_ms"] / 1000.0, 3) for k, v in PLAN.items()},
            "freq": {"ais": 162.000, "adsb": PLAN.get("adsb", {}).get("rf", 1090e6) / 1e6},
            "rf": {k: v["rf"] / 1e6 for k, v in PLAN.items()},
            "device": DEVICE, "link": LINK, "samp_rate": {"ais": 250000, "adsb": 200000},
            "gain_db": HW["gain_db"], "lo_lock": None if HW["lo_locked"] is None else ("OK" if HW["lo_locked"] else "UNLOCKED"),
            "frame": HW["frame"], "det": {k: {"active": d["active"], "age_s": round(now - d["t"], 1) if d["t"] else None,
                                              "peak": d.get("peak")} for k, d in DET.items()}}


async def status_pusher():
    while True:
        await ab.broadcast(status_msg())
        await asyncio.sleep(0.25)


async def iq_spectrum_reader(band):
    """Repo reader with one change: 'active' = the detector's fresh verdict for this band (not -60 dBFS)."""
    key, port = band["key"], band["port"]
    chunk_bytes = ab.IQ_FFT_N * 8
    while True:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(1.0)
            continue
        buf, last_send, last_idle_send = b"", 0.0, 0.0
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                buf += data
                while len(buf) >= chunk_bytes:
                    chunk, buf = buf[:chunk_bytes], buf[chunk_bytes:]
                    now = time.time()
                    samples = np.frombuffer(chunk, dtype=np.complex64)
                    if not np.all(np.isfinite(samples)):
                        continue
                    pwr = float(np.dot(samples.real, samples.real) + np.dot(samples.imag, samples.imag)) / max(1, len(samples))
                    rms = pwr ** 0.5
                    rms_db = 20 * np.log10(rms) if rms > 1e-12 else -120.0
                    if rms <= 1e-12:                         # zero-fill: CH2 is not on this band now
                        if now - last_idle_send > 0.5:
                            last_idle_send = now
                            await ab.broadcast({"type": "spectrum", "band": key, "active": False,
                                                "spectrum": None, "rms_db": round(rms_db, 1)})
                        continue
                    PORT_REAL_T[key] = now
                    if now - last_send < 0.1:
                        continue
                    last_send = now
                    win = samples * np.hanning(len(samples))
                    spec_db = 10 * np.log10(np.maximum(np.abs(np.fft.fftshift(np.fft.fft(win, ab.IQ_FFT_N))) ** 2, 1e-18))
                    d = DET[key]
                    await ab.broadcast({"type": "spectrum", "band": key,
                                        "active": bool(d["active"] and now - d["t"] < VERDICT_FRESH_S),
                                        "spectrum": [round(float(x), 1) for x in spec_db], "rms_db": round(rms_db, 1)})
        except (ConnectionResetError, OSError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass
        await asyncio.sleep(1.0)


async def ws_handler(ws):
    """Repo handler + 'status' on connect; schedule / gain requests answered with the real fixed values."""
    ab.CLIENTS.add(ws)
    await ws.send(json.dumps({"type": "init_state", "ais_vessels": list(ab.AIS_VESSELS.values()),
                              "adsb_aircraft": list(ab.ADSB_AIRCRAFT.values()),
                              "flowgraph_running": _decoder_up()}))
    await ws.send(json.dumps(status_msg()))
    try:
        async for raw in ws:
            try:
                cmd = json.loads(raw).get("cmd")
            except Exception:
                continue
            if cmd in ("start_flowgraph", "stop_flowgraph"):
                await ws.send(json.dumps({"type": "note", "text": "the air/maritime decoder is run by the monitoring "
                                          "watchdog (always on); it is %s" % ("RUNNING" if _decoder_up() else "not up yet")}))
                await ws.send(json.dumps(status_msg()))
            elif cmd == "apply_schedule":
                await ws.send(json.dumps({"type": "note", "text": "AIS / ADS-B dwell and frequency come from the CH2 MON "
                                          "scan plan (scan_plan.py): " + ", ".join("%s %.3f MHz %.0f ms" % (v["band"], v["rf"] / 1e6, v["dwell_ms"]) for v in PLAN.values())}))
            elif cmd == "ping":
                await ws.send(json.dumps({"type": "pong", "time": time.time()}))
    except Exception:
        pass
    finally:
        ab.CLIENTS.discard(ws)


async def main():
    import websockets
    ctx = zmq.asyncio.Context()
    tasks = [asyncio.create_task(ab.zmq_ais_listener(ctx)), asyncio.create_task(ab.zmq_adsb_listener(ctx)),
             asyncio.create_task(iq_spectrum_reader(ab.AIRMAR_BANDS[0])),
             asyncio.create_task(iq_spectrum_reader(ab.AIRMAR_BANDS[1])),
             asyncio.create_task(det_reader()), asyncio.create_task(status_pusher())]
    print("Air & Maritime bridge (X310 CH2) on ws://127.0.0.1:%d; plan: %s" % (ab.WS_PORT, PLAN), flush=True)
    async with websockets.serve(ws_handler, "127.0.0.1", ab.WS_PORT):
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
