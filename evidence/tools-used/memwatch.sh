#!/usr/bin/env bash
# memwatch.sh NAME LOG [MIN_AVAIL_MIB]
# Polls /proc/meminfo once a second, appends "epoch,avail_mib,free_mib,swapfree_mib" to LOG,
# and stops container NAME if MemAvailable stays below MIN_AVAIL_MIB for 3 consecutive samples.
# Exits when the container is gone.
set -u
NAME="$1"; LOG="$2"; MIN="${3:-3072}"
low=0
echo "epoch,avail_mib,free_mib,swapfree_mib" >"$LOG"
while docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -q true; do
  read -r avail free swapfree < <(awk '/^MemAvailable:/{a=$2}/^MemFree:/{f=$2}/^SwapFree:/{s=$2}END{printf "%d %d %d\n", a/1024, f/1024, s/1024}' /proc/meminfo)
  echo "$(date +%s),$avail,$free,$swapfree" >>"$LOG"
  if (( avail < MIN )); then low=$((low + 1)); else low=0; fi
  if (( low >= 3 )); then
    echo "$(date +%s),WATCHDOG_TRIP avail=${avail}MiB < ${MIN}MiB; stopping $NAME" >>"$LOG"
    docker stop -t 10 "$NAME" >/dev/null 2>&1
    exit 2
  fi
  sleep 1
done
