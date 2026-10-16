#!/usr/bin/env bash
# NVIDIA Nemotron 3.5 Super VL (120B total / 12B active, NVFP4) on one DGX Spark (GB10) with vLLM.
#
#   ./run.sh                      download (first run), start, wait until ready, smoke-test
#   PROFILE=throughput ./run.sh   no speculative decoding, most concurrent sequences
#   VALIDATE_ONLY=1 ./run.sh      check the settings and print the docker command; touches nothing
#   ./stop.sh                     graceful stop
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------- pins (do not float these)
# vLLM nightly 3f1bcfd8 (0.32.0rc1.dev190), the image the model card names. Multi-arch index digest.
IMAGE="vllm/vllm-openai@sha256:cb9bc64f0f038c2c2ebf13b31248fb87aca40c356c3d20f363be087cfcff1fcd"
MODEL="nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4"
MODEL_REV="82d93699acd3be9e4617c53360fe5b3f5dbeb1b3"
DRAFT="nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-LiLiCorr"
DRAFT_REV="7c7221aeb4cb3139307aa457f7dce11a8fb6ceb2"
LABEL="ai-lab.recipe=nemotron-3.5-super-vl-spark"

# ---------------------------------------------------------------- knobs
PROFILE="${PROFILE:-default}"
NAME="${NAME:-nemotron-3.5-super-vl}"
SERVED_NAME="${SERVED_NAME:-nemotron-3.5-super-vl}"
BIND="${BIND:-127.0.0.1}"
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-262144}"
IMAGES_PER_PROMPT="${IMAGES_PER_PROMPT:-4}"
HF_CACHE="$(realpath -m -- "${HF_CACHE:-$HOME/.cache/huggingface}")"
CACHE_DIR="$(realpath -m -- "${CACHE_DIR:-$SCRIPT_DIR/.cache}")"
READY_TIMEOUT="${READY_TIMEOUT:-1800}"
VALIDATE_ONLY="${VALIDATE_ONLY:-0}"
SKIP_SMOKE="${SKIP_SMOKE:-0}"
API_KEY="${API_KEY:-}"
EXTRA_ARGS="${EXTRA_ARGS:-}"
FORCE_UNSAFE_MEMORY="${FORCE_UNSAFE_MEMORY:-0}"
KV_USER="${KV_CACHE_GIB:-}"

case "$PROFILE" in
  default)
    # LiLiCorr drafter (7 tokens) for single-stream speed; block 256 keeps its sliding-window pages unpadded.
    PROFILE_SEQS=32
    PROFILE_KV_GIB=19
    PROFILE_BLOCK=256
    PROFILE_MNBT=4608
    PROFILE_SPEC="{\"method\":\"dflash\",\"model\":\"$DRAFT\",\"revision\":\"$DRAFT_REV\",\"num_speculative_tokens\":7}"
    BASE_GIB=88  # everything but the KV pool and the image-embedding cache, at the soak's worst point
    ;;
  throughput)
    # No drafter and no prefix caching: one 82 MiB Mamba state per sequence instead of nine.
    PROFILE_SEQS=192  # the 20 GiB pool holds about 200 short sequences; beyond that requests only queue
    PROFILE_KV_GIB=20
    PROFILE_BLOCK=64
    PROFILE_MNBT=4608
    PROFILE_SPEC=""
    BASE_GIB=86
    ;;
  *) echo "PROFILE=$PROFILE: use default or throughput." >&2; exit 1 ;;
esac
MAX_NUM_SEQS="${MAX_NUM_SEQS:-$PROFILE_SEQS}"
KV_CACHE_GIB="${KV_USER:-$PROFILE_KV_GIB}"
# vLLM's own start check: this fraction of the 121.7 GiB must be free. The KV pool itself is pinned below.
GPU_UTIL="${GPU_UTIL:-0.75}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'run.sh: %s\n' "$*" >&2; exit 1; }
is_uint() { [[ "$1" =~ ^[1-9][0-9]*$ ]]; }
in_range() { [[ "$1" =~ ^(0|[1-9][0-9]*)$ ]] && (( $1 >= $2 && $1 <= $3 )); }  # VALUE MIN MAX

