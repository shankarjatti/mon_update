#!/usr/bin/env python3
"""terr_audio_play - play the LIVE decoded terrestrial voice through the PC.

allinone.py publishes each protocol's decoded audio on ZMQ taps (float32 @ 48 kHz):
  dmr 9101 · nxdn 9102 · p25 9103 · tetra 9104
Only one terrestrial band decodes at a time (CH2 is on one band), so this
subscribes to all four, and plays whatever audio arrives out to PulseAudio via
paplay. You hear the decoded voice live, in real time, through PC speakers/phones
-- independent of the browser console's own Listen button.

  python3 terr_audio_play.py            # play all protocols (whichever is live)
  python3 terr_audio_play.py --only dmr # play only DMR
  python3 terr_audio_play.py --vol 1.5  # louder
"""
import argparse
import subprocess
import numpy as np
import zmq

TAPS = {"dmr": 9101, "nxdn": 9102, "p25": 9103, "tetra": 9104}
RATE = 48000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, choices=list(TAPS))
    ap.add_argument("--vol", type=float, default=1.0)
    ap.add_argument("--squelch", type=float, default=-45.0,
                    help="audio squelch (dBFS): mute blocks quieter than this, so "
                         "you hear voice not hiss. Raise toward 0 to cut more noise.")
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    taps = {a.only: TAPS[a.only]} if a.only else TAPS

    pa = subprocess.Popen(
        ["paplay", "--raw", "--format=s16le", "--rate=%d" % RATE, "--channels=1",
         "--latency-msec=200", "--stream-name=SecureCOM terrestrial"],
        stdin=subprocess.PIPE)

    ctx = zmq.Context.instance()
    socks = {}
    poller = zmq.Poller()
    for name, port in taps.items():
        s = ctx.socket(zmq.SUB)
        s.setsockopt(zmq.SUBSCRIBE, b"")
        s.setsockopt(zmq.RCVHWM, 32)
        s.connect("tcp://%s:%d" % (a.host, port))
        socks[s] = name
        poller.register(s, zmq.POLLIN)
    print("[audio] playing decoded voice (%s) squelch=%.0f dBFS vol=%.1f -> PulseAudio @ %d Hz. Ctrl-C to stop."
          % (", ".join(taps), a.squelch, a.vol, RATE), flush=True)

    vol = a.vol
    sq_lin = 10.0 ** (a.squelch / 20.0)     # squelch threshold as linear RMS
    try:
        while True:
            for s, _ in poller.poll(500):
                try:
                    while True:
                        raw = s.recv(flags=zmq.NOBLOCK)
                        y = np.frombuffer(raw, dtype=np.float32)
                        if y.size == 0:
                            continue
                        # SQUELCH: below the threshold = noise/hiss -> mute it
                        rms = float(np.sqrt(np.mean(y * y)) + 1e-12)
                        if rms < sq_lin:
                            y = np.zeros_like(y)
                        pcm = np.clip(y * vol, -1.0, 1.0)
                        pa.stdin.write((pcm * 32767.0).astype("<i2").tobytes())
                        pa.stdin.flush()
                except zmq.Again:
                    pass
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pa.stdin.close(); pa.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
