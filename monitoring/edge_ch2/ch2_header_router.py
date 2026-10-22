#!/usr/bin/env python3
"""ch2_header_router - Edge-side CH2 router: one stream in, 4 protocols out.

Architecture (user's design):
  RTOS scheduler PUBlishes CH2 as ONE stream (IQ + header, see ch2_header.py).
  Edge Computing SUBscribes to it, and THIS router reads each block's `proto`
  header and drops the IQ into the respective band's decoder -- its "respected
  place". For the working 4-protocol decoder (backupv1 allinone.py) those places
  are its 4 `network.tcp_source` blocks on TCP 7001-7004:

      dmr 7001 · nxdn 7002 · p25 7003 · tetra 7004

  So this replaces the repo's Module 1 (which served 4 physical per-protocol
  ports) with: 1 CH2 subscription + route-by-header -> the same 4 ports. Only the
  active band carries real IQ; the other 3 ports stream zero-fill at the decoder
  rate, exactly like Module 1 did, so the decode chains keep running.

  CH2 feed (ZMQ SUB)  --[header,iq]-->  router  --TCP 7001-7004-->  allinone.py

    python3 ch2_header_router.py --in tcp://127.0.0.1:5202
Then run the repo decoder (its tcp_sources connect to 7001-7004 as clients).
Rates: the decoder wants 200 kS/s/port; if the CH2 header says a higher samp_rate
(e.g. 2 MS/s from mon_scan) the router decimates by the integer ratio.
"""
import argparse
import asyncio
import json

import numpy as np
from scipy.signal import lfilter, firwin
import zmq
import zmq.asyncio


class StatefulDecimator:
    """Continuous polyphase decimator that carries the FIR state AND the sample
    phase across blocks, so decimating a stream in small chunks gives the same
    result as decimating it whole -- no per-block filter transients. Those
    transients corrupt symbol timing and stop DSD/TETRA from ever syncing, which
    is exactly the 'detects but won't decode' symptom when the feed sends many
    small blocks."""
    def __init__(self, dec, ntaps=None):
        self.dec = int(dec)
        n = ntaps if ntaps else 20 * self.dec + 1
        self.taps = firwin(n, 1.0 / self.dec).astype(np.float64)
        self.zi = np.zeros(len(self.taps) - 1, dtype=np.complex128)
        self.phase = 0

    def reset(self):
        self.zi[:] = 0
        self.phase = 0

    def __call__(self, x):
        y, self.zi = lfilter(self.taps, 1.0, x.astype(np.complex128), zi=self.zi)
        idx = np.arange(self.phase, len(y), self.dec)
        self.phase = (idx[-1] + self.dec - len(y)) if len(idx) else (self.phase - len(y))
        return y[idx].astype(np.complex64)

from ch2_header import decode_header, proto_for_band, KNOWN_PROTOS

OUT_RATE = 200000.0                       # the repo decoder's per-port rate
PROTO_ORDER = ("dmr", "nxdn", "p25", "tetra")   # port = base + index

def proto_ports(base=7001):
    return {p: base + i for i, p in enumerate(PROTO_ORDER)}

TICK_S = 0.02                             # sender cadence
CHUNK_OUT = int(OUT_RATE * TICK_S)        # 4000 samples / tick
ZERO_CHUNK = np.zeros(CHUNK_OUT, dtype=np.complex64).tobytes()


