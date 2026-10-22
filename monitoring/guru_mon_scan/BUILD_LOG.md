# guru_mon_scan — monitoring build log

Monitoring (MON) scanning system, built step by step from **guru_switch**
(copied 2026-10-08, originals untouched). DF is built LAST, after monitoring is
complete. Local only until the user shares the new GitHub repo.

## Plan — Phase A (monitoring), then Phase B (DF)
- **A1** one channel scanning + measure the REAL retune time  ← ready, needs the X310
- **A2** full per-channel scan frames (bands + HTML dwells)
- **A3** all 4 channels scanning in parallel, each own LO/frame
- **A4** tags on every block (channel, LO freq, look/frame id, radio time)
- **A5** 4 Pub-Sub links out to the edge modules
- **A6** GUI: per-channel spectrum + time graph (CH1..CH4), long-run check
- **B**  DF: request-driven scheduler, priority (drone x5 / others x2), emergency, back-to-MON

## Dwells — from the monitoring sim (monitoring_sim.html)
`scan_plan.py` is the single source of truth. Per-band dwell = HTML value.
`SWITCH_MS = 10 ms` is an ASSUMPTION until A1 measures it.
- CH1 Drone/Replay (ch0 A/RX1): 10 conv cycles (Wi-Fi 256, LoRa 257) + DroneID 2010 + 2 unconv cycles → ~14.27 s
- CH2 Terrestrial (ch1 A/RX2): 8 terr cycles (D-STAR 50, TETRA 142, DMR 150, P25 450, NXDN 200) + air (AIS 400, ADS-B 400) → 9.16 s
- CH3 Radar (ch2 B/RX1): 150 ms per band look
- CH4 Cellular DL (ch3 B/RX2): 10 ms per band
Note: CH3/CH4 totals differ from the HTML only because the HTML splits wide
bands into several 80 MHz looks; here one look = one band centre (look-splitting
depends on the host link, a later step). TwinRX cannot tune 5000-5140 MHz.

## Setup change (2026-10-08)
- NO HackRF now. Real over-the-air: 4 same-size antennas on the 4 TwinRX ports.
- DMR radios as the live source; CH2 DMR band set to **446.100 MHz** (covers 446-446.2).
- Network: NetworkManager was stripping the manual IP; fixed permanently with an
  nmcli profile `usrp` (enp3s0 = 192.168.10.1/24, never-default). X310 31082D8 reachable.

## Status
- 2026-10-08: copy made. `scan_plan.py` (frames: CH1 14.17 s, CH2 9.07 s at 10 ms switch).
- **A1 DONE (measured on the X310, `mon_scan_retune.py`):** MON retune+lock
  CH1 worst 6.2 / CH2 6.2 / CH3 6.7 / CH4 5.8 ms; mean ~4-6 ms; LO drops every retune.
  → real switch ~4-7 ms. User: **keep SWITCH_MS = 10 ms** (safe margin). Result JSON in results/.
- **A2/A3/A6 DONE (`mon_scan.py`, runs on the X310 2026-10-08):** 4 channels scan
  their frames in parallel, each own internal LO; per-channel tab with spectrum +
  time graph + status line (band, dwell, look, LO lock). Verified: all 4 scan at
  the right rates (CH4 fastest, CH1 slowest), LO locks every look, DMR 446.100 on CH2.
  Run: `python3 mon_scan.py --gain 50` (add --verbose to print looks).
- OPEN: A4 tags on every block, A5 Pub-Sub out. Then Phase B (DF).
  Note: one look = 2 MHz (samp rate) ~ 4 MHz usable on 1 Gb/s; wide-band look
  splitting still to do. GUI CPU is heavy at 4x2 MS/s - watch for overflow on a busy PC.
- Added per-channel POWER probe + ACTIVE/quiet verdict (8 dB over each band's own
  floor), shown live in the status line and graphs. Real RF confirmed on antennas:
  cellular B8 (925-960) ~ -10 dBFS, B1 (2110-2170) strong; DMR 446.1 present.
- 2026-10-08: USRP disconnected by user. Code finalized and left ready:
  `run_mon_scan.sh` (checks X310, no HackRF), `README_MON_SCAN.md`. All files
  byte-compile. To run again: `./run_mon_scan.sh --gain 50`
  (if NIC dropped: `sudo nmcli connection up usrp`).

