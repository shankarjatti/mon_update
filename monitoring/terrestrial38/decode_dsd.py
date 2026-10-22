#!/usr/bin/env python3
"""decode_dsd - one DSD decode chain (DMR / P25 / NXDN / D-STAR) in GR 3.8,
fed by the mon_scan CH2 ZeroMQ feed (no USRP; mon_scan owns the radio).

Chain:
  zmq_cc_source (CH2 IQ @ 2 MS/s)
    -> freq_xlating_fir_filter_ccf  (select the channel, decimate 2e6 -> 50 kHz)
    -> quadrature_demod_cf          (FM discriminator)
    -> rational_resampler 48/50     (-> 48 kHz, the DSD input rate)
    -> dsd_block_ff(frame, mod)     (-> 8 kHz voice)
    -> wav file  (+ prints talkgroup/source/nac as they change)

    source ~/gnuradio-3.8/setup_env.sh
    ./decode_dsd.py --proto dmr --offset 0           # CH2 feed on 5202
    ./decode_dsd.py --proto p25 --offset 0 --gain 4.2
Run mon_scan first (publishing), tuned so the protocol's channel is near CH2 centre.
"""
import argparse
import threading
import time
import math

from gnuradio import gr, blocks, analog, filter, audio
from gnuradio.filter import firdes

import dsd
from zmq_cc_source import zmq_cc_source

PROTO = {
    "dmr":   (dsd.dsd_FRAME_DMR_MOTOTRBO, dsd.dsd_MOD_C4FM),
    "p25":   (dsd.dsd_FRAME_P25_PHASE_1,  dsd.dsd_MOD_C4FM),
    "nxdn":  (dsd.dsd_FRAME_NXDN96,       dsd.dsd_MOD_GFSK),
    "dstar": (dsd.dsd_FRAME_DSTAR,        dsd.dsd_MOD_GFSK),
}

SAMP = 2e6
XDECIM = 40            # 2e6 -> 50 kHz
CHAN = SAMP / XDECIM   # 50000


class decode_dsd(gr.top_block):
    def __init__(self, endpoint, proto, offset, gain, wav, band, play=True, vol=1.0,
                 fifo=None, audio_tap=None):
        gr.top_block.__init__(self, "decode_dsd_%s" % proto)
        frame, mod = PROTO[proto]

        self.src = zmq_cc_source(endpoint, only_band=band)
        taps = firdes.low_pass(1, SAMP, 6250, 2000)
        self.xlate = filter.freq_xlating_fir_filter_ccf(XDECIM, taps, offset, SAMP)
        self.demod = analog.quadrature_demod_cf(gain)
        self.resamp = filter.rational_resampler_fff(interpolation=48, decimation=50)
        self.dsd = dsd.dsd_block_ff(frame, mod, 3, True, 2)
        self.wav = blocks.wavfile_sink(wav, 1, 8000, 16)

        self.connect(self.src, self.xlate, self.demod, self.resamp, self.dsd, self.wav)
        # AUDIO TAP: 8 kHz dsd -> 48 kHz float32 -> ZMQ PUB for the repo bridge
        # (bridge_server.audio_tap_reader reads raw float32 at 48 kHz).
        if audio_tap:
            from zmq_f32_sink import zmq_f32_sink
            self.tap_rs = filter.rational_resampler_fff(interpolation=6, decimation=1)
            self.tap = zmq_f32_sink(int(audio_tap))
            self.connect(self.dsd, self.tap_rs, self.tap)
            print("[decode_dsd] audio tap -> ZMQ PUB :%s (48 kHz f32)" % audio_tap, flush=True)
        # LIVE AUDIO
        if fifo:
            # dsd 8 kHz float -> int16 -> FIFO; play with: paplay --raw --rate=8000 ...
            self.vol = blocks.multiply_const_ff(vol)
            self.f2s = blocks.float_to_short(1, 32767.0)
            self.fsink = blocks.file_sink(gr.sizeof_short, fifo, False)
            self.fsink.set_unbuffered(True)
            self.connect(self.dsd, self.vol, self.f2s, self.fsink)
            print("[decode_dsd] audio -> FIFO %s (8 kHz s16)" % fifo, flush=True)
        elif play:
            self.vol = blocks.multiply_const_ff(vol)
            self.aud_rs = filter.rational_resampler_fff(interpolation=6, decimation=1)
            try:
                self.audio = audio.sink(48000, "", True)
                self.connect(self.dsd, self.vol, self.aud_rs, self.audio)
            except Exception as e:
                print("[decode_dsd] audio sink unavailable (%s); use --fifo" % e, flush=True)
        self.proto = proto

    def watch(self, stop):
        last = None
        while not stop.is_set():
            tg, sr, nac = self.dsd.last_talkgroup(), self.dsd.last_source(), self.dsd.nac()
            band = self.src.cur_band
            cur = (tg, sr, nac)
            if cur != last and (tg or sr or nac):
                print("[%s] band=%s  talkgroup=%s  source=%s  nac=%s"
                      % (self.proto.upper(), band, tg, sr, nac), flush=True)
                last = cur
            time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="tcp://127.0.0.1:5202")
    ap.add_argument("--proto", default="dmr", choices=list(PROTO))
    ap.add_argument("--offset", type=float, default=0.0, help="channel offset Hz from CH2 centre")
    ap.add_argument("--gain", type=float, default=None, help="FM demod gain (default auto)")
    ap.add_argument("--wav", default=None, help="output wav (default decode_<proto>.wav)")
    ap.add_argument("--band", default=None, help="only process this CH2 scan band (e.g. 'DMR 446.100')")
    ap.add_argument("--no-audio", action="store_true", help="do not play live audio")
    ap.add_argument("--vol", type=float, default=1.0, help="audio volume")
    ap.add_argument("--fifo", default=None, help="write 8 kHz s16 PCM to this FIFO (play with paplay)")
    ap.add_argument("--audio-tap", default=None,
                    help="publish 48 kHz float32 audio on this ZMQ port for the repo bridge (e.g. 9101)")
    a = ap.parse_args()
    gain = a.gain if a.gain is not None else CHAN / (2 * math.pi * 2500.0)
    wav = a.wav or ("decode_%s.wav" % a.proto)

    tb = decode_dsd(a.endpoint, a.proto, a.offset, gain, wav, a.band,
                    play=not a.no_audio, vol=a.vol, fifo=a.fifo, audio_tap=a.audio_tap)
    stop = threading.Event()
    th = threading.Thread(target=tb.watch, args=(stop,), daemon=True)
    tb.start(); th.start()
    print("[decode_dsd] %s decoding from %s (gain %.2f) -> %s ; Ctrl-C to stop"
          % (a.proto.upper(), a.endpoint, gain, wav), flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); tb.stop(); tb.wait()
        print("\n[decode_dsd] stopped; wrote", wav)


if __name__ == "__main__":
    main()
