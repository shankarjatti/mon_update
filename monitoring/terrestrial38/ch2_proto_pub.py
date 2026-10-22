#!/usr/bin/env python3
"""ch2_proto_pub - fan the CH2 monitoring feed out to per-protocol ports.

Architecture (user's design): CH2 monitoring receives the signal; its IQ goes to
the terrestrial decoders, and EACH PROTOCOL HAS ITS OWN SUBSCRIBE PORT (same idea
as the repo's module1 TCP ports 7001-7008). This bridge subscribes to the CH2
feed (mon_scan/mon_server PUB on 5202) and re-publishes each band's IQ on that
band's protocol port, so each decoder just subscribes to its own port.

Port map (repo numbering):
  DMR 7001 · NXDN 7002 · P25 7003 · TETRA 7004 · D-STAR 7006
(NXDN48 7005, X2-TDMA 7007, ProVoice 7008 reserved, unused on CH2.)

    ./ch2_proto_pub.py                      # CH2 feed 5202 -> 7001..7006
A decoder then does:  zmq_cc_source("tcp://127.0.0.1:7001")  (DMR), etc.
"""
import argparse
import json

import zmq

# band name (as mon_scan tags it) -> protocol subscribe port
BAND_PORT = {
    "DMR 446.100": 7001,
    "NXDN 451.0":  7002,
    "P25 450.0":   7003,
    "TETRA 420.0": 7004,
    "D-STAR 145.0": 7006,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="tcp://127.0.0.1:5202",
                    help="CH2 monitoring feed (mon_scan/mon_server PUB)")
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.connect(a.inp)

    # one PUB socket per protocol port
    pubs = {}
    for band, port in BAND_PORT.items():
        p = ctx.socket(zmq.PUB)
        p.setsockopt(zmq.SNDHWM, 64)
        p.setsockopt(zmq.LINGER, 0)
        p.bind("tcp://%s:%d" % (a.host, port))
        pubs[band] = p
    print("[ch2_proto_pub] CH2 %s -> ports: %s"
          % (a.inp, ", ".join("%s=%d" % (b.split()[0], pt) for b, pt in BAND_PORT.items())),
          flush=True)

    n = {b: 0 for b in BAND_PORT}
    while True:
        try:
            hdr_b, iq_b = sub.recv_multipart()
        except KeyboardInterrupt:
            break
        try:
            band = json.loads(hdr_b.decode()).get("band")
        except Exception:
            continue
        p = pubs.get(band)
        if p is not None:
            try:
                p.send_multipart([hdr_b, iq_b], flags=zmq.NOBLOCK)
                n[band] += 1
            except zmq.Again:
                pass


if __name__ == "__main__":
    main()
