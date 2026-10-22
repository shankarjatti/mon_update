#!/usr/bin/env python3
"""decode_tetra - TETRA pi/4-DQPSK decode in GR 3.8, fed by the mon_scan CH2 feed.

Chain (same as the repo's working TETRA path, single channel):
  zmq_cc_source (CH2 IQ @ 2 MS/s)
   -> freq_xlating_fir_filter (select channel, 2e6 -> 50 kHz)
   -> rational_resampler 18/25 (-> 36 kHz = 2 sps @ 18 ksym/s)
   -> feedforward AGC -> FLL band edge -> pfb_clock_sync (sps=2)
   -> linear_equalizer (CMA) -> diff_phasor -> constellation_decoder (DQPSK)
   -> map (pre-diff) -> unpack_k_bits (2) -> tetra_decoder_block
   -> 4x wav (TN1-4) ; call_log messages printed

    source ~/gnuradio-3.8/setup_env.sh
    ./decode_tetra.py --offset 0
Run mon_scan publishing CH2, tuned so the TETRA carrier is near CH2 centre.
"""
import argparse
import time

from gnuradio import gr, blocks, analog, digital, filter
from gnuradio.filter import firdes

import tetra
from zmq_cc_source import zmq_cc_source

SAMP = 2e6
XDECIM = 40          # 2e6 -> 50 kHz
SPS = 2
NFILTS = 32
SYM_RATE = 18000     # TETRA 18 ksym/s -> 36 kHz at sps=2


class decode_tetra(gr.top_block):
    def __init__(self, endpoint, offset, log_level, band, fifo=None, vol=1.0, audio_tap=None):
        gr.top_block.__init__(self, "decode_tetra")
        self.src = zmq_cc_source(endpoint, only_band=band)
        taps = firdes.low_pass(1, SAMP, 14000, 4000)   # ~25 kHz TETRA channel
        self.xlate = filter.freq_xlating_fir_filter_ccf(XDECIM, taps, offset, SAMP)
        # 50 kHz -> 36 kHz
        self.resamp = filter.rational_resampler_ccc(interpolation=18, decimation=25)
        self.agc = analog.feedforward_agc_cc(1024, 1.0)
        self.fll = digital.fll_band_edge_cc(SPS, 0.35, 45, 2 * 3.141592653589793 / 100.0)
        rrc = firdes.root_raised_cosine(NFILTS, NFILTS, 1.0 / float(SPS), 0.35, 11 * SPS * NFILTS)
        self.clock = digital.pfb_clock_sync_ccf(SPS, 2 * 3.141592653589793 / 100.0,
                                                rrc, NFILTS, NFILTS / 2, 1.5, SPS)
        self.constel = digital.constellation_dqpsk().base()
        # GR 3.8 has no adaptive_algorithm_cma/linear_equalizer; use the classic
        # CMA equalizer (DQPSK modulus 1.0). TETRA also decodes without it, but
        # the equalizer helps on a real channel.
        self.eq = digital.cma_equalizer_cc(11, 1.0, 0.01, SPS)
        self.diff = digital.diff_phasor_cc()
        self.cdec = digital.constellation_decoder_cb(self.constel)
        self.mapb = digital.map_bb(self.constel.pre_diff_code())
        self.unpack = blocks.unpack_k_bits_bb(self.constel.bits_per_symbol())
        self.tetra = tetra.tetra_decoder_block(log_level, True, False, False)

        self.connect(self.src, self.xlate, self.resamp, self.agc, self.fll,
                     self.clock, self.eq, self.diff, self.cdec, self.mapb,
                     self.unpack, self.tetra)
        for s in range(4):
            self.connect((self.tetra, s), blocks.wavfile_sink("tetra_tn%d.wav" % (s + 1), 1, 8000, 16))

        # LIVE AUDIO: mix the 4 timeslots -> int16 -> FIFO (play with paplay)
        if fifo:
            self.mix = blocks.add_vff(1)
            for s in range(4):
                self.connect((self.tetra, s), (self.mix, s))
            self.vol = blocks.multiply_const_ff(vol)
            self.f2s = blocks.float_to_short(1, 32767.0)
            self.fsink = blocks.file_sink(gr.sizeof_short, fifo, False)
            self.fsink.set_unbuffered(True)
            self.connect(self.mix, self.vol, self.f2s, self.fsink)
            print("[decode_tetra] audio (TN1-4 mix) -> FIFO %s (8 kHz s16)" % fifo, flush=True)

        # AUDIO TAP: TN1-4 mix (8 kHz) -> 48 kHz float32 -> ZMQ PUB for the repo
        # bridge (bridge_server.audio_tap_reader reads raw float32 @ 48 kHz on 9104).
        if audio_tap:
            from zmq_f32_sink import zmq_f32_sink
            self.tapmix = blocks.add_vff(1)
            for s in range(4):
                self.connect((self.tetra, s), (self.tapmix, s))
            self.tap_rs = filter.rational_resampler_fff(interpolation=6, decimation=1)
            self.tap = zmq_f32_sink(int(audio_tap))
            self.connect(self.tapmix, self.tap_rs, self.tap)
            print("[decode_tetra] audio tap -> ZMQ PUB :%s (48 kHz f32)" % audio_tap, flush=True)

        self.dbg = blocks.message_debug()
        self.msg_connect((self.tetra, 'call_log'), (self.dbg, 'print'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="tcp://127.0.0.1:5202")
    ap.add_argument("--offset", type=float, default=0.0, help="channel offset Hz from CH2 centre")
    ap.add_argument("--log-level", type=int, default=2)
    ap.add_argument("--band", default=None, help="only process this CH2 scan band")
    ap.add_argument("--fifo", default=None, help="write 8 kHz s16 PCM (TN mix) to this FIFO")
    ap.add_argument("--vol", type=float, default=1.0)
    ap.add_argument("--audio-tap", default=None,
                    help="publish 48 kHz float32 audio on this ZMQ port for the repo bridge (e.g. 9104)")
    a = ap.parse_args()
    tb = decode_tetra(a.endpoint, a.offset, a.log_level, a.band, a.fifo, a.vol, a.audio_tap)
    tb.start()
    print("[decode_tetra] decoding from %s (offset %.0f Hz); Ctrl-C to stop" % (a.endpoint, a.offset), flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        tb.stop(); tb.wait()
        print("\n[decode_tetra] stopped; wrote tetra_tn1..4.wav")


if __name__ == "__main__":
    main()
