#!/usr/bin/env python3
"""A1 - measure the REAL MON retune time on the USRP-2945.

In MON scanning each channel tunes its OWN internal LO to the next band in its
scan list. Our frame budgets use SWITCH_MS = 10 ms as an assumption; this script
measures what it actually is on this X310, so the budgets become real.

Method (pyuhd, same radio setup as mon_tools / guru MON):
  * all 4 channels: LO export off, own internal LO, DC offset on;
  * a continuous RX stream runs the whole time (as in real MON);
  * for the chosen channel, step through its scan_plan band list for N cycles.
    Per step: issue the MON tune (gain + two set_freq passes, as mon_setup),
    then poll that channel's lo_locked until it drops and returns (3 good reads).
    Record host wall time of the tune calls and the lock-return time after the
    tune was issued.

Nothing is inferred: if the lock bit never drops for a step, that step is
reported "no drop seen" and gets no lock time.

    source ~/gnuradio-3.8/setup_env.sh
    python3 mon_scan_retune.py --ch 1 --cycles 20
    python3 mon_scan_retune.py --ch all --cycles 10     # every channel in turn

Channels: 0 CH1(A/RX1) 1 CH2(A/RX2) 2 CH3(B/RX1) 3 CH4(B/RX2).
"""
import argparse
import json
import os
import threading
import time

import numpy as np
import uhd

import scan_plan

NCH = 4
SAMP_RATE = 2e6
SUBDEV = "A:0 A:1 B:0 B:1"
ANT = ["RX1", "RX2", "RX1", "RX2"]
# a reasonable fixed gain per channel for the measurement (lock timing does not
# depend on gain; this just keeps the front end sane)
GAIN = 40.0


def setup(addr):
    u = uhd.usrp.MultiUSRP("%s,recv_buff_size=33554432" % addr)
    u.set_clock_source("internal", 0)
    u.set_rx_subdev_spec(uhd.usrp.SubdevSpec(SUBDEV), 0)
    u.set_rx_rate(SAMP_RATE)
    for ch in range(NCH):
        u.set_rx_antenna(ANT[ch], ch)
        u.set_rx_dc_offset(True, ch)
    # MON: no LO sharing - export off everywhere, every channel its own internal LO
    for ch in range(NCH):
        try:
            u.set_rx_lo_export_enabled(False, "all", ch)
        except Exception as e:
            print("[setup] clear export ch%d: %s" % (ch, e))
    for ch in range(NCH):
        u.set_rx_lo_source("internal", "all", ch)
    for ch in range(NCH):
        rng = u.get_rx_gain_range(ch)
        u.set_rx_gain(max(rng.start(), min(rng.stop(), GAIN)), ch)
    return u


def streamer(u, stop):
    """Keep a continuous 4-channel stream running (samples discarded)."""
    sa = uhd.usrp.StreamArgs("fc32", "sc16")
    sa.channels = list(range(NCH))
    st = u.get_rx_stream(sa)
    args = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
    args.stream_now = False
    args.time_spec = u.get_time_now() + uhd.types.TimeSpec(0.2)
    st.issue_stream_cmd(args)
    buf = np.zeros((NCH, 4096), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    while not stop.is_set():
        try:
            st.recv(buf, md, 0.2)
        except Exception:
            pass
    st.issue_stream_cmd(uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont))


def mon_tune(u, ch, freq):
    """One MON retune of a single channel (gain already set): two set_freq
    passes, as mon_setup does. Untimed - MON channels are independent, so no
    phase-coherent timed tune is needed here."""
    for _ in range(2):
        u.set_rx_freq(uhd.types.TuneRequest(float(freq)), ch)


def watch_lock(u, ch, t_issue, limit=0.20):
    """Poll lo_locked on `ch` until it has dropped and returned (3 good reads).
    Returns (lock_dt, dropped) where lock_dt is seconds from t_issue to relock,
    or None if no drop was seen."""
    seen_false = False
    good = 0
    lock_at = None
    while time.perf_counter() < t_issue + limit:
        try:
            v = u.get_rx_sensor("lo_locked", ch).to_bool()
        except Exception:
            v = True
        now = time.perf_counter()
        if not v:
            seen_false = True
            good = 0
        elif seen_false:
            if good == 0:
                lock_at = now
            good += 1
            if good >= 3:
                return (lock_at - t_issue, True)
    return (None, seen_false)


def measure_channel(u, ch, cycles):
    bands = scan_plan.BAND_SETS[ch]
    print("\n[A1] CH%d %s - %d bands x %d cycles" % (ch + 1, scan_plan.PORTS[ch], len(bands), cycles))
    rows = []
    # park on the first band so the first measured step is a real change
    mon_tune(u, ch, bands[0][1])
    time.sleep(0.3)
    for cyc in range(cycles):
        for name, freq, _dwell in bands:
            t0 = time.perf_counter()
            mon_tune(u, ch, freq)
            t_calls = time.perf_counter() - t0
            lock_dt, dropped = watch_lock(u, ch, t0)
            rows.append({"ch": ch, "band": name, "freq": freq,
                         "tune_calls_ms": t_calls * 1e3,
                         "lock_ms": None if lock_dt is None else lock_dt * 1e3,
                         "dropped": bool(dropped)})
    # summary per band
    print("  %-22s %8s %10s %8s" % ("band", "calls ms", "relock ms", "ndrop"))
    for name, freq, _d in bands:
        r = [x for x in rows if x["band"] == name]
        locks = [x["lock_ms"] for x in r if x["lock_ms"] is not None]
        nd = sum(1 for x in r if x["dropped"])
        calls = np.mean([x["tune_calls_ms"] for x in r])
        if locks:
            print("  %-22s %8.2f  %5.1f/%5.1f %6d/%d" %
                  (name, calls, float(np.mean(locks)), float(np.max(locks)), nd, len(r)))
        else:
            print("  %-22s %8.2f  no drop seen   %6d/%d" % (name, calls, nd, len(r)))
    all_locks = [x["lock_ms"] for x in rows if x["lock_ms"] is not None]
    if all_locks:
        print("  CH%d retune+lock: mean %.1f ms, worst %.1f ms (n=%d)"
              % (ch + 1, float(np.mean(all_locks)), float(np.max(all_locks)), len(all_locks)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--ch", default="1", help="0..3 or 'all'")
    ap.add_argument("--cycles", type=int, default=20)
    a = ap.parse_args()

    u = setup(a.addr)
    stop = threading.Event()
    th = threading.Thread(target=streamer, args=(u, stop), daemon=True)
    th.start()
    time.sleep(0.5)

    chans = range(NCH) if a.ch == "all" else [int(a.ch)]
    out = {"samp_rate": SAMP_RATE, "cycles": a.cycles, "rows": []}
    try:
        for ch in chans:
            out["rows"] += measure_channel(u, ch, a.cycles)
    finally:
        stop.set()
        th.join(timeout=2.0)

    os.makedirs("results", exist_ok=True)
    fn = "results/mon_scan_retune_%s.json" % time.strftime("%Y%m%d_%H%M%S")
    with open(fn, "w") as f:
        json.dump(out, f, indent=1)
    print("\nsaved", fn)
    print("=> use the worst relock time as the real SWITCH_MS in scan_plan.py")


if __name__ == "__main__":
    main()
