#!/usr/bin/env bash
# Run the MON scanning GUI (guru_mon_scan). No HackRF - real antennas only.
# Checks the X310 link, then launches the 4-channel scanning app.
#
#   ./run_mon_scan.sh                 # gain 50 dB
#   ./run_mon_scan.sh --gain 55 --verbose
set -u
cd "$(dirname "$0")"

# GNU Radio 3.8 + UHD 3.15 isolated env
set +u
source ~/gnuradio-3.8/setup_env.sh
set -u
export DISPLAY="${DISPLAY:-:0}"

ADDR="192.168.10.2"
echo "[run] checking X310 at ${ADDR} ..."
if ! ping -c 2 -W 2 "${ADDR}" >/dev/null 2>&1; then
  echo "[run] X310 not answering."
  echo "      If the NIC lost its address (NetworkManager), bring it back with:"
  echo "        sudo nmcli connection up usrp"
  echo "      then check:  ip -br addr show enp3s0   (want 192.168.10.1/24)"
  exit 1
fi
echo "[run] X310 up. Starting MON scanning (close the window to stop)."
exec python3 mon_scan.py --addr "addr=${ADDR}" "$@"
