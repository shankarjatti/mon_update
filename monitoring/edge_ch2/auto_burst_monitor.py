#!/usr/bin/env python3
"""auto_burst_monitor - watch a protocol port and report every keyed burst.

Connects to a router protocol port (default 7001 DMR, 200 kHz complex64),
detects transmissions automatically (envelope rises), and for each burst logs:
level, clipping, carrier offset, occupied bandwidth -- so we can judge signal
quality WITHOUT having to time the operator's key-up. Saves the strongest burst
to a .cf32 for offline decode.

  python3 auto_burst_monitor.py                 # 7001 (DMR), run until Ctrl-C
"""
import argparse, socket, time, numpy as np

def analyze(x, fs=200000.0):
    a = np.abs(x)
    clip = float((a > 0.99).mean() * 100)
    rms = 20*np.log10(np.sqrt(np.mean(a*a))+1e-12)
    N = 8192
    if x.size < N: return None
    acc = np.zeros(N)
    for i in range(0, len(x)-N, N):
        acc += np.abs(np.fft.fftshift(np.fft.fft(x[i:i+N]*np.hanning(N))))**2
    fr = (np.arange(N)-N/2)*fs/N; c = N//2; acc[c-3:c+4] = np.median(acc)
    db = 10*np.log10(acc/acc.max()+1e-12); off = fr[int(acc.argmax())]
    mask = db > db.max()-6; occ = (fr[mask].max()-fr[mask].min())/1e3 if mask.sum()>1 else 0
    return dict(max=float(a.max()), rms=rms, clip=clip, off_khz=off/1e3, occ_khz=occ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7001)
    ap.add_argument("--save", default="/tmp/claude-1000/-home-shankar-radar2/94e56057-58b6-4060-8e7f-a9d11ae69ddc/scratchpad/burst_best.cf32")
    a = ap.parse_args()
    s = socket.create_connection(("127.0.0.1", a.port)); s.settimeout(0.5)
    print("[burst] watching port %d — key the radio anytime. Ctrl-C to stop." % a.port, flush=True)
    buf = np.zeros(0, np.complex64)
    in_burst = False; cur = []; best_rms = -999; nb = 0
    noise = -60.0
    last = b""
    while True:
        try: d = s.recv(262144)
        except socket.timeout: d = b""
        if d:
            last += d
            n = len(last)//8*8
            if n:
                x = np.frombuffer(last[:n], np.complex64); last = last[n:]
                p = 10*np.log10(np.mean(np.abs(x)**2)+1e-12)
                active = p > noise + 10
                if active:
                    cur.append(x); in_burst = True
                elif in_burst:
                    # burst ended
                    seg = np.concatenate(cur); cur = []; in_burst = False
                    if seg.size > 20000:
                        r = analyze(seg); nb += 1
                        if r:
                            print("[burst #%d] %.2fs rms=%.1f dBFS |x|max=%.3f clip=%.1f%% carrier=%+.1fkHz occ=%.1fkHz  %s"
                                  % (nb, seg.size/200000, r['rms'], r['max'], r['clip'], r['off_khz'], r['occ_khz'],
                                     "CLIP!" if r['clip']>1 else ("DMR-wide" if 4<r['occ_khz']<20 else "narrow/odd")), flush=True)
                            if r['rms'] > best_rms:
                                best_rms = r['rms']; seg.astype(np.complex64).tofile(a.save)
                                print("   saved as strongest -> %s" % a.save, flush=True)
                    else:
                        noise = 0.9*noise + 0.1*p


if __name__ == "__main__":
    main()
