# mon_update — 4-channel monitoring on the USRP-2945 (live updates)

Continuous monitoring on an NI USRP-2945 (Ettus X310 + 2 × TwinRX): 4 channels, each on its **own LO**, each
stepping through its own band list ("scan frame"); per-channel ZeroMQ Pub-Sub out to the edge modules; a
5-panel operator UI; a terrestrial-radio decoder chain on CH2. Direction finding (DF) is **not built yet** —
the proven MON ↔ DF switch lives in https://github.com/shankarjatti/guru_switch_mon-df .

This repo is updated after every stage. **Start with [docs/WORK_LOG.md](docs/WORK_LOG.md)** (CURRENT STATE at the top).

## Layout
| path | what |
|---|---|
| `monitoring/guru_mon_scan/` | scanner (`mon_server.py`, `mon_scan.py` GUI), `scan_plan.py` (every channel's bands + dwell), `mon_pub.py` (tags + ZeroMQ), UI, `BUILD_LOG.md` |
| `monitoring/edge_ch2/` | watchdog `run_monitor.py`, UI bridge `mon_ws_bridge.py`, CH2 header router, system block diagram |
| `monitoring/terrestrial38/` | CH2 decoder glue (GNU Radio 3.8) |
| `design/monitoring_sim.html` | animated monitoring + DF block diagram (the design) |
| `docs/` | `WORK_LOG.md` (live log), `DSD38_PORT_PLAN.md` |
| `sync.sh` | copies the published files from the lab folders into this repo (with a secret check) |

## Channels
| channel | port | content |
|---|---|---|
| CH1 | ch0 A/RX1 | drone + replay/DoS bands |
| CH2 | ch1 A/RX2 | terrestrial radio + air/maritime |
| CH3 | ch2 B/RX1 | radar |
| CH4 | ch3 B/RX2 | cellular downlink |

## Run (X310 on, 4 antennas connected)
```bash
sudo nmcli connection up usrp          # NIC must be 192.168.10.1/24 ; check: ping 192.168.10.2
cd ~/radar2/edge_ch2 && python3 -u run_monitor.py --gain 25 --ch2-gain 10 --samp-rate 1e6 --squelch -45
# UI: http://127.0.0.1:8099/securecom_ui.html     stop: ONE Ctrl-C (never kill the scanner by hand)
```
Needs GNU Radio 3.8 + UHD 3.15 (`~/gnuradio-3.8`, `~/uhd-3.15`). Full steps and checks: WORK_LOG entry 2026-10-22.

## Status (2026-10-22)
* **Done, run on the radio:** 4 channels scanning in parallel, retune + lock worst 6.7 ms, Pub-Sub 5201–5204,
  5-panel UI on real data, activity log, watchdog, CH2 decoder chain.
* **Gaps found:** one look ≈ 1 MHz at the band centre (design: 80 MHz); detector reads only the end of a dwell;
  CH3 "active" is energy only; switch time counted twice in `scan_plan.py`; host-time tags, no LO-lock read in
  `mon_server.py`; no proof yet of one correct terrestrial decode.
* **Not built:** the DF side — request path, priority scheduler, manual approve, emergency, DF Pub-Sub / AOA.

## Not in this repo (on purpose)
The design sheet and timing slides, recordings, result logs, tarballs, build folders and the decoder sources
(`gr-dsd`, `gr-tetra`: kept locally, saved as `terrestrial_port_v1.tar.gz`).
