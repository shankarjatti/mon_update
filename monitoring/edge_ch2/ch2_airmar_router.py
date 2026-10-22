#!/usr/bin/env python3
"""ch2_airmar_router - CH2 air & maritime bands -> the old repo's air/maritime decoder ports.

The terrestrial repo (terrestrial_src = GitHub 1stversiondone) has a working air/maritime chain built for
its B210 Module 1:  Module 1 TCP 7009 (AIS) / 7010 (ADS-B) -> airmaritime_decoder_live.py (gr-ais, gr-adsb)
-> ZMQ 9201 / 9202 -> airmaritime_bridge.py (ws 8887) -> airmaritime_console.html.
On the X310, CH2 (TwinRX A/RX2) visits "AIS 161.975" and "ADS-B 1090" in its MON frame (scan_plan) and
publishes them on ZMQ 5202 with the rest of CH2 at 200 kS/s. This router is the air/maritime twin of
ch2_header_router.py (which serves the 4 terrestrial ports and is NOT changed): it subscribes to the same
5202 stream (a second ZMQ subscriber), takes only the AIS / ADS-B blocks and serves them on 7009 / 7010 in
the form that decoder was built for:

  AIS 7009 : 250 kS/s with 162.000 MHz at 0 Hz. The decoder's two branches shift by -25 / +25 kHz
             (AIS 1 = 161.975, AIS 2 = 162.025) and its GMSK demod needs 250 kS/s (5 samples/symbol after
             its /5; README of that repo: 200 kS/s gives zero decodes). CH2 gives 200 kS/s centred 161.975 MHz
             -> phase-continuous shift by -25 kHz + stateful 5/4 polyphase resampler.
  ADS-B 7010: the real CH2 ADS-B samples, 200 kS/s, unchanged (airmar_decoder_ext.py tells the decoder that
             rate; its own resampler goes to the 2 MS/s its blocks are built for). NOTE: 200 kHz of bandwidth
             cannot carry 1 Mb/s Mode-S pulses, so ADS-B does not decode at this CH2 rate -- the spectrum and
             the detector are real, decoding needs a >= 2 MS/s CH2 dwell (not changed here).
Between dwells each port streams zero-fill at its rate (same keep-alive the repo's Module 1 used), and the
first 14 ms after every retune are dropped (old-frequency samples in flight), as in the terrestrial router.

    python3 ch2_airmar_router.py --in tcp://127.0.0.1:5202
"""
import argparse
import asyncio
import json

import numpy as np
import zmq
import zmq.asyncio
from scipy.signal import firwin, lfilter

SETTLE_S = 0.014          # = mon_server SETTLE_S
TICK_S = 0.02             # sender cadence
AIS_CENTRE_HZ = 162.000e6
AIS_RATE = 250000.0
PORTS = {"ais": 7009, "adsb": 7010}


def band_key(name):
    n = (name or "").upper()
    if n.startswith("AIS"):
        return "ais"
    if "ADS-B" in n or n.startswith("ADSB"):
        return "adsb"
    return None


class Shifter:
    """y[n] = x[n] * exp(-j 2 pi f n / fs), phase carried across blocks."""
    def __init__(self):
        self.ph = 0.0

    def __call__(self, x, f, fs):
        if not f:
            return x
        w = -2.0 * np.pi * f / fs
        y = x * np.exp(1j * (self.ph + w * np.arange(x.size)))
        self.ph = float((self.ph + w * x.size) % (2.0 * np.pi))
        return y.astype(np.complex64)

    def reset(self):
        self.ph = 0.0


class StatefulResampler:
    """Rational L/M resampler (zero-stuff by L, low-pass, keep every M-th), FIR state and output phase carried
    across blocks, so resampling a stream in small blocks equals resampling it whole (no block-edge transients
    -- those break GMSK timing recovery)."""
    def __init__(self, L, M, ntaps_per_phase=24):
        self.L, self.M = int(L), int(M)
        n = ntaps_per_phase * self.L + 1
        self.taps = (firwin(n, 0.9 / max(self.L, self.M)) * self.L).astype(np.float64)
        self.reset()

    def reset(self):
        self.zi = np.zeros(len(self.taps) - 1, dtype=np.complex128)
        self.phase = 0

    def __call__(self, x):
        u = np.zeros(x.size * self.L, dtype=np.complex128)
        u[::self.L] = x
        y, self.zi = lfilter(self.taps, 1.0, u, zi=self.zi)
        idx = np.arange(self.phase, y.size, self.M)
        self.phase = (idx[-1] + self.M - y.size) if idx.size else (self.phase - y.size)
        return y[idx].astype(np.complex64)


