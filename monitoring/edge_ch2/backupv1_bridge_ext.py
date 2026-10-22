#!/usr/bin/env python3
"""backupv1_bridge_ext - run the backupv1 console bridge WITHOUT Module 1.

In the new per-channel architecture the CH2 scheduler + header-router replace
Module 1: the router serves TCP 7001-7004 from the single CH2 stream. So the
bridge must NOT launch its own securecom_module1 (which would try to own a
radio). This wrapper imports the backupv1 bridge_server unchanged and patches
only start_module1 to external-feed mode: no subprocess, just mark running and
spawn the iq_readers, which connect to the router's 7001-7004 as clients (for the
console's spectrum). start_module2 (allinone.py + audio taps) is left as-is; it
also connects to 7001-7004, now served by the router.

  source ~/gnuradio-3.8/setup_env.sh    # NO -- use SYSTEM GR 3.10 for allinone.py
Run under the SYSTEM python (GR 3.10, where dsd is installed), same as the repo:
  python3 backupv1_bridge_ext.py
Then from the console: Start hardware (connects to router) + Start decoder.
"""
import asyncio
import importlib.util
import os
import time

REPO_BRIDGE = os.path.expanduser(
    "~/radar2/backupv1/secuecom-version1/gui/bridge_server.py")

spec = importlib.util.spec_from_file_location("bv1_bridge", REPO_BRIDGE)
bs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bs)


async def start_module1_ext():
    if bs.STATE["running"]:
        return
    bs.STATE["running"] = True
    bs.STATE["pid"] = None
    await bs.broadcast({"type": "log", "band": None, "t": time.time(),
                        "text": "[BRIDGE] EXTERNAL feed — IQ from ch2_header_router "
                                "(7001-7004), no Module 1 launched"})
    await bs.broadcast({"type": "status", **bs.STATE})
    await asyncio.sleep(0.3)
    for b in bs.BANDS:
        bs.spawn(bs.iq_reader(b))


bs.start_module1 = start_module1_ext


if __name__ == "__main__":
    main = getattr(bs, "main", None)
    if main is None:
        raise SystemExit("backupv1 bridge_server.py has no main()")
    import inspect
    if inspect.iscoroutinefunction(main):
        asyncio.run(main())
    else:
        main()