class Port:
    """One TCP listen port for a protocol: streams complex64 @ OUT_RATE to every
    connected decoder, real IQ when its band is active else zero-fill."""
    def __init__(self, proto, port):
        self.proto = proto
        self.port = port
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

    def feed(self, iq_c64_bytes):
        self.buf += iq_c64_bytes

    def flush(self):
        """Drop buffered IQ -- called on a new dwell so stale samples from the
        previous visit don't bleed into the new one."""
        self.buf.clear()

    async def _pump(self):
        loop = asyncio.get_event_loop()
        nbytes = CHUNK_OUT * 8            # complex64 = 8 bytes
        next_t = loop.time()
        while True:
            next_t += TICK_S
            # stay real-time: drop backlog, keep only the newest chunk
            if len(self.buf) > nbytes * 2:
                del self.buf[:len(self.buf) - nbytes]
            if len(self.buf) >= nbytes:
                chunk = bytes(self.buf[:nbytes]); del self.buf[:nbytes]
            else:
                chunk = ZERO_CHUNK
            for w in list(self.writers):
                try:
                    tr = w.transport
                    if tr is not None and tr.get_write_buffer_size() > nbytes * 4:
                        continue
                    w.write(chunk)
                except Exception:
                    self.writers.discard(w)
            await asyncio.sleep(max(0.0, next_t - loop.time()))


async def sub_loop(endpoint, ports, stats):
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVHWM, 64)
    sub.connect(endpoint)
    print("[router] CH2 %s -> %s @ %.0f kS/s"
          % (endpoint, ", ".join("%s:%d" % (p, ports[p].port) for p in PROTO_ORDER),
             OUT_RATE / 1e3), flush=True)
    last_dwell = {}
    decs = {}          # per-proto stateful decimators (continuous across blocks)
    while True:
        hdr_b, iq_b = await sub.recv_multipart()
        proto, samp_rate, dwell_id, dwell_start, band = _read_header(hdr_b)
        if proto not in ports:
            continue
        port = ports[proto]
        dec = int(round(samp_rate / OUT_RATE)) if samp_rate > OUT_RATE else 1
        # new dwell on this proto -> flush stale IQ + reset the decimator so the
        # new band starts with clean filter state
        if dwell_start or last_dwell.get(proto) != dwell_id:
            port.flush()
            if proto in decs:
                decs[proto].reset()
            last_dwell[proto] = dwell_id
        x = np.frombuffer(iq_b, dtype=np.complex64)
        if x.size == 0:
            continue
        # decimate to the decoder rate (CONTINUOUS, state carried across blocks)
        if dec > 1:
            if proto not in decs or decs[proto].dec != dec:
                decs[proto] = StatefulDecimator(dec)
            x = decs[proto](x)
            if x.size == 0:
                continue
        port.feed(x.tobytes())
        stats[proto] = stats.get(proto, 0) + 1
        if sum(stats.values()) % 100 == 0:
            print("[router] routed blocks: " +
                  " ".join("%s=%d" % (p, stats.get(p, 0)) for p in KNOWN_PROTOS),
                  flush=True)


def _read_header(hdr_b):
    """Return (proto, samp_rate, dwell_id, dwell_start, band). Accepts the new
    ch2_header format; falls back to the old mon header (band only) so the router
    also works against the current mon_scan feed during migration."""
    try:
        h = decode_header(hdr_b)
        return (h["proto"], float(h.get("samp_rate", OUT_RATE)),
                int(h.get("dwell_id", 0)), bool(h.get("dwell_start", False)),
                h.get("band", ""))
    except ValueError:
        pass
    # legacy mon header: {ch,band,freq,look,frame,host_time}
    try:
        h = json.loads(hdr_b.decode())
        band = h.get("band", "")
        return (proto_for_band(band), float(h.get("samp_rate", 2000000.0)),
                int(h.get("frame", 0)), False, band)
    except Exception:
        return ("unknown", OUT_RATE, 0, False, "")


async def main_async(endpoint, base_port):
    ports = {p: Port(p, pt) for p, pt in proto_ports(base_port).items()}
    stats = {}
    tasks = [asyncio.create_task(p.serve()) for p in ports.values()]
    tasks.append(asyncio.create_task(sub_loop(endpoint, ports, stats)))
    await asyncio.gather(*tasks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="tcp://127.0.0.1:5202",
                    help="CH2 stream (RTOS scheduler PUB)")
    ap.add_argument("--base-port", type=int, default=7001,
                    help="first protocol port (dmr=base, nxdn=base+1, p25=+2, tetra=+3)")
    a = ap.parse_args()
    try:
        asyncio.run(main_async(a.inp, a.base_port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
