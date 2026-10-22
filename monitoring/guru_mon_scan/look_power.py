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

Narrowband detection (added 2026-10-22): the total power misses a narrow line that is weaker than the
whole band's noise (measured: a 5.785 GHz generator tone +28.5 dB over the noise per bin, but 12 dB below
CH1's total floor). So the block also averages an `nfft`-point Hann power spectrum over the settled part
of the look; nb() returns the strongest line (outside +-dc_guard of 0 Hz) over the MEDIAN bin, its
frequency offset and level. Needs >= 3 averaged segments.
"""
import threading

import numpy as np
import pmt
from gnuradio import gr


class look_power(gr.sync_block):
    def __init__(self, samp_rate, settle_s=0.012, win_s=0.0005, nfft=2048, dc_guard_hz=2000.0, nb_pct=None):
        gr.sync_block.__init__(self, name="look_power",
                               in_sig=[np.complex64], out_sig=None)
        self.settle = int(settle_s * samp_rate)
        self.W = max(16, int(win_s * samp_rate))
        self.fs = float(samp_rate)
        self.nfft = int(nfft)
        self._win = np.hanning(self.nfft)
        self._wn = float((self._win ** 2).sum())
        f = (np.arange(self.nfft) - self.nfft // 2) * self.fs / self.nfft
        self._f = f
        self._use = np.abs(f) > dc_guard_hz                      # bins outside the DC guard
        self.nb_pct = nb_pct      # None: mean spectrum; e.g. 80: level each bin holds in >= 20 % of the segments (pulses ignored)
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
        self._wins = []      # mean power of every complete window (for the sustained level)
        self._spec = np.zeros(self.nfft)   # summed |FFT|^2 (Hann) of the settled samples
        self._nseg = 0
        self._sbuf = np.zeros(0, np.complex64)
        self._segs = []

    def _feed(self, x):
        if self._skip:
            d = min(self._skip, len(x))
            x = x[d:]
            self._skip -= d
        if len(x) == 0:
            return
        # narrowband: whole nfft segments of the settled samples (remainder carried to the next call)
        sb = np.concatenate((self._sbuf, x)) if self._sbuf.size else x
        k2 = sb.size // self.nfft
        if k2:
            segs = sb[:k2 * self.nfft].reshape(k2, self.nfft) * self._win
            ps = np.abs(np.fft.fft(segs, axis=1)) ** 2
            self._spec += ps.sum(axis=0)
            if self.nb_pct is not None:
                self._segs.extend(ps)
            self._nseg += k2
        self._sbuf = sb[k2 * self.nfft:].copy()
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
                self._wins.append(self._acc / self.W)
                self._nwin += 1
                self._acc, self._accn = 0.0, 0
        rest = p[i:]
        k = len(rest) // self.W
        if k:
            wm = rest[:k * self.W].reshape(k, self.W).mean(axis=1)
            self._peak = max(self._peak, float(wm.max()))
            self._wins.extend(wm.tolist())
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

    def nb(self):
        """Strongest narrowband line of the look: (dB over the median bin, offset Hz, level dBFS per bin,
        segments averaged, -10 dB occupied bandwidth Hz) or None. Level: a full-scale complex tone reads 0 dBFS."""
        with self._lock:
            if self._nseg < 3:
                return None
            if self.nb_pct is not None and len(self._segs) >= 3:
                s = np.fft.fftshift(np.percentile(np.vstack(self._segs), self.nb_pct, axis=0))
            else:
                s = np.fft.fftshift(self._spec) / self._nseg
            u = s[self._use]
            j = int(np.argmax(u))
            med = float(np.median(u))
            pk = float(u[j])
            f = float(self._f[self._use][j])
            # occupied bandwidth of the line: contiguous bins around the peak within 10 dB of it.
            # A 4FSK voice signal (DMR / P25 / NXDN, TETRA pi/4-DQPSK) spreads over ~4-25 kHz; a CW spur or a
            # generator tone is one Hann main lobe (~2-3 bins).
            jf = int(np.flatnonzero(self._use)[j])
            lo = hi = jf
            while lo > 0 and s[lo - 1] >= pk * 0.1:
                lo -= 1
            while hi < s.size - 1 and s[hi + 1] >= pk * 0.1:
                hi += 1
            bw = (hi - lo + 1) * self.fs / self.nfft
            return (10.0 * np.log10(pk / max(med, 1e-30)), f,
                    10.0 * np.log10(pk / (self._win.sum() ** 2) + 1e-30), self._nseg, bw)

    def sustained(self, min_s):
        """Level (dBFS) reached by at least min_s of the look's windows in total: the K-th largest window,
        K = min_s / win. A pulse shorter than min_s cannot raise it; a real burst / call longer than min_s does."""
        with self._lock:
            if not self._wins:
                return None
            k = max(1, int(round(min_s * self.fs / self.W)))
            if k > len(self._wins):
                return None
            v = np.partition(np.asarray(self._wins), len(self._wins) - k)[len(self._wins) - k]
            return 10.0 * np.log10(v + 1e-15)

    def stats(self):
        """(look key = host_time of its set_look, peak dB, mean dB, settled samples)."""
        with self._lock:
            if not self._nwin:
                return self._key, None, None, self._n
            return (self._key, 10.0 * np.log10(self._peak + 1e-15),
                    10.0 * np.log10(self._sum / max(1, self._n) + 1e-15), self._n)