# ---------------------------------------------------------------- validation (also runs under VALIDATE_ONLY)
[[ "$NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || die "NAME=$NAME is not a valid container name."
[[ "$SERVED_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_./:-]*$ ]] || die "SERVED_NAME=$SERVED_NAME has unsupported characters."
valid_ip=1
IFS=. read -r o1 o2 o3 o4 extra <<<"$BIND"
for o in "$o1" "$o2" "$o3" "$o4"; do in_range "$o" 0 255 || valid_ip=0; done
[[ "$valid_ip" == 1 && -z "$extra" ]] || die "BIND=$BIND must be an IPv4 address (127.0.0.1, 0.0.0.0 or one interface's address)."
in_range "$PORT" 1 65535 || die "PORT=$PORT is not a valid port."
in_range "$MAX_MODEL_LEN" 1024 1048576 || die "MAX_MODEL_LEN=$MAX_MODEL_LEN must be 1024..1048576."
in_range "$MAX_NUM_SEQS" 1 512 || die "MAX_NUM_SEQS=$MAX_NUM_SEQS must be 1..512."
in_range "$IMAGES_PER_PROMPT" 0 16 || die "IMAGES_PER_PROMPT=$IMAGES_PER_PROMPT must be 0..16."
in_range "$KV_CACHE_GIB" 4 40 || die "KV_CACHE_GIB=$KV_CACHE_GIB must be 4..40 (whole GiB)."
[[ "$GPU_UTIL" =~ ^0\.[0-9]{1,3}$ ]] || die "GPU_UTIL=$GPU_UTIL must look like 0.75."
is_uint "$READY_TIMEOUT" || die "READY_TIMEOUT=$READY_TIMEOUT is not a positive integer."

# Image embeddings stay cached until vLLM needs the room. The cache budget is max-model-len tokens of 8 KiB each
# (vLLM sizes it from the context, not from the 3328-token largest image), so it can grow to that size: 2 GiB at
# 262144, 8 GiB at 1048576. It sits outside the KV pool, so the memory plan below counts it.
if (( IMAGES_PER_PROMPT > 0 )); then
  ENC_GIB=$(( (MAX_MODEL_LEN * 8192 + (1 << 30) - 1) >> 30 ))
  # Profiling sizes its dummy image to fill the whole context (8184x8184 px at 1M) and the buffers stay resident
  # (about 7 GiB more host memory at 1M). Real images are clipped to 13312 patches by the model's processor, so cap
  # the dummy at 1824x1824 px (114x114 = 12996 patches), the largest image the model actually sees.
  MM_ARGS=(--limit-mm-per-prompt "{\"image\":{\"count\":$IMAGES_PER_PROMPT,\"width\":1824,\"height\":1824},\"video\":0}"
    --mm-processor-cache-gb 1)
else
  ENC_GIB=0
  MM_ARGS=(--language-model-only)  # text only: the vision tower is not loaded
fi
RESERVE_GIB=4  # MemAvailable left at the worst measured point

# shellcheck disable=SC2206  # EXTRA_ARGS is a documented, word-split list of extra vllm flags
EXTRA=($EXTRA_ARGS)

build_vllm_args() {
  VLLM_ARGS=(
    "$MODEL" --revision "$MODEL_REV"
    --served-model-name "$SERVED_NAME" --host 0.0.0.0 --port 8000 --trust-remote-code
    --max-model-len "$MAX_MODEL_LEN"
    --max-num-seqs "$MAX_NUM_SEQS"
    --max-num-batched-tokens "$PROFILE_MNBT"
    --gpu-memory-utilization "$GPU_UTIL"
    --kv-cache-memory-bytes "${KV_CACHE_GIB}G"
    --block-size "$PROFILE_BLOCK"
    --mamba-backend flashinfer --mamba-ssm-cache-dtype float16
    --enable-mamba-cache-stochastic-rounding --mamba-cache-philox-rounds 5
    --kernel-config '{"linear_backend_per_quant":{"fp8_w8a8":"cutlass"}}'
    "${MM_ARGS[@]}"
    --load-format fastsafetensors
    --shutdown-timeout 45
    --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser nemotron_v3
  )
  if [[ -n "$PROFILE_SPEC" ]]; then
    VLLM_ARGS+=(--speculative-config "$PROFILE_SPEC" --enable-prefix-caching)
  else
    VLLM_ARGS+=(--no-enable-prefix-caching)
  fi
}
build_vllm_args

# EXTRA_ARGS may add flags, not override the ones above (vLLM keeps the last value, so an override would silently
# change what bench.sh, test.sh and the memory plan assume). vLLM accepts --a_b for --a-b, --a.key=v (one key of a
# JSON flag), --no-a for booleans, any unique prefix of a flag name, and -sc for --speculative-config.
norm() { local f="${1%%=*}"; f="${f%%.*}"; f="${f//_/-}"; printf '%s' "${f/#--no-/--}"; }
owned="--speculative-config"
for a in "${VLLM_ARGS[@]}"; do [[ "$a" == --* ]] && owned+=" $(norm "$a")"; done
for a in "${EXTRA[@]}"; do
  [[ "$a" == -* ]] || continue
  [[ "${a%%[=.]*}" != -sc ]] || die "EXTRA_ARGS must not set $a; run.sh owns it (see README Settings)."
  flag="$(norm "$a")"
  for o in $owned; do
    [[ "$o" != "$flag"* ]] || die "EXTRA_ARGS must not set $a; run.sh owns it ($o, see README Settings)."
  done
done
VLLM_ARGS+=("${EXTRA[@]}")

DOCKER_ARGS=(
  run -d --name "$NAME" --label "$LABEL" --label "ai-lab.profile=$PROFILE"
  --gpus all --ipc host --init --restart no --oom-score-adj 1000 --ulimit core=1
  --log-opt max-size=100m --log-opt max-file=3
  -p "$BIND:$PORT:8000"
  -v "$HF_CACHE:/root/.cache/huggingface:ro"
  -v "$CACHE_DIR:/jit-cache"
  -e HF_HUB_OFFLINE=1
  -e HF_MODULES_CACHE=/jit-cache/hf-modules
  -e VLLM_ENGINE_READY_TIMEOUT_S=3600
  -e VLLM_CACHE_ROOT=/jit-cache/vllm
  -e FLASHINFER_WORKSPACE_BASE=/jit-cache/flashinfer
  -e TRITON_CACHE_DIR=/jit-cache/triton
  -e TORCHINDUCTOR_CACHE_DIR=/jit-cache/inductor
)
[[ -n "$API_KEY" ]] && DOCKER_ARGS+=(-e VLLM_API_KEY)
DOCKER_ARGS+=("$IMAGE")

if [[ "$VALIDATE_ONLY" == 1 ]]; then
  echo "PROFILE=$PROFILE MAX_NUM_SEQS=$MAX_NUM_SEQS KV_CACHE_GIB=$KV_CACHE_GIB MAX_MODEL_LEN=$MAX_MODEL_LEN" \
    "memory plan: ${BASE_GIB}+KV+${ENC_GIB}+${RESERVE_GIB} GiB (KV shrinks at start if memory is short)"
  printf 'docker'; printf ' %q' "${DOCKER_ARGS[@]}" "${VLLM_ARGS[@]}"; echo
  exit 0
fi

# ---------------------------------------------------------------- preflight
command -v docker >/dev/null || die "docker not found."
docker info >/dev/null 2>&1 || die "cannot talk to the Docker daemon (is your user in the docker group?)."
command -v curl >/dev/null || die "curl not found."
gpu="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
[[ "$gpu" == *GB10* ]] || log "warning: GPU is '${gpu:-unknown}', not GB10. This recipe is tuned for DGX Spark."

if grep -Fqx "$NAME" <<<"$(docker ps -a --format '{{.Names}}')"; then
  die "a container named $NAME already exists. Run ./stop.sh first."
fi
# One GPU serve at a time: weights alone are 70 GiB of the 121.7 GiB shared memory.
others=""
while read -r cid; do
  [[ -z "$cid" ]] && continue
  if [[ "$(docker inspect -f '{{json .HostConfig.DeviceRequests}}' "$cid")" == *gpu* ]]; then
    others+=" $(docker inspect -f '{{.Name}}' "$cid" | tr -d /)"
  fi
done <<<"$(docker ps -q)"
[[ -z "$others" ]] || die "another GPU container is running:$others. Stop it first; this model needs the whole Spark."
if command -v ss >/dev/null && [[ -n "$(ss -ltnH "sport = :$PORT" 2>/dev/null)" ]]; then
  die "port $PORT is already in use. Set PORT=... or free it."
fi

mkdir -p "$HF_CACHE/hub" "$CACHE_DIR" "$SCRIPT_DIR/.run-state"

# ---------------------------------------------------------------- image and weights
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  log "Pulling $IMAGE (about 26 GB)"
  for i in 1 2 3; do docker pull "$IMAGE" && break; (( i == 3 )) && die "docker pull failed."; sleep 5; done
fi

have_snapshot() {  # REPO REV: true when every file listed in the snapshot's index (or its single file) is present
  local dir="$HF_CACHE/hub/models--${1//\//--}/snapshots/$2"
  [[ -d "$dir" ]] || return 1
  if [[ -f "$dir/model.safetensors.index.json" ]]; then
    local f
    for f in $(grep -o '"model-[0-9]*-of-[0-9]*\.safetensors"' "$dir/model.safetensors.index.json" | sort -u | tr -d '"'); do
      [[ -e "$dir/$f" ]] || return 1
    done
  else
    [[ -e "$dir/model.safetensors" ]] || return 1
  fi
}
fetch() {  # REPO REV SIZE_GIB
  have_snapshot "$1" "$2" && return 0
  log "Downloading $1 @ ${2:0:8} into $HF_CACHE (resumable)"
  local have_gib free_gib
  have_gib=$( { du -sBG "$HF_CACHE/hub/models--${1//\//--}" 2>/dev/null || true; } | cut -f1 | tr -dc '0-9')
  free_gib=$(df -BG --output=avail "$HF_CACHE" | tail -1 | tr -dc '0-9')
  (( free_gib + ${have_gib:-0} > $3 + 2 )) || die "need about $(( $3 + 2 - ${have_gib:-0} )) GiB more free disk under $HF_CACHE, have ${free_gib} GiB."
  if command -v hf >/dev/null; then
    hf download "$1" --revision "$2" --cache-dir "$HF_CACHE/hub"
  else
    # As the calling user, so the shared Hugging Face cache does not fill with root-owned files.
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e HF_TOKEN -v "$HF_CACHE:/hf" --entrypoint hf "$IMAGE" \
      download "$1" --revision "$2" --cache-dir /hf/hub
  fi
  have_snapshot "$1" "$2" || die "download of $1 is incomplete; run ./run.sh again to resume."
}
fetch "$MODEL" "$MODEL_REV" 70
[[ -n "$PROFILE_SPEC" ]] && fetch "$DRAFT" "$DRAFT_REV" 2

# ---------------------------------------------------------------- memory plan
# Measured worst case on a Spark (evidence/): base + KV pool + image-embedding cache, with RESERVE_GIB of
# MemAvailable left over. Memory a serve that just stopped frees can take a few seconds to show, so wait up to
# 2 minutes for the smallest workable pool (8 GiB, or a smaller KV_CACHE_GIB you set), then size the pool to what is
# free.
fixed_gib=$(( BASE_GIB + ENC_GIB + RESERVE_GIB ))
min_kv=8
[[ -n "$KV_USER" ]] && (( KV_USER < min_kv )) && min_kv=$KV_USER
for i in $(seq 1 24); do
  avail_gib=$(awk '/^MemAvailable:/{printf "%d", $2/1048576}' /proc/meminfo)
  (( avail_gib >= fixed_gib + min_kv )) && break
  (( i == 24 )) && die "only ${avail_gib} GiB available; this profile needs at least $(( fixed_gib + min_kv )) GiB free. Find what holds the memory (free -h; docker ps)."
  sleep 5
done
sleep 3
avail_gib=$(awk '/^MemAvailable:/{printf "%d", $2/1048576}' /proc/meminfo)
fit_gib=$(( avail_gib - fixed_gib ))
(( fit_gib >= min_kv )) || die "MemAvailable fell to ${avail_gib} GiB while starting; this profile needs at least $(( fixed_gib + min_kv )) GiB."
if (( KV_CACHE_GIB > fit_gib )); then
  if [[ -n "$KV_USER" && "$FORCE_UNSAFE_MEMORY" != 1 ]]; then
    die "KV_CACHE_GIB=$KV_CACHE_GIB does not fit: ${avail_gib} GiB free, plan needs ${fixed_gib}+${KV_CACHE_GIB}. Use KV_CACHE_GIB=$fit_gib or less."
  elif [[ -z "$KV_USER" ]]; then
    log "Only ${avail_gib} GiB free: KV pool ${fit_gib} GiB instead of $KV_CACHE_GIB (fewer concurrent sequences)."
    KV_CACHE_GIB=$fit_gib
    build_vllm_args
    VLLM_ARGS+=("${EXTRA[@]}")
  fi
fi

# ---------------------------------------------------------------- start
log "Starting $NAME: profile=$PROFILE max-num-seqs=$MAX_NUM_SEQS kv=${KV_CACHE_GIB}GiB context=$MAX_MODEL_LEN images=$IMAGES_PER_PROMPT port=$BIND:$PORT"
VLLM_API_KEY="$API_KEY" docker "${DOCKER_ARGS[@]}" "${VLLM_ARGS[@]}" >/dev/null

setsid nohup bash "$SCRIPT_DIR/tools/memguard.sh" "$NAME" "$SCRIPT_DIR/.run-state/$NAME.memguard.log" \
  >/dev/null 2>&1 </dev/null &
echo $! >"$SCRIPT_DIR/.run-state/$NAME.memguard.pid"

# ---------------------------------------------------------------- wait for ready
PROBE_HOST="$BIND"
[[ "$BIND" == 0.0.0.0 ]] && PROBE_HOST=127.0.0.1
URL="http://$PROBE_HOST:$PORT"
api() {  # PATH [curl args...]: the key goes through a file descriptor, not the process list
  local path="$1"; shift
  if [[ -n "$API_KEY" ]]; then
    curl -fsS -H @<(printf 'Authorization: Bearer %s\n' "$API_KEY") "$@" "$URL$path"
  else
    curl -fsS "$@" "$URL$path"
  fi
}
t0=$(date +%s)
last=""
while :; do
  if api /v1/models >/dev/null 2>&1; then break; fi
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != true ]]; then
    echo "run.sh: $NAME exited during startup. Last log lines:" >&2
    docker logs --tail 60 "$NAME" >&2 2>&1 || true
    exit 1
  fi
  el=$(( $(date +%s) - t0 ))
  (( el > READY_TIMEOUT )) && die "not ready after ${READY_TIMEOUT}s; the container is still up. See: docker logs $NAME"
  phase="$(docker logs --tail 200 "$NAME" 2>&1 | grep -oE 'Loading (weights|fastsafetensors)|Model loading took|Autotun|Capturing CUDA graphs|JIT kernel warmup|init engine|Starting vLLM' | tail -1 || true)"
  if [[ -n "$phase" && "$phase" != "$last" ]]; then log "${el}s: $phase"; last="$phase"; fi
  sleep 5
done
log "Ready after $(( $(date +%s) - t0 ))s"

# ---------------------------------------------------------------- smoke
if [[ "$SKIP_SMOKE" != 1 ]]; then
  reply="$(api /v1/chat/completions -H 'Content-Type: application/json' -d "{
    \"model\": \"$SERVED_NAME\", \"max_tokens\": 16, \"temperature\": 0,
    \"messages\": [{\"role\": \"user\", \"content\": \"Reply with exactly the word: pong\"}],
    \"chat_template_kwargs\": {\"enable_thinking\": false}}" || true)"
  if grep -qi pong <<<"$reply"; then log "Smoke test passed (pong)."; else die "smoke test failed: $reply"; fi
fi

cat <<EOF
==> Serving $MODEL as "$SERVED_NAME"
    OpenAI API : $URL/v1   (bound to $BIND:$PORT)
    Profile    : $PROFILE, up to $MAX_NUM_SEQS concurrent sequences, KV pool ${KV_CACHE_GIB} GiB, $MAX_MODEL_LEN-token context
    Memory     : $(awk '/^MemAvailable:/{printf "%.1f GiB", $2/1048576}' /proc/meminfo) still available to the host
    Logs       : docker logs -f $NAME
    Stop       : ./stop.sh
EOF
