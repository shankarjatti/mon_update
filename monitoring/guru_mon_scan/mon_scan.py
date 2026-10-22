#!/usr/bin/env python3
"""guru_mon_scan - MON scanning, 4 channels, with per-channel graphs.

Each TwinRX channel is on its OWN internal LO (MON) and scans its band list from
scan_plan.py: it retunes to the next band, holds for that band's dwell, then moves
on - continuously. Per channel you see a spectrum (frequency) graph and a time
graph, a status line (current band, LO lock), in its own tab (CH1..CH4).

No transmitter is used: the graphs show whatever the 4 antennas receive. Key a
DMR radio near 446.1 MHz and it appears on the CH2 tab when the scan is on the
DMR look.

    source ~/gnuradio-3.8/setup_env.sh
    python3 mon_scan.py                 # all 4 channels scanning
    python3 mon_scan.py --gain 55       # set RX gain (dB) for all channels

Switch 10 ms per look (measured safe, mon_scan_retune.py). Close the window to stop.
"""
import argparse
import signal
import sys

from PyQt5 import Qt
from gnuradio import gr, blocks, uhd, qtgui
from gnuradio.filter import firdes
import sip

import scan_plan

NCH = 4
CH_NAME = ["CH1 Drone/Replay", "CH2 Terrestrial", "CH3 Radar", "CH4 Cellular DL"]
PORTS = ["A/RX1", "A/RX2", "B/RX1", "B/RX2"]
ANT = ["RX1", "RX2", "RX1", "RX2"]
SUBDEV = "A:0 A:1 B:0 B:1"


