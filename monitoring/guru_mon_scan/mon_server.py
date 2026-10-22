#!/usr/bin/env python3
"""guru_mon_scan server - headless MON scanning with tags + Pub-Sub (A4 + A5).

Same scanning as mon_scan.py but no GUI: each channel scans its scan_plan frame
on its own LO, and every channel's IQ is tagged and PUBLISHED on its own ZeroMQ
socket for the edge modules to consume:

    CH1 tcp://127.0.0.1:5201    CH2 ...:5202    CH3 ...:5203    CH4 ...:5204

It also measures each band's power and prints active bands (the monitoring job:
which bands are busy). See mon_sub_example.py for how an edge module subscribes.

    source ~/gnuradio-3.8/setup_env.sh
    ./mon_server.py --gain 50
    ./mon_server.py --gain 50 --no-pub       # scan + detect only, no publishing
"""
import argparse
import math
import os
import signal
import threading
import time

from gnuradio import gr, blocks, uhd, filter
from gnuradio.filter import firdes

import scan_plan
from mon_pub import mon_pub

NCH = 4
CH_NAME = ["CH1 Drone/Replay", "CH2 Terrestrial", "CH3 Radar", "CH4 Cellular DL"]
PORTS = ["A/RX1", "A/RX2", "B/RX1", "B/RX2"]
ANT = ["RX1", "RX2", "RX1", "RX2"]
SUBDEV = "A:0 A:1 B:0 B:1"
BASE_PORT = 5201

# CH2 terrestrial mode, set by the UI (written by mon_ws_bridge):
#   "scan" (Mode 1) = scan all terrestrial bands per the plan (default)
#   "auto" (Mode 2) = search all protocols 2 cycles, lock on the STRONGEST active
#                     one, hold/decode it until it is silent for 2 s, then re-search
CH2_MODE_FILE = os.path.expanduser("~/radar2/edge_ch2/ch2_mode.txt")
CH2_LOCK_FILE = os.path.expanduser("~/radar2/edge_ch2/ch2_lock.txt")
CH2 = 1                      # 0-indexed terrestrial channel
ACTIVE_MARGIN_DB = 8.0       # a band reads "active" at floor+8 dB (detection/UI)
LOCK_MARGIN_DB = 10.0        # Mode 2 only LOCKS on a clearly real signal (floor+10 dB)
                             # so a single noise blip never captures the lock
HOLD_SILENT_DWELLS = 2       # release the lock after this many silent dwells in a row
                             # (each dwell = the held band's own planned dwell)
SEARCH_CYCLES = 2            # search every terrestrial band this many cycles before locking
# Mode 2 applies to the TERRESTRIAL PROTOCOL bands only (the decodable land-mobile
# voice protocols) -- not AIS / ADS-B / D-STAR. Matched by substring on the band
# name as scan_plan tags it.
TERR_PROTO_KEYS = ("DMR", "NXDN", "P25", "TETRA")
def is_terr_proto(name):
    return any(k in name for k in TERR_PROTO_KEYS)


