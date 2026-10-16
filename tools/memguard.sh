#!/usr/bin/env bash
# memguard.sh NAME LOG: last line of defence against a host OOM on unified memory.
# Every 2 s it reads /proc/meminfo. If MemAvailable < MEMGUARD_MIN_AVAIL_MIB and SwapFree < MEMGUARD_MIN_SWAP_MIB
# for 3 samples in a row, it stops container NAME (SIGTERM, then SIGKILL after 10 s) so the rest of the box survives.
# It exits when the container is gone. ./run.sh starts it; ./stop.sh stops it.
set -u
NAME="$1"
LOG="$2"
MIN_AVAIL="${MEMGUARD_MIN_AVAIL_MIB:-2048}"
MIN_SWAP="${MEMGUARD_MIN_SWAP_MIB:-2048}"
low=0
while [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" == true ]]; do
  read -r avail swapfree < <(awk '/^MemAvailable:/{a=$2} /^SwapFree:/{s=$2} END{printf "%d %d\n", a/1024, s/1024}' /proc/meminfo)
  if (( avail < MIN_AVAIL && swapfree < MIN_SWAP )); then low=$((low + 1)); else low=0; fi
  if (( low >= 3 )); then
    msg="memguard: MemAvailable ${avail} MiB and SwapFree ${swapfree} MiB below ${MIN_AVAIL}/${MIN_SWAP} MiB for 6 s; stopping $NAME"
    echo "$(date -Is) $msg" >>"$LOG"
    logger -t "$NAME-memguard" "$msg" 2>/dev/null || true
    docker stop -t 10 "$NAME" >/dev/null 2>&1 || docker kill "$NAME" >/dev/null 2>&1 || true
    exit 2
  fi
  sleep 2
done
