# WORK LOG — live

Updated at **every stage** of the work, so nothing is lost when a session is compacted
or restarted. Newest entry first. The finished story is in [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md);
hardware facts are in [lab_notes/](lab_notes/README.md).

**Rule for each entry:** date + time, what was asked (user's words where it matters),
what was done, what was measured (numbers, file in `results/`), what failed and why,
decisions taken, and what comes next. Only measured facts; anything not verified is marked so.

---

## CURRENT STATE (keep this block up to date) — last update 2026-10-22

| | |
|---|---|
| **THIS LOG / REPO (user, 2026-10-22)** | **"keep updating on https://github.com/shankarjatti/mon_update always, until I tell you"** → from 2026-10-22 the LIVE log and the monitoring code are updated HERE (`~/radar2/mon_update`, GitHub `mon_update`, PUBLIC, branch `main`). **When (user, same day): "keep updating after every CORRECT result, I will tell you when to stop"** — update after each verified correct result (not after every chat message; an unverified or failed attempt goes in the log only as a failed/open note). Update = edit the lab files → `./sync.sh` → edit this log (entry + CURRENT STATE) → commit → push. Older copy of this log: guru_switch_mon-df (stops at 2026-10-22, has a pointer here). Never publish `main_sched/` (private), recordings, result CSVs, tarballs |
| **Monitoring (built 2026-10-08…16)** | lab folders `~/radar2/guru_mon_scan` (scanner, scan_plan, pub-sub, UI) + `~/radar2/edge_ch2` (watchdog, UI bridge, CH2 router) + `~/radar2/terrestrial38`, `gr-dsd`, `gr-tetra` (GR 3.8 decoders). 4 channels scan their frames in parallel, own LO each, ZeroMQ PUB 5201–5204, 5-panel UI, activity CSV. Frozen: `guru_mon_scan_v1` / `_v2` (+ `.tar.gz`, `.sha256`), `terrestrial_port_v1.tar.gz` (local). Published here: `monitoring/` (code), `design/` (sim), `docs/`. Details: the 2026-10-08…16 entry and `monitoring/guru_mon_scan/BUILD_LOG.md` |
| **Run monitoring** | `sudo nmcli connection up usrp` (NIC must be 192.168.10.1/24) → X310 on, 4 antennas → `cd ~/radar2/edge_ch2 && python3 -u run_monitor.py --gain 25 --ch2-gain 10 --samp-rate 1e6 --squelch -45` → UI http://127.0.0.1:8099/securecom_ui.html → stop with ONE Ctrl-C. Checked 2026-10-22 (files, toolchain, modules, ports; hardware not run) |
| **CH1 — APPLIED 2026-10-22 ("update all things related to cha 1")** | **Later the same day (15–16 h): DC removal on all channels, sample-accurate detector (look_power, 14 ms skip, 0.5 ms peak, 2.5 dB margin), CH1 band lock from the UI (MON plan / one band), GNU Radio-style graphs + waterfall, binary per-view feed (lag fix), continuous traces — see the 15:xx–16:xx entry.** DroneID listen = 2000 ms dwell (frame 14,256 ms, 47 looks: conventional ×10 [Wi-Fi 2.4 / 5.2 / 5.8 / LoRa SF7] + DroneID ×1 + unconventional ×2 [433 / FPV 1080–1280 / Video 5645–5945]); CH1 UI graphs rebuilt (GNU Radio style); `samp_rate` added to every published header (also fixed the CH2 router rate bug). Details: the 2026-10-22 13:xx entry |
| **PENDING EDITS — NOT APPLIED (user: "I tell all edits at once")** | **CH1 still open:** DroneID listen FREQUENCY (placeholder 2442 MHz); detector = peak over the whole dwell (suggested, NOT approved; affects every channel). **CH2, CH3, CH4 — not reviewed yet** (known: CH3 dwell 160 and CH4 dwell 20 are the sim's look totals, switch counted twice; CH2 gaps listed below). The UI "Monitoring Backend" copy of CH2–CH4 is still the old saved list |
| **Monitoring gaps found 2026-10-22** | (1) each look ≈ 1 MHz at the band centre, not 80 MHz; (2) detector reads only the last 1–2 ms of a dwell; (3) CH3 "ACTIVE" is energy only; (4) `scan_plan.py` adds the 10 ms switch twice for CH3 (160), CH4 (20), DroneID (2010); (5) host `sleep` timing, host-time tags, no LO-lock read in `mon_server.py`; (6) no proof yet of one correct terrestrial decode; (7) **CH2 power is dominated by the DC spur (≈ 100 % within ±3 kHz of DC, −57 dBFS on every band) → floor is the spur**; (8) CH2 console centres ≠ scan plan, saves a .wav per dwell, shows "B210"; (9) UI ACTIVE flag always on (bridge floor bug); (10) load ≈ 10 on 12 cores; (11) **RX1 ports (CH1, CH3) have a huge DC offset (−6 / −8 dBFS) and ≈ 30 dB more noise than the RX2 ports; the CH1 centre spike is DC, not a signal; the scanner's detector still counts the DC so CH1 can hardly read ACTIVE** (see the 14:xx entry). See the 2026-10-22 entries (12:0x, 11:5x) |
| **DF side of the design (`~/radar2/monitoring_sim.html`)** | NOT built: request path, priority scheduler (drone ×5 / others ×2), manual approve, emergency, DF Pub-Sub + AOA. Only the MON↔DF switch itself is proven (guru_switch). Field calibration with real antennas still undecided |
| Working system | **guru_switch** (`~/radar2/guru_switch`, `./run_hop.sh --switch`): DF (shared LO, 2.4 → 5.2 → 5.8 GHz, 7 ms switching + 5 ms dwell, burst, 2 MS/s) + MON (own LO per channel: ch0 900 MHz, ch1 2.4, ch2 5.2, ch3 5.8 GHz, ONE continuous stream) in one program; mode changed ONLY by hand with the MODE selector (control API off by default) |
| Proven | DF phase after returning from MON ≤ 0.33° (same as a plain retune); switch ~20–33 ms request → first dwell; 30-min run 2026-09-30 18:12–18:42: 0 TIMING LOST, 0 errors, HackRF 0 stalls |
| GitHub | **this work + this log**: https://github.com/shankarjatti/guru_switch_mon-df (PUBLIC, main) · old (do not change): https://github.com/shankarjatti/guru10ms |
| Frozen safe copies | DF `~/radar2/guru_DF_v1` · MON `~/radar2/guru_MON_v1` · earlier `guru0930`, `guru57`, `guru10ms` (each: git, SHA256SUMS, `.tar.gz`; DF ones `RESTORE.sh`). guru_switch itself is NOT frozen locally yet (GitHub has it) |
| Work copies | `~/radar2/guru_switch` (switching), `~/radar2/guru_mon` (MON), `~/radar2/guru` (DF lab), `~/radar2/guru_ota` (over-the-air, paused) |
| Run | `cd ~/radar2/guru_switch && ./run_hop.sh --switch` → CALIBRATE in DF at every start → MODE selector; close the window to stop (never kill) |
| Radio / source | X310 `31082D8` at 192.168.10.2 (1 Gb/s link, enp3s0); HackRF 200 kHz tone, 2 MS/s, VGA 14 (0.9/2.4 GHz) / 47 (5.2/5.8), UDP 127.0.0.1:5123, restarts itself as a fresh process after stalls |
| Docs of the switch work | `guru_switch/docs/switching/`: THEORY, ENGINE_AND_BLOCKS, DEVELOPMENT_AND_TESTS, RUN_AND_HARDWARE |
| User rules | everything real, no fakes/fallbacks; RX does all calculations, TX only a source; plan first, build after the go; MON continuous; mode manual only; keep this log updated every stage (sessions get compacted) |
| Open items | ~1–2 % DF slots late when the PC is busy (CPU governor `powersave`, kernel worker load); 10 missing bursts seen once (first continuous-MON run, not reproduced); ch0 (A/RX1) 13–16 dB low (cable/port); HackRF drops off USB (another port/cable); MON bands fixed at start; CPU headroom of the DF Python chain; over-the-air jitter (guru_ota) |
| Monitoring plan (2026-10-05, architecture only) | per-channel scan frames: CH1 14.26 s · CH2 9.16 s · CH3 5.12 s · CH4 0.3 s; look = (T_pkt + T_rep) × 2.5 + 10 ms (CH3 150 ms, CH4 10 ms dwell); MON = 4 Pub-Sub links, DF = 1 Pub-Sub from AOA — see the 2026-10-05 entry |
| Next (user's plan) | step by step, only on the user's go: more MON bands with retuning, DOA requests from edge modules → priority scheduler → DF on the band → back to MON |

**After a compacted session:** read this block, then the newest entries below; the switch work's details are in
`~/radar2/guru_switch/docs/switching/`. This log lives ONLY in `~/radar2/guru_switch/docs/WORK_LOG.md`
(GitHub guru_switch_mon-df). **Never change the old repos** (guru10ms on GitHub and locally, guru57, guru0930,
guru_DF_v1, guru_MON_v1) — user, 2026-10-01.

---|---|
| Working system | guru_burst (lab `~/radar2/guru`): 2.4 → 5.2 → 5.8 GHz, 7 ms switch + 5 ms dwell, 36 ms cycle, burst mode, 2 MS/s, 200 kHz HackRF tone (pure source). guru_fast 10/10 ms still available |
| Code on the lab PC | `~/radar2/guru10ms/` (this repo, pushed) and `~/radar2/guru/` (same code; lab git repo `~/radar2`, tag `guru10ms` = `d135177`) |
| GitHub | https://github.com/shankarjatti/guru10ms (public, branch `main`) |
| Backups | `~/radar2/guru10ms.tar.gz`, `~/radar2/BACKUP_FAST_2026-09-28/` (+ `.tar.gz`), `~/radar2/BACKUP_WORKING_2026-09-28/` (10 s guru) |
| Run | `./run_hop.sh --fast`, then CALIBRATE; every 5–10 min for < 1° |
| Radio | X310 `31082D8` at 192.168.10.2; HackRF tone on 2.4 GHz (UDP 127.0.0.1:5123) |
| Open items | thermal drift (~8°/16 min); rtprio not enabled (limit 0); CPU governor = `powersave` (not yet tested as a cause of late slots); field calibration without HackRF; overflow recovery untested; RTOS choice |
| Saved state | DF: `~/radar2/guru_DF_v1`, MON: `~/radar2/guru_MON_v1` (both frozen 2026-09-30); earlier `~/radar2/guru0930` (frozen 2026-09-30, lab tag `guru0930`) — base for the next step |
| Setup now (2026-09-30) | back to CABLE (HackRF → splitter → 4 ch); installed blocks = guru57; over-the-air work paused in `~/radar2/guru_ota` |
| Next step | user: `cd ~/radar2/guru && ./run_hop.sh --burst` + CALIBRATE; long run (> 11 min) to prove the 2 MS/s fix; rtprio needs log out/in |

---

## 2026-10-22

### 2026-10-22 19:xx — user: "I should see a good proper real signal … tell me the TX gain … do real changes, no fake signals" — narrowband detector BUILT, VERIFIED with the user's generator
* `look_power.py` now also averages a 2048-point Hann power spectrum over the settled part of each look (sample-accurate, real samples);
  `nb()` = strongest line outside ±2 kHz of 0 Hz, in dB over the MEDIAN bin, its frequency and level (needs ≥ 3 segments).
  `mon_server.py`: ACTIVE = band-power rule (floor + 2.5 dB) OR narrowband line ≥ 10 dB over the median bin; verdict JSON adds
  `nb_db`, `nb_mhz`, `nb_dbfs`, `nb_active`, `power_active`; the [ACTIVE] log line prints the line frequency.
  UI: status chip shows "line <MHz> +<dB>", detections table shows the line frequency (6 decimals), its level, and "line +x dB" / "power +x dB".
* MEASURED (generator 5.785 GHz, CH1 gain 65 dB, locked on Wi-Fi 5.8): every verdict ACTIVE by narrowband line at **5785.002441 MHz,
  +26.5 … +27.2 dB over the median bin, −25.9 … −26.6 dBFS**; the band-power rule alone stays inactive (band peak −19.0, floor −19.2).
  Gain 65 dB and the lock were restored from their files after the restart ("[pin] … LOCKED", "[gain] … 65.0 dB").
* TX advice given: raise the generator ≈ +10 dB from its current setting → line ≈ −15 dBFS (≈ 38 dB over the noise); no more than ≈ +20 dB
  (approaching full scale); cabled: TwinRX port must never see more than +10 dBm (damage limit), use attenuators.
* Open: false-alarm check of the narrowband rule on quiet bands over a full MON frame (and on CH2–CH4, which also use it now).

### 2026-10-22 18:3x–19:xx — user: "CH1: I can set the receiving gain … signal not strong, do we need more gain?" · "we are generating 5.785 GHz with a signal generator — check it is detected, I should see it clearly"
* **CH1 RX gain from the UI (live):** UI "RX gain [ ] dB / Set gain / applied … dB" (CH1) → bridge `gain` command → `edge_ch2/gain_ch1.txt` →
  mon_server applies it at the next look (clamped to the radio range, reported 0…99 dB) and RESETS that channel's band floors (else every
  band reads ACTIVE after a gain increase); the applied gain is in every detection verdict (`gain_db`). Verified: log "[gain] CH1 RX gain ->
  65.0 dB (UI); band floors of CH1 reset", UI shows "applied 65 dB".
* **MEASURED — CH1 noise does NOT depend on the gain:** gain 0 → 40 dB on Wi-Fi 2.4: noise (median 0.5 ms power, DC removed) −21.5 dBFS at
  every step (rise 0.00 dB per dB); the strongest Wi-Fi bursts rose from +0.7 dB (0–30 dB) to +2.6 dB (40 dB) over it; no clipping (max|x| ≤ 0.58).
  → CH1's floor is created AFTER the gain stage (not RF noise), so on CH1 more gain directly improves detection. Why the RX1 ports
  (CH1, CH3) have this fixed −22 dBFS floor is NOT found (hardware / port check needed; RX2 ports are 30 dB lower).
* **MEASURED — the user's 5.785 GHz generator tone on CH1 (locked on Wi-Fi 5.8, LO 5785.000 MHz, 16384-pt FFT, RBW 61 Hz):**
  gain 25 dB → not visible (below the floor); 45 dB → line at +2319 Hz = 5785.002319 MHz, −54.0 dBFS (+8.3 dB over the median bin);
  65 dB → same line −33.8 dBFS (+28.5 dB), i.e. +20.2 dB for +20 dB gain = a real RF signal; total level and median bin unchanged
  (−21.6…−21.9 dBFS, −62.3 dBFS/bin); max|x| 0.37. The +2.3 kHz offset (generator vs radio reference) keeps it clear of the DC filter.
  UI at 65 dB, 8192-pt FFT: peak readout 5785.0022 MHz ≈ −38…−41 dB; visible as a line, clearer when zoomed (±10 kHz).
* **NOT detected by the detector:** status "quiet", no detection rows — the detector uses the band's total power, and the tone (−34 dBFS)
  is 12 dB below CH1's broadband floor (−21.6 dBFS). Needs a narrowband (spectral peak) detector — proposed, not built.
* State left for the user: CH1 gain 65 dB, CH1 locked on Wi-Fi 5.8 (both changeable in the UI).

### 2026-10-22 18:1x — user: "in the polar plot no need to mention DF not built yet; if real data comes show it, if not don't show" — DONE
* AOA polar plot: the "no AOA data — DF not built yet" text removed; it shows only the empty polar grid, and bearings are drawn only when
  real AOA data arrives (no AOA source exists yet). Checked in the browser, 0 console errors.

### 2026-10-22 18:0x — user: "now remove that constellation plot also from CH1" — DONE, checked
* CH1 view: constellation sink removed (CH3 / CH4 panels keep theirs until those channels are reviewed). CH1 one-frame layout now: Frequency +
  Time on the left, AOA polar over the full right column, Detections row at the bottom. Reset layout uses the page's own default order.
* A first edit broke the page (the condition around the multi-line constellation tile was closed after its first line → AOA and Detections
  vanished); found in the browser and fixed. AOA radius now keeps the 0° / 90° / 180° / 270° labels inside the tile. 0 console errors at 1850 × 930.

### 2026-10-22 17:5x — user: "I should see all plots in 1 frame, and all plots should be draggable" — DONE, checked
* CH1 view is a one-screen dashboard: grid sized to the window (Frequency + Time wide on the left, Constellation + AOA on the right,
  Detections row at the bottom); page width no longer capped. Checked at 1850 × 930 (the user's Chrome size): everything visible, no scrolling.
* Tiles are draggable: drag a plot's title bar onto another plot → they swap places (plots redraw at the new size); the layout is
  remembered in that browser (localStorage, per-viewer convenience only); "Reset layout" restores the default. Inside a plot, drag still zooms.
  Checked: Constellation dropped on the Frequency place → swapped (Constellation 1039 px wide, Frequency 512 px), saved; Reset → default order.
  0 console errors. Same layout code serves the CH3 / CH4 panels.

### 2026-10-22 17:3x — user: "those options should show only when I click a control panel option" — DONE, checked
* As GNU Radio (control panel off by default): every sink (Frequency, Time, Constellation) starts with its control panel HIDDEN and the plot at
  full width; a "Control Panel" button in each sink's title bar shows / hides that sink's panel. Checked in the browser: hidden → plot 747 px;
  click → panel shown, plot 534 px, button highlighted; click again → hidden, 747 px. 0 console errors.

### 2026-10-22 17:xx — user: "still graphs are not good in CH1 … copy the GNU Radio graph style and set it 100 % same" · "remove waterfall graph" — DONE, checked in the browser
* Reference taken from the REAL GNU Radio 3.8 qtgui sinks on this PC: freq_sink_c, time_sink_c, waterfall_sink_c, const_sink_c rendered
  off-screen (GRC default settings, plus grid + control panel) to PNG (`monitoring/guru_mon_scan/tools/render_gr_sinks.py`), then copied:
  light-grey widget, white canvas with grey frame, black axes with major + minor (5 per major) ticks, 13 px DejaVu Sans labels, bold 15 px axis
  titles, 1 px traces Data 0 = blue / Data 1 = red, legend right of the canvas, default ranges Freq −140…10 dB ("Relative Gain (dB)",
  "Frequency (MHz)", 3 decimals), Time ±1 ("Amplitude", "Time (us/ms)" with thousands separators), Constellation ±2 ("In-phase" /
  "Quadrature", filled blue dots), dotted trigger-level line, Qwt-style tracker text next to the cursor, left-drag zoom box, right-click = zoom
  out one step, double-click = reset; left margin sized to the tick labels.
* GNU Radio control panels next to each plot: Frequency — Trace Options (Max Hold, Min Hold, Avg slider), Axis Options (Grid, Axis Labels,
  Y Range ±10 dB, Ref Level ±10 dB, Autoscale), FFT (size, window: Blackman-harris default as GRC), Trigger (Free/Auto/Normal, Level ±),
  Extras (Stop, Save Image, Export CSV); Time — Axes (Autoscale, Grid, Axis Labels, Y Offset ±, Y Range ±, X Max ±), Trigger (mode, slope,
  channel, Level ±, Delay ±), Extras (Autoscale, Stop, Save Image, Export CSV); Constellation — Axes (Autoscale, Grid, Axis Labels, Range ±),
  Extras (Stop, Save Image).
* Waterfall sink (built in the GNU Radio look: Multi-Color map, Time (s) axis) — REMOVED on the user's request.
* Checked in the built-in browser: 0 console errors, all CH1 sinks drawing live data. Ctrl+Shift+R needed in the user's Chrome.

### 2026-10-22 15:xx–16:xx — user: "remove DC offset from all channels, all bands should detect when active" · CH1 UI: one band = lock, MON plan = run the plan, all GNU Radio plot options · "graphs lag, not proper" · "continuous signal, not discrete" · "come only for CH1 now" — DONE, VERIFIED on the X310
* **DC removal, all 4 channels** (`mon_server.py`, right after the radio, before the detector AND the published IQ): y = x − single-pole
  low-pass(x), alpha 0.001 (≈ 160 Hz high-pass at 1 MS/s), option `--dc-alpha` (0 = off). MEASURED DC left (median): CH1 −6 → **−56 dBFS**,
  CH3 −8 → −56, CH2 → −116, CH4 → −96. Time plot and constellation now centred on 0. A small near-centre component remains on CH1
  (≈ −42…−45 dBFS per bin, ≈ 8 dB over the noise, visible in the waterfall) — open.
* **Detector rebuilt (sample-accurate)** — new block `look_power.py`: starts at each look's stream tag, skips the first 14 ms (10 ms switch +
  retune transient + 2 ms chunk), peak of 0.5 ms power windows over the rest of the look; mon_server reads it at the end of the dwell.
  Reason (MEASURED): the PC-timed probe still saw the retune transient — on CH2 98 % and on CH4 almost all of the loud 0.5 ms windows sat in
  the first 10 ms of a look (broadband, at 0 Hz). Floor = lowest look peak per (channel, band); **ACTIVE margin 8 → 2.5 dB** (quiet-band
  noise peaks measured within +1.4 dB of the floor). Verdicts published on ZeroMQ 5210 (one JSON per dwell) → bridge → UI detections table.
  75 s result (2.5 dB, before the 14 ms skip): CH1 quiet bands 5.2 / 5.8 / Video **0 % ACTIVE**, Wi-Fi 2.4 active when Wi-Fi is on air
  (60 % in one run, real narrow carriers at 2441.98 / 2442.06 MHz seen while locked); CH4 cellular bands 8–57 %; CH3 63–77 % (RX1-port noise
  −20 dBFS, not yet understood).
* **CH2 / CH4 events — OPEN (user: "come only for CH1 now")**: short (0.5 ms) broadband bursts at 0 Hz in the middle of looks on CH2 (and CH4).
  Board-mate retune test: CH1 + CH3 held (no retunes) 15.7 events/s on CH2, all scanning 0.9 events/s → NOT explained by the board-mate
  retunes; the event rate changes a lot with time. Not radios (radios are long and 12.5 kHz wide). To continue later.
* **Lag fixed (MEASURED):** load was 11.3 on 12 cores, mon_server 156 % CPU, pipeline stalls up to 257 ms (no UHD overflows — an earlier count of
  "O" was letters in words, corrected). (1) `mon_pub` works in 2048-sample chunks (was 364-sample network packets, ~2,700 Python calls/s/ch);
  (2) the bridge sends full graph data only for the channel being viewed, as BINARY (`MON1` + header + float32 spectrum / I / Q) at 10 Hz,
  other channels a small JSON status at 2 Hz. After: mon_server 89–100 %, bridge 66 → 22–25 %, router 36 → 20 %. Load still 9–14 because of the
  CH2 decode chain (allinone 72–75 %, backupv1 bridge 25–41 %), kernel workers and the CPU governor `powersave` (user setting).
* **CH1 band lock (MEASURED end to end):** UI "Receiver" menu = "MON plan — all bands (47 looks, 14.26 s frame)" + every band of the REAL plan
  (sent by the bridge from `scan_plan.py`, with dwell and count ×10 / ×1 / ×2). Choosing a band → bridge writes `edge_ch2/pin_ch1.txt` →
  mon_server holds that band (no retune between dwells) — log "[pin] CH1 LOCKED on 'Wi-Fi 2.4 2412-2472'", 6 s of status = that band only;
  choosing "MON plan" → "[pin] CH1 back to the MON plan", the bands rotate again. `scan_plan.find_band` also finds DroneID listen.
* **GNU Radio-style graphs (CH1 panel; CH3 / CH4 panels share the code but keep the display-only band filter):** frequency: Run/Stop, FFT size
  256…8192, window (Hann, Hamming, Blackman, Blackman-Harris, Flat-top, Kaiser, Rectangular — computed in the bridge), averaging Off/Low/Medium/High
  (0.2 / 0.1 / 0.05), max hold, min hold, clear holds, peak marker, Y min/max, Auto Y, one-shot Autoscale, reset zoom, grid, PNG, CSV;
  waterfall (new): per-band history 300 rows at 10 rows/s, colormap Turbo/Viridis/Hot/Gray, auto / manual intensity, clear, PNG;
  time: Run/Stop, points 256…4096, show I+Q / I / Q / |x| / phase, line / dots, trigger Free / Auto / Normal, source I / Q / |x|, level, slope,
  delay, Y min/max, Auto Y, autoscale, reset, grid, PNG, CSV; constellation: Run/Stop, points, fixed range or auto, grid, PNG; mouse: drag = zoom,
  wheel = X (shift = Y), shift+drag = pan, double-click = reset, cursor readout. Y stays fixed unless Auto Y (no jitter, like GNU Radio).
* **Bugs fixed while testing:** the UI loop used requestAnimationFrame, which the browser pauses when the tab/pane is not visible → now a 33 ms
  timer; zoomed traces were drawn as separate vertical bars ("discrete") because the draw mode looked at all samples, not the visible ones →
  now always one continuous line (every sample joined when zoomed in, min/max envelope when there are more samples than pixels).
  Verified in the browser pane: 0 console errors.
* User's Chrome: press **Ctrl+Shift+R** — the screenshots were from a cached older page.
* Open (CH1): DroneID listen frequency; RX1-port noise ≈ 30 dB above RX2 (hardware); residual near-centre component; CH2/CH3/CH4 later.

### 2026-10-22 14:xx — user (screenshot of the CH1 UI): "is this UI detecting a signal? if it is in the frequency plot why not in the time graph with the correct offset?" — ANSWER MEASURED: the spike is the receiver's DC offset, not a signal
* Raw CH1 IQ, 30 s, 16384-point FFT (61 Hz bins), first 12 ms of every look dropped, all 8 CH1 bands (433 MHz … 5.9 GHz): the spike sits at
  **exactly 0 Hz offset** on every band, 57–59 dB over the median bin, and the sample mean is the same complex number everywhere:
  I ≈ −0.31, Q ≈ −0.31 (|DC| 0.43–0.52 = −7.4 … −5.7 dBFS), stable across looks over 30 s. A constant I/Q value is exactly what a time plot shows
  as traces shifted away from zero (blue ≈ −0.3, red ≈ −0.3 in the screenshot) — a tone at offset f would show as a sine of frequency f. After
  subtracting the mean, no peak stands out (12–13 dB over the median bin on 7 bands = noise extremes; DroneID listen 19 dB at +31 kHz in 2 looks —
  only candidate, not confirmed).
* **Consequences:** (1) the old UI "rms −5.6 dBFS" was the DC, the real signal level (DC removed) is ≈ −22 dBFS; (2) the scanner's ACTIVE rule
  (floor + 8 dB) on CH1 would need a signal above full scale → **CH1 can practically never read ACTIVE** (matches: no CH1 ACTIVE line all day);
  (3) the screenshot status "scanning" (not ACTIVE) was correct.
* **Port pattern (new, measured via the bridge):** DC offset / noise (DC removed) in dBFS — CH1 A/RX1 gain 25: DC −5.8 / −21.7; CH3 B/RX1 gain 25:
  −7.8 / −22.8; CH4 B/RX2 gain 25: −79.5 / −52.3; CH2 A/RX2 gain 10: −56.5 / −73.3. Both RX1 ports show a huge DC and ≈ 30 dB more noise than the RX2
  ports at the same gain → something differs on the A/RX1 and B/RX1 paths (antenna / amplifier / bias / port). Cause NOT found; not fixed.
* **Changed (bridge + UI, verified in the browser):** `mon_ws_bridge.py` now measures the DC offset (`dc_i`, `dc_q`, `dc_dbfs`) and computes rms, floor and
  ACTIVE on the DC-REMOVED signal; the UI shows a "DC offset … dBFS (I, Q)" chip, "scanning x dBFS without DC", "peak excl. DC" (the DC bins ±3 are
  skipped) and "signal rms · DC" on the time plot. The spectrum still shows the DC spike (as a GNU Radio sink would). The scanner (`mon_server.py`) detector
  is NOT changed (still counts the DC) — needs the user's decision.
* **Options for the DC (not applied, waiting for the user):** (a) DC removal in the receive chain before the detector and the publish (mean-subtract / high-pass,
  costs ≈ 0 for signals wider than a few kHz); (b) detector on DC-removed power only; (c) tune the LO a few 100 kHz off the wanted band so the spur falls
  outside it; (d) find why the RX1 ports are so different (hardware).

### 2026-10-22 13:xx — user: "update all things related to cha 1" · CH1 UI like GNU Radio graphs, draggable, AOA polar zero, no dummy data · "conventional 10 cycles, 1 DroneID, 2 unconventional" — DONE and VERIFIED on the X310
* **Scan plan:** `scan_plan.py` DroneID listen 2010 → **2000 ms** (+10 ms switch). Frame now 14,256 ms = 10 × 1,065 + 2,010 + 2 × 798, 47 looks.
  Cycles as the user states: conventional ×10, DroneID ×1, unconventional ×2 — confirmed in the live stream (28 s ≈ 2 frames: 19–20 looks of each
  conventional band, 2 DroneID, 4 of each unconventional band).
* **MEASURED real look length** (samples in the published stream ÷ 1 MS/s, one look = switch + dwell) vs plan: Wi-Fi 2.4 267.8 / 5.2 267.0 /
  5.8 267.4 ms (plan 266), LoRa 268.7 (267), DroneID 2,012.7 (2,010), 433 267.6 / FPV 267.5 / Video 267.8 (266) → each look runs 1–3 ms longer than
  plan (host `sleep` + tune call); estimated frame ≈ 14.33 s instead of 14.256 s (+0.5 %). Order inside the frame correct.
* **ROOT CAUSE of the CH2 decode problem (found while adding the sample rate to the header, fixed, measured):** `mon_pub` headers had no `samp_rate`;
  `ch2_header_router.py` then assumes 2 MS/s, but the watchdog runs 1 MS/s → decimation 10 instead of 5 → decoder port got IQ at 100 kS/s into a
  200 kS/s stream: before the fix the P25 port showed real IQ and zero fill alternating every 20 ms during each dwell (`R.R.R.R.`, ≈ 52 % real);
  after the fix each dwell arrives as one continuous run (`RRRRRRRRRRRRRRRRR`, 17–23 ticks per 450 ms dwell). Fix: `mon_pub.py` / `mon_server.py`
  put `samp_rate` in every header. Decode itself still NOT re-tested with a keyed radio.
* **UI (`securecom_ui.html`, all four signal panels share the code; verified in the built-in browser, 0 console errors):** frequency and time
  graphs with axes and units (MHz, dBFS, ms, full-scale amplitude), GNU Radio behaviour: drag = zoom box, wheel = scale (shift = y), shift+drag = pan,
  double-click / Reset zoom, Autoscale, Max hold, cursor readout, "zoomed" marker; time plot shows real I (blue) and Q (red); AOA polar plot is
  empty ("0 bearings", "no AOA data — DF not built yet"); IQ scatter kept as a separate real-data panel; "Show band" filter learns the band
  names from the live feed (replaces the fake Scan / Pin buttons). CH1 subtitle fixed A/RX2 → A/RX1.
* **Dummy data removed:** the hardware chips (LO lock all green, Overflow "no", CPU "performance", Link "1 Gb/s") were hard-coded placeholders —
  replaced by live facts only (feed connected, CH1–CH4 live / no data from message age, sample rate from the header, Mode MON) plus the note
  "LO lock · overflow · CPU: not reported by the backend yet". The "Monitoring Backend" tab is labelled as a saved editable copy that does not
  control the scanner; its CH1 list now matches the plan (with a Cycles column), CH2–CH4 values are still the old copy.
* **Bridge (`mon_ws_bridge.py`) rewritten:** per-look buffer, first 12 ms (switch) dropped, ≥ 4096 settled samples before a push, 1024-point FFT
  averaged over up to 8192 samples (dBFS, full-scale tone = 0 dBFS), 2048 raw I/Q samples, per-band floor = lowest rms seen (the old floor started at
  −120 dBFS and never rose → every channel showed ACTIVE all the time; fixed). The watchdog restarted the bridge by itself after I killed it (20 s).
* **New finding (visible in the new time plot):** CH1 raw IQ has a large DC offset — I ≈ −0.2, Q ≈ −0.4, a spur exactly at the centre frequency
  ≈ −6 dBFS, ≈ 40 dB above the noise, on every CH1 band (same DC-spur problem as CH2). `set_dc_offset(True)` does not remove it. Not fixed.
* **Tool note:** the Claude-in-Chrome extension is not connected; I checked the UI in the built-in browser pane (the user's Chrome has the page open
  via `xdg-open`; hard-reload it with Ctrl+Shift+R — the old page is cached). The synthetic drag of the test tool left the zoom box on screen; real mouse
  events (dispatched from the page) zoomed and finished correctly.
* **Not done / open:** DroneID listen frequency; detector still reads only the end of each dwell (not approved); DC offset; CH2–CH4 review; a long run
  (load average was ≈ 8–10 before this restart, not re-measured).

### 2026-10-22 12:3x — user: CH1 first — bands, dwell, frame and cycles explained with a block diagram; "for DroneID set 2 sec, and don't edit now, note it down; we check the other channels and I tell all edits at once"
* Read from `scan_plan.py` (nothing run, nothing edited): CH1 = ch0 A/RX1, 47 looks per frame, each look = 10 ms switch + dwell
  (dwell = 2.5 × repeat time). Conventional cycle ×10: Wi-Fi 2.4 (2412–2472, centre 2442) 256 · Wi-Fi 5.2 (5180–5240, 5210) 256 ·
  Wi-Fi 5.8 (5745–5825, 5785) 256 · LoRa SF7 (865–928, 896.5) 257 ms → 1,065 ms per cycle, 10,650 ms. DroneID listen ×1: 2010 + 10 =
  2,020 ms (centre 2442 MHz = placeholder). Unconventional cycle ×2: Drone 433 (433.05–434.79) · FPV 1080–1280 · Video 5645–5945,
  256 ms each → 798 ms per cycle, 1,596 ms. Frame 14,266 ms (computed from the plan, not measured).
* **Decision:** DroneID listen = **2 s (2000 ms dwell)**; recorded under PENDING EDITS in CURRENT STATE, **not applied**. Then the CH1
  frame is 14,256 ms. The user collects the edits of all channels and gives them together.
* Still open for CH1: the DroneID listen frequency; whether the detector should use the whole dwell (suggested, not approved).

### 2026-10-22 12:0x — user: "check channel 2 not working correctly" — CH2 DIAGNOSIS (measured on the running system, nothing changed)
* **Data flow and timing are correct.** 10 s tap of ports 5201–5204: every channel 1.000 MS/s, blocks of 364 samples
  (≈ 2,400 msgs/s/channel), no gaps. CH2 samples per band in 10 s match the plan within ≈ 5–10 % (P25 4.16 M, NXDN
  1.90 M, DMR 1.36 M, TETRA 1.23 M, D-STAR 0.53 M, AIS 0.41 M, ADS-B 0.41 M; plan 450/200/150/142/50/400/400 ms per cycle).
* **Found 1 — DC spur dominates every CH2 look.** Raw IQ per dwell (60 s, first 15 ms of each dwell dropped, 1 MS/s):
  in ALL 7 CH2 bands ≈ 100 % of the power sits within ±3 kHz of DC, the spectrum peak is exactly 0.0 kHz and 47–49 dB over
  the median, and the wideband level reads the same −57.3 dBFS on every band (145 MHz … 1090 MHz) → **the CH2 "floor" is the
  DC / LO spur, not thermal noise**. Strongest non-DC peak only 1–9 dB over the median; 0 loud dwells (rms > −45 dBFS) in
  the 60 s window. So: weak real signals sit below the spur and cannot trigger "ACTIVE" (floor + 8 dB), and the console's
  "P25 carrier at +0.00 kHz, +30 dB SNR, no decoded audio" is this spur, not a radio. `set_dc_offset(True)` in
  `mon_server.py` does not remove it.
* **Found 2 — real events do happen:** 11:53–11:55 the scanner logged DMR 446.100 / NXDN 451.0 / P25 450.0 up to −19 dBFS,
  rising together over ≈ 6 s, and D-STAR 145.0 once at −3.6 dBFS. Whether these were hand-radios or broadband leakage was
  NOT separated (nothing was keyed during the 60 s IQ capture). Open.
* **Found 3 — the CH2 console (`securecom_gui.html`, old backupv1 code) does not match the scan plan:** its band centres are
  DMR 446.11853 / NXDN 451.09375 / P25 450.09375 / TETRA 420.0 MHz, the radio is tuned to 446.100 / 451.0 / 450.0 / 420.0
  (offsets 18.5 / 93.75 / 93.75 kHz) — whether the router re-centres the IQ is not shown in `ch2_header_router.py` (no shift found).
  The console also says "USRP · B210 · RUNNING" (the radio is the X310), and it saves a `.wav` for EVERY dwell ("saved
  dmr_… 0.7 s, dwell captured") even when nothing is on air → the thousands of recordings are mostly empty/false.
* **Found 4 — decoder taps:** DMR / NXDN / P25 audio taps stream 48 kHz continuously (silence); TETRA tap 0 messages in 5 s
  (not shown whether that is normal when idle). `allinone.py` start-up prints are static (not a restart loop).
  `backupv1_bridge.log` fills with `InvalidMessage: did not receive a valid HTTP request` (130×) = the watchdog's plain TCP
  port probe, harmless noise.
* **Load:** `mon_server` 126 %, `mon_ws_bridge` 86 %, `allinone` 72 %, router 51 %; load average 3.3 → 6.5 → 10 within 6 min on
  12 cores (the bridge handles every 364-sample message separately; likely cause of the earlier "getting stuck").
* **UI labels:** CH1 panel subtitle says "A/RX2" (CH1 is A/RX1). UI "ACTIVE" is always on (bridge floor bug, see the 11:5x entry).
* Not done / next: waiting for the user — channel-by-channel dwell setup was requested right after this diagnosis.

### 2026-10-22 11:5x — user: "RUN THAT monitoring work and show me UI result … in chrome … I have connected 2945" — RAN ON THE X310: OK
* Before: NIC `enp3s0` = 192.168.10.1/24 (profile `usrp` active), X310 ping 0.63 ms, ports free.
* Started `run_monitor.py --gain 25 --ch2-gain 10 --samp-rate 1e6 --squelch -45` (log `/tmp/run_monitor.log`):
  all 8 parts up in ≈ 30 s (`[watchdog] all up`), **0 restarts, 0 errors / tracebacks in `mon_server.log`**,
  `[hb] alive` every 5 s, ports 5201–5204 (PUB), 7001, 8099 (UI), 8780 (ws), 8787, 8788 listening.
  Load average rose to ≈ 6.8 after start (watch for stalls in a long run — not yet run long today).
* UI feed read directly on ws 8780 (12 s): all 4 channels deliver real data every push — 256-point spectrum,
  256-point time envelope, 160 IQ points (CH1 LoRa 865-928, CH2 NXDN 451.0, CH3 C 5400-5900, CH4 2G 925.2-934.8).
  `securecom_ui.html` and the CH2 console (:8788) answer HTTP 200. The CH2 router routes blocks to all 4 decoder ports.
* Scanner `[ACTIVE]` after the first minute: CH4 busy on every cellular downlink band (B5 869-894 strongest,
  −23 dBFS; B40 −21, B28 −35); CH2 saw DMR 446.100 (−19), NXDN 451.0 (−20), P25 450.0 (−26), TETRA 420.0 (−40),
  D-STAR 145.0 (one reading at −3.6 dBFS, close to clipping); CH1 and CH3 had no ACTIVE line (quiet by the
  scanner rule: floor + 8 dB).
* **Browser:** the Claude-in-Chrome extension was NOT connected, so I could not drive or screenshot Chrome; the UI
  was opened in the default browser with `xdg-open` (not confirmed on screen by me).
* **New bug found (visible in the UI feed):** `edge_ch2/mon_ws_bridge.py` starts its rolling floor at −120 dBFS and
  only raises it when `rms < floor + 8` → never true, so the floor stays −120 and **every channel is marked
  active=True all the time** (e.g. CH2 at −55.7 dBFS, floor −120). The UI "ACTIVE" is therefore wrong; the scanner's
  own `[ACTIVE]` log (its own floor per band) is the right one. Fix proposed (floor from the first readings / track
  the minimum), not done yet — waiting for the user's go.
* Mode: CH2 came up in Mode 1 (scan all bands); `ch2_mode.txt` can hold `auto` from an earlier session.

### 2026-10-22 11:4x — user: "https://github.com/shankarjatti/mon_update — keep updating on this github repo always … until I tell you"
* Repo found EMPTY and PUBLIC; `gh` logged in as shankarjatti. Published a curated first set (41 files, 436 KB):
  `monitoring/guru_mon_scan` (scanner, `scan_plan.py`, `mon_pub.py`, UI, `BUILD_LOG.md`), `monitoring/edge_ch2`
  (watchdog, UI bridge, CH2 router), `monitoring/terrestrial38` (decoder glue), `design/monitoring_sim.html`,
  `docs/` (this log, `DSD38_PORT_PLAN.md`), `README.md`, `sync.sh`. Checked before push: no secrets, no `main_sched`
  / design-sheet / slides references, nothing over 2 MB.
* **Left out on purpose:** `main_sched/` (private), `decode_dmr.wav` (10 GB), result CSVs (52 MB), recordings,
  tarballs, `gr-dsd` / `gr-tetra` sources (59 MB / 6.7 MB, prebuilt libs; saved locally in
  `terrestrial_port_v1.tar.gz`), the old frozen repos. Ask the user before adding any of them.
* **Decision (mine, user may correct):** this repo's `docs/WORK_LOG.md` is now the single LIVE log; the copy in
  guru_switch_mon-df gets a pointer and stops, so the two do not drift.
* **Mistake caught and fixed during this step:** the first clone failed (DNS blip) and my script went on in the
  wrong folder: it created empty `monitoring/`, `design/`, `docs/` in `~/radar2` and switched the lab repo
  `~/radar2` from `master` to a new branch `main`. Both undone (back on `master`, branch deleted, empty folders
  removed with `rmdir`); no file was changed or lost (the lab repo's uncommitted edits are untouched). The redo ran with
  absolute paths and `set -euo pipefail`; `sync.sh` has the same guards.

### 2026-10-22 — user: "check that monitoring work … based on the monitoring and DF html file … what is done, what is to do" · "check how to run" · "keep updating on .md file always"
* **Read-only check, nothing was run.** The X310 was not reachable: NIC `enp3s0` was on "Wired connection 1"
  (192.168.0.180), not the saved `usrp` profile (192.168.10.1/24). Compared `~/radar2/monitoring_sim.html`
  (design) with `guru_mon_scan`, `edge_ch2`, `BUILD_LOG.md`, the activity CSVs and the memory notes.
* **Done and run on the X310 (per BUILD_LOG / edge_ch2 README, not re-run today):** 4 channels scan in parallel
  (CH1 47 looks, CH2 42, CH3 5, CH4 9), MON retune + lock worst 6.7 ms (switch kept at 10 ms), ZeroMQ PUB 5201–5204
  (header: ch, band, freq, look, frame, host_time, n), 5-panel UI on real data, activity CSV (17 logs 14–16 Oct;
  longest run 16:53 → 17:46 on 16 Oct), watchdog `run_monitor.py` (CH2 gain 10, 1 MS/s), CH2 router + 4-protocol
  decoder chain live, `--pin`, `--look-bw`.
* **Gaps found (from reading the code and the logs; hardware not re-measured):**
  1. One look = `--samp-rate` wide (1 MS/s in the watchdog) at the band centre → ≈ 1 MHz of bands that are
     25–760 MHz wide. The design's 80 MHz look needs ≥ 100 MS/s per channel (dual 10 GbE).
  2. `mon_server.py` reads a 2000-sample moving average ONCE at the end of the dwell → only the last 1–2 ms of the
     dwell is judged; bursts earlier in the dwell are missed (needs peak / max over the dwell).
  3. CH3 "ACTIVE" = wideband energy, 10–12 dB over floor on every radar band; a 2 ms average hides µs pulses and
     cannot separate radar from Wi-Fi. No radar detection yet.
  4. `scan_plan.py`: CH3 dwell 160, CH4 dwell 20, DroneID 2010 are the sim's look totals that already contain the
     10 ms switch; the code adds `SWITCH_MS` again → CH3 850 ms (plan 800), CH4 270 ms (plan 180), CH1 14,266 ms
     (plan 14,256). To confirm with the user, then fix.
  5. Timing is host `time.sleep` in 4 threads (real switch probably ≈ tune time + 10 ms; not measured — use
     `MON_DBG_TIMING=1`); tags carry host time, not radio time; blocks around a retune can mix two bands;
     `mon_server.py` (the running path) does not read the LO lock — only the older `mon_scan.py` GUI does.
  6. Pub-Sub carries IQ + header only; the FFT is made in the UI bridge (design says IQ + FFT).
  7. Terrestrial decode: thousands of `.wav` recordings (dmr / nxdn / p25) exist, all protocols firing in the same
     second at times → they include false triggers; no recorded proof of one correct decode (talkgroup / ID).
  8. Sim: the CH1 and CH2 timelines leave out the 10 ms switch (13.8 s / 8.7 s vs labels 14.26 s / 9.16 s).
     DroneID listen sits on 2.442 GHz as a placeholder; DMR is on 446.100 (the radio's real frequency).
* **DF side of the sim: not built.** No request path, priority scheduler (drone ×5 / others ×2), manual approve,
  emergency, DF Pub-Sub or AOA in `guru_mon_scan`; the UI has no DF controls. The MON↔DF switch itself is proven in
  guru_switch, but its MON mode has 4 fixed bands (cannot run 47-look frames) and `mon_server` is untimed Python →
  two code bases to merge. Open: field calibration with real antennas; one array for DF and monitoring or two;
  the 5 emergency questions of the 2026-10-05 entry.
* **How to run (checked: all files exist, GR 3.8 + UHD 3.15 python modules import, system python has numpy / zmq /
  websockets, `paplay` for audio, all ports 5201–5204 / 7001–7004 / 8099 / 8788 / 8780 / 8787 free):**
  `sudo nmcli connection up usrp` → `ping 192.168.10.2` → X310 on, 4 antennas on A/RX1, A/RX2, B/RX1, B/RX2 →
  `cd ~/radar2/edge_ch2 && python3 -u run_monitor.py --gain 25 --ch2-gain 10 --samp-rate 1e6 --squelch -45`
  (look for `[watchdog] all up`, ≈ 30 s) → http://127.0.0.1:8099/securecom_ui.html (the `guru_mon_scan/README`
  path `:8099/guru_mon_scan/…` is wrong for the watchdog, which serves from `guru_mon_scan`) → stop with ONE Ctrl-C
  (never kill the scanner one by one: can leave the X310 stuck). Do not press "Start decoder" (the watchdog starts
  it). Logs: `/tmp/mon_server.log` (`[hb] alive` every 5 s), `guru_mon_scan/results/activity_*.csv`.
* **Suggested order (waiting for the user's go):** fix the double-counted switch time → detector = peak over the
  dwell + LO lock + radio-time tags in `mon_server` → measure the real look timing and a long run → prove one
  correct DMR decode → then DF (request path + scheduler with manual approve, then the engine merge).
* **Rule from the user today: "keep updating on .md file always"** → every stage and every answer that changes the
  state goes into this log (and CURRENT STATE) in the same turn.

### 2026-10-08 … 10-16 — MONITORING BUILT (backfilled on 2026-10-22 from `guru_mon_scan/BUILD_LOG.md`, `README_MON_SCAN.md`, `edge_ch2/README.md`; numbers are those sessions' measurements, not re-run today)
* Setup change 2026-10-08: no HackRF — 4 real antennas on the 4 TwinRX ports, DMR hand-radios as the live source
  (CH2 band 446.100 MHz); NetworkManager profile `usrp` (enp3s0 = 192.168.10.1/24, never-default) fixes the NIC address.
* `guru_mon_scan` made from guru_switch (originals untouched). Plan A (monitoring) before B (DF).
  A1 retune measured (`mon_scan_retune.py`): CH1 6.2 / CH2 6.2 / CH3 6.7 / CH4 5.8 ms worst, LO relocks every retune.
  A2/A3/A6: `mon_scan.py` GUI, 4 channels in parallel, per-channel band table + FFT + time graph + ACTIVE/quiet.
  A4/A5: `mon_pub.py` (stream tag + ZeroMQ PUB 5201–5204), `mon_server.py` (headless), `mon_sub_example.py`;
  verified offline by loopback (12,964 messages, correct headers). Look splitting (`--look-bw 80e6`), activity CSV,
  `--pin "CH=BAND"`. Monitoring verified on hardware 2026-10-12; frozen `guru_mon_scan_v1` (12 Oct), `_v2` (+pin, 12 Oct).
* Terrestrial module (user's repo, B210 + GR 3.10 + UHD 4) ported 2026-10-12 to GR 3.8 C++ OOTs: `gr-dsd`
  (DMR / P25 / NXDN / D-STAR) and `gr-tetra`; saved as `terrestrial_port_v1.tar.gz`.
* 2026-10-14 (X310): all channels scanned and published, CH3 ACTIVE on C 5650 / S 3250; CH2 console embedded and live.
  `edge_ch2`: CH2 header + router (5202 → TCP 7001–7004 by protocol), UI bridge `mon_ws_bridge.py` (ws 8780), 5-panel
  `securecom_ui.html`. B210 unusable on USB 2.0 (LIBUSB_TRANSFER_OVERFLOW) → the X310 is the target.
* 2026-10-16: root cause of false cross-detections ("DMR detecting at 450") and ruined decode = CH2 ADC overload
  (close keyed hand-radio at gain 25 read −0.9 dBFS) → `--ch2-gain 10` (keyed radio ≈ −16 dBFS); sample rate 1 MS/s
  (2 MS/s × 4 pushed `mon_server` to 180 % CPU, load ≈ 10, stalls); `mon_ws_bridge` FFT capped; watchdog
  `run_monitor.py` restarts a stalled component (mon_server only after the X310 re-enumerates). CH2 Mode 1 (scan all)
  / Mode 2 (auto-detect, lock the strongest, release after 2 silent dwells).
* Open then: DMR decode (frequency match / clipping) — see the 2026-10-22 gaps.

## 2026-10-05

### 2026-10-05 — REQUIREMENT: emergency mode skips DF approval (spec only, nothing built)
* User: *"in emergency mode no need to wait for DF approval"*.
* What it changes: today the mode changes **only by hand** with the MODE selector and the
  control API is off by default. This is the first case where a DF request would move
  MON → DF with no operator action, i.e. the control API path has to be live under an
  emergency condition.
* Not built. Questions that change the architecture, waiting on the user:
  1. What raises "emergency"? A flag on the edge module's DOA request, a separate operator
     arm switch, or a classification by the priority scheduler?
  2. Where does it preempt? Abort the MON look in progress, or at the next slot boundary?
     (the engine switches at a slot boundary today; mid-look abort is new work)
  3. How does it go back to MON? Fixed DF dwell, operator release, or when the emergency
     clears?
  4. Two emergency requests at once — what decides?
  5. **Calibration.** DF runs CALIBRATE at every start today. An instant emergency DF has no
     time for it, so it has to use a stored per-band calibration. Offsets re-randomise on
     every power cycle and drift with RF frequency, so the stored set has an age limit —
     what is acceptable, and what should happen when it is stale?
* Related known limits to carry into the design: TwinRX will not retune into 5.0–5.14 GHz
  (UHD picks a high-side LO1 that never locks); ~1–2 % DF slots late when the PC is busy.


### 2026-10-01 … 10-05 — MONITORING PLAN (architecture only: no code, no measurements)
* User: "no we not going to building any code project now, I need to give architecture" · "no file creation,
  just analyse … make plan and update block diagram" · "we'll come only for MONITORING". Inputs: the user's design
  sheet (Frequency List tab = bands per module; its dwell column NOT used) and timing slides; per-channel
  plans and block diagrams were made in chat. **Everything below is from standards / the sheet, not measured.**
* Rules decided by the user:
  * every look = **(T_pkt + T_rep) × 2.5 + 10 ms switch** (T_pkt = one packet/pulse on air, T_rep = gap to the
    next one from the same transmitter); **switch 10 ms everywhere**; bands from the sheet only.
  * CH3 radar: **150 ms dwell per look** (user override); CH4: **10 ms dwell per band** (user override).
  * one look = one LO tune; 80 MHz wide looks assumed (needs ≥ 100 MS/s per channel = dual 10 GbE; today's
    1 Gb/s gives ~4 MHz looks).
* **CH1 — ch0 A/RX1 — Drone + Replay/DoS — frame 14,256 ms**
  * Conventional × 10, 1,065 ms per cycle: Wi-Fi 2412–2472 · 5180–5240 · 5745–5825 (beacon 102.4 ms × 2.5 =
    256 ms each) + LoRa 865–928 (SF7, 51 B packet 103 ms × 2.5 = 257 ms) = 10,650 ms.
  * DroneID listen 10 ms + 2 s = 2,010 ms.
  * Unconventional × 2, 798 ms per cycle: 433.05–434.79 · 1080–1280 · 5645–5945 (256 ms each) = 1,596 ms.
    865–928, 2399.5–2483.5, 5150–5250 left out (ISM, already covered by the conventional cycle).
* **CH2 — ch1 A/RX2 — Terrestrial + Air/Maritime — frame 9,156 ms**
  * Terrestrial × 8, 1,042 ms per cycle (dwell ms): D-STAR 145.0 (20 + 0 → 50) · TETRA 420.0 (14.17 + 42.5 → 142)
    · DMR 446.00625 (27.5 + 32.5 → 150) · P25 450.0 (180 + 0 → 450) · NXDN 451.0 (80 + 0 → 200) = 8,336 ms.
  * Air & maritime × 1: AIS 161.975 (400, same as ADS-B — user) · ADS-B 1090 (0.12 + 160 → 400) = 820 ms.
  * Gaps are for ONE radio (handheld: DMR 32.5 ms, TETRA 42.5 ms), not slot-to-slot (2.5 / 0.25 ms).
* **CH3 — ch2 B/RX1 — Radar — frame 5,120 ms**: 32 looks × (150 + 10 ms): L 1200–1400 (3) · S 2700–3100 (5) ·
  S 3000–3500 (7) · C 5140–5900 (10; 5000–5140 cannot be tuned) · C 5400–5900 (7, inside the C row above).
  Without the duplicate row 4.0 s; one look per row 0.8 s (user to choose). Earlier PRI rule (2.5 × slowest PRI:
  L 10, S 8.3, C 25 ms) replaced by the 150 ms.
* **CH4 — ch3 B/RX2 — cellular downlink only — frame 300 ms**: 15 looks × (10 + 10 ms): 10 sheet bands
  (3 × 2G, B28, B5, B8, B3/n3, B1/n1, B40 × 2 looks, n78 × 5 looks). n78 sync repeats every 20 ms → seen ~half
  the time at 10 ms. One look per band: 200 ms.
* **Data paths** (block diagram):
  * MON (parallel): scheduler → **4 Pub-Sub links**, one per channel (IQ + FFT + tags: channel, LO freq,
    look/frame id, radio time) → its edge module → its UI.
  * Control Pub-Sub: detections + DOA requests → scheduler.
  * DF (sequential): **PS 1–4 OFF**; shared LO, DF bursts → AOA → **one DF Pub-Sub** (IQ + FFT + az/el + tags)
    → the related module → its UI; then back to MON, PS 1–4 on. MON ↔ DF switch stays manual.
* Open: CH3 150 ms per look or per row; CH4 merge 2G into B8/B3; where edge modules run (80 MHz raw IQ is
  ~800 MB/s per link → same PC or FFT only); GNSS has no channel; separate DF antenna array vs same 4 antennas;
  ground radars outside the sheet (VHF/UHF, wind profilers, 1030 MHz) not added; CH3 + CH4 share board B
  (~55 dB board-mate leak); host link 1 Gb/s vs dual 10 GbE.
* Next: only on the user's go (measure MON retune time per step and max MS/s per channel first).

## 2026-09-28

### 2026-10-01 — user: "keep updating in .md file because of compact session"
* CURRENT STATE block rewritten for the switch work.
* User: "don't change anything in our old repos" → this log is kept ONLY here (guru_switch_mon-df) from now on.
  One commit with this CURRENT STATE update had already been pushed to guru10ms (before the message arrived) —
  left as it is; nothing else changed there.
* `phase_table_live_deg.txt` changed: written by the user's CALIBRATE of 2026-09-30 18:10 (real table).

### 2026-09-30 evening — MON/DF switch work published: https://github.com/shankarjatti/guru_switch_mon-df (PUBLIC)
* User gave the repo (created public) and asked for everything: MON + DF switch information, files, custom blocks,
  theory. Pushed `~/radar2/guru_switch` (branch main, 36da0bb, 491 files in SHA256SUMS; fresh clone from GitHub:
  all intact). New docs: `docs/switching/THEORY.md`, `ENGINE_AND_BLOCKS.md`, `DEVELOPMENT_AND_TESTS.md`,
  `RUN_AND_HARDWARE.md`; landing README; today's logs + 30-min watch in `logs/` / `results/`.
* Checked before push: no secrets (hits = GPL text, upstream author emails), no secureCOM / private material,
  0 broken doc links; largest file 85 MB (GitHub warns > 50 MB, accepted).
* Mistake on the way: the work copy's `origin` still pointed at the local frozen `guru_DF_v1` (it was cloned from
  it), so the first push created a branch `main` there. Removed at once (`git branch -D main`, gc), guru_DF_v1
  files verified intact (449/449); remote renamed `guru_DF_v1_local`, `origin` = GitHub.

### 2026-09-30 18:12–18:42 — 30-min run of guru_switch: PASSED (no failure)
* User: "keep monitoring, we'll run it for 30 min; if it fails we'll check root cause". Watched every minute.
* CALIBRATE OK 18:10:15 (worst single window 0.06°). User switched MON/DF by hand 7 times (last: MON at ~18:31).
* 30 min: guru_switch running all the time, TIMING LOST 0, tracebacks 0; HackRF: 0 new TIMEOUTs, 0 watchdog
  restarts (after the fresh-process fix + fresh start).
* DF 2.4 GHz (18:13–18:32, in DF): tone +192.6..193.1 kHz, 10,000 samples per dwell every time, phases after CAL
  ch1 +0.05..+0.13°, ch2 +0.28..+0.52°, ch3 +0.26..+0.52° (slow drift ~0.2° over 20 min, max dev ≤ 0.08°).
  From 18:32 the program is in MON, so the DF meter holds its last value (expected).
* First run of the 2 MS/s DF chain past 11 min without TIMING LOST since the 09-29/09-30 failures (6 and 11 min);
  that earlier one coincided with me building a tarball — load matters, not proven fixed.

### 2026-09-30 18:08 — "not getting correct signal": HackRF stalled again (not the receiver)
* guru_switch log: every meter "no tone"; receiver healthy (locked, 0 missing, no TIMING LOST). HackRF log: 7046
  TIMEOUTs, watchdog restarting every ~1 s, each restart stalling again. HackRF USB device number 006 → 009 → 013
  over the day = it dropped off USB and came back at least 3 times (cable / port / power).
* Fix: 3 stalls within 60 s → the transmitter re-execs itself as a fresh process on the band last asked for
  (lab commit; copied to guru_switch, guru_mon, guru10ms). Fresh transmitter: 0 TIMEOUTs; guru_switch 2.4 GHz
  tone back (+192.8 kHz, 10,000 samples, phases +0.05/+0.14/+0.13°). 5.2/5.8 need CALIBRATE.
* Recommended to the user: HackRF on another USB port / shorter cable / powered hub.

### 2026-09-30 18:20 — user ran guru_switch: "ITS WORKING SUPER"
* User started `cd ~/radar2/guru_switch && ./run_hop.sh --switch` with the run instructions (CALIBRATE in DF,
  MODE selector manual only, MON tab, LAB TONE selector) and confirmed it works.
* Not yet frozen as a safe copy (guru_switch is the work copy, last commit a2a0140 + message fix).

### 2026-09-30 17:00–18:10 — switching steps 3–5: GUI, API, validation; user: MON continuous, manual mode only
* `guru_switch.grc/.py` (`make_guru_switch.py`): guru_burst's DF flowgraph unchanged on outputs 0-3 + MON tab
  (per LO spectrum / time / status) on 4-7 + MODE selector above the tabs. `./run_hop.sh --switch`.
* First GUI start: TIMING LOST at once — the Python MON meter (all 4 MON streams through Python) + 8 displays
  on top of the DF chain. Fix: MON path C++ only (probe snapshots of 8192 samples, displays thinned to whole
  4096-sample blocks, MON count from the engine). Then no TIMING LOST.
* Bugs found and fixed: MON band-stats key "MON" (string) broke the DF lock line; a repeated request (GUI
  selector following an API request) moved the request time.
* Validation (`switch_validate.py`, GUI + API, 151 switches over 566 s, then burst-mode MON):
  150/151 switches locked + used (1 not used, marked), bursts 50,720 ok / 0 missing, no TIMING LOST; DF 2.4 GHz
  phase over the whole run (guru's own meter): worst change 0.09 / 0.28 / 0.15°; request → first dwell:
  to DF mean 46.6 ms (worst 56.3), to MON 27.8 ms (worst 33.5); routing 1.0 ms mean (worst 4.0);
  555 / 50,722 slots late (1.1 %, marked, never used) = the PC's latency (see 16:20 entry).
* User: "MON work should be in continuous mode now ... don't follow burst mode there" → MON = ONE continuous
  stream (timed START_CONTINUOUS at the first MON sample; STOP at the switch back, the stream ends where it
  ends, end-of-burst gives the exact last sample); engine keeps 20 ms MON records with a lock read. DF stays burst.
* User: "don't set auto changing mode between MON and DF, that should be manually controlled" → the program never
  switched by itself (the automatic switching seen was my validation script through the API); API now OFF by
  default, mode only via the MODE selector.
* Continuous MON headless (`switch_engine_check.py`, a TEST that switches): 10 cycles: 0 missing bursts, DF phase
  after each return ≤ 0.27°, DF dwells 10,000; 1000 MON records locked; MON→DF now 20–29 ms, DF→MON 23–33 ms.
  First continuous run had bursts missing 10 (= number of switches), NOT reproduced in 3 runs since — open.
* GUI started for the user in DF (CALIBRATE first: the X310 was power-cycled).

### 2026-09-30 16:20–16:45 — switching steps 2 (engine) done, headless-verified on the radio
* `guru_switch/oot/engine/twinrx_engine.cpp` → `libtwinrx_switch.so` (separate lib; installed engine untouched):
  MON = one more band, own freq per channel, own internal LOs; mode request taken at the next planned slot;
  consecutive MON slots not retuned → MON bursts join with no gap. `switch_source.py` (local block, 8 outputs:
  0-3 DF with the old tags, 4-7 MON with mon_on / mon_bad / mon_off).
* Measured facts found on the way (route_burst_test.py):
  - timed LO routing takes effect at T (ch0 tone gone +0.12 ms after T, never before), phase back ≤ 0.16°;
  - BUT in the running engine a TIMED routing call blocks the host until T (each call reads the TwinRX back and
    the read waits behind the timed write) → tune after it went out late (all 10 switch slots late, send 30–45 ms).
    Fix: after the old mode's last dwell has ENDED, route UNTIMED (0.6–2.9 ms), then the timed tune at
    end + switch_gap (10 ms);
  - 200 burst commands at once overflow the radio's command queue (only 32 ran); the engine queues one ahead.
* Headless check (`switch_engine_check.py`, 5 cycles DF 2 s / MON 2 s, tone on 2.4 GHz):
  1558/1558 slots used, 0 late/unlocked/skipped, bursts 1557 ok / 0 missing, 10/10 switches locked;
  DF phase after each return from MON ≤ 0.26° (single-dwell std 0.06/0.11/0.09°); every DF dwell 10,000 samples,
  every MON dwell 40,000 (20 ms); MON: only ch1 (2.4 GHz) sees the tone (84.8 dB), ch0 34 dB board-mate leak,
  ch2/ch3 noise; request → first dwell of the new mode: DF→MON 24–33 ms, MON→DF 39–48 ms.
* One earlier run had 165 late DF slots with the same code (band change 4 ms instead of 1.1): a kernel worker at
  62–67 % CPU (D state), rustdesk, CPU governor `powersave`. DF-only and the next run: 0 late. PC latency, not the
  design — the performance governor needs the user (system setting).
* Next: control API + GUI (steps 3–4), then validation (step 5).

### 2026-09-30 16:05–16:17 — switching step 1 (`guru_switch/switch_check.py`): DF phase SURVIVES a trip through MON
* `~/radar2/guru_switch` = working copy of guru_DF_v1 + guru_MON_v1 (`59d2ed4`); frozen copies untouched.
* First trial tuned UNTIMED → phases after any retune jumped by exact multiples of 90° (also in the DF-only
  baseline) = the TwinRX LO divider state. Test-script error; fixed by using the engine's tune exactly
  (gains at T, ch c at T + c·0.4 ms, second pass at T + 3 ms, DDC policy NONE; lock read after the second pass).
* Full run (`results/switch_check_20260930_161434.json`): per DF band 50 MON trips (DF → MON with ch0..3 on
  0.9/2.4/5.2/5.8 GHz, each own LO, 0.2 s → DF) interleaved with 50 DF-only retune baselines:
  - phase change after a MON trip, worst of ch1/ch2/ch3: 2.4 GHz 0.33°, 5.2 GHz 0.20°, 5.8 GHz 0.22°
    (baseline retune: 0.26°, 0.14°, 0.12°); extra caused by the switch ≈ 0.03–0.11° (mean), std ≤ 0.07°.
  - MON set up correctly (all internal, all locked) 150/150; lock timeouts 0.
  - LO routing change ~2 ms (host, worst 4.7 ms); lock confirmed 4–8 ms after the timed tune (radio clock;
    includes the 3 ms second pass and sensor reads). Tune lead 30 ms was a choice, not a limit.
* Caveats: `lo_locked` on external channels (ch0/ch1 in DF) reports their own synth, so it proves nothing
  there — the phase + SNR are the proof. Between program starts the reference phase of ch2 came up 180° apart
  (+27.7° vs −152.8° at 2.4 GHz) → the start state is ambiguous: calibrate at every start (already the rule);
  within one run it is stable. MON-mode reception during the trips was not checked (only routing + locks).
* Conclusion: switching needs NO recalibration on return to DF (with the engine's tune). Next: step 2 (engine).

### 2026-09-30 15:45 — both works saved separately: `guru_DF_v1` and `guru_MON_v1`
* User: "keep both work separate and safe ... with other name ... after that we'll come to combining with switching".
* `~/radar2/guru_DF_v1` (git `b579304`, 449 files, `RESTORE.sh --verify/--check` OK, lab tag `guru_DF_v1` = `d9c5f78`,
  `guru_DF_v1.tar.gz` 245 MB): guru0930 + HackRF re-exec fix + 3-packet X310 ping. Needs CALIBRATE (X310 power-cycled).
* `~/radar2/guru_MON_v1` (git `6e975ff`, 15 files, `guru_MON_v1.tar.gz` 186 kB): MON only, standalone (stock gr-uhd,
  embedded meter, no installed doa blocks); block templates in `templates/`; regenerates the same flowgraph.
* ch0 port check (MON mode, same freq/gain): ch0 A/RX1 13–16 dB low on all 4 bands, others within ~3 dB → RF path
  of ch0, not LO sharing. Open: swap ch0/ch1 cables.
* User asked about "apk" for switching — unclear (API vs Android app); answered both. Next: MON↔DF switching plan
  (step 1 = switch_check.py measurement), only after the user's go.

### 2026-09-30 15:12 — MON step 1 (guru_mon): 4 LOs, own band each — WORKS on the cable
* Built in `~/radar2/guru_mon` (clone of guru0930; `d98421c`, `ad333a8`): `make_guru_mon.py` → `guru_mon.grc/.py`,
  `mon_tools.py`, embedded MON meter; `./run_hop.sh --mon`. Per LO: spectrum, time graph (I/Q), gain, frequency,
  status line (own `lo_locked`, every sample counted, stream breaks via rx_time tags, strongest line, ADC peak).
  MON setup at start, in order: export off → all LOs internal → tune each twice (TwinRX keeps the last routing).
* Blocked first: X310 was powered off (enp3s0 NO-CARRIER); HackRF had been replugged and its watchdog retried
  1843× in-process → fix: after 3 failed restarts it re-execs itself on the last band (lab `d9c5f78`).
* Measured (HackRF stepped 900 MHz → 2.4 → 5.2 → 5.8 GHz, 2 MS/s, gains 40/46/60/69):

| HackRF on | ch0 900 MHz | ch1 2.4 GHz | ch2 5.2 GHz | ch3 5.8 GHz |
|---|---|---|---|---|
| 900 MHz | **TONE +197.0 kHz 66.6 dB** | noise 12.0 | noise 11.5 | noise 11.6 |
| 2.4 GHz | 29.5 dB at the same +191.7 kHz | **TONE 83.4 dB** | noise 12.6 | noise 11.8 |
| 5.2 GHz | noise 12.1 | noise 12.5 | **TONE 80.1 dB** | 23.0 dB at the same +182.1 kHz |
| 5.8 GHz | noise 11.4 | noise 11.6 | 25 dB at +181.6 kHz (15:12) | **TONE 77.3–80.1 dB** |

  All 4 LOCKED all the time; each ~2.00 MS/s (counted); 1 stream break (at start, not growing); ADC peak ≤ 0.21.
* Finding: the other channel on the SAME TwinRX board sees the tone ~54–57 dB below, at the identical baseband
  offset (crosstalk after down-conversion, within a board); the other board shows nothing (> ~65 dB).
* X310 was power-cycled → DF phase table is invalid; CALIBRATE on the next DF run.

### 2026-09-30 13:30 — the user's whole work plan (discussion only, no code) — step by step
* User: "we continuously monitor all frequencies ... edge computing modules [find their] band ... send request for DOA
  ... based on the requests we make a schedule and find the target ... after that again move to monitoring".
  Scope is only BEFORE the USRP (Monitor mode, priority switching, USRP); DOA itself and everything after the USRP
  are other people's work.
* User: "this is my whole work plan, don't go directly for the full plan ... we'll do step by step".
* Plan agreed as an outline only (each step starts only when the user says so):
  0. measure: independent-LO retune time; LO mode-switch time; phase before/after a mode switch; scan speed
  1. Monitor mode (engine scans a frequency list on the radio clock, real counters)
  2. doa_request interface (frequency, priority, id, time; accepted/started/done)
  3. scheduler (priority queue, max time away from monitoring, timeout)
  4. DOA slot (mode switch if needed, coherent IQ + timestamps + calibration status)
  5. back to monitoring; end-to-end test, request-to-DOA latency measured
  6. robustness (CPU headroom; TIMING LOST after 6 min on 2026-09-30)
* Open design choice: Monitor with independent LOs (≈4× scan coverage, but a mode switch → relock, maybe recalibration)
  vs shared LO always (one freq at a time, calibration always valid, DOA from the next slot). Decide from step 0.
* Open questions to the user: "all frequencies" = 10 MHz–6 GHz or a band list; request format/transport and owner;
  DOA length per request; two requests at once; max time away from monitoring.

### 2026-09-30 12:52 — work saved as `guru0930` (user: "save this work... i need to take it in to next big step")
* `~/radar2/guru0930`: guru57 + today's fixes (`hackrf_tone_source.py`, `run_hop.sh`), all results, logs of today's run,
  WORK_LOG; own git `99d7436`; 449 files in SHA256SUMS (`RESTORE.sh --verify` OK); installed blocks = this copy
  (`--check` OK); `~/radar2/guru0930.tar.gz` (245 MB) + `.sha256`; lab tag `guru0930` = `d818647`.
* guru57 left frozen: today's 4 `tone_freq_*.json` that had been written into guru57/results moved to guru/results
  (guru57 git clean, 421 files intact).

### 2026-09-30 12:30–12:50 — cables fixed; HackRF stall; launcher bug; guru_burst running — user: "now its working correct"
* After the user reseated the cables: ch2 level with ch1/ch3 on every band (2.4 GHz 94.4 / 95.1 / 94.8 dB; ch0 84.7 dB,
  4–10 dB below the others — enough, but more than on 09-29).
* First re-check showed no tone on any channel: the HackRF's transmit stream was stalling (USB TIMEOUT, 13 watchdog
  restarts, each stalled again within ~1 s). Transmitter process restarted → 0 TIMEOUTs since.
* Bug found in the log: a stall during 5.8 GHz came back "restarted on 2.4 GHz" — a 'freq' request arriving during
  the restart went to the dead flowgraph. Fix (`hackrf_tone_source.py`): the band last asked for is kept, and the
  restart and every UDP command share one lock. Lab commit `d818647`.
* Raw radio-block capture (guru_burst settings, 2 MS/s, burst, rt 0 and rt 90): tone on all 4 channels 72–87 dB —
  real-time priority 90 is now granted ('rt_priority': 'on') and does not change reception.
* Launcher bug: `run_hop.sh` has `set -u`, `setup_env.sh` appends to `$LD_LIBRARY_PATH`; when that is unset bash stops
  before the receiver starts (exit 1, no receiver log). Fix: `set +u` around the source (guru, guru10ms, guru_ota;
  guru57 left frozen — same bug there if LD_LIBRARY_PATH is unset).
* guru_burst on the cable (12:46): 2.4 GHz tone +192.3 kHz, 10,000 samples/dwell, ch1/ch2/ch3 +0.02/−0.02/−0.01°
  (max dev 0.07°) with the stored table. 5.2/5.8 GHz still show the startup values (−64/−20/−101°, −45/+140/+30°) —
  cables were reseated, so CALIBRATE is needed on those bands.
* 15-min watch of the run started (covers the 11-min TIMING LOST problem).

### 2026-09-30 12:25–12:35 — "not getting signal from ch2" → ch2 RF input nearly disconnected (cable)
* Measured with guru57's own `tone_freq_check.py` (guru57 blocks installed, no trim, 2 MS/s, 200 kHz tone):
  tone over noise ch0/ch1/ch2/ch3 = 2.4 GHz 88.8/99.2/**66.5**/99.0 dB; 5.2 GHz 91.2/97.9/**76.9**/97.0; 5.8 GHz 92.8/97.5/**77.5**/97.5.
  Yesterday (cable, same tool): ch2 equal to ch1/ch3. LO locked on every band; ch2 phase still steady (0.05–0.2°).
* Conclusion: not software — ch2 (Rx B RX1) gets only leakage; ch0 also 5–10 dB lower than yesterday.
  Asked the user to reseat/tighten ch2 and ch0 SMAs (2945 + divider), swap ch2/ch3 cables if still weak.
* Waiting for the user; then re-measure and run guru_burst.

### 2026-09-30 12:18 — back to the CABLE setup; guru57 blocks restored
* User: "that antenna test we ll come latter.... we ll come back to old setup using cable connection".
* `~/radar2/guru57/RESTORE.sh` run: installed blocks in `~/gnuradio-3.8` = guru57 exactly (`--check`),
  all 421 files of guru57 intact (`--verify`). The OTA blocks that were installed are saved in
  `~/radar2/pre_restore_20260930_121829/`.
* `~/radar2/guru` = guru57 (same blocks, `guru_burst.py`, `run_hop.sh`, byte-compared).
* User re-connects HackRF → splitter → 4 channels. Run: `cd ~/radar2/guru && ./run_hop.sh --burst`, then CALIBRATE.

### 2026-09-29 evening — over-the-air test (paused), in the copy `~/radar2/guru_ota` only
* HackRF antenna → 4 antennas on the 2945 (same PC, UDP control). guru57 / guru untouched.
* Found: a fan made a 70 Hz phase wobble (±3°) — seen in the phase spectrum; fan off removes it.
* Found: 5.2 GHz Wi-Fi bursts pulled the whole-band phase estimate (up to 175°) → in guru_ota the meter takes
  the phase only at the tone's own bins (±2 bins). Spread at 5.2 GHz 19–44° → ~7°.
* 5.2 GHz RX gain 60 → 70 dB in guru_ota (no overload).
* Measured: continuous 2 s, nothing moving: phase spread 0.44–0.87°. Hopping: 10,000 samples/dwell, 476/476 dwells
  with the tone, 0 unlocked; but dwell-to-dwell jitter 2.3–3.1° (**unexplained, open**) and ~40°/17 s slow wander
  (movement near the antennas). CALIBRATE rejects over the air (cable rule 0.3°).
* guru_ota commits `ec124fe`, `bb4cb81`; `ota_check.py` = RX-only over-the-air check.

### 2026-09-29 — guru57 frozen copy; 2 MS/s long-run fix
* User: "its working good and save this work properly take copy name it as guru57".
* `~/radar2/guru57`: own git (`1d267be`), 421 files, SHA256SUMS, `installed_snapshot/`, RESTORE.sh, `guru57.tar.gz`;
  lab tag `guru57` = `b3673fb`.
* TIMING LOST after 11 min at 2 MS/s (host ring full: all Python blocks share one core) → each meter processes
  only its own band, no DC remover at 200 kHz (`1c7fe33`). Long run (> 11 min) after this fix: **not yet proven**.

### 2026-09-28 20:00 — run of guru10ms; HackRF stalled; watchdog blind to it
* User ran `~/radar2/guru10ms/run_hop.sh --fast --restart` (my background start exited without a message;
  `import guru_fast` works — likely no GUI from my shell). Screen: SCHEDULE 8021 slots, 8020 used, 1 late,
  0 unlocked; LO LOCK all dwells; LAB TONE 5.2 GHz → **NO TONE (0/8 dwells)**, receiver OK.
* `/tmp/hackrf_tone.log`: **1387 × `Soapy sink error: TIMEOUT`, no `[watchdog]` line.** Cause: in this
  stall the gr-soapy sink keeps consuming samples (drops them with TIMEOUT), so `probe_rate` stays
  normal and the watchdog (rate < 25 % for 2 s) never fires. Fix designed, **not applied** (user
  interrupted): tap stderr and count TIMEOUT warnings per second; ≥ 3/s for 2 s → restart the stream.
* Earlier run 17:18–18:03 (from its log): 135,007 slots, 134,992 used, **15 late** (worst send
  19.6 ms > 13 ms limit), 0 unlocked, 0 skipped, 0 overflow, rtprio off.

### 2026-09-29 17:55–18:00 — DECISION: 200 kHz tone, 2 MS/s; burst mode works on every band
* User: "use 200k only, and 2 MHz sample rate". Lab `…`: guru_burst at 2 MS/s (dwell 10,000 samples), HackRF plain
  200 kHz (pure source), close-up waveform view + autoscale.
* Measured on the radio: CAL OK (worst window 0.05°); tone +190.8 / +180.2 / +177.9 kHz on 2.4 / 5.2 / 5.8 GHz
  (HackRF −3.8 ppm); 953.8 / 901.0 / 889.3 cycles counted; **samples / dwells = 10,000.000 exactly** (every reading);
  phases ≤ 0.1°; 5,630/5,632 slots (2 late, no rtprio); 0 unlocked; 0 overflow. Pictures
  `results/gui_burst_2Msps_200k_*MHz_20260929_1758.png`.

### 2026-09-29 17:40–17:52 — every band, TX pure source: counters exact; 2.4 GHz tone lands at 0 Hz
* User run 3.6 min: 17,989/17,995 used, 0 unlocked, 2.4 GHz tone +2,102…+2,217 Hz (TX clock), 5000 samples every dwell.
* Counters: mid-burst readings were off (19,408,754 / 3,881 = 5000.97) → totals now published together per complete
  burst: 20 random readings per band = **5000.000000** exactly.
* 2.4 GHz showed −8,828 Hz = the HackRF carrier leak taken as the tone (real tone inside the ±2 kHz guard) → meter now
  takes only the strongest line; inside the guard = NOT measured. Synthetic test passes.
* Radio now: HackRF −3.8 ppm (all bands agree) → 2.4 GHz tone at **+835 Hz → NOT measured**, CAL refused; 5.2 GHz
  −9,696 Hz (48.44 cycles), 5.8 GHz −12,053 Hz (60.23 cycles). With a pure-source TX, a 10 kHz offset cannot work on
  every band without a shared clock. Options for the user: REF OUT → CLKIN cable (exact 10 kHz everywhere) or a larger
  offset (e.g. 200 kHz).

### 2026-09-29 17:50 — DECISION: TX is only a source; everything measured on the RX
* User's run: 19,400,000 samples / 3,880 dwells = 5,000; tone 9,970.2 Hz → 49.84 cycles counted (9,970.2 × 5 ms =
  49.85). Question "if the tone and cycles vary, how are the samples fixed at 5000?" → two clocks: samples = X310 ticks.
* User: "everything should be calculated from the RX side; TX side is just a source" → the HackRF clock correction
  (fed back from RX to TX) is removed (lab `…`). HackRF sends plain 10 kHz; RX measures wherever it lands (≈ +3 kHz on
  2.4 GHz, ≈ −6 kHz on 5.8 GHz at −2.8 ppm); meters search both sides of 0 Hz. 50 cycles exactly only with the
  REF OUT → CLKIN cable. Not yet run on the radio (user's GUI running).

### 2026-09-29 17:40 — counters made independent; tone + cycles back on screen
* User restarted with run_hop --burst: transmitter v2 reports `ppm=-3.2186` (measured at start by asking it) — correct.
* User: "samples and dwells … calculate independently; tone frequency and cycles need real-time update". Engine now
  keeps two separate counters (dwell samples added packet by packet, pre-roll excluded; +1 per complete burst); screen
  line 1 = those, line 2 = tone Hz + cycles counted on the last dwell (lab `…`). Not yet run on the radio (user's GUI
  was running).

### 2026-09-29 17:25–17:35 — 87.75 cycles on the user's screen = my bug; bottom line simplified
* User's run: tone 17,549 Hz = 87.75 cycles; screen said clock "now −3.271 ppm (−6.417 at start)". Cause (mine): I had
  restarted the HackRF by hand with `--ppm 0`; `run_hop` kept it, and its start-up measurement ASSUMED the correction in
  `hackrf_ppm.txt` (−3.374) was active → computed −6.417, applied it → over-corrected. Receiver measured it correctly.
* Fix (lab `9f8d77e`): transmitter answers UDP `get` (its real correction); `tone_freq_check` asks it (refuses if it
  can't); run_hop restarts an older transmitter ('v2'); screen asks the transmitter each second.
* User: "no paragraph — just total samples received and number of dwells, updating; I divide them". Bottom line is now
  only `SAMPLES RECEIVED: n   DWELLS: m` (meter counters, every dwell of every band, 10×/s).
* Not yet verified on the radio (user's old guru_burst was running).

### 2026-09-29 17:05–17:20 — live sample counts; HackRF unplugged; CLKIN not in effect yet
* DWELL CHECK now live (10×/s): dwell number, samples counted between its marks + min/max of last 200, the radio's
  own burst count (5,250 = 250 pre-roll + 5,000) with its X310 time stamp, cycles COUNTED from the signal's rotation.
  Test: a 4,990-sample window is reported as 4,990. Radio: #1394 5000 [5000..5000].
* HackRF USB was unplugged (user, for the CLKIN cable): the new watchdog saw it (10 TIMEOUT/s) but its one restart
  failed ("No such device") and it never retried → fixed: retries every 3 s. Tone source restarted with `--ppm 0`.
* Measured with no correction: HackRF **−2.810 ppm** vs X310 on all bands → not running from the X310's clock yet.
  UHD turns X310 REF OUT on by default at every open (and the engine forces it) → cable not connected yet, or HackRF
  not accepting the level. Waiting for the user.

### 2026-09-29 16:45 — user's 16-min burst run; "in long run I should get 10 kHz and 50 cycles — root cause"
* Screen: 81,756 slots, 81,751 used (4 late, 1 skipped, 0 unlocked), **5000 samples every dwell**, phases
  +0.016/+0.029/+0.075°, but tone at 5.8 GHz **6,871.9 Hz → 34.36 cycles**. Still no rtprio (limit 0).
* **Root cause: two free-running clocks.** Samples counted with the X310's reference, tone made with the HackRF's
  crystal; they drifted −3.374 → −3.913 ppm = **0.54 ppm in 16 min** (3.1 kHz at 5.8 GHz). Software cannot fix that
  without faking. **Fix: one clock — X310 REF OUT → HackRF CLKIN.** Engine now switches REF OUT on at every start
  (lab `…`); screen shows the drift in ppm; meter log has time stamps + tone Hz per band.
* To verify after the cable: `tone_freq_check.py --offset 10e3 --applied-ppm 0` must show ~0 ppm on all bands, and
  again after 20+ min.

### 2026-09-29 16:25 — "LO lock not confirmed on every dwell"
* That text appeared with **unlocked 0**: the unused dwells were **late** (PC, no rtprio), not LO failures — the
  message lumped both. Now per band: `used N/M (not used: x not locked, y late, …)` and the SHOWING line names the
  reason (lab `8739f10`). The LO lock check itself: `lo_locked` read on ch2 at 6.5 ms, before the first used sample.

### 2026-09-29 16:00–16:18 — "signal not clean, distorted" (5.8 GHz picture) → clean display
* 5.2/5.8 GHz `tone_level_check` (HackRF VGA 47…27): no clipping (peak ≤ 0.125 FS), every line ≤ −37 dBc, but a
  **flat noise floor ~22 dB below the tone** over the 300 kHz display band, constant with HackRF level, identical on
  all channels = the HackRF's transmit noise (raw dwell: `results/raw_dwell_5800_20260929.png`). And 5.8 GHz arrives
  ~16× stronger than 2.4 GHz → drawn off the fixed ±0.6 plot (looked cut/peaky).
* Fix (lab `…` "clean display"): **±10 kHz zero-phase display filter around each dwell's tone, same filter on all
  channels** (phase untouched; measurements unfiltered) + autoscale. Synthetic test: ripple 3.95 → 0.62 %, phases exact.
* On the radio: CAL OK (worst window 0.05°), 3,632/3,632 slots, 0 late, 5,000 samples every dwell, clean sine at 2.4 and
  5.8 GHz, phases ≤ 0.07° (`results/gui_burst_clean_*_20260929_1617.png`). Cycles 41.1 (5.8) / 45.9 (2.4): HackRF
  drifted since its clock was last measured (my tests do not re-measure; `run_hop.sh --burst` does at each start).

### 2026-09-29 15:52–15:58 — quick verification (user: "check and verify fast")
* Full GUI program on the radio (offscreen), right after the start-up clock measurement: **5000 samples = 5.000 ms
  exactly**, tone 9,935 → 10,047 Hz = **49.7 → 50.2 cycles**, slots 2,633/2,633 and 2,947/2,947 used, 0 late.
* Raw phases changed since 13:28 (e.g. 2.4 GHz ch1−ch0 172.2° → −45.5°) after my test tools re-opened the X310 →
  CALIBRATE after every start stays mandatory.
* CALIBRATE was REJECTED (0.64–0.77°): it started while the HackRF still sent its old buffered baseband. Calibrator
  now waits 1.5 s + 5 dwells of a steady tone (lab `…` hop_calibrator). Next run: CAL OK (worst window 0.78°).
  ch2 spread in the GUI 0.16–0.26° (ch1/ch3 0.02°) — near the 0.3° limit; not loosened.

### 2026-09-29 15:45–15:52 — "why distorted / not continuous / why more than 50 cycles"
* User's screen: zoomed plot (troughs outside the zoom box = "not continuous"), not calibrated (−59°), 51.26 cycles.
* `tone_level_check.py` (HackRF VGA 14→30 dB, signal +16 dB): SNR in the 300 kHz display band stays **~28 dB** on all
  channels → the wobble scales with the signal. Residual after an ideal sine: **coherence 0.991–0.996 between
  channels**; receiver's own noise (HackRF moved away) **31–45 dB** below the tone → the wobble is **in the HackRF's
  signal** (phase/frequency noise; 96.6 % within 1 kHz of the tone = its drift), identical on all channels, so it
  cancels in chN − ch0 (phase spread 0.03–0.1°). Receiver does not distort. VGA left at 14.
* **More than 50 cycles:** HackRF clock vs X310 drifted **−4.5 → −5.2 → −3.2 ppm** today; with a stored correction the
  10 kHz tone landed at up to 14.5 kHz (72 cycles). `run_hop.sh --burst` now measures and applies the clock error at
  every start (`tone_freq_check --set-live`): right after it 9,960 / 9,856 / 9,780 Hz = **49.8 / 49.3 / 48.9 cycles**.
  It keeps drifting afterwards (shown per dwell). Exactly 50.00 for good: **X310 REF OUT → HackRF CLKIN**.

### 2026-09-29 13:10–13:40 — 10 kHz tone in burst mode: whole 5 ms dwell on screen, DWELL CHECK
* User: "in 5 ms I should receive 5k samples ... for 10 kHz I should see 50 cycles ... not distorted ...
  everything should be real, no fake, no fallback, 100 % real". Lab commit `ce7342e`.
* User's run 13:05 (guru_burst, 200 kHz): 131/2,995 late. Their process had **Max realtime priority 0**
  (the rtprio file exists; needs a new login) — all 89 threads normal priority.
* Measured: receiver 0 Hz leakage is only **13–16 dB below the tone** in every dwell (engine DC correction on).
  With a 10 kHz tone it must be removed per dwell (synthetic test: without it phase −175° for 25° true).
  Added: meter `remove_dc`, `hop_band_select remove_dc`, new `hop_dc_remove` (one-dwell delay; tested:
  tone amplitude exactly constant, tags on exact samples). Meter reports per dwell samples / tone Hz / cycles.
* HackRF clock vs X310: −4.894 ppm at 13:24 (3 bands within 0.011 ppm), `--ppm` correction added — but it
  **drifts**: tone seen at 9,177 … 10,828 Hz during the session → **45.9 … 54.1 cycles per 5 ms**. Not forced
  to 50 by any loop (that would be fake). Exactly 50.00 needs **X310 REF OUT → HackRF CLKIN**.
* CALIBRATE at 10 kHz first REJECTED (5.2 GHz 20/111 windows no tone): HackRF sends from a ~1 s buffer, so after
  a retune the old baseband continues ~1.2 s. Calibrator now waits for 5 dwells in a row with the tone (≤ 3 s).
* Result, full GUI program on the radio (offscreen), `results/gui_burst10k_tab0_20260929_1337.png`:
  every dwell **exactly 5,000 samples**, bursts 2,629/2,629, **CAL OK, phases +0.013 / −0.014 / +0.001°**,
  one whole dwell = clean sine on 4 channels, ~52 cycles (tone 10,347.6 Hz), Switching tab flat; 1 late in 2,343
  (no rtprio).

### 2026-09-29 12:25–13:05 — HackRF fix done; burst mode 5 ms ON / 7 ms switching built and measured
* **HackRF watchdog** (`hackrf_tone_source.py`, lab commit `069cdba`): GR 3.10 prints the Soapy TIMEOUT
  warning on **stdout**; the script's stdout/stderr now pass through a pipe that counts it (and forwards
  everything, flushed at exit). ≥ 3/s for 2 s → restart. Test with the real GR logger: healthy 0 restarts,
  1/s 0 restarts, 10/s → restart after 2 s.
* **10 kHz tone tried and dropped** (user: "in continuous which method we are using follow same in burst").
  Measured (`tone_freq_check.py`, results `tone_freq_20260929_12*.json`): the HackRF runs **−4.5 ppm** vs the
  X310 (−10.9 kHz at 2.4 GHz, −26.3 kHz at 5.8 GHz), drifting 8.8 kHz while warming up → a +10 kHz tone
  landed at −0.9 kHz on 2.4 GHz, on top of the receiver's 0 Hz leakage (which is *stronger* than the tone at
  2.4 GHz). Back to 200 kHz. Real fix if 10 kHz is ever needed: X310 REF OUT → HackRF CLKIN.
* **Burst mode** (lab commit `03f222b`, `~/radar2/guru/guru_burst.grc/.py`, `./run_hop.sh --burst`): engine
  sends a timed NUM_SAMPS_AND_DONE per dwell (0.25 ms pre-roll + 5,000 samples), checks every burst's start
  sample and length, puts it on the continuous timeline (zeros in gaps). Same chain/method as guru_fast;
  lock read at 6.5 ms; averaging 20 dwells; rt_priority 90 requested. `burst=False` = old continuous mode
  (regression: generated 10 ms flowgraph identical apart from the new params).
* Measured on the radio (no rtprio, GRC + Chrome open):
  * continuous CALIBRATE → table `phase_table_20260929_cont.txt` (2468/2468 slots, spread ≤ 0.13°)
  * **burst VERIFY: 4,112/4,112 bursts exact, every dwell exactly 5,000 samples, 0 unlocked, all bands
    ≤ 0.57°**; second run 2,360/2,360 exact, ≤ 1°
  * continuous VERIFY right after: ≤ 0.80° → the burst residual is drift, burst = continuous phase
  * **late: 598/4,112 (14.5 %) and 39/2,361 (1.65 %)** — timing record: UHD tune calls stall to ~6 ms
    (typical 2.27 ms) while the budget after the 6.5 ms lock read is ~5.5 ms. PC, not radio. Needs rtprio.
* Found: `~/radar2/guru/guru_fast.grc` was overwritten 2026-09-28 20:26 by a GRC save of an older version
  (no phase meter, plots on other tabs). `guru_fast.py` unaffected; the good .grc is in git and in guru10ms.
  Left as is — user to decide.

### 2026-09-29 — DECISION: no ping-pong; keep the current hardware setup
* User: "no we'll not go with ping pong ... follow that same hardware setup, only B can be the master".
* Fixed from now on: ch0 `external`, ch1 `external`, ch2 `internal` + export (the one synthesiser),
  ch3 `companion`; cables B J3→A J4, B J1→A J2; one synthesiser retunes at every hop.
* Consequence: switching cannot be shorter than that synthesiser's lock (5.40–5.84 ms single tune; locked
  by 7 ms with our 2nd pass) → realistic minimum ~6–7 ms, to be measured. Dwell 5 ms is possible.

### 2026-09-29 — user: does it work for a circular array too?
* Yes: the receiver, hopping and ping-pong do not depend on antenna layout. What changes is the DF maths:
  circular-array (UCA) steering vector a_n(θ) = exp(j·2π·R/λ·cos(θ − 2πn/4)), per band λ; gr-doa has only
  linear-array MUSIC → write UCA MUSIC ourselves. Pilot-at-known-angle antenna calibration is general.
* 4-element UCA, neighbour spacing d = R·√2 ≤ λ/2 → R ≤ λ/(2√2): 4.42 cm (2.4), 2.04 cm (5.2),
  1.83 cm (5.8 GHz) (calculated, not measured). Gives 360° azimuth; up to 3 sources; no elevation.

### 2026-09-29 — user: "ping-pong works only for linear array, 180° search?"
* Answered: no — the linear array / 0–180° limit belongs to AN-244's MUSIC direction finding (a linear
  array cannot tell front from back). Ping-pong is only an LO/tuning method (from a different Ettus
  example, one channel, spectrum sweep) and does not depend on antenna geometry. 360° needs a circular
  array + our own steering vectors (gr-doa implements linear arrays only). With 3 bands one spacing
  cannot be λ/2 for all: λ/2 = 6.25 cm (2.4), 2.88 cm (5.2), 2.58 cm (5.8 GHz).

### 19:20 — user: can both boards A and B be master (exporter) in ping-pong?
* Today only B exports (ch0 `external`, ch1 `external`, ch2 `internal`+export, ch3 `companion`) because
  **the A→B LO jumpers pass no LO** (measured 2026-09-19, twice, hours apart: ch0 as exporter → ch2/ch3 dead,
  tone +1.2 / −1.1 dB). B→A works. Cause: that cable pair faulty, unseated, or wired out-to-out
  (must be J3 OUT → J4 IN for LO1, J1 OUT → J2 IN for LO2). Known separately: RF A board has a 15.4 dB
  amplitude imbalance (ch0 weak port), phase coherence fine.
* Basic ping-pong does **not** need A as master: both synthesisers used are on board B.
* If the A→B pair is repaired, both boards can be master → **4 synthesisers for 3 bands** → each band can
  keep its **own synthesiser locked all the time** (no retune at all). Switch = only source/export switches;
  dwell no longer limited by lock time; a synth that never retunes keeps its phase state → table per band.
  Cost: each hop flips all 4 channels' sources and both boards' export at one radio time; A→B cable drift.
  To be measured, not assumed.
* Proposed order: (1) user checks the A→B jumpers (which connectors, seated); (2) `twinrx_lo_check.py
  --lo-sources internal,companion,external,external` with ch0 exporting to confirm A→B carries LO;
  (3) ping-pong test on board B (works with today's cabling); (4) if A→B works, the 4-synth fixed-LO test.

### 19:10 — user: "we are working with shared LO ... all LOs should be synchronized"
* Ping-pong keeps the shared-LO rule: at every instant **all 4 channels use one and the same synthesiser**
  (ch0/ch1 `external` via the cable, ch2/ch3 on board B, export follows ch2's source). The spare synthesiser
  feeds no channel while it tunes; at the hop all 4 channels move to it together.
* The two synthesisers never serve at the same time, so they do not need to be phase-locked to each other;
  both run from the same reference clock. The inter-channel phase (chN − ch0) is what is measured, and the
  common LO phase cancels in it.
* What changes: the LO reaches each channel by a slightly different path from synth A (ch2's) than from
  synth B (ch3's) → a phase table per (band, synth): with 3 bands and 2 synths the pattern repeats every
  6 dwells → 6 table rows, CALIBRATE measures all 6.
* Must be verified in the test: each (band, synth) state repeats its phase; no 180° states; the spare
  synth's retuning does not leak into the active LO (spurs / phase disturbance during the dwell).

### 19:00 — user: switching must be below 5 ms — is it possible by code?
* Answer: **not by making the retune faster** (the ~5.4–5.8 ms is the TwinRX synthesiser itself: ADF5355
  VCO auto-calibration + PLL lock, plus the SPI writes at 3 MHz, all executed in the radio's command queue —
  UHD source `adf535x.cpp` waits `_wait_time_us` during autocal).
* **Yes by a different method: ping-pong LOs** — Ettus's own `host/examples/twinrx_freq_hopping.cpp`
  (default hop interval 5 ms): while one LO set receives, the spare LO set is tuned to the next band; at the
  hop only the LO **source switch** flips (`internal` ↔ `companion`).
* Our mapping: board B has two LO sets (ch2's, currently exported, and ch3's, currently idle because ch3 is
  `companion`). UHD source `twinrx_experts.cpp` l.333–345: the exported LO **follows** the exporting
  channel's source (ch2 `companion` → exports ch3's synth), so board A (`external`) follows the flip and all
  4 channels stay on one LO.
* Unknown until measured: switch time after the flip; whether the phase repeats (the 180° / wrong-state
  problem of a single timed tune may come back); whether the spare LO locks within dwell + switch
  (5 ms + 1 ms = 6 ms vs lock 5.4–5.84 ms single pass, 2nd pass unknown) → dwell 5 ms is at the edge;
  spurs from the spare synth retuning during a dwell.

### 18:45 — user: move to 5 ms, solve the open problems during that work
* User: "we need to move 1 more step like 5ms ... during that time only we'll solve these problems also".
* Facts that decide 5 ms (measured): LO lock after a **single** timed tune = 5.40–5.84 ms after T
  (`timed_tune_20260928_122715.json`, 300 hops). Our phase-correct method adds a 2nd pass at S+3 ms;
  its lock time has never been measured on its own (only "locked at S+7 ms" in > 100,000 slots).
* So: **5 ms dwell is possible; 5 ms switching is not** with this tune (the LO is still unlocked at 5 ms).
* The PC's time per slot shrinks (lock read at S+7 ms, next batch must be sent before the next S):
  10/10 → 13 ms; 5 dwell/10 switch → 8 ms (worst send seen with GUI ~9 ms). So the real-time
  settings (problem A) become required, not optional — they get solved inside the 5 ms work.
* Plan: (1) measure lock time of the exact method → shortest safe switch; (2) rtprio + CPU performance;
  (3) 5 ms dwell with that switch: exact-sample check, then 30-min GUI soak, target 0 dropped;
  (4) drift + automatic recovery along the way. guru10ms stays untouched; work in `~/radar2/guru`,
  save as `guru5ms` when verified.

### 18:35 — requirement: receiver side 100 % correct
* User: "for testing only we are using hack rf ... i need receiver side should be 100% correct".
* Already true by design and measured: a dwell is used only if its band, LO lock and exact timing are
  confirmed; everything else is discarded and counted. **No wrong number is ever shown.**
* Not yet 100 %: (A) dropped dwells, 3 / 90,008 in the 30-min GUI soak (Linux late); (B) phase accuracy
  between calibrations (drift up to ~8° / 16 min, receiver LO cable A↔B); (C) no automatic recovery
  after lost samples (untested).
* Plan proposed: Stage 1 timing (rtprio 95 + CPU `performance`, engine threads pinned to own cores;
  target 0 dropped in 30 min). Stage 2 automatic resync after sample loss, tested by forcing a stall.
  Stage 3 one-hour drift log with a fixed table → calibration interval from numbers; phase-stable LO
  cable as the permanent fix (software cannot make a cable's thermal drift zero).

### 18:25 — work log started
* User: "every time keep updating things on .md file ... some time we need to compact the session".
* Created this file. From now on every stage is written here as it happens, committed and pushed
  to `guru10ms`.

### 18:20 — repo pushed to GitHub
* User gave https://github.com/shankarjatti/guru10ms: "every small information should be there ... every related file".
* Repo was empty and **public**; asked the user — answer: **push as public**.
* Added: raw `.npz` results (110 MB) + `results/README.md` (every run with its own verdict),
  `docs/DEVELOPMENT_LOG.md`, `docs/lab_notes/`, lab git history, `third_party/gr-doa` source + patch vs
  upstream `7f982b7`, `environment/` (versions, network, `uhd_usrp_probe`), `earlier_work/lo_sharing/`,
  `logs/`, landing `README.md`.
* Checked before push: no secrets (grep for tokens/keys/passwords), 0 broken links, 366 files in SHA256SUMS.
* Pushed 2 commits (`45c7579`, `35a5bfe`). Fresh clone from GitHub: all 366 files intact.
  GitHub warned on one 85 MB file (limit is 100 MB) — uploaded complete.
* Found: `results/sched_10on_10off_20260928_122954.json` is incomplete (numpy-bool JSON bug); marked so.
* Left out on purpose: `guru2/3/4`, `guru_phase`, `guru_doa`, `gururaj` (older/stale), `BACKUP_*` (duplicates).

### 18:10 — safe copy `guru10ms` made
* User: "KEEP THIS WORK SAFE MAKE A COPY OF IT AND NAME IT AS A guru10ms".
* `run_hop.sh` changed to run the files in its own folder (commit `d135177`, tag `guru10ms` in `~/radar2`);
  from `~/radar2/guru` behaviour is unchanged.
* `~/radar2/guru10ms/`: project + `installed_snapshot/` + `RESTORE.sh` + `SHA256SUMS`.
* Verified: installed blocks = copy; engine rebuilt from the copy is byte-identical to the installed one;
  `hop_blocks_selftest.py` passed; `guru_fast.grc` regenerates the same `guru_fast.py`.

### Before 18:00 — guru_fast built and verified
* See [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) §3–§5 (stages 1–14, all measurements, all fixes).
