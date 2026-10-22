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

import json
import zmq
from gnuradio import gr, blocks, uhd, filter
from gnuradio.filter import firdes

import scan_plan
from mon_pub import mon_pub
from look_power import look_power

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
# UI band lock: the UI (via mon_ws_bridge) writes a band name into pin_chN.txt -> that channel holds
# that band only (no scanning); an empty file = run the MON plan. Read every look (cached by mtime).
PIN_FILE = os.path.expanduser("~/radar2/edge_ch2/pin_ch%d.txt")
CH2 = 1                      # 0-indexed terrestrial channel
DET_PORT = 5210                # detections (one JSON per dwell) -> UI bridge / edge modules
SETTLE_S = 0.014               # detector ignores the first 14 ms of each look (10 ms switch + retune transient, measured,
                               # + 2 ms because look tags sit on 2048-sample chunk boundaries)
WIN_S = 0.0005                 # detector power window 0.5 ms; ACTIVE uses the peak window of the look
ACTIVE_MARGIN_DB = 2.5       # a band reads "active" at its own floor + 2.5 dB. Measured 2026-10-22: with DC removed, noise-only
                             # 0.5 ms peaks stay within +1.4 dB of the band floor, so 2.5 dB gives >1 dB safety (old value 8 dB hid real bursts)
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
                 ch2_gain=None, dc_alpha=0.001):
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
        # The TwinRX leaves a large constant (DC) offset on I/Q (-6 dBFS on the RX1 ports, a spike at the
        # centre frequency). It is not a signal: it hides weak signals and blocks detection. It is removed
        # here, right after the radio, so the detector AND the published IQ are DC-free:
        #   y = x - single_pole_lowpass(x)   (a high-pass, corner ~ alpha*fs/2pi = 160 Hz at alpha 0.001, 1 MS/s)
        self.dc_alpha = float(dc_alpha)
        self._avg_len = max(200, int(samp_rate * 0.001))       # 1 ms power window
        self.pub = []
        self.probes = []
        for ch in range(NCH):
            p = mon_pub(ch, "tcp://127.0.0.1:%d" % (BASE_PORT + ch), publish=publish,
                        samp_rate=samp_rate)
            pr = look_power(samp_rate, settle_s=SETTLE_S, win_s=WIN_S)   # sample-accurate per-look power
            if self.dc_alpha > 0:
                dcsub = blocks.sub_cc(1)
                dclp = filter.single_pole_iir_filter_cc(self.dc_alpha)
                self.connect((self.src, ch), (dcsub, 0))
                self.connect((self.src, ch), dclp, (dcsub, 1))
                head = (dcsub, 0)
            else:
                head = (self.src, ch)
            if ch == CH2:
                lpf = filter.fir_filter_ccf(1, self._ch2_lpf_taps)
                self.connect(head, p, lpf, pr)
            else:
                self.connect(head, p, pr)
            self.pub.append(p)
            self.probes.append(pr)
        print("[setup] DC removal %s (alpha %g); detector = sample-accurate peak of %.1f ms power windows, first %.0f ms of each look skipped"
              % ("ON" if self.dc_alpha > 0 else "OFF", self.dc_alpha, WIN_S * 1e3, SETTLE_S * 1e3), flush=True)

        self._pin_cache = {}
        self.floor = {}              # (channel, centre Hz) -> lowest dwell peak seen = noise floor of that band
        self._det = None
        if publish:
            self._det = zmq.Context.instance().socket(zmq.PUB)
            self._det.setsockopt(zmq.LINGER, 0)
            self._det.bind("tcp://127.0.0.1:%d" % DET_PORT)
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

    def read_pin(self, ch):
        """Band name the UI locked this channel to, or '' (= run the MON plan)."""
        fn = PIN_FILE % (ch + 1)
        try:
            mt = os.path.getmtime(fn)
        except OSError:
            return ""
        c = self._pin_cache.get(ch)
        if c and c[0] == mt:
            return c[1]
        try:
            v = open(fn).read().strip()
        except Exception:
            v = ""
        self._pin_cache[ch] = (mt, v)
        return v

    def _measure(self, ch, name, freq, idx, frame_no, dwell_ms, retune=True):
        """Tune, tag, settle+dwell, return (db, active). Logs active bands.
        retune=False (band lock, same band again): no retune and no switch wait."""
        self._last_tick[ch] = time.time()
        _t0 = time.time()
        if retune:
            self.src.set_center_freq(uhd.tune_request(float(freq)), ch)
        _t_tune = time.time()
        self.pub[ch].set_look(name, freq, idx, frame_no)
        if retune:
            time.sleep(scan_plan.SWITCH_MS / 1000.0)
        lk = self.pub[ch].current_host_time()
        time.sleep(dwell_ms / 1000.0)
        # sample-accurate verdict of THIS look (look_power keys every look by its set_look host_time)
        db = -120.0
        for _ in range(40):                      # the last samples may still be in flight: wait up to 40 ms
            key, pk, _mean, nset = self.probes[ch].stats()
            if key == lk and pk is not None:
                db = pk
                break
            time.sleep(0.001)
        if ch == CH2 and getattr(self, "_dbg_timing", False):
            print("[TIMING] CH2 %-14s want=%.0fms  retune=%.0fms  total=%.0fms"
                  % (name, dwell_ms, (_t_tune - _t0) * 1e3, (time.time() - _t0) * 1e3),
                  flush=True)
        active = False
        if db > -115.0:
            fl = self.floor.get((ch, freq))
            if fl is None or db < fl:
                self.floor[(ch, freq)] = db
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
            if self._det is not None:
                try:
                    self._det.send_string(json.dumps({
                        "ch": ch + 1, "band": name, "freq_mhz": freq / 1e6,
                        "peak_dbfs": round(db, 1), "floor_dbfs": round(fl, 1),
                        "active": bool(active), "frame": int(frame_no), "look": int(idx),
                        "dwell_ms": float(dwell_ms), "t": time.time()}), flags=zmq.NOBLOCK)
                except Exception:
                    pass
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
        held_pin = None      # band the UI locked this channel to (None = MON plan)
        while self._run:
            # ---- UI band lock: hold ONE band, no scanning, until the UI returns to the MON plan ----
            pin = self.read_pin(ch)
            b = scan_plan.find_band(ch, pin) if pin else None
            if b is not None:
                name, freq, dwell = b
                first = (held_pin != name)
                if first:
                    print("[pin] CH%d LOCKED on '%s' (%.4f MHz) by the UI" % (ch + 1, name, freq / 1e6), flush=True)
                    held_pin = name
                self._measure(ch, name, freq, 0, frame_no, dwell, retune=first)
                continue
            if held_pin is not None:
                print("[pin] CH%d back to the MON plan" % (ch + 1), flush=True)
                held_pin = None
                idx = 0
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
                               d >= self.floor.get((ch, fq), d) + LOCK_MARGIN_DB:
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
    ap.add_argument("--dc-alpha", type=float, default=0.001,
                    help="DC removal: single-pole corner alpha (0 = off). Default 0.001 = ~160 Hz high-pass at 1 MS/s")
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
                    pins=pins, ch2_gain=a.ch2_gain, dc_alpha=a.dc_alpha)
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