## A4 + A5 DONE (2026-10-08, verified offline without the X310)
- `mon_pub.py` - per-channel block, pass-through, does BOTH:
  A4 adds a stream tag "look" (pmt dict: ch, band, freq, look, frame, host_time)
     on the first sample after each retune;
  A5 publishes the IQ on a ZeroMQ PUB socket (pyzmq; GR's zeromq is not built here)
     as multipart [header_json, iq_bytes], one socket per channel (5201..5204).
- `mon_server.py` - headless scanner: 4 channels scan + tag + publish + print ACTIVE bands.
- `mon_sub_example.py` - edge-module subscriber stub (prints header per band change).
- `mon_scan.py` GUI gained `--pub` (view AND publish in one program).
- VERIFIED offline (loopback, no USRP):
  A5 publish: 12,964 msgs received, correct headers (band/freq/look/frame/host_time/n).
  A4 tag: collector saw the "look" tag with the full dict (band DMR 446.100, look 3, frame 7).

## Module stand-in display (2026-10-08)
- User: the edge modules' core work (decode/classify) is not ready; for now just
  SHOW the data on each module's frequencies.
- Added a per-module band TABLE in each tab (mon_scan.py): one row per band the
  module uses, live Power dBFS + State (ACTIVE/quiet, active=red). Stands in for
  the module - shows which of its frequencies have signal, no module core work.
  Each tab now: band table + spectrum + time graph + status. Compiles; test on X310.

## Wide-band look splitting DONE (2026-10-08)
- `scan_plan.WIDTHS` (full RF width per band) + `expand_frame(frame, look_bw)` +
  `build_frames(look_bw)`. `--look-bw` on both apps. Default 0 = one look per band
  (1 Gb/s). `--look-bw 80e6` (10 GbE) matches the sim: CH3 32 looks/5.12 s, CH4 14/280 ms,
  CH1 57/16.9 s, CH2 42/9.16 s (all narrow). Default frames unchanged.

## Activity log DONE (2026-10-08)
- mon_server.py writes `results/activity_<ts>.csv`
  (iso_time, ch, port, band, freq_mhz, power_dbfs, floor_dbfs) on each ACTIVE detection.

## Module stand-in table DONE
- Per-module band table in each GUI tab (live Power dBFS + ACTIVE/quiet), standing
  in for the not-yet-ready edge modules.

## GUI layout change (2026-10-08)
- User wants all 4 channels shown SEPARATELY at once (not tabs). mon_scan.py now
  stacks 4 panels in a scroll area, each panel = status + band table + its own
  FFT (left) + time graph (right). 8 live plots at 2 MS/s => CPU heavy; update
  rate 0.15 s. Compiles; layout is pure Qt (low risk). Test on X310.

## BACKUP (2026-10-12)
- Monitoring verified on hardware (all 4 ch scan + LO lock + power + publish).
  Frozen backup: `~/radar2/guru_mon_scan_v1` (+ SHA256SUMS inside), tarball
  `~/radar2/guru_mon_scan_v1.tar.gz` (+ .sha256 = fc3795d5...). Keep this safe;
  the working copy stays `~/radar2/guru_mon_scan`.

## PENDING - terrestrial module port (B210 -> our setup) + integration
- User will share the terrestrial radio GitHub repo. It was written for a **B210**
  and needs many changes for our setup. Plan (decide when the repo is read):
  * Preferred: replace its UHD/B210 source with a SUBSCRIBER to our ZeroMQ CH2
    feed (tcp://127.0.0.1:5202, complex64 + JSON header), so one program (mon_scan)
    owns the X310. Align sample rate (we publish 2 MS/s; resample to its expected Fs).
  * Drop its own device tuning/gain (we handle that in mon_scan); keep its decode core.
  * If it must own the radio instead: port B210 args -> X310+TwinRX MON (subdev
    A:0 A:1 B:0 B:1, antenna RX1/RX2, own internal LO, no master_clock_rate change).
  * Match CH2 scan_plan bands to the radios' exact TX freqs; for a single-module
    check, pin CH2 to the module's band (no scan) so it gets continuous IQ.

## (old) PENDING - terrestrial module integration (user: details earlier)
- User will share terrestrial radio details tomorrow; then integrate that module.
- Verify monitoring with CH2 (terrestrial) first, using their DMR radios (446.1).
  Run: `./run_mon_scan.sh --gain 50 --channels 2 --pub` ; `./mon_sub_example.py --ch 2`.
- To integrate, I need from the user:
  * the terrestrial module's INPUT interface: does it subscribe to ZeroMQ (our
    5202 feed) or read a file/pipe? expected sample rate + IQ format (we publish
    complex64 @ 2 MS/s + JSON header)?
  * the exact TX frequencies of their radios (D-STAR/TETRA/DMR/P25/NXDN) so CH2's
    scan_plan bands match what they will key;
  * whether the module wants continuous IQ on one band, or the scanning feed.
- Decision likely: for a one-module check, may pin CH2 to the module's band(s)
  instead of scanning, so the module gets continuous IQ.
- DF (Phase B) stays after monitoring is verified on hardware.

## Phase A (MONITORING) COMPLETE
- A1 retune measured, A2/A3 4-ch scanning, A4 tags, A5 Pub-Sub, A6 graphs,
  + module stand-in table, + wide-band splitting, + activity CSV log.
  On-hardware: A1/A2/A3/A6. Offline-verified (no X310): A4 tag, A5 pub/sub loopback,
  splitting, compiles. Everything byte-compiles.
- RUN when the USRP is back:
    ./run_mon_scan.sh --gain 50 --pub        # GUI (4 module tabs + tables + graphs) + publish
    ./mon_server.py --gain 50                # headless pipeline + activity log
    ./mon_sub_example.py --ch 2              # example edge module on CH2
  (if NIC dropped: sudo nmcli connection up usrp)
- NEXT: Phase B (DF).

## Run A1 (on the X310)
```
source ~/gnuradio-3.8/setup_env.sh
cd ~/radar2/guru_mon_scan
python3 mon_scan_retune.py --ch 1 --cycles 20      # CH2 terrestrial
python3 mon_scan_retune.py --ch all --cycles 10    # all channels
```
Prints per-band retune+relock ms and a worst-case; saves results/mon_scan_retune_*.json.

## TERRESTRIAL PORT (B210/GR3.10 -> GR3.8/UHD3.15) — 2026-10-12
- Repo github shankarjatti/1stversiondone cloned to ~/radar2/terrestrial_src.
- DSD (DMR/P25/NXDN/D-STAR) ported to GR 3.8 C++ OOT: ~/radar2/gr-dsd, installed to
  ~/gnuradio-3.8. Verified. See DSD38_PORT_PLAN.md.
- TETRA: user wants a C++ OOT too (option A). Building ~/radar2/gr-tetra (GR3.8 SWIG),
  links prebuilt libtetrakit_capi.so + libtetra_codec.so; replicates the python block:
  UDP 42100 JSON reports -> base64+zlib voice -> ACELP codec -> 4 float outs; call_log PMT.

## PIN mode (2026-10-12)
- --pin "CH=BANDNAME" holds a channel on one band continuously (no scanning), for
  sustained decode. e.g. --pin "2=DMR 446.100" (band names from scan_plan CH2 list).
  scan_plan.pin_frame() returns a single 10-min look; mon_pub still tags the band so
  the terrestrial decoder's --band filter matches. In mon_scan.py (GUI) and mon_server.py.
- Live DMR decode test flow:
    T1: ./run_mon_scan.sh --gain 45 --channels 2 --pin "2=DMR 446.100" --pub
    T2: cd ~/radar2/terrestrial38 && python3 decode_dsd.py --proto dmr --band "DMR 446.100"
    key DMR on 446.1 -> watch decode_dmr.wav + talkgroup in the log.

## BACKUP 2026-10-12 (save point: monitoring + pin + terrestrial C++ ports)
- guru_mon_scan_v2: ~/radar2/guru_mon_scan_v2 + guru_mon_scan_v2.tar.gz (+ .sha256
  4614167094...). Monitoring with: module band table, --pub, --channels, --look-bw,
  --pin (hold one band). Working copy stays ~/radar2/guru_mon_scan.
- terrestrial_port_v1.tar.gz (+ .sha256 1e36c3056a...): gr-dsd (DSD C++ OOT, +build .so),
  gr-tetra (TETRA C++ OOT, +build .so), terrestrial38 (zmq_cc_source + decode_dsd +
  decode_tetra + run_terrestrial_ch2.sh), DSD38_PORT_PLAN.md. Both OOTs also installed
  in ~/gnuradio-3.8. Restorable without rebuild.
