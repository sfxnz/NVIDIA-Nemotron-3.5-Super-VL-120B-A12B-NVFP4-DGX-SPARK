#!/usr/bin/env bash
# Graceful stop of the container that ./run.sh started, and of its memory guard.
# Only a container carrying this recipe's label is touched. On SIGTERM vLLM stops taking requests and lets running
# ones finish for up to 45 s (--shutdown-timeout in run.sh); Docker kills it after STOP_TIMEOUT seconds.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="${NAME:-nemotron-3.5-super-vl}"
STOP_TIMEOUT="${STOP_TIMEOUT:-60}"
LABEL="ai-lab.recipe=nemotron-3.5-super-vl-spark"
PIDFILE="$SCRIPT_DIR/.run-state/$NAME.memguard.pid"

[[ "$NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || { echo "NAME=$NAME is not a valid container name." >&2; exit 1; }
[[ "$STOP_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "STOP_TIMEOUT=$STOP_TIMEOUT is not a positive integer." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "cannot talk to the Docker daemon." >&2; exit 1; }

stop_memguard() {
  [[ -f "$PIDFILE" ]] || return 0
  local pid
  pid="$(tr -cd '0-9' <"$PIDFILE")"
  # Only the guard this recipe started for NAME: its argv is "bash .../memguard.sh NAME LOG".
  if [[ -n "$pid" ]] && [[ "$(tr '\0' '\n' <"/proc/$pid/cmdline" 2>/dev/null | sed -n 3p)" == "$NAME" ]]; then
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
}

# A here-string, not a pipe: under pipefail an early-exiting `grep -q` can turn a match into a miss.
if ! grep -Fqx "$NAME" <<<"$(docker ps -a --filter "label=$LABEL" --format '{{.Names}}')"; then
  if grep -Fqx "$NAME" <<<"$(docker ps -a --format '{{.Names}}')"; then
    echo "Container $NAME exists but was not started by this recipe (no $LABEL label). Not touching it." >&2
    exit 1
  fi
  stop_memguard
  echo "No container $NAME from this recipe."
  exit 0
fi

# Stop the guard first so it cannot act on a container that is shutting down on purpose.
stop_memguard
echo "Stopping $NAME (running requests get up to 45 s to finish)"
docker stop -t "$STOP_TIMEOUT" "$NAME" >/dev/null 2>&1 || true
docker rm -f "$NAME" >/dev/null
echo "Stopped $NAME. Memory now: $(awk '/^MemAvailable:/{printf "%.1f GiB", $2/1048576}' /proc/meminfo) available"
