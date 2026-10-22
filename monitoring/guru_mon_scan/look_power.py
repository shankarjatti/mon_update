"""look_power - sample-accurate power statistics of each look, for the detector.

Why: the old detector read a power probe by PC time ("sleep the switch, then poll").
The samples reach the probe a few ms late, so the poll still saw the retune transient
(measured 2026-10-22: 98 % of the loud 0.5 ms windows on CH2 sat in the first 10 ms of
a look) and reported broadband bursts at 0 Hz as detections.

This block works on the samples themselves. mon_pub puts a "look" stream tag on the
first sample after every retune; at that tag this block starts a new look, skips the
first `settle_s` of samples (retune / switch transient), then tracks
  - the PEAK of the mean power in windows of `win_s` (catches short bursts), and
  - the MEAN power over the settled part of the look.
mon_server reads stats() at the end of the dwell. Nothing is estimated from time.
"""
import threading

import numpy as np
import pmt
from gnuradio import gr


class look_power(gr.sync_block):
    def __init__(self, samp_rate, settle_s=0.012, win_s=0.0005):
        gr.sync_block.__init__(self, name="look_power",
                               in_sig=[np.complex64], out_sig=None)
        self.settle = int(settle_s * samp_rate)
        self.W = max(16, int(win_s * samp_rate))
        self._lock = threading.Lock()
        self._key = None
        self._reset()

    def _reset(self):
        self._skip = self.settle
        self._acc = 0.0      # partial window sum
        self._accn = 0       # partial window length
        self._peak = 0.0     # max window mean power
        self._sum = 0.0      # total power (settled part)
        self._n = 0          # settled samples
        self._nwin = 0       # complete windows

    def _feed(self, x):
        if self._skip:
            d = min(self._skip, len(x))
            x = x[d:]
            self._skip -= d
        if len(x) == 0:
            return
        p = x.real.astype(np.float64) ** 2 + x.imag.astype(np.float64) ** 2
        self._sum += float(p.sum())
        self._n += len(p)
        i = 0
        if self._accn:
            take = min(self.W - self._accn, len(p))
            self._acc += float(p[:take].sum())
            self._accn += take
            i = take
            if self._accn == self.W:
                self._peak = max(self._peak, self._acc / self.W)
                self._nwin += 1
                self._acc, self._accn = 0.0, 0
        rest = p[i:]
        k = len(rest) // self.W
        if k:
            wm = rest[:k * self.W].reshape(k, self.W).mean(axis=1)
            self._peak = max(self._peak, float(wm.max()))
            self._nwin += k
        r = rest[k * self.W:]
        if len(r):
            self._acc += float(r.sum())
            self._accn += len(r)

    def work(self, input_items, output_items):
        x = input_items[0]
        n = len(x)
        base = self.nitems_read(0)
        tags = sorted(self.get_tags_in_window(0, 0, n, pmt.intern("look")),
                      key=lambda t: t.offset)
        with self._lock:
            pos = 0
            for t in tags:
                off = int(t.offset - base)
                if off > pos:
                    self._feed(x[pos:off])
                ht = pmt.dict_ref(t.value, pmt.intern("host_time"), pmt.PMT_NIL)
                self._key = pmt.to_double(ht) if pmt.is_real(ht) else None
                self._reset()
                pos = off
            self._feed(x[pos:])
        return n

    def stats(self):
        """(look key = host_time of its set_look, peak dB, mean dB, settled samples)."""
        with self._lock:
            if not self._nwin:
                return self._key, None, None, self._n
            return (self._key, 10.0 * np.log10(self._peak + 1e-15),
                    10.0 * np.log10(self._sum / max(1, self._n) + 1e-15), self._n)
