#!/usr/bin/env bash
# Functional acceptance suite against the server ./run.sh started: thinking modes, tool calls, streaming, JSON schema,
# images, a ~102K-token needle, multi-turn prefix caching, concurrent crosstalk, errors. Exit 0 only if every hard
# check passed. Needs python3 on the host (standard library; Pillow optional, for the text-in-image check).
#
#   ./test.sh          full suite (about 4 min with the needle; longer for PROFILE=throughput's 256-way burst)
#   ./test.sh quick    skip the long-context needle
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="${NAME:-nemotron-3.5-super-vl}"
API_KEY="${API_KEY:-}"
LABEL="ai-lab.recipe=nemotron-3.5-super-vl-spark"
MODE="${1:-full}"

die() { printf 'test.sh: %s\n' "$*" >&2; exit 1; }
[[ "$MODE" == full || "$MODE" == quick ]] || die "usage: ./test.sh [full|quick]"
command -v python3 >/dev/null || die "python3 not found."
docker info >/dev/null 2>&1 || die "cannot talk to the Docker daemon."
grep -Fqx "$NAME" <<<"$(docker ps --filter "label=$LABEL" --format '{{.Names}}')" || die "$NAME is not running. ./run.sh first."

ARGS="$(docker inspect -f '{{join .Args " "}}' "$NAME")"
arg() { { grep -oE -- "--$1 [^ ]+" <<<"$ARGS" || true; } | tail -1 | cut -d' ' -f2; }  # vLLM keeps the last value
SEQS="$(arg max-num-seqs)"; SEQS="${SEQS:-1}"
MML="$(arg max-model-len)"; MML="${MML:-0}"
SERVED="$(arg served-model-name)"
IMAGES="$(grep -oE '"image":\{"count":[0-9]+' <<<"$ARGS" | tail -1 | grep -oE '[0-9]+$' || true)"
HOSTPORT="$(docker port "$NAME" 8000/tcp | head -1)"
HOST="${HOSTPORT%:*}"
[[ "$HOST" == 0.0.0.0 || "$HOST" == "[::]" ]] && HOST=127.0.0.1
# The http-URL image check serves a PNG on the Docker bridge gateway, which only containers can reach.
GATEWAY="$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || echo 172.17.0.1)"

OUT_DIR="$SCRIPT_DIR/test-results"; mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/functional-$(date +%Y%m%d-%H%M%S).json"
EXTRA=()
[[ "$MODE" == quick ]] && EXTRA+=(--skip-long)
VLLM_API_KEY="$API_KEY" python3 "$SCRIPT_DIR/tools/functional_tests.py" \
  --base "http://$HOST:${HOSTPORT##*:}" --model "$SERVED" --concurrency "$SEQS" \
  --image-limit "${IMAGES:-0}" --expect-max-model-len "$MML" \
  --http-bind "$GATEWAY" --http-host "$GATEWAY" --out "$OUT" "${EXTRA[@]}"
