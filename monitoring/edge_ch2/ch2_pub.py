#!/usr/bin/env python3
"""ch2_pub - the CH2 publish block (RTOS scheduler side).

A GR sink block that takes the CH2 IQ stream and PUBlishes it as ONE ZeroMQ
stream of [header, iq] messages using the shared ch2_header format. The scheduler
calls set_band(...) at each retune; this block stamps every outgoing block with
the current band's header, sets dwell_start on the first block of each dwell, and
carries a monotonic seq + dwell_id so the edge router/decoder can detect drops and
reset state at dwell boundaries.

Pairs with ch2_header_router.py on the edge side.
"""
import threading

import numpy as np
import zmq
from gnuradio import gr

from ch2_header import make_header, encode_header


class ch2_pub(gr.sync_block):
    def __init__(self, endpoint, samp_rate, chunk=4096):
        gr.sync_block.__init__(self, name="ch2_pub",
                               in_sig=[np.complex64], out_sig=None)
        self.samp_rate = float(samp_rate)
        self.chunk = int(chunk)
        self.ctx = zmq.Context.instance()
        self.sock = self.ctx.socket(zmq.PUB)
        self.sock.setsockopt(zmq.SNDHWM, 64)
        self.sock.setsockopt(zmq.LINGER, 0)
        self.sock.bind(endpoint)
        self._lk = threading.Lock()
        self._band = ""
        self._center = 0.0
        self._target = 0.0
        self._dwell_id = 0
        self._seq = 0
        self._dwell_start_pending = False

    def set_band(self, band, center_hz, target_hz=None, new_dwell=True):
        """Called by the scheduler at each retune. new_dwell=True marks a fresh
        dwell so the next published block carries dwell_start=True."""
        with self._lk:
            self._band = str(band)
            self._center = float(center_hz)
            self._target = float(center_hz if target_hz is None else target_hz)
            if new_dwell:
                self._dwell_id += 1
                self._dwell_start_pending = True

    def work(self, input_items, output_items):
        x = input_items[0]
        n = len(x)
        i = 0
        while i < n:
            seg = np.ascontiguousarray(x[i:i + self.chunk], dtype=np.complex64)
            with self._lk:
                ds = self._dwell_start_pending
                self._dwell_start_pending = False
                hdr = make_header(self._band, self._center, self.samp_rate,
                                  len(seg), self._seq, self._dwell_id,
                                  dwell_start=ds, target_hz=self._target)
                self._seq += 1
            try:
                self.sock.send_multipart([encode_header(hdr), seg.tobytes()],
                                         flags=zmq.NOBLOCK)
            except zmq.Again:
                pass
            i += self.chunk
        return n