class mon_scan(gr.top_block, Qt.QWidget):
    def __init__(self, addr, samp_rate, gain, verbose=False, publish=False,
                 look_bw=0.0, channels=None, pins=None):
        gr.top_block.__init__(self, "guru_mon_scan")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("guru_mon_scan - MON scanning")
        self.top_layout = Qt.QVBoxLayout(self)
        self.samp_rate = samp_rate
        self.verbose = verbose
        self.publish = publish
        self.look_bw = look_bw
        self.selected = sorted(channels) if channels else list(range(NCH))

        # ---- USRP source, 4 channels, MON (own LO per channel) ----
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
        # MON: no LO sharing - export off, every channel its own internal LO
        for ch in range(NCH):
            try:
                self.src.set_lo_export_enabled(False, uhd.ALL_LOS, ch)
            except Exception as e:
                print("[setup] clear export ch%d: %s" % (ch, e))
        for ch in range(NCH):
            self.src.set_lo_source("internal", uhd.ALL_LOS, ch)
        for ch in range(NCH):
            rng = self.src.get_gain_range(ch)
            self.src.set_gain(max(rng.start(), min(rng.stop(), gain)), ch)

        # per-channel scan frame + state
        self.frames = scan_plan.build_frames(self.look_bw)
        # --pin: hold a channel on one band continuously (for sustained decode)
        for ch, name in (pins or {}).items():
            pf = scan_plan.pin_frame(ch, name)
            if pf:
                self.frames[ch] = pf
                print("[pin] CH%d held on '%s' (%.4f MHz) - no scanning"
                      % (ch + 1, pf[0][0], pf[0][1] / 1e6))
            else:
                print("[pin] CH%d: band '%s' not found - ignoring" % (ch + 1, name))
        self.idx = [0, 0, 0, 0]
        # park each channel on the first band of its frame
        for ch in range(NCH):
            self.src.set_center_freq(uhd.tune_request(self.frames[ch][0][1]), ch)

        # optional Pub-Sub tap per channel (tags + ZeroMQ publish). If on, every
        # downstream block taps the pub block so published IQ == displayed IQ.
        self.pub = [None] * NCH
        self.frame_no = [0] * NCH
        self.tap = [(self.src, ch) for ch in range(NCH)]
        if self.publish:
            from mon_pub import mon_pub
            for ch in self.selected:
                p = mon_pub(ch, "tcp://127.0.0.1:%d" % (5201 + ch), publish=True)
                self.connect((self.src, ch), p)
                self.pub[ch] = p
                self.tap[ch] = (p, 0)
            print("[gui] publishing CH %s on tcp://127.0.0.1:520x"
                  % ",".join(str(c + 1) for c in self.selected))
        # the USRP always streams all 4 channels; consume the ones we don't display
        for ch in range(NCH):
            if ch not in self.selected:
                self.connect((self.src, ch), blocks.null_sink(gr.sizeof_gr_complex))

        # ---- GUI: all 4 channels shown SEPARATELY at once, each in its own
        #      panel with its own FFT (left) + time graph (right) ----
        scroll = Qt.QScrollArea()
        scroll.setWidgetResizable(True)
        container = Qt.QWidget()
        grid = Qt.QVBoxLayout(container)
        scroll.setWidget(container)
        self.top_layout.addWidget(scroll)
        self.freq_sinks = [None] * NCH
        self.status = [None] * NCH
        self.btable = [None] * NCH   # per-channel band table (stands in for the module)
        self.brow = [None] * NCH     # per-channel freq -> table row
        for ch in self.selected:
            box = Qt.QGroupBox("%s   (%s)" % (CH_NAME[ch], PORTS[ch]))
            box.setStyleSheet("QGroupBox{font-weight:bold; margin-top:6px;}")
            v = Qt.QVBoxLayout(box)
            lbl = Qt.QLabel("starting...")
            lbl.setStyleSheet("font-size:12px; padding:2px;")
            v.addWidget(lbl)
            self.status[ch] = lbl

            # band table (stand-in for the module): live power + state per band
            bands, seen = [], set()
            for nm, fq, _d in self.frames[ch]:
                if fq not in seen:
                    seen.add(fq); bands.append((nm, fq))
            tbl = Qt.QTableWidget(len(bands), 4)
            tbl.setHorizontalHeaderLabels(["Band", "Freq MHz", "Power dBFS", "State"])
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(Qt.QAbstractItemView.NoEditTriggers)
            tbl.horizontalHeader().setStretchLastSection(True)
            row_of = {}
            for r, (nm, fq) in enumerate(bands):
                tbl.setItem(r, 0, Qt.QTableWidgetItem(nm))
                tbl.setItem(r, 1, Qt.QTableWidgetItem("%.4f" % (fq / 1e6)))
                tbl.setItem(r, 2, Qt.QTableWidgetItem("-"))
                tbl.setItem(r, 3, Qt.QTableWidgetItem("-"))
                row_of[fq] = r
            tbl.resizeColumnsToContents()
            tbl.setMaximumHeight(min(140, 26 * (len(bands) + 1)))
            v.addWidget(tbl)
            self.btable[ch] = tbl
            self.brow[ch] = row_of

            # FFT (left) + time (right), side by side, each its own graph
            graphs = Qt.QHBoxLayout()
            f0 = self.frames[ch][0][1]
            fsink = qtgui.freq_sink_c(1024, firdes.WIN_BLACKMAN_hARRIS, f0, samp_rate,
                                      "%s FFT" % CH_NAME[ch], 1)
            fsink.set_update_time(0.15)
            fsink.enable_grid(True)
            fsink.enable_autoscale(True)
            fw = sip.wrapinstance(fsink.pyqwidget(), Qt.QWidget)
            fw.setMinimumHeight(220)
            graphs.addWidget(fw)
            self.freq_sinks[ch] = fsink

            tsink = qtgui.time_sink_c(1024, samp_rate, "%s time" % CH_NAME[ch], 1)
            tsink.set_update_time(0.15)
            tsink.enable_grid(True)
            tsink.enable_autoscale(True)
            tw = sip.wrapinstance(tsink.pyqwidget(), Qt.QWidget)
            tw.setMinimumHeight(220)
            graphs.addWidget(tw)

            v.addLayout(graphs)
            self.connect(self.tap[ch], (fsink, 0))
            self.connect(self.tap[ch], (tsink, 0))
            grid.addWidget(box)

        # per-channel power probe (mean |x|^2) to tell which band is ACTIVE
        self.probes = [None] * NCH
        self.floor = {}                    # per-band noise floor (dBFS), keyed by freq
        self.active = {}                   # (ch, freq) -> bool, last activity verdict
        for ch in self.selected:
            mag2 = blocks.complex_to_mag_squared(1)
            avg = blocks.moving_average_ff(2000, 1.0 / 2000, 8000)
            pr = blocks.probe_signal_f()
            self.connect(self.tap[ch], mag2, avg, pr)
            self.probes[ch] = pr

        self.resize(1200, 900)

    # ---- scanning: one self-chaining single-shot timer per channel ----
    def start_scan(self):
        for ch in self.selected:
            self._next_look(ch)

    def _read_power(self, ch):
        """dBFS mean power on this channel right now (end of the current dwell)."""
        import math
        lvl = self.probes[ch].level()
        return 10.0 * math.log10(lvl + 1e-12)

    def _next_look(self, ch):
        frame = self.frames[ch]
        look = self.idx[ch]
        name, freq, dwell = frame[look]
        self.src.set_center_freq(uhd.tune_request(float(freq)), ch)
        if self.pub[ch] is not None:
            self.pub[ch].set_look(name, freq, look, self.frame_no[ch])   # A4/A5 metadata
        self.freq_sinks[ch].set_frequency_range(freq, self.samp_rate)
        # measure near the END of the dwell (LO settled, probe filled)
        Qt.QTimer.singleShot(max(int(scan_plan.SWITCH_MS) + 1, int(dwell * 0.9)),
                             lambda: self._measure(ch, name, freq, dwell, look))
        self.status[ch].setText(
            "%s  (%s)  -  %s @ %.4f MHz  dwell %.0f ms  look %d/%d  -  measuring..."
            % (CH_NAME[ch], PORTS[ch], name, freq / 1e6, dwell, look + 1, len(frame)))
        nxt = look + 1
        if nxt >= len(frame):
            nxt = 0
            self.frame_no[ch] += 1
        self.idx[ch] = nxt
        Qt.QTimer.singleShot(int(dwell + scan_plan.SWITCH_MS), lambda: self._next_look(ch))

    def _measure(self, ch, name, freq, dwell, look):
        try:
            locked = self.src.get_sensor("lo_locked", ch).to_bool()
        except Exception:
            locked = None
        db = self._read_power(ch)
        verdict = ""
        if db > -115.0:                                  # a real read (probe filled)
            fl = self.floor.get(freq)                    # per-band noise floor
            if fl is None or db < fl:
                self.floor[freq] = db
                fl = db
            active = (db > fl + 8.0)                     # 8 dB over this band's own floor
            self.active[(ch, freq)] = active
            verdict = "ACTIVE" if active else "quiet"
        self.status[ch].setText(
            "%s  (%s)  -  %s @ %.4f MHz  dwell %.0f ms  look %d/%d  LO %s  -  %.1f dBFS %s"
            % (CH_NAME[ch], PORTS[ch], name, freq / 1e6, dwell, look + 1,
               len(self.frames[ch]), "lock" if locked else "?", db, verdict))
        # update this band's row in the module table
        r = self.brow[ch].get(freq)
        if r is not None and verdict:
            self.btable[ch].item(r, 2).setText("%.1f" % db)
            st = self.btable[ch].item(r, 3)
            st.setText("ACTIVE" if verdict == "ACTIVE" else "quiet")
            st.setBackground(Qt.QColor(255, 220, 220) if verdict == "ACTIVE"
                             else Qt.QColor(235, 235, 235))
        if self.verbose:
            print("[scan] %s %-18s %.4f MHz  look %d/%d  LO %s  %6.1f dBFS  %s"
                  % (CH_NAME[ch][:3], name, freq / 1e6, look + 1, len(self.frames[ch]),
                     "lock" if locked else "?", db, verdict), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--samp-rate", type=float, default=2e6)
    ap.add_argument("--gain", type=float, default=50.0)
    ap.add_argument("--verbose", action="store_true", help="print each look to the terminal")
    ap.add_argument("--pub", action="store_true", help="also publish per-channel IQ+tags on tcp://127.0.0.1:5201..5204")
    ap.add_argument("--look-bw", type=float, default=0.0,
                    help="look bandwidth Hz for splitting wide bands (0 = one look per band; 80e6 for 10 GbE)")
    ap.add_argument("--channels", default="",
                    help="which channels to display/scan, e.g. 2 or 1,2 (default: all 4)")
    ap.add_argument("--pin", action="append", default=[],
                    help="hold a channel on one band, e.g. --pin '2=DMR 446.100' (repeatable)")
    a = ap.parse_args()

    chans = None
    if a.channels.strip():
        chans = [int(x) - 1 for x in a.channels.split(",") if x.strip()]
    pins = {}
    for p in a.pin:
        ch_s, name = p.split("=", 1)
        pins[int(ch_s) - 1] = name.strip()

    qapp = Qt.QApplication(sys.argv)
    tb = mon_scan(a.addr, a.samp_rate, a.gain, a.verbose, a.pub, a.look_bw, chans, pins)
    tb.start()
    tb.show()
    tb.start_scan()

    def sig_handler(sig=None, frame=None):
        tb.stop(); tb.wait(); qapp.quit()
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    timer = Qt.QTimer(); timer.start(200); timer.timeout.connect(lambda: None)

    qapp.exec_()
    tb.stop(); tb.wait()


if __name__ == "__main__":
    main()
