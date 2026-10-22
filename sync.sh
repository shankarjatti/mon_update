#!/usr/bin/env bash
# sync.sh - copy the monitoring work from the lab folders (~/radar2) into this repo.
# Only the files listed here are published. NEVER add: main_sched/ (private design sheet and
# slides), *.wav / results CSVs / tarballs, build folders, old frozen repos.
set -euo pipefail
R="${R:-$HOME/radar2}"
M="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$M/monitoring/guru_mon_scan" "$M/monitoring/edge_ch2" "$M/monitoring/terrestrial38" "$M/design" "$M/docs"

for f in scan_plan.py mon_scan.py mon_server.py mon_pub.py mon_sub_example.py mon_scan_retune.py \
         run_mon_scan.sh securecom_ui.html monitoring_ui.html README_MON_SCAN.md BUILD_LOG.md BLOCK_DIAGRAM.md look_power.py; do
  [ -f "$R/guru_mon_scan/$f" ] && cp -p "$R/guru_mon_scan/$f" "$M/monitoring/guru_mon_scan/"
done
rsync -a --delete --exclude __pycache__ --exclude ch2_lock.txt --exclude ch2_mode.txt --exclude 'pin_ch*.txt' \
      "$R/edge_ch2/" "$M/monitoring/edge_ch2/"
rsync -a --delete --exclude __pycache__ --exclude '*.wav' --exclude deps \
      "$R/terrestrial38/" "$M/monitoring/terrestrial38/"
cp -p "$R/monitoring_sim.html" "$M/design/"
[ -f "$R/DSD38_PORT_PLAN.md" ] && cp -p "$R/DSD38_PORT_PLAN.md" "$M/docs/"

# secret / private check before anything is committed
if grep -rniE "ghp_|gho_|github_pat|BEGIN [A-Z ]*PRIVATE|main_sched|SecureCOM_Design" "$M" \
     --exclude-dir=.git --exclude=sync.sh --exclude=WORK_LOG.md | grep -q .; then
  echo "STOP: secret or private reference found:" >&2
  grep -rniE "ghp_|gho_|github_pat|BEGIN [A-Z ]*PRIVATE|main_sched|SecureCOM_Design" "$M" \
     --exclude-dir=.git --exclude=sync.sh --exclude=WORK_LOG.md >&2
  exit 1
fi
big=$(find "$M" -path "$M/.git" -prune -o -type f -size +2M -print)
[ -z "$big" ] || { echo "STOP: file over 2 MB: $big" >&2; exit 1; }
echo "synced: $(find "$M" -path "$M/.git" -prune -o -type f -print | wc -l) files, $(du -sh --exclude=.git "$M" | cut -f1)"
