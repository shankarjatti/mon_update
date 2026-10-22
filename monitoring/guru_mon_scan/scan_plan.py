"""Monitoring scan plan — one place for every channel's band list and dwell.

Dwell times are taken from the monitoring simulation (monitoring_sim.html):
each look = (T_pkt + T_rep) x 2.5 for CH1/CH2, 150 ms per look for CH3,
10 ms per band for CH4. SWITCH_MS (the retune + settle time between looks) is
an ASSUMPTION of 10 ms until it is measured on the X310 by mon_scan_retune.py
(step A1). Nothing here is measured yet.

Channel -> TwinRX port (same mapping as the block diagram):
  CH1 Drone/Replay     -> ch0  A/RX1
  CH2 Terrestrial      -> ch1  A/RX2
  CH3 Radar            -> ch2  B/RX1
  CH4 Cellular downlink-> ch3  B/RX2

Each band: (name, center_hz, dwell_ms). For a band given as a range in the
design sheet, center_hz is the midpoint; splitting a wide band into several
look windows (needed on the 1 Gb/s link, ~4 MHz per look) is a later step.
TwinRX cannot tune 5000-5140 MHz, so the C-band centers stay >= 5140.
"""

SWITCH_MS = 10.0          # user: keep 10 ms for every switch. MEASURED 2026-10-08
                          # (mon_scan_retune.py) MON retune+lock worst 6.7 ms (CH3),
                          # mean ~4-6 ms, LO drops every retune -> 10 ms is safe margin.
PORTS = ["A/RX1", "A/RX2", "B/RX1", "B/RX2"]

# ---- CH1  Drone + Replay/DoS  (ch0, A/RX1) ----
# Conventional (Replay/DoS, ISM) x10 cycles, DroneID listen, unconventional x2.
CH1_CONV = [
    ("Wi-Fi 2.4 2412-2472", 2442e6, 256.0),
    ("Wi-Fi 5.2 5180-5240", 5210e6, 256.0),
    ("Wi-Fi 5.8 5745-5825", 5785e6, 256.0),
    ("LoRa 865-928",         896.5e6, 257.0),
]
CH1_UNCONV = [
    ("Drone 433",            433.9e6, 256.0),
    ("FPV 1080-1280",        1180e6, 256.0),
    ("Video 5645-5945",      5795e6, 256.0),
]
CH1_DRONEID = ("DroneID listen", 2442e6, 2000.0)   # user 2026-10-22: DroneID listen = 2 s dwell (+10 ms switch). Listen band TBD; placed at 2.4 for now

# ---- CH2  Terrestrial + Air/Maritime  (ch1, A/RX2) ----
CH2_TERR = [
    ("D-STAR 145.0",  145.0e6, 50.0),
    ("TETRA 420.0",   420.0e6, 142.0),
    ("DMR 446.100",   446.100e6, 150.0),  # radio's real TX (measured from a keyed capture ~446.104); 446.100 keeps it inside channelizer ch0
    ("P25 450.0",     450.0e6, 450.0),
    ("NXDN 451.0",    451.0e6, 200.0),
]
CH2_AIR = [
    ("AIS 161.975",   161.975e6, 400.0),
    ("ADS-B 1090",    1090.0e6, 400.0),
]

# ---- CH3  Radar  (ch2, B/RX1) ----  160 ms per look (monitoring_sim.html: lk ms:160)
CH3 = [
    ("L 1200-1400",   1300e6, 160.0),
    ("S 2700-3100",   2900e6, 160.0),
    ("S 3000-3500",   3250e6, 160.0),
    ("C 5140-5900",   5520e6, 160.0),
    ("C 5400-5900",   5650e6, 160.0),
]

# ---- CH4  Cellular downlink  (ch3, B/RX2)  20 ms per band (monitoring_sim.html ms:20) ----
CH4 = [
    ("2G 925.2-934.8", 930.0e6, 20.0),
    ("2G 935.2-959.8", 947.5e6, 20.0),
    ("2G 1805-1880",   1842.5e6, 20.0),
    ("B28 758-803",    780.5e6, 20.0),
    ("B5 869-894",     881.5e6, 20.0),
    ("B8 925-960",     942.5e6, 20.0),
    ("B1 2110-2170",   2140e6, 20.0),
    ("B40 2300-2400",  2350e6, 20.0),
    ("n78 3300-3670",  3485e6, 20.0),
]


def ch1_frame():
    """One CH1 frame: 10 conventional cycles, DroneID, 2 unconventional cycles."""
    looks = []
    for _ in range(10):
        looks += CH1_CONV
    looks.append(CH1_DRONEID)
    for _ in range(2):
        looks += CH1_UNCONV
    return looks


