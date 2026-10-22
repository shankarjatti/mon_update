#!/usr/bin/env python3
"""decode_dmr_direct - STANDALONE DMR decode straight off the X310, GR 3.8/UHD 3.15.

This is the repo's OWN terrestrial decode path (github 1stversiondone, was
UHD4/GR3.10/B210) reproduced faithfully in our GR 3.8 / UHD 3.15 env, with NO
monitoring / ZeroMQ / bridge in the way. One program owns the USRP. Use it to
prove the PORT is correct before integrating with the CH2 monitoring feed.

Repo chain (allinone.py), per DMR channel:
  USRP @ 200 kHz  ->  12.5 kHz channel  ->  48 kHz  ->  quad_demod(gain 1.0)
  ->  dsd_block_ff(DMR_MOTOTRBO, C4FM, 3, True, 0)
(The repo channelizes 200 kHz into 16 x 12.5 kHz; for one known carrier we select
 it directly with a freq-xlating filter — equivalent for a single channel.)

    source ~/gnuradio-3.8/setup_env.sh
    ./decode_dmr_direct.py --freq 446.1e6                 # tune straight to carrier
    ./decode_dmr_direct.py --freq 446.0e6 --offset 100e3  # carrier off-DC (avoids LO spike)
Add --fifo <path> + a paplay to hear it; --rf-gain to set USRP gain.
"""
import argparse, math, threading, time
from gnuradio import gr, blocks, analog, filter, uhd
from gnuradio.filter import firdes
import dsd

SAMP = 200000.0        # repo Module 1 USRP rate
CH_DECIM = 4           # 200k -> 50k, 12.5 kHz channel
GAIN_DEMOD = 1.0       # repo gain_demod for DMR (NOT our 3.18)


class decode_dmr_direct(gr.top_block):
    def __init__(self, addr, freq, offset, rf_gain, fifo=None, vol=1.0, wav="dmr_direct.wav", ant=None):
        gr.top_block.__init__(self, "decode_dmr_direct")
        self.src = uhd.usrp_source(addr, uhd.stream_args(cpu_format="fc32", channels=[0]))
        self.src.set_samp_rate(SAMP)
        self.src.set_center_freq(uhd.tune_request(freq), 0)
        self.src.set_dc_offset(True, 0)
        if ant:
            self.src.set_antenna(ant, 0)
        g = self.src.get_gain_range(0)
        self.src.set_gain(max(g.start(), min(g.stop(), rf_gain)), 0)

        # 200k -> 50k, 12.5 kHz channel (repo channel bandwidth)
        taps = firdes.low_pass(1, SAMP, 6250, 2000)
        self.xlate = filter.freq_xlating_fir_filter_ccf(CH_DECIM, taps, offset, SAMP)
        # 50k -> 48k, like the repo's per-channel rate into the demod
        self.resamp = filter.rational_resampler_ccf(interpolation=24, decimation=25)
        self.demod = analog.quadrature_demod_cf(GAIN_DEMOD)
        self.dsd = dsd.dsd_block_ff(dsd.dsd_FRAME_DMR_MOTOTRBO, dsd.dsd_MOD_C4FM, 3, True, 0)
        try:                       # GR 3.8 signature
            self.wav = blocks.wavfile_sink(wav, 1, 8000, 16)
        except TypeError:          # GR 3.10 needs format enums
            self.wav = blocks.wavfile_sink(wav, 1, 8000,
                                           blocks.FORMAT_WAV, blocks.FORMAT_PCM_16, False)

        self.connect(self.src, self.xlate, self.resamp, self.demod, self.dsd, self.wav)

        if fifo:
            self.vol = blocks.multiply_const_ff(vol)
            self.f2s = blocks.float_to_short(1, 32767.0)
            self.fsink = blocks.file_sink(gr.sizeof_short, fifo, False)
            self.fsink.set_unbuffered(True)
            self.connect(self.dsd, self.vol, self.f2s, self.fsink)
            print("[direct] audio -> FIFO %s (8 kHz s16)" % fifo, flush=True)

    def watch(self, stop):
        last = None
        while not stop.is_set():
            tg, sr, nac = self.dsd.last_talkgroup(), self.dsd.last_source(), self.dsd.nac()
            cur = (tg, sr, nac)
            if cur != last and (tg or sr or nac):
                print("[DMR] talkgroup=%s source=%s nac=%s" % (tg, sr, nac), flush=True)
                last = cur
            time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="type=b200", help="UHD device (default B210)")
    ap.add_argument("--freq", type=float, default=446.1e6, help="USRP centre freq Hz")
    ap.add_argument("--offset", type=float, default=0.0, help="channel offset Hz from centre")
    ap.add_argument("--rf-gain", type=float, default=40.0, help="USRP RX gain dB")
    ap.add_argument("--ant", default="RX2", help="RX antenna port (B210: RX2 or TX/RX)")
    ap.add_argument("--fifo", default=None)
    ap.add_argument("--vol", type=float, default=1.0)
    ap.add_argument("--wav", default="dmr_direct.wav")
    a = ap.parse_args()
    tb = decode_dmr_direct(a.addr, a.freq, a.offset, a.rf_gain, a.fifo, a.vol, a.wav, a.ant)
    stop = threading.Event()
    th = threading.Thread(target=tb.watch, args=(stop,), daemon=True); th.start()
    tb.start()
    print("[direct] DMR @ %.4f MHz (offset %.0f Hz, rf-gain %.0f) rate %.0f kHz -> %s"
          % (a.freq/1e6, a.offset, a.rf_gain, SAMP/1e3, a.wav), flush=True)
    print("[direct] repo chain: 12.5kHz chan -> 48k -> quad_demod(1.0) -> dsd(...,0). Ctrl-C to stop.", flush=True)
    try:
        while True: time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); tb.stop(); tb.wait()
        print("\n[direct] stopped; wrote", a.wav)


if __name__ == "__main__":
    main()
