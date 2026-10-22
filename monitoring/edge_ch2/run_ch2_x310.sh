#!/usr/bin/env bash
# The NEW per-channel CH2 pipeline on the X310 (USRP-2945) — no B210, no Module 1.
#
#   ch2_scheduler (GR3.8/UHD3.15, X310 @200kHz, hop 4 bands)
#      --PUB 5202 (CH2 header stream)-->  ch2_header_router  --TCP 7001-7004-->
#      allinone.py (the proven 4-protocol decoder, GR3.10)  -->  bridge + console
#
# The scheduler REPLACES Module 1 (X310 owns the radio over Ethernet). The router
# splits the single CH2 stream to the 4 protocol ports the decoder reads.
#
# Run:  ./run_ch2_x310.sh         then open the console, Start hardware + Start decoder
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$HOME/radar2/backupv1/secuecom-version1"
GR38="source $HOME/gnuradio-3.8/setup_env.sh"
# system GR3.10 env (strip the leaking 3.8 paths)
SYS="env -u LD_LIBRARY_PATH -u PYTHONPATH PATH=/usr/local/bin:/usr/bin:/bin LD_LIBRARY_PATH=/usr/local/lib"
ADDR="addr=192.168.10.2"
PIDS=()
cleanup(){ echo; echo "[ch2-x310] stopping"; kill "${PIDS[@]}" 2>/dev/null; pkill -P $$ 2>/dev/null; exit 0; }
trap cleanup INT TERM

echo "[ch2-x310] checking X310 at 192.168.10.2 ..."
ping -c2 -W2 192.168.10.2 >/dev/null 2>&1 || { echo "  X310 not answering. Connect it, then: sudo nmcli connection up usrp"; exit 1; }
echo "  OK"

# 1) console bridge WITHOUT Module 1 (system GR3.10) + web server
echo "[ch2-x310] bridge (external, no Module 1) + web console"
( cd "$REPO/gui" && $SYS python3 -u "$HERE/backupv1_bridge_ext.py" ) > /tmp/ch2x310_bridge.log 2>&1 &
PIDS+=($!)
( cd "$REPO/gui" && $SYS python3 -m http.server 8788 --bind 127.0.0.1 ) > /tmp/ch2x310_http.log 2>&1 &
PIDS+=($!)
sleep 2

# 2) header-router: CH2 stream 5202 -> TCP 7001-7004
echo "[ch2-x310] header-router  5202 -> 7001-7004"
( cd "$HERE" && $SYS python3 -u ch2_header_router.py --in tcp://127.0.0.1:5202 --base-port 7001 ) > /tmp/ch2x310_router.log 2>&1 &
PIDS+=($!)
sleep 1

# 3) scheduler on the X310 (GR3.8/UHD3.15) -> PUB 5202
echo "[ch2-x310] scheduler on X310 @200kHz, hop DMR/NXDN/P25/TETRA -> PUB 5202"
( cd "$HERE" && bash -c "$GR38 >/dev/null 2>&1; exec python3 -u ch2_scheduler.py --addr '$ADDR' --samp-rate 200000 --gain 40 --dwell 2 --out tcp://127.0.0.1:5202" ) > /tmp/ch2x310_sched.log 2>&1 &
PIDS+=($!)

echo
echo "[ch2-x310] up. Open the console:   http://127.0.0.1:8788/securecom_gui.html"
echo "           then Hardware tab -> Start hardware, then Start decoder."
echo "           Key your DMR radio on 446.118 MHz. Logs in /tmp/ch2x310_*.log"
echo "           Ctrl-C stops everything."
wait
