#!/usr/bin/env python3
"""ch2_scheduler - RTOS-side CH2 scheduler: burst-hop the terrestrial bands and
PUBlish ONE CH2 stream (IQ + header) for the edge router to split.

This is Module 1's role in the new per-channel architecture: own the radio, hop
across the 4 terrestrial bands on a dwell schedule, and publish a single CH2
stream. Each retune calls ch2_pub.set_band(...) so every block is stamped with
its band's header (and dwell_start on the first block of each dwell).

Source modes:
  --addr <uhd>       real USRP (e.g. addr=192.168.10.2 for X310, type=b200 for B210)
  --replay <file>    replay a complex64 capture (offline test, no radio) -- cycles
                     the band LABELS on the dwell timer so the header/dwell logic
                     is exercised end-to-end into the router.

    # offline: scheduler(replay) -> router -> (decoder)
    python3 ch2_scheduler.py --replay dmr.cf32 --samp-rate 200000 --out tcp://127.0.0.1:5202
    # live:
    python3 ch2_scheduler.py --addr addr=192.168.10.2 --samp-rate 200000 --out tcp://127.0.0.1:5202
"""
import argparse
import threading
import time

from gnuradio import gr, blocks

from ch2_pub import ch2_pub

# the repo's working 4-protocol terrestrial bands (centre freqs retuned per §5)
BANDS = [
    ("DMR446",  446.118528e6),
    ("NXDN96",  451.09375e6),
    ("P25-Ph1", 450.09375e6),
    ("TETRA",   420.00000e6),
]


class ch2_scheduler(gr.top_block):
    def __init__(self, samp_rate, endpoint, usrp=None):
        gr.top_block.__init__(self, "ch2_scheduler")
        self.samp_rate = samp_rate
        self.usrp = usrp
        self.pub = ch2_pub(endpoint, samp_rate)

    def run_schedule(self, dwell_sec, stop, only=None):
        """Hop bands on a dwell timer; retune the USRP (if any) and stamp the
        publisher with each band so the stream carries the right header.
        only=<band> pins to a single band (no hopping) for a clean decode test."""
        bands = [(b, f) for b, f in BANDS if (only is None or b == only)]
        if not bands:
            bands = BANDS
        while not stop.is_set():
            for band, freq in bands:
                if stop.is_set():
                    break
                if self.usrp is not None:
                    from gnuradio import uhd
                    self.usrp.set_center_freq(uhd.tune_request(freq), 0)
                self.pub.set_band(band, freq, new_dwell=True)
                stop.wait(dwell_sec)


def make_usrp(addr, samp_rate, gain):
    from gnuradio import uhd
    src = uhd.usrp_source(addr, uhd.stream_args(cpu_format="fc32", channels=[0]))
    src.set_samp_rate(samp_rate)
    src.set_center_freq(uhd.tune_request(BANDS[0][1]), 0)
    try:
        src.set_dc_offset(True, 0)
    except Exception:
        pass
    g = src.get_gain_range(0)
    src.set_gain(max(g.start(), min(g.stop(), gain)), 0)
    return src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tcp://127.0.0.1:5202", help="CH2 PUB endpoint")
    ap.add_argument("--samp-rate", type=float, default=200000.0)
    ap.add_argument("--dwell", type=float, default=1.0, help="dwell seconds per band")
    ap.add_argument("--addr", default=None, help="UHD device (live mode)")
    ap.add_argument("--gain", type=float, default=40.0)
    ap.add_argument("--replay", default=None, help="complex64 capture to replay (offline)")
    ap.add_argument("--only", default=None,
                    help="pin to one band (e.g. DMR446) instead of hopping")
    a = ap.parse_args()

    if a.replay:
        tb = ch2_scheduler(a.samp_rate, a.out, usrp=None)
        fsrc = blocks.file_source(gr.sizeof_gr_complex, a.replay, True)  # repeat
        thr = blocks.throttle(gr.sizeof_gr_complex, a.samp_rate)
        tb.connect(fsrc, thr, tb.pub)
        print("[sched] REPLAY %s @ %.0f kS/s -> %s" % (a.replay, a.samp_rate/1e3, a.out), flush=True)
    elif a.addr:
        usrp = make_usrp(a.addr, a.samp_rate, a.gain)
        tb = ch2_scheduler(a.samp_rate, a.out, usrp=usrp)
        tb.connect(usrp, tb.pub)
        print("[sched] LIVE %s @ %.0f kS/s -> %s" % (a.addr, a.samp_rate/1e3, a.out), flush=True)
    else:
        ap.error("need --replay <file> or --addr <uhd>")

    stop = threading.Event()
    th = threading.Thread(target=tb.run_schedule, args=(a.dwell, stop),
                          kwargs={"only": a.only}, daemon=True)
    tb.start(); th.start()
    print("[sched] hopping %s, %.1fs dwell each. Ctrl-C to stop."
          % ("/".join(b for b, _ in BANDS), a.dwell), flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); tb.stop(); tb.wait()
        print("\n[sched] stopped")


if __name__ == "__main__":
    main()
