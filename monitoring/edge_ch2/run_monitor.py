#!/usr/bin/env python3
"""run_monitor.py - supervisor/watchdog for the whole monitoring pipeline.

Launches every component in the right order and KEEPS THEM ALIVE: if one dies or
stalls (stops making progress), the watchdog restarts just that one. mon_server
owns the X310, so before restarting it the watchdog waits until the radio is
released and re-enumerates. The result is a monitor that runs for hours without
getting stuck -- any single wedge self-heals.

Pipeline (one per channel + the CH2 decode chain):

  X310 --mon_server(GR3.8)--> ZMQ 5201-5204
     5201/3/4 --mon_ws_bridge--> ws 8780 --> 5-panel UI (http 8099)
     5202 (CH2) --ch2_header_router--> TCP 7001-7004 --allinone.py(decoder)-->
        audio taps 9101-4 + events --> backupv1 bridge (ws 8787) + console (http 8788)
        --terr_audio_play--> live voice

  python3 run_monitor.py                 # run until Ctrl-C, auto-restart on stall
  python3 run_monitor.py --gain 25 --ch2-gain 10 --samp-rate 1e6

Health per component: process alive, its port listening (servers), and its log
file still growing (producers). A component that fails its check for longer than
its stall timeout is killed and relaunched, with a grace period after each start.
"""
import argparse
import os
import signal
import socket
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "radar2")
MON_DIR = os.path.join(ROOT, "guru_mon_scan")
EDGE = os.path.join(ROOT, "edge_ch2")
REPO = os.path.join(ROOT, "backupv1", "secuecom-version1")
GUI = os.path.join(REPO, "gui")
LOGDIR = "/tmp"

GR38_ENV = os.path.join(HOME, "gnuradio-3.8", "setup_env.sh")


def sys_env():
    """System GR 3.10 / clean env: strip the leaking GR-3.8 paths."""
    e = dict(os.environ)
    e.pop("PYTHONPATH", None)
    e["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    e["LD_LIBRARY_PATH"] = "/usr/local/lib"
    return e


def port_open(port, host="127.0.0.1"):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def log_fresh(path, max_age):
    try:
        return (time.time() - os.path.getmtime(path)) <= max_age
    except Exception:
        return False


def x310_free(addr_serial="31082D8"):
    """True when the X310 enumerates (radio released and reachable)."""
    env = dict(os.environ)
    env["PATH"] = os.path.join(HOME, "uhd-3.15", "bin") + ":/usr/bin:/bin"
    env["LD_LIBRARY_PATH"] = os.path.join(HOME, "uhd-3.15", "lib")
    env.pop("PYTHONPATH", None)
    try:
        out = subprocess.run(
            [os.path.join(HOME, "uhd-3.15", "bin", "uhd_find_devices"),
             "--args", "addr=192.168.10.2"],
            capture_output=True, text=True, timeout=12, env=env).stdout
        return addr_serial in out
    except Exception:
        return False


class Comp:
    """One supervised component."""
    def __init__(self, name, cmd, env, cwd, log, shell=False,
                 port=None, log_max_age=None, grace=4.0, stall=20.0,
                 needs_x310=False, after=()):
        self.name = name
        self.after = tuple(after)      # restart me whenever one of these restarts (I hold a client link to it)
        self.cmd = cmd                 # list (shell=False) or str (shell=True via bash -c)
        self.env = env
        self.cwd = cwd
        self.log = log
        self.shell = shell
        self.port = port
        self.log_max_age = log_max_age
        self.grace = grace             # seconds after start before health applies
        self.stall = stall             # seconds unhealthy before restart
        self.needs_x310 = needs_x310
        self.proc = None
        self.started_at = 0.0
        self.bad_since = None
        self.restarts = 0

    def start(self):
        if self.needs_x310:
            # wait for the radio to be free (previous instance released it)
            for _ in range(20):
                if x310_free():
                    break
                time.sleep(1.0)
        f = open(self.log, "w")
        if self.shell:
            self.proc = subprocess.Popen(["bash", "-c", self.cmd], cwd=self.cwd,
                                         env=self.env, stdout=f, stderr=subprocess.STDOUT,
                                         preexec_fn=os.setsid)
        else:
            self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, env=self.env,
                                         stdout=f, stderr=subprocess.STDOUT,
                                         preexec_fn=os.setsid)
        self.started_at = time.time()
        self.bad_since = None
        print("[watchdog] started %-16s pid=%d (restart #%d)"
              % (self.name, self.proc.pid, self.restarts), flush=True)

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def healthy(self):
        if not self.alive():
            return False
        if time.time() - self.started_at < self.grace:
            return True                # still warming up
        if self.port is not None and not port_open(self.port):
            return False
        if self.log_max_age is not None and not log_fresh(self.log, self.log_max_age):
            return False
        return True

    def kill(self):
        if self.proc is None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            pass


