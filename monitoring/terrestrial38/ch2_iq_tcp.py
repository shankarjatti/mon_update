#!/usr/bin/env python3
"""ch2_iq_tcp - feed the repo bridge's IQ ports from our CH2 monitoring feed.

The repo's securecom console (gui/securecom_gui.html) is driven by
gui/bridge_server.py, which connects as a TCP CLIENT to one port per protocol
(127.0.0.1:7001-7008) and reads a raw complex64 stream at 200 kS/s -- exactly
what Module 1's tcp_server.cpp served. We don't run Module 1 (our mon_scan owns
the USRP), so this program IS that server: it subscribes to the CH2 monitoring
feed (mon_scan/mon_server PUB on 5202), decimates each dwell's 2 MS/s IQ to
200 kS/s, and serves it as complex64 on that band's port.

Only one band dwells at a time, so the active band's port streams real IQ and
the other ports stream zero-fill at 200 kS/s -- the same "7 of 8 are zero-fill"
pattern the bridge already expects (see iq_reader() in bridge_server.py).

  source ~/gnuradio-3.8/setup_env.sh
  ./ch2_iq_tcp.py                 # CH2 feed 5202 -> TCP 7001..7008 @ 200 kS/s

Run mon_scan publishing CH2 first:
  cd ~/radar2/guru_mon_scan && ./run_mon_scan.sh --channels 2 --pub
"""
import argparse
import asyncio
import json

import numpy as np
from scipy.signal import resample_poly
import zmq
import zmq.asyncio

SAMP_IN = 2_000_000.0     # CH2 capture rate (mon_scan)
SAMP_OUT = 200_000.0      # what bridge_server expects per port
DECIM = int(round(SAMP_IN / SAMP_OUT))   # 10

# band name (as mon_scan tags it in the header) -> bridge protocol port.
# Matches bridge_server.py BANDS: dmr 7001, nxdn 7002, p25 7003, tetra 7004,
# dstar 7006. 7005/7007/7008 have no CH2 band -> pure zero-fill.
BAND_PORT = {
    "DMR 446.100": 7001,
    "NXDN 451.0":  7002,
    "P25 450.0":   7003,
    "TETRA 420.0": 7004,
    "D-STAR 145.0": 7006,
}
ALL_PORTS = [7001, 7002, 7003, 7004, 7005, 7006, 7007, 7008]

TICK_S = 0.02                              # sender cadence
CHUNK_OUT = int(SAMP_OUT * TICK_S)         # 4000 samples / tick
ZERO_CHUNK = np.zeros(CHUNK_OUT, dtype=np.complex64).tobytes()
MAXBUF = int(SAMP_OUT * 2)                 # cap per-port backlog at 2 s


class Port:
    """One TCP listen port: broadcasts a complex64 200 kS/s stream to every
    connected client (bridge, and anything else that connects)."""
    def __init__(self, port):
        self.port = port
        self.writers = set()
        self.buf = bytearray()             # pending real IQ bytes (complex64)

    async def serve(self):
        srv = await asyncio.start_server(self._client, '127.0.0.1', self.port)
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

    def feed(self, iq_c64_bytes):
        self.buf += iq_c64_bytes
        if len(self.buf) > MAXBUF * 8:     # drop oldest if a client stalls
            del self.buf[:len(self.buf) - MAXBUF * 8]

    async def _pump(self):
        loop = asyncio.get_event_loop()
        nbytes = CHUNK_OUT * 8             # complex64 = 8 bytes
        next_t = loop.time()
        while True:
            next_t += TICK_S
            # STAY REAL-TIME: the upstream ZMQ feed can burst far faster than
            # 200 kS/s (startup backlog, HWM drain). If we buffered it all we'd
            # lag seconds behind and the bridge display would go stale. Drop old
            # backlog and keep only the most recent chunk so the console always
            # shows NOW, not a delayed replay.
            if len(self.buf) > nbytes * 2:
                del self.buf[:len(self.buf) - nbytes]
            if len(self.buf) >= nbytes:
                chunk = bytes(self.buf[:nbytes]); del self.buf[:nbytes]
            else:
                chunk = ZERO_CHUNK          # idle -> zero-fill, like Module 1
            dead = []
            for w in list(self.writers):
                try:
                    # if a client (the bridge) is backed up, skip this tick for
                    # it rather than queueing unbounded in the kernel -> the
                    # bridge never falls behind real-time.
                    tr = w.transport
                    if tr is not None and tr.get_write_buffer_size() > nbytes * 4:
                        continue
                    w.write(chunk)
                except Exception:
                    dead.append(w)
            for w in dead:
                self.writers.discard(w)
            await asyncio.sleep(max(0.0, next_t - loop.time()))


async def sub_loop(endpoint, ports):
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVHWM, 64)
    sub.connect(endpoint)
    print("[ch2_iq_tcp] CH2 %s -> TCP %s @ %.0f kS/s (decim %d)"
          % (endpoint, ",".join(map(str, BAND_PORT.values())), SAMP_OUT/1e3, DECIM),
          flush=True)
    n = 0
    while True:
        hdr_b, iq_b = await sub.recv_multipart()
        try:
            band = json.loads(hdr_b.decode()).get("band")
        except Exception:
            continue
        port = BAND_PORT.get(band)
        if port is None:
            continue
        x = np.frombuffer(iq_b, dtype=np.complex64)
        if x.size < DECIM:
            continue
        y = resample_poly(x, 1, DECIM).astype(np.complex64)   # 2 MS/s -> 200 kS/s
        ports[port].feed(y.tobytes())
        n += 1
        if n % 50 == 0:
            print("[ch2_iq_tcp] %s: %d blocks, last %d->%d samp"
                  % (band, n, x.size, y.size), flush=True)


async def main_async(endpoint):
    ports = {p: Port(p) for p in ALL_PORTS}
    tasks = [asyncio.create_task(p.serve()) for p in ports.values()]
    tasks.append(asyncio.create_task(sub_loop(endpoint, ports)))
    await asyncio.gather(*tasks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="tcp://127.0.0.1:5202",
                    help="CH2 monitoring feed (mon_scan/mon_server PUB)")
    a = ap.parse_args()
    try:
        asyncio.run(main_async(a.inp))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
