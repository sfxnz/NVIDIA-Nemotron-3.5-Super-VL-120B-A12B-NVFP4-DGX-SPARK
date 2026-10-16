#!/usr/bin/env bash
# Benchmark the server that ./run.sh started, with the same harness and prompts as the README tables.
#
#   ./bench.sh                    decode + concurrency sweep + prefill (about 40 min; 60+ for PROFILE=throughput)
#   ./bench.sh decode             single-stream decode only (about 12 min)
#   ./bench.sh sweep              concurrency sweep only
#   LEVELS=1,8,32 ./bench.sh sweep
#
# The client is a throwaway container from the serving image on the host network, run as you. It never touches the
# serving container. First run needs internet once: pip installs pandas/pyarrow and SPEED-Bench is fetched (cached).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="${NAME:-nemotron-3.5-super-vl}"
SETS="${1:-${SETS:-decode,sweep,prefill}}"
CACHE_DIR="$(realpath -m -- "${CACHE_DIR:-$SCRIPT_DIR/.cache}")"
OUT="$(realpath -m -- "${OUT:-$SCRIPT_DIR/bench-results/$(date +%Y%m%d-%H%M%S)}")"
API_KEY="${API_KEY:-}"
LABEL="ai-lab.recipe=nemotron-3.5-super-vl-spark"

die() { printf 'bench.sh: %s\n' "$*" >&2; exit 1; }
[[ "$SETS" =~ ^(decode|sweep|prefill)(,(decode|sweep|prefill))*$ ]] || die "sets must be decode, sweep and/or prefill."
docker info >/dev/null 2>&1 || die "cannot talk to the Docker daemon."
grep -Fqx "$NAME" <<<"$(docker ps --filter "label=$LABEL" --format '{{.Names}}')" || die "$NAME is not running. ./run.sh first."

IMAGE="$(docker inspect -f '{{.Config.Image}}' "$NAME")"
ARGS="$(docker inspect -f '{{join .Args " "}}' "$NAME")"
arg() { { grep -oE -- "--$1 [^ ]+" <<<"$ARGS" || true; } | tail -1 | cut -d' ' -f2; }  # vLLM keeps the last value
MODEL="$(tr ' ' '\n' <<<"$ARGS" | grep -m1 -E '^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+$')"  # first org/name arg
REV="$(arg revision)"
SEQS="$(arg max-num-seqs)"; SEQS="${SEQS:-1}"
HF_CACHE="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/root/.cache/huggingface"}}{{.Source}}{{end}}{{end}}' "$NAME")"
[[ -n "$HF_CACHE" ]] || die "cannot find the Hugging Face cache mount of $NAME."
HOSTPORT="$(docker port "$NAME" 8000/tcp | head -1)"
HOST="${HOSTPORT%:*}"
[[ "$HOST" == 0.0.0.0 || "$HOST" == "[::]" ]] && HOST=127.0.0.1
BASE="http://$HOST:${HOSTPORT##*:}"
models() {
  if [[ -n "$API_KEY" ]]; then curl -fsS -H @<(printf 'Authorization: Bearer %s\n' "$API_KEY") "$BASE/v1/models"
  else curl -fsS "$BASE/v1/models"; fi
}
info="$(models | python3 -c 'import json,sys; m=json.load(sys.stdin)["data"][0]; print(m["id"], m["max_model_len"])' 2>/dev/null)" \
  || die "cannot reach $BASE/v1/models (if the server has an API key, export API_KEY)."
read -r SERVED MML <<<"$info"

if [[ -z "${LEVELS:-}" ]]; then
  LEVELS=""
  for c in 1 2 4 8 16 32 64 128 256 512; do (( c <= SEQS )) && LEVELS+="${LEVELS:+,}$c"; done
  [[ ",$LEVELS," == *",$SEQS,"* ]] || LEVELS+=",$SEQS"
fi
[[ "$LEVELS" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$ ]] || die "LEVELS=$LEVELS must look like 1,8,32."

mkdir -p "$OUT" "$CACHE_DIR/bench"
echo "==> $SERVED at $BASE, max-num-seqs $SEQS, sets $SETS, levels $LEVELS"
echo "==> results in $OUT"
{
  echo "date: $(date -Is)"
  echo "container: $NAME image: $IMAGE"
  echo "args: $ARGS"
  echo "free -h before:"; free -h
} >"$OUT/conditions.txt"

TOK="/hf/hub/models--${MODEL//\//--}/snapshots/$REV"
set +e
OPENAI_API_KEY="${API_KEY:-EMPTY}" docker run --rm --network host --user "$(id -u):$(id -g)" --entrypoint bash \
  -e HOME=/tmp -e OPENAI_API_KEY -e HF_HOME=/bench/hf -e PIP_CACHE_DIR=/bench/pip \
  -v "$HF_CACHE:/hf:ro" -v "$CACHE_DIR/bench:/bench" -v "$OUT:/out" -v "$SCRIPT_DIR/tools:/tools:ro" \
  "$IMAGE" -c "
    set -e
    if [ ! -s /bench/speedbench.json ]; then
      pip install -q --user pandas pyarrow || { echo 'bench.sh: pip install pandas pyarrow failed (the first run needs internet)' >&2; exit 3; }
      python3 /tools/prepare_speedbench.py /bench/speedbench.json $TOK
    fi
    HF_HUB_OFFLINE=1 python3 /tools/bench_suite.py --base-url $BASE --model '$SERVED' --tokenizer $TOK \
      --prompts /bench/speedbench.json --out /out --levels $LEVELS --sets $SETS --max-model-len $MML" 2>&1 \
  | tee "$OUT/client.log" | grep --line-buffered -v -E '^(WARNING|INFO|DEBUG)|Warning|warn\('
rc=${PIPESTATUS[0]}
set -e

{ echo "free -h after:"; free -h; } >>"$OUT/conditions.txt"
(( rc == 0 )) || die "one or more cells failed (exit $rc); see client.log and the *.log files in $OUT."
echo "==> summary: $OUT/summary.md"
