#!/usr/bin/env python3
"""Continuous DMR diagnostic: logs carrier offset + decoded-audio level whenever
the DMR band is active. Run in background; key the radio whenever."""
import zmq, json, numpy as np, time, sys

FS = 2e6
s = zmq.Context.instance().socket(zmq.SUB)
s.setsockopt(zmq.SUBSCRIBE, b""); s.setsockopt(zmq.RCVHWM, 16)
s.connect("tcp://127.0.0.1:5202")
a = zmq.Context.instance().socket(zmq.SUB)
a.setsockopt(zmq.SUBSCRIBE, b""); a.setsockopt(zmq.RCVHWM, 16)
a.connect("tcp://127.0.0.1:9101")
time.sleep(0.5)
print("[dmr_monitor] watching DMR 446.100 — key the radio", flush=True)

buf = np.zeros(0, np.complex64)
last_log = 0.0
au_peak = -99.0
while True:
    # collect RF
    try:
        while True:
            hdr, iq = s.recv_multipart(flags=zmq.NOBLOCK)
            if json.loads(hdr).get("band") == "DMR 446.100":
                x = np.frombuffer(iq, np.complex64)
                buf = np.concatenate([buf, x])[-200000:]
    except zmq.Again:
        pass
    # collect decoded audio
    try:
        while True:
            au = a.recv(flags=zmq.NOBLOCK); y = np.frombuffer(au, np.float32)
            if y.size:
                r = 20*np.log10(np.sqrt(np.mean(y**2))+1e-9); au_peak = max(au_peak, r)
    except zmq.Again:
        pass

    now = time.time()
    if now - last_log >= 2.0 and buf.size >= 8192:
        p = 10*np.log10(np.mean(np.abs(buf)**2)+1e-12)
        if p > -55:   # signal present
            N = 8192; seg = buf[-N:]*np.hanning(N)
            sp = np.abs(np.fft.fftshift(np.fft.fft(seg)))**2
            fr = (np.arange(N)-N/2)*FS/N
            off = fr[int(sp.argmax())]
            clip = float(np.abs(buf).max())
            print("[dmr] RF=%.1f dBFS  carrier %+.1f kHz off-center  |x|max=%.2f  decoded-audio peak=%.1f dBFS  %s"
                  % (p, off/1e3, clip, au_peak, "VOICE" if au_peak > -38 else "(no voice decoded)"), flush=True)
        else:
            print("[dmr] idle (RF=%.1f dBFS)" % p, flush=True)
        au_peak = -99.0
        last_log = now
    time.sleep(0.05)