def ch2_frame():
    """One CH2 frame: 8 terrestrial cycles, 1 air & maritime cycle."""
    looks = []
    for _ in range(8):
        looks += CH2_TERR
    looks += CH2_AIR
    return looks


def ch3_frame():
    return list(CH3)


def ch4_frame():
    return list(CH4)


FRAMES = [ch1_frame, ch2_frame, ch3_frame, ch4_frame]
# the distinct band set per channel (for retune measurement: unique centers)
BAND_SETS = [
    CH1_CONV + CH1_UNCONV,                 # CH1 (skip the passive DroneID listen)
    CH2_TERR + CH2_AIR,                    # CH2
    CH3,                                  # CH3
    CH4,                                  # CH4
]


# Full RF width of each band (Hz). Narrow protocol channels are < one look, so
# they are never split. Wide ranges split into several looks once the host link
# allows a wide look (10 GbE / 80 MHz). Keyed by band name.
WIDTHS = {
    # CH1
    "Wi-Fi 2.4 2412-2472": 60e6, "Wi-Fi 5.2 5180-5240": 60e6,
    "Wi-Fi 5.8 5745-5825": 80e6, "LoRa 865-928": 63e6,
    "Drone 433": 1.74e6, "FPV 1080-1280": 200e6, "Video 5645-5945": 300e6,
    # CH2 (narrow protocol channels)
    "D-STAR 145.0": 0.1e6, "TETRA 420.0": 0.1e6, "DMR 446.100": 0.2e6,
    "P25 450.0": 0.1e6, "NXDN 451.0": 0.1e6, "AIS 161.975": 0.05e6, "ADS-B 1090": 2e6,
    # CH3 radar sub-bands
    "L 1200-1400": 200e6, "S 2700-3100": 400e6, "S 3000-3500": 500e6,
    "C 5140-5900": 760e6, "C 5400-5900": 500e6,
    # CH4 cellular downlink ranges
    "2G 925.2-934.8": 9.6e6, "2G 935.2-959.8": 24.6e6, "2G 1805-1880": 75e6,
    "B28 758-803": 45e6, "B5 869-894": 25e6, "B8 925-960": 35e6,
    "B1 2110-2170": 60e6, "B40 2300-2400": 100e6, "n78 3300-3670": 370e6,
}


def expand_frame(frame, look_bw_hz):
    """Split any band wider than look_bw_hz into several look windows that tile
    the band (same dwell each). Narrow bands pass through unchanged. Returns
    (name, center_hz, dwell_ms) tuples. look_bw_hz large -> one look per band."""
    import math
    out = []
    for name, center, dwell in frame:
        w = WIDTHS.get(name, 0.0)
        if w <= look_bw_hz or look_bw_hz <= 0:
            out.append((name, center, dwell))
            continue
        k = int(math.ceil(w / look_bw_hz))
        lo = center - w / 2.0 + look_bw_hz / 2.0
        for i in range(k):
            sub = lo + i * (w - look_bw_hz) / max(1, k - 1) if k > 1 else center
            out.append(("%s #%d/%d" % (name, i + 1, k), sub, dwell))
    return out


def build_frames(look_bw_hz=0.0):
    """Every channel's frame, optionally split into looks of look_bw_hz.
    look_bw_hz = 0 (default) -> one look per band centre (for the 1 Gb/s link).
    look_bw_hz = 80e6 -> 80 MHz looks (10 GbE), matching the sim."""
    return [expand_frame(f(), look_bw_hz) for f in FRAMES]


PIN_DWELL_MS = 600000.0      # 10 min: a pinned channel holds one band continuously


def find_band(ch, name):
    """Return (name, center_hz, dwell_ms) for a band of channel `ch` by name,
    or None. Used by --pin to hold a channel on one band for continuous decode."""
    for b in BAND_SETS[ch]:
        if b[0] == name:
            return b
    return None


def pin_frame(ch, name):
    """A one-look 'frame' that holds channel `ch` on band `name` continuously."""
    b = find_band(ch, name)
    if b is None:
        return None
    return [(b[0], b[1], PIN_DWELL_MS)]


def frame_ms(looks):
    """Total frame time with the current SWITCH_MS assumption."""
    return sum(d + SWITCH_MS for _, _, d in looks)


if __name__ == "__main__":
    names = ["CH1 Drone/Replay", "CH2 Terrestrial", "CH3 Radar", "CH4 Cellular"]
    for i, f in enumerate(FRAMES):
        looks = f()
        print("%s (%s): %d looks, frame %.0f ms (switch %.0f ms each)"
              % (names[i], PORTS[i], len(looks), frame_ms(looks), SWITCH_MS))
