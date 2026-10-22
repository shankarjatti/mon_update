"""mon_pub - per-channel monitoring tap: stream tags (A4) + ZeroMQ publish (A5).

One block per channel, inserted right after the USRP source. It passes samples
through unchanged (so the graphs/probe downstream still work), and:

  A4  adds a GNU Radio stream tag "look" (a pmt dict: ch, band, freq, look,
      frame, host_time) on the first sample after each retune, so any in-flowgraph
      consumer (e.g. a file_meta_sink) knows which band/time each block is.
  A5  publishes the samples on a ZeroMQ PUB socket as multipart messages
      [header_json, iq_bytes] (iq = raw complex64), one socket per channel. Edge
      modules SUBSCRIBE (see mon_sub_example.py). GR's zeromq module is not built
      in this env, so pyzmq is used directly.

The scan controller calls set_look(name, freq, look, frame) at each retune.
"""
import json
import threading
import time

import numpy as np
import pmt
import zmq
from gnuradio import gr


class mon_pub(gr.sync_block):
    def __init__(self, ch, endpoint, publish=True, samp_rate=0.0):
        gr.sync_block.__init__(self, name="mon_pub_ch%d" % ch,
                               in_sig=[np.complex64], out_sig=[np.complex64])
        self.ch = ch
        self.publish = publish
        self.samp_rate = float(samp_rate)   # IQ rate of the payload, in every header (router + UI need it)
        self._lock = threading.Lock()
        self._look = {"ch": ch, "band": "", "freq": 0.0, "look": 0,
                      "frame": 0, "host_time": time.time(),
                      "samp_rate": self.samp_rate}
        self._pending_tag = True
        # work() in chunks of 2048 samples (2 ms at 1 MS/s) instead of the 364-sample network packets:
        # ~7x fewer Python calls and ZeroMQ messages per channel (measured: 364-sample blocks pushed the
        # scanner to 156 % CPU, load 11 on 12 cores, UHD overflows). Look tags land on these chunk
        # boundaries, so the detector settle time covers +2 ms (see mon_server SETTLE_S).
        self.set_output_multiple(2048)
        if self.publish:
            self._ctx = zmq.Context.instance()
            self._sock = self._ctx.socket(zmq.PUB)
            self._sock.setsockopt(zmq.SNDHWM, 16)      # drop if a subscriber is slow
            self._sock.setsockopt(zmq.LINGER, 0)
            self._sock.bind(endpoint)
            self.endpoint = endpoint
        else:
            self._sock = None
            self.endpoint = None

    def set_look(self, name, freq, look, frame):
        """Called by the scan controller at each retune."""
        with self._lock:
            self._look = {"ch": self.ch, "band": str(name), "freq": float(freq),
                          "look": int(look), "frame": int(frame),
                          "host_time": time.time(),
                          "samp_rate": self.samp_rate}
            self._pending_tag = True

    def current_host_time(self):
        """host_time of the look set last (the key look_power uses for that look)."""
        with self._lock:
            return self._look["host_time"]

    def _tag_dict(self, d):
        t = pmt.make_dict()
        t = pmt.dict_add(t, pmt.intern("ch"), pmt.from_long(d["ch"]))
        t = pmt.dict_add(t, pmt.intern("band"), pmt.intern(d["band"]))
        t = pmt.dict_add(t, pmt.intern("freq"), pmt.from_double(d["freq"]))
        t = pmt.dict_add(t, pmt.intern("look"), pmt.from_long(d["look"]))
        t = pmt.dict_add(t, pmt.intern("frame"), pmt.from_long(d["frame"]))
        t = pmt.dict_add(t, pmt.intern("host_time"), pmt.from_double(d["host_time"]))
        return t

    def work(self, input_items, output_items):
        inp = input_items[0]
        out = output_items[0]
        n = len(out)
        out[:n] = inp[:n]
        with self._lock:
            look = dict(self._look)
            tag_now = self._pending_tag
            self._pending_tag = False
        if tag_now:
            self.add_item_tag(0, self.nitems_written(0), pmt.intern("look"),
                              self._tag_dict(look))
        if self.publish and self._sock is not None:
            hdr = dict(look)
            hdr["n"] = n
            try:
                self._sock.send_multipart(
                    [json.dumps(hdr).encode(), inp[:n].tobytes()],
                    flags=zmq.NOBLOCK)
            except zmq.Again:
                pass          # no subscriber ready / slow -> drop this block
        return n

    def close(self):
        if self._sock is not None:
            self._sock.close(0)
