#!/usr/bin/env python3
"""Example edge-module subscriber for the monitoring Pub-Sub (A5).

Subscribes to one channel's ZeroMQ PUB socket from mon_server.py and prints each
message's header (which band/look/time) and the IQ sample count. This is the
shape an edge module (drone / terrestrial / radar / cellular) consumes.

Message = multipart [header_json, iq_bytes]:
  header: {ch, band, freq, look, frame, host_time, n}
  iq    : n * complex64 (little-endian float32 I,Q)

    ./mon_sub_example.py --ch 2            # CH2 terrestrial (port 5202)
    ./mon_sub_example.py --port 5202
"""
import argparse
import json

import numpy as np
import zmq

BASE_PORT = 5201


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", type=int, default=2, help="channel 1..4 (sets the port)")
    ap.add_argument("--port", type=int, default=None, help="override the port")
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    port = a.port if a.port else (BASE_PORT + (a.ch - 1))

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    sock.connect("tcp://%s:%d" % (a.host, port))
    print("[sub] listening on tcp://%s:%d (Ctrl-C to stop)" % (a.host, port))

    last_band = None
    while True:
        hdr_b, iq_b = sock.recv_multipart()
        hdr = json.loads(hdr_b.decode())
        iq = np.frombuffer(iq_b, dtype=np.complex64)
        # print once per band change (the stream is continuous)
        if hdr["band"] != last_band:
            last_band = hdr["band"]
            pwr = 10.0 * np.log10(np.mean(np.abs(iq) ** 2) + 1e-12)
            print("[sub] CH%d  %-18s %.4f MHz  look %d  frame %d  %d samp  %.1f dBFS"
                  % (hdr["ch"] + 1, hdr["band"], hdr["freq"] / 1e6, hdr["look"],
                     hdr["frame"], len(iq), pwr), flush=True)


if __name__ == "__main__":
    main()
