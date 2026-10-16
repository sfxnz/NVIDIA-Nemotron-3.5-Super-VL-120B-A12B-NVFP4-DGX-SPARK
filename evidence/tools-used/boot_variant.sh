#!/usr/bin/env bash
# boot_variant.sh SCRIPT EXPDIR : start a variant container, wait for /v1/models, start memwatch.
set -euo pipefail
S=/tmp/claude-1000/-home-sfxnz-projects-ai-lab-recipes-NVIDIA-Nemotron-3-5-Super-VL-120B-A12B-NVFP4-DGX-SPARK/ed423547-af69-4f64-a551-32ddd0b572a3/scratchpad
mkdir -p "$2"; free -h >"$2/free-before.txt"; cp "$1" "$2/"
t0=$(date +%s); bash "$1" >/dev/null
nohup "$S/tools/memwatch.sh" nemotron-3.5-super-vl "$2/mem.csv" 3072 >/dev/null 2>&1 &
until curl -fsS localhost:8000/v1/models >/dev/null 2>&1; do
  docker ps --format '{{.Names}}' | grep -qx nemotron-3.5-super-vl || { echo EXITED; docker logs nemotron-3.5-super-vl 2>&1 | tail -30; exit 1; }
  sleep 5
done
echo "ready after $(( $(date +%s) - t0 ))s" | tee "$2/ready.txt"; free -h | tee "$2/free-after-boot.txt"