class mon_server(gr.top_block):
    def __init__(self, addr, samp_rate, gain, publish=True, look_bw=0.0, pins=None,
                 ch2_gain=None):
        gr.top_block.__init__(self, "mon_server")
        self.samp_rate = samp_rate
        self.publish = publish
        self.look_bw = look_bw
        # CH2 (terrestrial) sees strong, close hand-radios: too much gain overloads
        # the ADC, which makes a keyed signal clip AND spill power into every other
        # band (false cross-detections) and wrecks the decode. So CH2 runs at a
        # lower gain than the channels that must hear weak drone/radar/cellular.
        self.ch2_gain = ch2_gain

        self.src = uhd.usrp_source(
            ",".join([addr, "recv_buff_size=33554432"]),
            uhd.stream_args(cpu_format="fc32", args="", channels=list(range(NCH))),
        )
        self.src.set_clock_source("internal", 0)
        self.src.set_subdev_spec(SUBDEV, 0)
        self.src.set_samp_rate(samp_rate)
        for ch in range(NCH):
            self.src.set_antenna(ANT[ch], ch)
            self.src.set_dc_offset(True, ch)
        for ch in range(NCH):
            try:
                self.src.set_lo_export_enabled(False, uhd.ALL_LOS, ch)
            except Exception as e:
                print("[setup] clear export ch%d: %s" % (ch, e))
        for ch in range(NCH):
            self.src.set_lo_source("internal", uhd.ALL_LOS, ch)
        for ch in range(NCH):
            rng = self.src.get_gain_range(ch)
            g = self.ch2_gain if (ch == CH2 and self.ch2_gain is not None) else gain
            g = max(rng.start(), min(rng.stop(), g))
            self.src.set_gain(g, ch)
            print("[setup] CH%d gain = %.0f dB" % (ch + 1, g), flush=True)

        self.frames = scan_plan.build_frames(look_bw)
        for ch, name in (pins or {}).items():
            pf = scan_plan.pin_frame(ch, name)
            if pf:
                self.frames[ch] = pf
                print("[pin] CH%d held on '%s' (%.4f MHz) - no scanning"
                      % (ch + 1, pf[0][0], pf[0][1] / 1e6))
            else:
                print("[pin] CH%d: band '%s' not found - ignoring" % (ch + 1, name))
        for ch in range(NCH):
            self.src.set_center_freq(uhd.tune_request(self.frames[ch][0][1]), ch)

        # per channel: src -> mon_pub (tag + publish) -> [CH2: 200 kHz LPF] -> mag2 -> avg -> probe
        # CH2 terrestrial probe is band-limited to 200 kHz around the tuned centre:
        # the protocols sit close (P25 450 / NXDN 451 are 1 MHz apart), so a full
        # 2 MHz power reading would cross-trigger neighbours. 200 kHz = one channel.
        self._ch2_lpf_taps = firdes.low_pass(1.0, samp_rate, 100e3, 40e3)
        self.pub = []
        self.probes = []
        for ch in range(NCH):
            p = mon_pub(ch, "tcp://127.0.0.1:%d" % (BASE_PORT + ch), publish=publish,
                        samp_rate=samp_rate)
            mag2 = blocks.complex_to_mag_squared(1)
            avg = blocks.moving_average_ff(2000, 1.0 / 2000, 8000)
            pr = blocks.probe_signal_f()
            if ch == CH2:
                lpf = filter.fir_filter_ccf(1, self._ch2_lpf_taps)
                self.connect((self.src, ch), p, lpf, mag2, avg, pr)
            else:
                self.connect((self.src, ch), p, mag2, avg, pr)
            self.pub.append(p)
            self.probes.append(pr)

        self.floor = {}
        self._dbg_timing = os.environ.get("MON_DBG_TIMING") == "1"
        self._last_tick = {ch: time.time() for ch in range(NCH)}  # per-thread liveness
        self._run = True
        # activity log (a record of which bands were active, when)
        os.makedirs("results", exist_ok=True)
        self.logfn = "results/activity_%s.csv" % time.strftime("%Y%m%d_%H%M%S")
        self.log = open(self.logfn, "w")
        self.log.write("iso_time,ch,port,band,freq_mhz,power_dbfs,floor_dbfs\n")
        self.log.flush()
        self.loglock = threading.Lock()

    def power_db(self, ch):
        return 10.0 * math.log10(self.probes[ch].level() + 1e-12)

    def read_ch2_mode(self):
        """CH2 terrestrial mode set by the UI: 'scan' (Mode 1) or 'auto' (Mode 2)."""
        try:
            with open(CH2_MODE_FILE) as f:
                return "auto" if f.read().strip() == "auto" else "scan"
        except Exception:
            return "scan"

    def _set_ch2_status(self, text):
        """Publish CH2's live state for the UI (the mon_ws bridge polls this file):
        'scan' (Mode 1), 'search' (Mode 2 looking), or 'lock|<band>|<MHz>' (Mode 2
        holding a locked protocol). De-duped so we only write on a real change."""
        if getattr(self, "_ch2_status_cache", None) == text:
            return
        self._ch2_status_cache = text
        try:
            with open(CH2_LOCK_FILE, "w") as f:
                f.write(text)
        except Exception:
            pass

    def _measure(self, ch, name, freq, idx, frame_no, dwell_ms):
        """Tune, tag, settle+dwell, return (db, active). Logs active bands."""
        self._last_tick[ch] = time.time()
        _t0 = time.time()
        self.src.set_center_freq(uhd.tune_request(float(freq)), ch)
        _t_tune = time.time()
        self.pub[ch].set_look(name, freq, idx, frame_no)
        time.sleep(scan_plan.SWITCH_MS / 1000.0)
        time.sleep(dwell_ms / 1000.0)
        db = self.power_db(ch)
        if ch == CH2 and getattr(self, "_dbg_timing", False):
            print("[TIMING] CH2 %-14s want=%.0fms  retune=%.0fms  total=%.0fms"
                  % (name, dwell_ms, (_t_tune - _t0) * 1e3, (time.time() - _t0) * 1e3),
                  flush=True)
        active = False
        if db > -115.0:
            fl = self.floor.get(freq)
            if fl is None or db < fl:
                self.floor[freq] = db
                fl = db
            if db > fl + ACTIVE_MARGIN_DB:
                active = True
                print("[ACTIVE] %s %-18s %.4f MHz  %6.1f dBFS  (floor %6.1f)"
                      % (CH_NAME[ch][:3], name, freq / 1e6, db, fl), flush=True)
                with self.loglock:
                    self.log.write("%s,%d,%s,%s,%.4f,%.1f,%.1f\n"
                                   % (time.strftime("%Y-%m-%dT%H:%M:%S"), ch,
                                      PORTS[ch], name, freq / 1e6, db, fl))
                    self.log.flush()
        return db, active

    def scan_channel(self, ch):
        """Thread: step this channel through its frame forever.
        CH2 also supports Mode 2 (auto-detect & hold) via the control file.
        Mode 2 searches the TERRESTRIAL PROTOCOL bands only (DMR/NXDN/P25/TETRA);
        AIS/ADS-B/D-STAR are scanned in Mode 1 but not auto-held."""
        frame = self.frames[ch]
        # Mode-2 search set: only the terrestrial protocol bands of this channel
        terr_frame = [b for b in frame if is_terr_proto(b[0])] if ch == CH2 else []
        idx = 0           # Mode 1 index (full frame)
        sidx = 0          # Mode 2 search index (terr_frame)
        frame_no = 0
        search_cycles = 0
        best = {}            # name -> (db, freq, dwell)  best power seen this search pass
        act_cyc = {}         # name -> how many of this pass's cycles the band was active
        held = None          # (name, freq, dwell) currently held/decoded
        silent_dwells = 0    # consecutive silent dwells on the held band
        while self._run:
            mode = self.read_ch2_mode() if ch == CH2 else "scan"

            # ================= CH2 Mode 2 (terrestrial protocol bands only) =================
            if ch == CH2 and mode == "auto" and terr_frame:
                # ---- HOLD the locked protocol (dwell = the band's own planned dwell) ----
                if held is not None:
                    name, freq, dwell = held
                    db, active = self._measure(ch, name, freq, 0, frame_no, dwell)
                    if active:
                        silent_dwells = 0
                    else:
                        silent_dwells += 1
                        if silent_dwells >= HOLD_SILENT_DWELLS:
                            print("[CH2 auto] '%s' OFF for %d dwells -> release, re-search"
                                  % (name, HOLD_SILENT_DWELLS), flush=True)
                            held = None; silent_dwells = 0
                            search_cycles = 0; best = {}; act_cyc = {}; sidx = 0
                            self._set_ch2_status("search")
                    continue
                # ---- SEARCH every terrestrial protocol band (its own dwell each) ----
                self._set_ch2_status("search")
                name, freq, dwell = terr_frame[sidx]
                db, active = self._measure(ch, name, freq, sidx, frame_no, dwell)
                if active:
                    act_cyc[name] = act_cyc.get(name, 0) + 1
                    if name not in best or db > best[name][0]:
                        best[name] = (db, freq, dwell)
                sidx += 1
                if sidx >= len(terr_frame):
                    sidx = 0; frame_no += 1; search_cycles += 1
                    if search_cycles >= SEARCH_CYCLES:
                        # LOCK the STRONGEST band that was active in EVERY search cycle
                        # (sustained) AND clearly above its own floor. A lone noise
                        # blip on a quiet band (active just one cycle, barely over
                        # floor) never qualifies -> no more wrong lock on P25/450.
                        cand = {}
                        for n, (d, fq, dw) in best.items():
                            if act_cyc.get(n, 0) >= SEARCH_CYCLES and \
                               d >= self.floor.get(fq, d) + LOCK_MARGIN_DB:
                                cand[n] = (d, fq, dw)
                        if cand:
                            name, (db, freq, dwell) = max(cand.items(), key=lambda kv: kv[1][0])
                            held = (name, freq, dwell); silent_dwells = 0
                            print("[CH2 auto] LOCK '%s' %.1f dBFS (sustained, strongest) -> hold/decode"
                                  % (name, db), flush=True)
                            self._set_ch2_status("lock|%s|%.4f" % (name, freq / 1e6))
                        search_cycles = 0; best = {}; act_cyc = {}
                continue

            # ================= Mode 1 scan (full frame) =================
            # reset Mode-2 state so a mode switch back to auto starts clean
            held = None; silent_dwells = 0; search_cycles = 0; best = {}; act_cyc = {}; sidx = 0
            if ch == CH2:
                self._set_ch2_status("scan")
            name, freq, dwell = frame[idx]
            self._measure(ch, name, freq, idx, frame_no, dwell)
            idx += 1
            if idx >= len(frame):
                idx = 0; frame_no += 1

    def start_scan(self):
        self.threads = []
        for ch in range(NCH):
            t = threading.Thread(target=self.scan_channel, args=(ch,), daemon=True)
            t.start()
            self.threads.append(t)

    def stop_scan(self):
        self._run = False
        for p in self.pub:
            p.close()
        try:
            self.log.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--samp-rate", type=float, default=2e6)
    ap.add_argument("--gain", type=float, default=50.0)
    ap.add_argument("--ch2-gain", type=float, default=None,
                    help="separate gain for CH2 terrestrial (lower, so strong close "
                         "hand-radios don't overload the ADC). Default: same as --gain.")
    ap.add_argument("--no-pub", action="store_true", help="scan + detect only, do not publish")
    ap.add_argument("--look-bw", type=float, default=0.0,
                    help="look bandwidth Hz for splitting wide bands (0 = one look per band; 80e6 for 10 GbE)")
    ap.add_argument("--pin", action="append", default=[],
                    help="hold a channel on one band, e.g. --pin '2=DMR 446.100' (repeatable)")
    a = ap.parse_args()
    pins = {}
    for p in a.pin:
        ch_s, name = p.split("=", 1)
        pins[int(ch_s) - 1] = name.strip()

    tb = mon_server(a.addr, a.samp_rate, a.gain, publish=not a.no_pub, look_bw=a.look_bw,
                    pins=pins, ch2_gain=a.ch2_gain)
    tb.start()
    tb.start_scan()
    if tb.publish:
        print("[server] publishing per-channel IQ+tags on tcp://127.0.0.1:%d..%d"
              % (BASE_PORT, BASE_PORT + NCH - 1))
    print("[server] activity log: %s" % tb.logfn)
    print("[server] scanning. Ctrl-C to stop.")

    stop = threading.Event()

    def sig_handler(sig=None, frame=None):
        stop.set()
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    try:
        _hb = 0.0
        while not stop.is_set():
            time.sleep(0.2)
            now = time.time()
            if now - _hb >= 5.0:
                _hb = now
                # heartbeat: oldest scan-thread age. If a thread wedges (e.g. a
                # UHD retune hangs) its age climbs; the watchdog reads this line's
                # freshness AND the reported age to decide to restart us.
                ages = {ch: now - t for ch, t in tb._last_tick.items()}
                oldest = max(ages, key=ages.get)
                print("[hb] alive  oldest=CH%d %.1fs  CH2=%s"
                      % (oldest + 1, ages[oldest], tb._ch2_status_cache), flush=True)
    finally:
        tb.stop_scan()
        tb.stop()
        tb.wait()
        print("\n[server] stopped.")


if __name__ == "__main__":
    main()
