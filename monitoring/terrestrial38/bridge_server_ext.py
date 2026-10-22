#!/usr/bin/env python3
"""bridge_server_ext - run the repo's bridge_server in EXTERNAL-FEED mode.

The repo bridge (terrestrial_src/gui/bridge_server.py) normally launches its own
Module 1 (securecom_module1, which opens the B210) and Module 2 (the decoder
flowgraph). In our system mon_scan owns the USRP and our ported decoders do the
decoding, so we must NOT let the bridge touch the radio. This wrapper imports the
repo bridge unchanged and monkey-patches just its two launchers:

  * start_module1 -> no subprocess; mark running and spawn the IQ readers, which
    connect to our ch2_iq_tcp.py TCP servers on 7001-7008.
  * start_module2 -> no subprocess; spawn the audio-tap readers for the protocols
    our decoders publish (dmr/nxdn/p25/tetra/dstar) plus the tetra event reader.

Everything else in the bridge -- the WebSocket server on 8787, spectrum /
waterfall / time framing, active-band logic, DF log, recordings -- runs exactly
as shipped, so securecom_gui.html needs no change. The repo file is not edited.

  source ~/gnuradio-3.8/setup_env.sh
  ./bridge_server_ext.py
Then feed it:  ch2_iq_tcp.py  (IQ) + decode_*.py --audio-tap (audio).
"""
import asyncio
import importlib.util
import os
import time

REPO_BRIDGE = os.path.expanduser(
    "~/radar2/terrestrial_src/gui/bridge_server.py")

# import the repo bridge as a module without needing it on sys.path
spec = importlib.util.spec_from_file_location("bridge_server", REPO_BRIDGE)
bs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bs)

# protocols our decoders actually feed (ZMQ audio taps 9101-9104, 9107)
OUR_TAPS = ["dmr", "nxdn", "p25", "tetra", "dstar"]


async def start_module1_ext():
    """Same as the real start_module1(), minus the subprocess: just mark the
    stack running and connect the IQ readers to our external TCP servers."""
    if bs.STATE["running"]:
        return
    bs.STATE["running"] = True
    bs.STATE["pid"] = None
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] EXTERNAL feed mode — IQ from ch2_iq_tcp "
                                "(7001-7008), no Module 1 launched"})
    await bs.broadcast({"type": "status", **bs.STATE})
    await asyncio.sleep(0.3)
    for b in bs.BANDS:
        bs.spawn(bs.iq_reader(b))


async def start_module2_ext(combined=None):
    """Same as the real start_module2(), minus the subprocess: just attach the
    audio-tap readers for the protocols our decoders publish."""
    if bs.proc2 is not None:
        return
    # a sentinel so audio_tap_reader()'s `while proc2 is not None` loop runs
    bs.proc2 = object()
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] EXTERNAL decoders — audio taps "
                                + ", ".join(OUR_TAPS) + " (9101-9107)"})
    await bs.broadcast({"type": "decoder_status", "running": True,
                        "combined": False})
    for k in OUR_TAPS:
        bs.spawn(bs.audio_tap_reader(k))
    bs.spawn(bs.tetra_event_reader())


# swap the launchers before anything calls them
bs.start_module1 = start_module1_ext
bs.start_module2 = start_module2_ext


if __name__ == "__main__":
    # bridge_server.main() is a coroutine; run it like the repo's __main__ does.
    main = getattr(bs, "main", None)
    if main is None:
        raise SystemExit("repo bridge_server.py has no main(); check the file")
    asyncio.run(main())
