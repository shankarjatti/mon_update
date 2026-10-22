# edge_ch2 — CH2 header pub/sub + full 4-channel monitoring UI

Per-channel architecture (user's design): the RTOS scheduler owns the radio and
publishes ONE stream per channel; Edge Computing subscribes. CH2 (terrestrial)
carries a per-block HEADER so the edge router sends each band's IQ to the right
protocol decoder. +1 pub/sub is added for AOA during DF (not built yet).

## Pieces
- `ch2_header.py`       — the CH2 header format (shared: scheduler + router).
- `ch2_pub.py`          — GR block that stamps + publishes the CH2 header stream.
- `ch2_scheduler.py`    — RTOS scheduler: own radio, hop terrestrial bands, PUB CH2
                          (`--addr <uhd>` live, or `--replay <cf32>` offline; `--only <band>` pins).
- `ch2_header_router.py`— Edge router: CH2 stream -> TCP 7001-7004 by `proto` header.
- `backupv1_bridge_ext.py` — runs the WORKING 4-protocol console bridge
                          (backupv1/secuecom-version1) WITHOUT its Module 1 (the
                          router replaces it). allinone.py reads 7001-7004.
- `mon_ws_bridge.py`    — monitoring -> UI: subscribes mon_server 5201-5204, sends
                          REAL spectrum + |IQ| envelope + IQ scatter + active/idle
                          per channel over ws://127.0.0.1:8780.

## Full integrated system (as run on the X310 / USRP-2945)
```
mon_server (X310, 4 ch, scans all planned bands @2 MS/s)
  ├─ 5201 CH1 ─┐
  ├─ 5202 CH2 ─┼─► mon_ws_bridge ──ws 8780──► 5-panel UI (guru_mon_scan/securecom_ui.html)
  ├─ 5203 CH3 ─┤                               CH1 drone · CH3 radar · CH4 cellular (REAL FFT/time/IQ)
  ├─ 5204 CH4 ─┘
  └─ 5202 CH2 ──► ch2_header_router ─► 7001-7004 ─► allinone.py ─► CH2 terrestrial console (embedded)
```

The UI shows **real data only** — each panel draws exactly what that dwell
received (noise as noise, signal when detected). No dwell data yet -> "waiting
for this band's dwell…". Detections logged only when the channel is really active.

## Run (next hardware test — X310 connected, radio on a terrestrial band)
Start each in its own terminal (envs differ):
```bash
# 1) radio owner + scanner (GR 3.8 / UHD 3.15)
cd ~/radar2/guru_mon_scan && source ~/gnuradio-3.8/setup_env.sh
python3 mon_server.py --addr addr=192.168.10.2 --gain 20       # add --pin "2=DMR 446.100" for sustained terrestrial decode

# 2) monitoring -> UI bridge   (any python w/ numpy+zmq+websockets)
cd ~/radar2/edge_ch2 && python3 mon_ws_bridge.py               # ws 8780

# 3) CH2 terrestrial: router + console (SYSTEM GR 3.10)
cd ~/radar2/edge_ch2 && env -u LD_LIBRARY_PATH -u PYTHONPATH PATH=/usr/local/bin:/usr/bin:/bin LD_LIBRARY_PATH=/usr/local/lib python3 ch2_header_router.py --in tcp://127.0.0.1:5202 --base-port 7001
cd ~/radar2/backupv1/secuecom-version1/gui && env ... DISPLAY=:0 python3 backupv1_bridge_ext.py     # ws 8787
cd ~/radar2/backupv1/secuecom-version1/gui && python3 -m http.server 8788 --bind 127.0.0.1          # console

# 4) serve the 5-panel UI
cd ~/radar2 && python3 -m http.server 8099 --bind 127.0.0.1
# open http://127.0.0.1:8099/guru_mon_scan/securecom_ui.html
```
Console inside CH2 panel: Hardware tab -> Start hardware, Start decoder.

## Verified (2026-10-14, X310)
- All 4 channels scanned their planned bands (CH1 8, CH2 7, CH3 5, CH4 9) and
  published; mon_ws fed real per-channel spectrum to the UI; CH3 radar lit ACTIVE
  on C-band 5650 MHz / S-band 3250 MHz. CH2 terrestrial console embedded + live.
- Open: DMR decode (frequency match / clipping) — the signal seen at DC on the CH2
  feed was a narrow carrier, not a wide DMR hump; confirm radio TX freq next time.
- B210 is unusable on USB 2.0 (LIBUSB_TRANSFER_OVERFLOW); X310 over Ethernet is the target.
