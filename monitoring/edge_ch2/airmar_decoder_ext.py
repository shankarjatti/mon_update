#!/usr/bin/env python3
"""airmar_decoder_ext - run the old repo's air/maritime decoder (terrestrial_src/airmaritime_decoder_live.py)
UNCHANGED on the X310 CH2 feed.

The repo file reads AIS on TCP 7009 (250 kS/s, 162.000 MHz at 0 Hz) and ADS-B on TCP 7010, and publishes
decoded AIS NMEA on ZMQ 9201 and ADS-B on 9202. ch2_airmar_router.py serves 7009 / 7010 from CH2. The only
setting that differs on this hardware is the rate actually arriving on 7010 (the repo's own file says to set
ADSB_SOURCE_RATE_HZ to what the port really delivers): CH2 gives 200 kS/s, not the B210's 2 MS/s. The repo's
resampler then brings it to the 2 MS/s its adsb.* blocks are built around.

Run under the SYSTEM python (GR 3.10, gr-ais / gr-adsb), from run_monitor.py.
"""
import importlib.util
import os
import sys

REPO = os.path.expanduser("~/radar2/terrestrial_src")
ADSB_RATE_HZ = float(os.environ.get("AIRMAR_ADSB_RATE_HZ", "200000"))

spec = importlib.util.spec_from_file_location("airmaritime_decoder_live",
                                              os.path.join(REPO, "airmaritime_decoder_live.py"))
mod = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
spec.loader.exec_module(mod)
mod.ADSB_SOURCE_RATE_HZ = ADSB_RATE_HZ
print("[airmar decoder] repo airmaritime_decoder_live.py: AIS tcp %d, ADS-B tcp %d at %.0f S/s -> ZMQ 9201/9202"
      % (mod.AIS_TCP_PORT, mod.ADSB_TCP_PORT, ADSB_RATE_HZ), flush=True)

if __name__ == "__main__":
    mod.main()