def build(args):
    senv = sys_env()
    comps = []

    # 1) mon_server on the X310 (GR 3.8) -> PUB 5201-5204. Heartbeat every 5 s,
    #    so a >15 s gap in its log means a scan thread wedged -> restart.
    ch2g = "" if args.ch2_gain is None else (" --ch2-gain %g" % args.ch2_gain)
    mon_cmd = ("source %s >/dev/null 2>&1; export MON_DBG_TIMING=0; "
               "exec python3 -u mon_server.py --addr 'addr=192.168.10.2' "
               "--samp-rate %g --gain %g%s"
               % (GR38_ENV, args.samp_rate, args.gain, ch2g))
    comps.append(Comp("mon_server", mon_cmd, dict(os.environ), MON_DIR,
                      "%s/mon_server.log" % LOGDIR, shell=True,
                      log_max_age=15.0, grace=20.0, stall=20.0, needs_x310=True))

    # 2) mon -> UI websocket bridge (ws 8780)
    comps.append(Comp("mon_ws_bridge", ["python3", "-u", "mon_ws_bridge.py",
                      "--port", "8780"], senv, EDGE,
                      "%s/mon_ws_bridge.log" % LOGDIR, port=8780, grace=4.0))

    # 3) CH2 header router: 5202 -> TCP 7001-7004. Logs "routed blocks" steadily.
    comps.append(Comp("ch2_router", ["python3", "-u", "ch2_header_router.py",
                      "--in", "tcp://127.0.0.1:5202", "--base-port", "7001"],
                      senv, EDGE, "%s/ch2_router.log" % LOGDIR,
                      port=7001, log_max_age=20.0, grace=5.0))

    # 4) backupv1 console bridge (ws 8787), external mode (no Module 1)
    comps.append(Comp("backupv1_bridge", ["python3", "-u",
                      os.path.join(EDGE, "backupv1_bridge_ext.py")],
                      senv, GUI, "%s/backupv1_bridge.log" % LOGDIR,
                      port=8787, grace=5.0))

    # 5) web servers for the 5-panel UI (8099) and the console (8788)
    comps.append(Comp("ui_http", ["python3", "-m", "http.server", "8099",
                      "--bind", "127.0.0.1"], senv, MON_DIR,
                      "%s/ui_http.log" % LOGDIR, port=8099, grace=3.0))
    #    console = our X310 copy of the terrestrial console (edge_ch2/ch2_console; backupv1 stays unchanged)
    comps.append(Comp("console_http", ["python3", "-m", "http.server", "8788",
                      "--bind", "127.0.0.1"], senv, os.path.join(EDGE, "ch2_console"),
                      "%s/console_http.log" % LOGDIR, port=8788, grace=3.0))

    # 6) the decoder (allinone.py) - connects to the router's 7001-7004 as a client
    #    Its network.tcp_source blocks connect ONCE and never reconnect: after a router restart the
    #    decoder kept running on dead sockets with no input (seen 2026-10-22) -> restart it with the router.
    comps.append(Comp("allinone", ["python3", "-u", "allinone.py"],
                      senv, REPO, "%s/allinone.log" % LOGDIR, grace=10.0, stall=25.0,
                      after=("ch2_router",)))

    # 6b) Air & Maritime (AIS / ADS-B) = the old repo terrestrial_src's chain, unchanged, on CH2:
    #     5202 -> ch2_airmar_router (TCP 7009 AIS 250 kS/s @162.000, 7010 ADS-B) -> airmaritime_decoder_live
    #     (ZMQ 9201/9202) -> airmaritime_bridge (ws 8887) -> console (http 8789). Terrestrial pieces untouched.
    comps.append(Comp("airmar_router", ["python3", "-u", "ch2_airmar_router.py", "--in", "tcp://127.0.0.1:5202"],
                      senv, EDGE, "%s/airmar_router.log" % LOGDIR, port=7009, grace=5.0))
    comps.append(Comp("airmar_decoder", ["python3", "-u", "airmar_decoder_ext.py"],
                      senv, EDGE, "%s/airmar_decoder.log" % LOGDIR, grace=10.0, stall=25.0,
                      after=("airmar_router",)))
    comps.append(Comp("airmar_bridge", ["python3", "-u", "airmar_bridge_ext.py"],
                      senv, EDGE, "%s/airmar_bridge.log" % LOGDIR, port=8887, grace=5.0))
    comps.append(Comp("airmar_http", ["python3", "-m", "http.server", "8789", "--bind", "127.0.0.1"],
                      senv, os.path.join(EDGE, "airmar_console"), "%s/airmar_http.log" % LOGDIR,
                      port=8789, grace=3.0))

    # 7) live decoded voice to the PC speakers
    comps.append(Comp("terr_audio", ["python3", "-u", "terr_audio_play.py",
                      "--squelch", str(args.squelch), "--vol", str(args.vol)],
                      senv, EDGE, "%s/terr_audio.log" % LOGDIR, grace=4.0))
    return comps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gain", type=float, default=25.0,
                    help="RX gain for CH1/CH3/CH4 (weak drone/radar/cellular)")
    ap.add_argument("--ch2-gain", type=float, default=10.0,
                    help="lower RX gain for CH2 terrestrial (strong close radios)")
    ap.add_argument("--samp-rate", type=float, default=1e6)
    ap.add_argument("--squelch", type=float, default=-45.0)
    ap.add_argument("--vol", type=float, default=1.0)
    args = ap.parse_args()

    comps = build(args)
    stop = {"v": False}

    def on_sig(*_):
        stop["v"] = True
    signal.signal(signal.SIGINT, on_sig)
    signal.signal(signal.SIGTERM, on_sig)

    print("[watchdog] launching pipeline (gain=%g ch2-gain=%g samp=%g)"
          % (args.gain, args.ch2_gain, args.samp_rate), flush=True)
    for c in comps:
        c.start()
        # small stagger so dependents find their upstream
        time.sleep(3.0 if c.name == "mon_server" else 1.0)

    print("[watchdog] all up. Open http://127.0.0.1:8099/securecom_ui.html", flush=True)

    try:
        while not stop["v"]:
            time.sleep(2.0)
            now = time.time()
            for c in comps:
                if c.healthy():
                    c.bad_since = None
                    continue
                if c.bad_since is None:
                    c.bad_since = now
                    print("[watchdog] %s unhealthy (alive=%s port=%s) - watching"
                          % (c.name, c.alive(),
                             port_open(c.port) if c.port else "n/a"), flush=True)
                elif now - c.bad_since >= c.stall:
                    print("[watchdog] %s stalled %.0fs -> RESTART"
                          % (c.name, now - c.bad_since), flush=True)
                    c.kill()
                    c.restarts += 1
                    c.start()
                    for d in comps:
                        if c.name in d.after:
                            time.sleep(2.0)            # let the upstream open its ports first
                            print("[watchdog] %s restarted -> restart %s (client of it)"
                                  % (c.name, d.name), flush=True)
                            d.kill()
                            d.restarts += 1
                            d.start()
    finally:
        print("[watchdog] stopping all components", flush=True)
        for c in comps:
            c.kill()
        print("[watchdog] stopped.", flush=True)


if __name__ == "__main__":
    main()
