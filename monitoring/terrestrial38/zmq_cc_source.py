"""zmq_cc_source - GNU Radio 3.8 source that subscribes to a mon_scan channel feed.

mon_scan / mon_server publish each channel's IQ as ZeroMQ PUB multipart
[header_json, iq_bytes] (iq = complex64), one socket per channel (5201..5204).
This block SUBSCRIBES and outputs that IQ as a complex stream, so a GR 3.8
decode flowgraph (e.g. DSD / TETRA) can consume the monitoring CH2 feed
without the USRP — one program (mon_scan) owns the radio.

A background thread drains the socket into a ring; work() hands out what is
available and pads with zeros on underrun so the flowgraph never stalls.

    src = zmq_cc_source("tcp://127.0.0.1:5202")   # CH2 terrestrial
"""
import threading
import collections

import numpy as np
import zmq
from gnuradio import gr


class zmq_cc_source(gr.sync_block):
    def __init__(self, endpoint="tcp://127.0.0.1:5202", only_band=None):
        gr.sync_block.__init__(self, name="zmq_cc_source",
                               in_sig=None, out_sig=[np.complex64])
        self.endpoint = endpoint
        self.only_band = only_band          # optional: only pass a given band's IQ
        self._buf = collections.deque()
        self._have = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.cur_band = None
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.SUB)
        self._sock.setsockopt(zmq.SUBSCRIBE, b"")
        self._sock.setsockopt(zmq.RCVTIMEO, 300)
        self._sock.connect(endpoint)
        self._rx = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx.start()

    def _rx_loop(self):
        import json
        while not self._stop.is_set():
            try:
                hdr_b, iq_b = self._sock.recv_multipart()
            except zmq.Again:
                continue
            except Exception:
                break
            try:
                hdr = json.loads(hdr_b.decode())
            except Exception:
                hdr = {}
            self.cur_band = hdr.get("band")
            if self.only_band is not None and self.cur_band != self.only_band:
                continue                     # skip blocks from other bands
            iq = np.frombuffer(iq_b, dtype=np.complex64)
            with self._lock:
                self._buf.append(iq)
                self._have += len(iq)

    def stop(self):
        self._stop.set()
        try:
            self._sock.close(0)
        except Exception:
            pass
        return True

    def work(self, input_items, output_items):
        out = output_items[0]
        n = len(out)
        got = 0
        with self._lock:
            while got < n and self._buf:
                chunk = self._buf[0]
                take = min(len(chunk), n - got)
                out[got:got + take] = chunk[:take]
                got += take
                if take == len(chunk):
                    self._buf.popleft()
                else:
                    self._buf[0] = chunk[take:]
                self._have -= take
        if got < n:
            out[got:] = 0            # underrun: pad with zeros, keep running
        return n
