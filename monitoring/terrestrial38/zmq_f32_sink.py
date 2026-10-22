#!/usr/bin/env python3
"""zmq_f32_sink - GR 3.8 sink that PUBLISHES float32 audio over ZeroMQ.

The repo bridge's audio_tap_reader() subscribes to tcp://127.0.0.1:910x and does
`np.frombuffer(msg, dtype=np.float32)` on each message -- i.e. each ZMQ message
is a raw little-endian float32 buffer, no header. GR 3.8 has no gnuradio.zeromq
module, so this is a tiny pyzmq PUB sink that matches that exact wire format.

Use at the 48 kHz audio rate the taps expect:
    tap = zmq_f32_sink(9101)        # DMR
    tb.connect(audio_48k, tap)
"""
import numpy as np
import zmq
from gnuradio import gr


class zmq_f32_sink(gr.sync_block):
    def __init__(self, port, host="127.0.0.1", chunk=4096):
        gr.sync_block.__init__(self, name="zmq_f32_sink",
                               in_sig=[np.float32], out_sig=None)
        self.ctx = zmq.Context.instance()
        self.sock = self.ctx.socket(zmq.PUB)
        self.sock.setsockopt(zmq.SNDHWM, 64)
        self.sock.setsockopt(zmq.LINGER, 0)
        self.sock.bind("tcp://%s:%d" % (host, port))
        self.chunk = int(chunk)

    def work(self, input_items, output_items):
        x = input_items[0]
        # send in bounded chunks so each message stays small
        n = len(x)
        i = 0
        while i < n:
            seg = x[i:i + self.chunk]
            try:
                self.sock.send(np.ascontiguousarray(seg, dtype=np.float32).tobytes(),
                               flags=zmq.NOBLOCK)
            except zmq.Again:
                pass
            i += self.chunk
        return n
