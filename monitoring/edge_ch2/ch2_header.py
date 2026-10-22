#!/usr/bin/env python3
"""ch2_header - the CH2 terrestrial IQ header format (single source of truth).

CH2 is ONE channel but the RTOS scheduler burst-hops it across the terrestrial
bands (DMR / NXDN / P25 / TETRA ...). So every IQ block the scheduler PUBlishes
carries a header saying which band this chunk is. The Edge-Computing router reads
that header and drops the IQ into the respective band's decoder ("respected
place"). This file defines that header so the scheduler side and the edge side
can never disagree.

Wire format  (one message = two parts, same for ZMQ multipart or TCP length-framed):
    part 0 : header  -> UTF-8 JSON (the dict below)
    part 1 : payload -> raw IQ, little-endian complex64 (interleaved float32 I,Q)

Header fields
-------------
  v           int    header schema version (bump on any breaking change)
  ch          int    source channel (2 = terrestrial)
  proto       str    ROUTING KEY: "dmr"|"nxdn"|"p25"|"tetra"  (what the router
                     switches on; "" or "unknown" => drop/ignore)
  band        str    human band label, e.g. "DMR446" (for display/logging)
  center_hz   float  RF centre the radio was tuned to for THIS block
  target_hz   float  where the signal of interest actually is (==center_hz if the
                     carrier is tuned to DC; lets the decoder set its xlate offset)
  samp_rate   float  IQ sample rate of the payload, Hz (e.g. 200000 or 2000000)
  n           int    number of complex samples in the payload
  dtype       str    IQ encoding, always "complex64" for now
  seq         int    monotonic block counter per channel (gap => dropped blocks)
  dwell_id    int    id of the current dwell (all blocks of one visit share it)
  dwell_start bool   True on the FIRST block of a new dwell -> decoder should
                     flush/reset its state (DSD sync, channelizer) for a clean start
  t           float  host wall-clock time, epoch seconds (UTC)

Routing: the edge router looks at `proto`. `band`/`center_hz` are for the decoder
and for humans. One header per IQ block; blocks within a dwell share dwell_id and
only the first has dwell_start=True.
"""
import json
import time

HEADER_VERSION = 1

# band label (as the scheduler names it) -> protocol routing key.
# Add a row here when a new terrestrial band is scanned on CH2. The repo's
# working 4-protocol core is DMR/NXDN/P25/TETRA; others route to their own key.
BAND_TO_PROTO = {
    "DMR446":      "dmr",
    "DMR 446.100": "dmr",
    "NXDN96":      "nxdn",
    "NXDN 451.0":  "nxdn",
    "P25-Ph1":     "p25",
    "P25 450.0":   "p25",
    "TETRA":       "tetra",
    "TETRA 420.0": "tetra",
    "D-STAR 145.0": "dstar",
}

# protocols the edge side actually decodes (the working 4-protocol core).
KNOWN_PROTOS = ("dmr", "nxdn", "p25", "tetra")


def proto_for_band(band):
    """Map a band label to its routing key (or 'unknown')."""
    return BAND_TO_PROTO.get(band, "unknown")


def make_header(band, center_hz, samp_rate, n, seq, dwell_id,
                dwell_start=False, target_hz=None, ch=2, proto=None, t=None):
    """Build a CH2 header dict. `proto` is derived from `band` unless given."""
    return {
        "v": HEADER_VERSION,
        "ch": int(ch),
        "proto": proto if proto is not None else proto_for_band(band),
        "band": str(band),
        "center_hz": float(center_hz),
        "target_hz": float(center_hz if target_hz is None else target_hz),
        "samp_rate": float(samp_rate),
        "n": int(n),
        "dtype": "complex64",
        "seq": int(seq),
        "dwell_id": int(dwell_id),
        "dwell_start": bool(dwell_start),
        "t": float(time.time() if t is None else t),
    }


def encode_header(hdr):
    """Header dict -> bytes (message part 0)."""
    return json.dumps(hdr, separators=(",", ":")).encode("utf-8")


def decode_header(raw):
    """bytes -> header dict. Raises ValueError on anything malformed."""
    try:
        hdr = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError("bad CH2 header: %s" % e)
    if not isinstance(hdr, dict) or "proto" not in hdr or "band" not in hdr:
        raise ValueError("CH2 header missing required fields")
    if int(hdr.get("v", 0)) != HEADER_VERSION:
        raise ValueError("CH2 header version %r != %d" % (hdr.get("v"), HEADER_VERSION))
    return hdr


if __name__ == "__main__":
    # self-check / example
    h = make_header("DMR446", 446118528.0, 200000.0, n=4096, seq=42,
                    dwell_id=7, dwell_start=True)
    b = encode_header(h)
    print("example header bytes (%d):" % len(b), b.decode())
    back = decode_header(b)
    assert back == h, "round-trip mismatch"
    assert back["proto"] == "dmr"
    print("round-trip OK; proto =", back["proto"])
