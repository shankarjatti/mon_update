# terrestrial38 — terrestrial decode in GR 3.8 / UHD 3.15, fed by monitoring CH2

Ported from github shankarjatti/1stversiondone (was GR 3.10 + UHD 4 + B210).
Everything now GR 3.8 / UHD 3.15, custom blocks as C++ OOTs. One program
(mon_scan) owns the X310 and publishes CH2 IQ over ZeroMQ; these decoders
subscribe — no second radio owner.

## Decoder blocks (installed into ~/gnuradio-3.8)
- dsd  (DMR/P25/NXDN/D-STAR): ~/radar2/gr-dsd   — C++ OOT (SWIG). VERIFIED decoding
  a real D-STAR discriminator recording (callsigns + voice out).
- tetra (TETRA): ~/radar2/gr-tetra — C++ OOT (gr::block + tetra-kit capi + ACELP).

## Pieces here
- zmq_cc_source.py : GR 3.8 source, subscribes to a mon_scan channel feed
  (tcp://127.0.0.1:5202 = CH2) -> complex stream.
- decode_dsd.py    : one DSD chain (DMR/P25/NXDN/D-STAR):
    zmq_cc_source -> freq_xlating (2e6->50k) -> quadrature_demod -> resample 48/50
    -> dsd_block_ff -> wav + prints talkgroup/source/nac.
- deps/            : tetra decoder sources + libs (for the C++ OOT build).

## Run (with mon_scan publishing CH2, tuned so the channel is near CH2 centre)
```bash
source ~/gnuradio-3.8/setup_env.sh
# terminal 1: the radio owner + publisher
cd ~/radar2/guru_mon_scan && ./run_mon_scan.sh --gain 45 --channels 2 --pub
# terminal 2: decode DMR from the CH2 feed
cd ~/radar2/terrestrial38 && ./decode_dsd.py --proto dmr --offset 0
```
`--offset` selects the channel's Hz offset from the CH2 centre; `--gain` tunes the
FM discriminator. Output: decode_<proto>.wav + talkgroup/nac printed as they change.

## Status 2026-10-12
- DONE: both decoder blocks as C++ OOTs; DSD verified decoding real D-STAR; the DSD
  decode flowgraph builds + runs fed from the CH2 ZeroMQ feed.
- NEXT: TETRA demod chain (pi4-DQPSK -> symbol sync -> bits -> tetra_decoder_block);
  live on-hardware test with the DMR radio (needs USRP + exact TX freq to tune CH2).

## CH2 integration (2026-10-12) — all protocols on the CH2 monitoring feed
- ONE port for all terrestrial protocols: tcp://127.0.0.1:5202 (mon_scan CH2 PUB).
- Each decoder filters to its scan band via --band (mon_scan tags each block):
    D-STAR "D-STAR 145.0" · TETRA "TETRA 420.0" · DMR "DMR 446.100" · P25 "P25 450.0" · NXDN "NXDN 451.0"
- Only the CH2 monitor protocols are enabled; all other repo protocols (ProVoice,
  X2-TDMA, NXDN48, air/maritime) are DISABLED (not launched).
- Custom blocks are OUR GR 3.8 C++ OOTs (dsd, tetra). Demod chains kept the same as
  the repo (DSD: xlating->quad demod->resample->dsd; TETRA: agc->fll->clock_sync->
  eq->diff_phasor->const_decoder->map->unpack->tetra). GR3.10-only bits swapped for
  3.8 equivalents (cma_equalizer_cc for the TETRA equalizer); no gr-zeromq (we use pyzmq).
- Launch: ./run_terrestrial_ch2.sh  (after mon_scan --channels 2 --pub).

### IMPORTANT for a real decode test
Monitoring SCANS CH2 (each band ~a few hundred ms per visit). Continuous voice decode
needs the signal sustained, so for a live DMR test PIN CH2 to the band instead of
scanning: run mon_scan on CH2 holding DMR 446.100 (single-band), key the radio, watch
logs/dmr.log. (Scan-mode feed still proves plumbing/activity; sustained decode wants a pin.)

## FINAL ARCHITECTURE (2026-10-12) — per-protocol subscribe ports (user's design)
Signal into CH2 -> each protocol has its OWN subscribe port (repo idea), decoded by
our GR 3.8 C++ OOT blocks:

  mon_scan CH2 (X310) --PUB 5202--> ch2_proto_pub --per-protocol ports--> decoders
     DMR 7001 · NXDN 7002 · P25 7003 · TETRA 7004 · D-STAR 7006
  decoder (our dsd/tetra) -> audio via FIFO + paplay (PulseAudio) + wav + call_log.

- ch2_proto_pub.py : subscribes the CH2 feed, re-publishes each band's IQ on its
  protocol port. Each decoder subscribes only to its port.
- decode_dsd.py / decode_tetra.py : --endpoint tcp://127.0.0.1:<port>, --fifo for audio.
- run_terrestrial_ch2.sh : starts the fan-out + all CH2 protocol decoders with audio.
- AUDIO: GR 3.8 audio.sink here is OSS-only (/dev/dsp absent) and padsp is broken, so
  audio goes dsd(8k)->int16->FIFO-> `paplay --raw --format=s16le --rate=8000 --channels=1`.
  Verified paplay->PulseAudio works.
- VERIFIED OFFLINE (no USRP): fan-out routes each band to its port; a decoder subscribes
  to its port and processes IQ (wav grows). DSD verified decoding real D-STAR earlier.
- FOR SUSTAINED VOICE: scanning gives short dwells; pin CH2 to the active band
  (mon_scan --pin "2=DMR 446.100") so the decoder gets continuous IQ.

## REPO CONSOLE WIRED (2026-10-13) — CH2 drives securecom_gui.html live
The repo's own console (terrestrial_src/gui/securecom_gui.html, Decodio-style
spectrum/waterfall/time + audio) is now driven by our CH2 feed, WITHOUT running the
repo's Module 1 (RF, owns the B210) or Module 2 (decoder). The repo files are NOT edited.