class Port:
    """One TCP listen port: complex64 at `rate` to every client, real IQ while its band dwells, else zero-fill."""
    def __init__(self, key, port, rate):
        self.key, self.port, self.rate = key, port, float(rate)
        self.n = int(round(self.rate * TICK_S))
        self.zero = np.zeros(self.n, dtype=np.complex64).tobytes()
        self.writers = set()
        self.buf = bytearray()

    async def serve(self):
        srv = await asyncio.start_server(self._client, "127.0.0.1", self.port)
        asyncio.create_task(self._pump())
        async with srv:
            await srv.serve_forever()

    async def _client(self, reader, writer):
        self.writers.add(writer)
        try:
            while not reader.at_eof():
                if not await reader.read(4096):
                    break
        except Exception:
            pass
        finally:
            self.writers.discard(writer)
            try:
                writer.close()
            except Exception:
                pass

    def feed(self, b):
        self.buf += b

    def flush(self):
        self.buf.clear()

    async def _pump(self):
        loop = asyncio.get_event_loop()
        nbytes = self.n * 8
        next_t = loop.time()
        while True:
            next_t += TICK_S
            if len(self.buf) > nbytes * 2:                  # stay real-time
                del self.buf[:len(self.buf) - nbytes]
            if len(self.buf) >= nbytes:
                chunk = bytes(self.buf[:nbytes]); del self.buf[:nbytes]
            else:
                chunk = self.zero
            for w in list(self.writers):
                try:
                    tr = w.transport
                    if tr is not None and tr.get_write_buffer_size() > nbytes * 4:
                        continue
                    w.write(chunk)
                except Exception:
                    self.writers.discard(w)
            await asyncio.sleep(max(0.0, next_t - loop.time()))


async def sub_loop(endpoint, ports):
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVHWM, 64)
    sub.connect(endpoint)
    print("[airmar] CH2 %s -> AIS :%d (250 kS/s, 162.000 MHz at 0 Hz), ADS-B :%d (CH2 rate)"
          % (endpoint, PORTS["ais"], PORTS["adsb"]), flush=True)
    shift, rs = Shifter(), None
    last_freq, last_look, blank, nblk = None, None, 0, {"ais": 0, "adsb": 0}
    while True:
        hdr_b, iq_b = await sub.recv_multipart()
        try:
            h = json.loads(hdr_b.decode())
        except Exception:
            continue
        freq = h.get("freq")
        fs = float(h.get("samp_rate", 200000.0))
        if freq is not None and freq != last_freq:
            if last_freq is not None:
                blank = int(SETTLE_S * fs)
            last_freq = freq
        k = band_key(h.get("band"))
        if k is None:
            continue
        look = (h.get("frame"), h.get("look"), h.get("host_time"))
        if look != last_look:                           # new dwell: clean state, no stale samples
            last_look = look
            ports[k].flush()
            if k == "ais":
                shift.reset()
                if rs is not None:
                    rs.reset()
        x = np.frombuffer(iq_b, dtype=np.complex64)
        if blank:
            d = min(blank, x.size)
            x = x[d:]
            blank -= d
        if x.size == 0:
            continue
        if k == "ais":
            x = shift(x, AIS_CENTRE_HZ - float(freq), fs)
            if rs is None or rs.fs != fs:
                from fractions import Fraction
                fr = Fraction(int(AIS_RATE), int(fs)).limit_denominator(64)
                rs = StatefulResampler(fr.numerator, fr.denominator)
                rs.fs = fs
            x = rs(x)
        ports[k].feed(x.tobytes())
        nblk[k] += 1
        if sum(nblk.values()) % 200 == 0:
            print("[airmar] routed blocks: ais=%d adsb=%d" % (nblk["ais"], nblk["adsb"]), flush=True)


async def main_async(endpoint, adsb_rate):
    ports = {"ais": Port("ais", PORTS["ais"], AIS_RATE), "adsb": Port("adsb", PORTS["adsb"], adsb_rate)}
    tasks = [asyncio.create_task(p.serve()) for p in ports.values()]
    tasks.append(asyncio.create_task(sub_loop(endpoint, ports)))
    await asyncio.gather(*tasks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="tcp://127.0.0.1:5202")
    ap.add_argument("--adsb-rate", type=float, default=200000.0, help="CH2 rate of the ADS-B dwell (header samp_rate)")
    a = ap.parse_args()
    try:
        asyncio.run(main_async(a.inp, a.adsb_rate))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
