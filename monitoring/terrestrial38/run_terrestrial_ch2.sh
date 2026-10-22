#!/usr/bin/env bash
# Terrestrial decoding on CH2 — our GR 3.8 / UHD 3.15 version of the repo pipeline.
#
# Data flow (user's design, same idea as the repo's per-protocol TCP ports):
#   mon_scan CH2 (X310)  --PUB 5202-->  ch2_proto_pub  --per-protocol ports-->  decoders
#     DMR 7001 · NXDN 7002 · P25 7003 · TETRA 7004 · D-STAR 7006
#   each decoder (our dsd / tetra C++ OOT) subscribes to ITS port, decodes, and
#   plays audio to PulseAudio via a FIFO + paplay (GR 3.8 audio.sink here is OSS-only).
#
# Start the publisher first (one terminal):
#   cd ~/radar2/guru_mon_scan && ./run_mon_scan.sh --gain 45 --channels 2 --pub
#   (for sustained voice on one band:  add  --pin "2=DMR 446.100")
# Then this:
#   cd ~/radar2/terrestrial38 && ./run_terrestrial_ch2.sh
set -u
cd "$(dirname "$0")"
set +u; source ~/gnuradio-3.8/setup_env.sh; set -u
CH2="tcp://127.0.0.1:5202"
PCM="$(mktemp -d /tmp/terr_ch2.XXXXXX)"
mkdir -p logs
PIDS=()

cleanup(){ echo; echo "[terr] stopping"; kill "${PIDS[@]}" 2>/dev/null; pkill -P $$ 2>/dev/null; rm -rf "$PCM"; exit 0; }
trap cleanup INT TERM

echo "[terr] CH2 fan-out: $CH2 -> per-protocol ports 7001..7006"
python3 ch2_proto_pub.py --in "$CH2" > logs/proto_pub.log 2>&1 &
  PIDS+=($!)
sleep 1

# proto  port  launch
start_dsd(){ # name port protoflag
  local name=$1 port=$2 proto=$3 fifo="$PCM/$1.pcm"
  mkfifo "$fifo"
  paplay --raw --format=s16le --rate=8000 --channels=1 "$fifo" >/dev/null 2>&1 &
  PIDS+=($!)
  python3 -u decode_dsd.py --endpoint "tcp://127.0.0.1:$port" --proto "$proto" \
     --fifo "$fifo" --wav "logs/$name.wav" > "logs/$name.log" 2>&1 &
  PIDS+=($!)
  echo "[terr] $name  port $port  -> audio+log"
}
start_tetra(){
  local fifo="$PCM/tetra.pcm"; mkfifo "$fifo"
  paplay --raw --format=s16le --rate=8000 --channels=1 "$fifo" >/dev/null 2>&1 &
  PIDS+=($!)
  python3 -u decode_tetra.py --endpoint "tcp://127.0.0.1:7004" --fifo "$fifo" \
     > logs/tetra.log 2>&1 &
  PIDS+=($!)
  echo "[terr] tetra port 7004 -> audio+log"
}

start_dsd  dstar 7006 dstar
start_dsd  dmr   7001 dmr
start_dsd  p25   7003 p25
start_dsd  nxdn  7002 nxdn
start_tetra

echo "[terr] all CH2 terrestrial protocols running. Logs in logs/. Ctrl-C to stop."
wait
