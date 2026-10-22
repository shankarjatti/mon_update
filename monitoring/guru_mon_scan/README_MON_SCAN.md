# guru_mon_scan — MON scanning (Phase A of the monitoring build)

4-channel monitoring on the USRP-2945. Each TwinRX channel is on its **own
internal LO** (MON) and **scans its band list** from `scan_plan.py`: retune →
hold for that band's dwell → next band, continuously. Per channel you get a
spectrum graph, a time graph, and a status line (band, dwell, look, LO lock,
power dBFS, ACTIVE/quiet) in its own tab (CH1..CH4). **No transmitter** — the
graphs show whatever the 4 antennas receive. DF is built later (Phase B).

Built from **guru_switch** (originals untouched). Dwells come from the
monitoring simulation (`../monitoring_sim.html`).

## Run (X310 connected, 4 antennas on the 4 ports)
```bash
./run_mon_scan.sh                 # GUI, all 4 channels, gain 50 dB
./run_mon_scan.sh --gain 50 --channels 2        # CH2 (terrestrial) only - lighter CPU
./run_mon_scan.sh --gain 50 --pub # GUI + publish per-channel IQ to the edge modules
./run_mon_scan.sh --gain 45 --channels 2 --pin "2=DMR 446.100" --pub   # PIN CH2 to DMR (no scan)
./run_mon_scan.sh --gain 55 --verbose
```
All 4 channels show at once (scroll area), each with its own FFT + time graph.
`--channels 2` (or `1,2`) runs just those - useful to verify one module at a time.
Headless pipeline (no GUI), publishes to the edge modules:
```bash
./mon_server.py --gain 50         # scan + tag + publish + print ACTIVE bands
./mon_sub_example.py --ch 2       # example edge module: subscribe to CH2 (port 5202)
```
If the X310 is unreachable (NetworkManager dropped the NIC address):
```bash
sudo nmcli connection up usrp     # restores enp3s0 = 192.168.10.1/24
```

## Pub-Sub to the edge modules (A5)
Each channel publishes on its own ZeroMQ PUB socket:
`CH1 tcp://127.0.0.1:5201 · CH2 5202 · CH3 5203 · CH4 5204`.
Message = multipart `[header_json, iq_bytes]`:
header `{ch, band, freq, look, frame, host_time, n}`, iq = `n` × complex64.
In-flowgraph consumers also get a stream tag `look` (same fields) on each retune (A4).

## Files (new in this build)
| file | what |
|---|---|
| `scan_plan.py` | the scan plan: every channel's bands + dwell (from the sim). One source of truth. `SWITCH_MS = 10 ms`. Run it to print frame times. |
| `mon_scan.py` | the 4-channel scanning GUI (A2/A3/A6): UHD source in MON config, per-channel spectrum + time graph, scan controller, power/active readout. `--pub` to also publish. |
| `mon_pub.py` | per-channel tap: stream tag (A4) + ZeroMQ publish (A5), pass-through. |
| `mon_server.py` | headless scanner: scan + tag + publish + print ACTIVE bands. |
| `mon_sub_example.py` | example edge-module subscriber (prints header per band). |
| `mon_scan_retune.py` | A1: measures the real MON retune+lock time on the X310. |
| `run_mon_scan.sh` | launcher: checks the X310, runs the GUI. |
| `BUILD_LOG.md` | step-by-step build log. |

## Channel → port
CH1 Drone/Replay = ch0 A/RX1 · CH2 Terrestrial = ch1 A/RX2 ·
CH3 Radar = ch2 B/RX1 · CH4 Cellular DL = ch3 B/RX2.

## Status (2026-10-08)
Working on the X310: all 4 channels scan in parallel, LO locks every look,
real signals seen (cellular B8/B1 strong, DMR 446.1 present). Measured MON
retune+lock worst 6.7 ms (10 ms switch kept as margin).

**MONITORING COMPLETE:** A1 (retune measured), A2/A3 (4-channel scanning),
A4 (stream tags), A5 (Pub-Sub per channel), A6 (per-channel graphs), per-module
band table (stand-in for the modules), wide-band look splitting (`--look-bw 80e6`
for 10 GbE), activity CSV log. On-hardware: scanning + graphs + retune. Offline-
verified (no X310): tags, pub/sub loopback, splitting; all byte-compile.
**Next:** Phase B (DF).

## Wide-band look splitting
Default = one look per band centre (1 Gb/s, ~4 MHz usable). With 10 GbE:
`--look-bw 80e6` splits wide bands into 80 MHz looks (matches the sim). Widths
are in `scan_plan.WIDTHS`.

## Notes
- One look = `--samp-rate` wide (2 MHz default; ~4 MHz usable on the 1 Gb/s link).
  Wide bands use one look at the band centre for now; splitting is a later step.
- CH3/CH4 frame totals differ from the sim only because the sim split wide bands
  into several 80 MHz looks. Per-band dwells match the sim.
- TwinRX cannot tune 5000–5140 MHz; C-band centres stay ≥ 5140.
- GUI is heavy at 4 × 2 MS/s; on a busy PC watch for overflow (`O`). Performance
  CPU governor helps.
