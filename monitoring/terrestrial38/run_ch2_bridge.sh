#!/usr/bin/env bash
# CH2 terrestrial -> the REPO's own console (securecom_gui.html), driven live.
#
# Pipeline (no USRP touched by the bridge; mon_scan owns the radio):
#
#   mon_scan CH2 --pub ──ZMQ 5202──┬─> ch2_iq_tcp.py ──TCP 7001-7008──> bridge_server_ext
#                                   │                                    (repo bridge,
#                                   │                                     ws 8787) ──> console
#                                   └─> decode_*.py (band-filtered) ──ZMQ 9101-9107──┘
#                                                                         (48 kHz audio taps)
#
# bridge_server_ext.py = the repo bridge in EXTERNAL-feed mode: it does NOT launch
# Module 1 (RF) or Module 2 (decoder); it reads our IQ (7001-8) and audio (9101-7).
#
# Start mon_scan publishing CH2 in another terminal FIRST:
#   cd ~/radar2/guru_mon_scan && ./run_mon_scan.sh --channels 2 --pub
#   (sustained voice on one band:  add  --pin "2=DMR 446.100")
# Then this. Then open the console (serve_ui.sh) and click Start + Start decoder.
set -u
cd "$(dirname "$0")"
set +u; source ~/gnuradio-3.8/setup_env.sh; set -u
CH2="tcp://127.0.0.1:5202"
mkdir -p logs
PIDS=()
cleanup(){ echo; echo "[ch2-bridge] stopping"; kill "${PIDS[@]}" 2>/dev/null; pkill -P $$ 2>/dev/null; exit 0; }
trap cleanup INT TERM

echo "[ch2-bridge] repo bridge (external feed) on ws://127.0.0.1:8787"
python3 -u bridge_server_ext.py            > logs/bridge.log      2>&1 & PIDS+=($!)
sleep 1
echo "[ch2-bridge] IQ feed: CH2 $CH2 -> TCP 7001-7008 @ 200 kS/s"
python3 -u ch2_iq_tcp.py --in "$CH2"       > logs/iq_tcp.log      2>&1 & PIDS+=($!)
sleep 1

# proto  band(as mon_scan tags)  audio-tap port
start_dsd(){ # proto "band" tap
  python3 -u decode_dsd.py --endpoint "$CH2" --proto "$1" --band "$2" \
      --audio-tap "$3" --no-audio --wav "logs/$1.wav" > "logs/$1.log" 2>&1 & PIDS+=($!)
  echo "[ch2-bridge] $1  band='$2'  audio-tap $3"
}
start_dsd dmr   "DMR 446.100" 9101
start_dsd nxdn  "NXDN 451.0"  9102
start_dsd p25   "P25 450.0"   9103
start_dsd dstar "D-STAR 145.0" 9107
python3 -u decode_tetra.py --endpoint "$CH2" --band "TETRA 420.0" \
    --audio-tap 9104 > logs/tetra.log 2>&1 & PIDS+=($!)
echo "[ch2-bridge] tetra band='TETRA 420.0' audio-tap 9104"

echo "[ch2-bridge] up. Open the console:  cd ~/radar2 && ./serve_ui.sh"
echo "[ch2-bridge]   then CH2 panel -> Land radio -> click Start, then Start decoder."
echo "[ch2-bridge] logs in $(pwd)/logs/.  Ctrl-C to stop."
wait