Data flow:
  mon_scan CH2 --pub ──ZMQ 5202──┬─ ch2_iq_tcp.py ──TCP 7001-7008 @200kS/s─┐
                                 │                                          ├─> bridge_server_ext
                                 └─ decode_*.py (band-filtered)             │   (repo bridge,
                                      --audio-tap ──ZMQ 9101-9107 (48k f32)─┘    ws 8787) ─> console

- bridge_server reads IQ as a TCP CLIENT on 7001-7008 (complex64 @200 kHz) and audio as
  ZMQ SUB on 9101-9109 (raw float32 @48 kHz); it derives the DF/decode log from audio RMS.
- ch2_iq_tcp.py : NEW. Subscribes CH2 (5202), decimates 2 MS/s->200 kS/s (scipy
  resample_poly 1/10), serves each band on its TCP port; idle bands stream zero-fill
  (matches the bridge's "7 of 8 zero-fill" model). Band->port: DMR 7001, NXDN 7002,
  P25 7003, TETRA 7004, D-STAR 7006.
- zmq_f32_sink.py : NEW. GR 3.8 sink (no gnuradio.zeromq) that PUBs raw float32 — the
  exact wire format audio_tap_reader expects.
- decode_dsd.py / decode_tetra.py : added --audio-tap PORT (8k dsd -> 48k -> ZMQ PUB).
  DMR 9101 · NXDN 9102 · P25 9103 · TETRA 9104 · D-STAR 9107.
- bridge_server_ext.py : NEW wrapper. Imports the repo bridge unchanged, monkey-patches
  start_module1/start_module2 to EXTERNAL-feed mode (no subprocess; just spawn iq_readers
  + audio_tap_readers). Everything else (ws 8787, spectrum/waterfall/time, active-band,
  DF log, recordings) runs as shipped. Console needs no change.
- run_ch2_bridge.sh : starts bridge_ext + ch2_iq_tcp + the 5 decoders (audio-tap, --no-audio).
- Console UX: open serve_ui.sh -> CH2 panel -> Land radio -> click Start, then Start decoder.

VERIFIED OFFLINE (no USRP), synthetic CH2 publisher (DMR band = +30 kHz tone):
  end-to-end ws stream = 'iq' messages for all 8 bands; the 5 CH2 bands go active=True
  with real 256-bin spectra, the 3 unused ports stay zero-fill. DMR tone landed at
  bin 166/256 = centre+38 bins = +30 kHz (decimation + spectrum correct). Decoder ran
  and bound its 48 kHz float32 tap on 9101. active-band + idle logic correct.
NEXT: live hardware run (mon_scan CH2 --pin "2=DMR 446.100", key the DMR radio) to
  confirm real spectrum + decoded voice in the embedded console.

## Unified console UI (guru_mon_scan/securecom_ui.html)
One page, 5 selectable panels: CH1 Drone, CH2 Terrestrial (embeds the repo consoles via
iframe — land securecom_gui.html, air/marine airmaritime_console.html), CH3 Radar, CH4
IMSI, Monitoring Backend (scan_plan editor). Serve via radar2/serve_ui.sh so the iframes
share one origin (Chrome blocks cross-folder file:// iframes).
