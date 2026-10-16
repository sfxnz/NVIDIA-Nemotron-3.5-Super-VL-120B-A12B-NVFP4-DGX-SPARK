#!/usr/bin/env bash
# exp.sh TAG [extra vllm args...]   — boot one experiment config as container nemotron-exp, wait for /health.
# Env: UTIL (0.78) SEQS (64) MNBT (8448) MML (262144) LOADFMT (fastsafetensors) MM ('{"image":4,"video":0}') ENVS (extra -e list)
set -euo pipefail
TAG="$1"; shift
S=/tmp/claude-1000/-home-sfxnz-projects-ai-lab-recipes-NVIDIA-Nemotron-3-5-Super-VL-120B-A12B-NVFP4-DGX-SPARK/ed423547-af69-4f64-a551-32ddd0b572a3/scratchpad
IMG=vllm/vllm-openai@sha256:cb9bc64f0f038c2c2ebf13b31248fb87aca40c356c3d20f363be087cfcff1fcd
C=/home/sfxnz/projects/data/nemotron-super-vl-jit-cache/9dfef102a162
D=$S/exp/$TAG; mkdir -p "$D" "$S/results"
UTIL="${UTIL:-0.78}"; SEQS="${SEQS:-64}"; MNBT="${MNBT:-8448}"; MML="${MML:-262144}"; LOADFMT="${LOADFMT:-fastsafetensors}"
DEFMM='{"image":4,"video":0}'; MM="${MM:-$DEFMM}"
read -r -a ENVA <<<"${ENVS:-}"
EARGS=(); for e in "${ENVA[@]}"; do EARGS+=(-e "$e"); done
CN="${CN:-nemotron-exp}"
docker rm -f "$CN" >/dev/null 2>&1 || true
echo "free before: $(free -m | awk '/Mem:/{print "avail="$7"MiB"} /Swap:/{print "swapused="$3"MiB"}' | tr '\n' ' ')" | tee "$D/meta.txt"
ARGS=(nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 --revision 82d93699acd3be9e4617c53360fe5b3f5dbeb1b3 --host 0.0.0.0 --port 8000
  --served-model-name nemotron-3.5-super-vl --trust-remote-code
  --gpu-memory-utilization "$UTIL" --max-model-len "$MML" --max-num-seqs "$SEQS" --max-num-batched-tokens "$MNBT"
  --mamba-backend flashinfer --mamba-ssm-cache-dtype float16 --enable-mamba-cache-stochastic-rounding --mamba-cache-philox-rounds 5
  --block-size 64 --prefix-match-unit 64
  --limit-mm-per-prompt "$MM" --mm-processor-cache-gb 1
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser nemotron_v3
  --load-format "$LOADFMT" "$@")
printf '%q ' "${ARGS[@]}" >>"$D/meta.txt"; echo >>"$D/meta.txt"
echo "ENVS=${ENVS:-}" >>"$D/meta.txt"
docker run -d --name "$CN" --label ai-lab.recipe=nemotron-3.5-super-vl-spark --gpus all --ipc=host --oom-score-adj 1000 --ulimit core=1 \
  -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -v /home/sfxnz/projects/data/benchmarks/speed-bench/vllm:/bench/speed-bench:ro \
  -v "$S/results:/results" -v "$C:/jit-cache" \
  -e HF_HUB_OFFLINE=1 -e FLASHINFER_WORKSPACE_BASE=/jit-cache/flashinfer -e VLLM_CACHE_ROOT=/jit-cache/vllm \
  -e TRITON_CACHE_DIR=/jit-cache/triton -e TORCHINDUCTOR_CACHE_DIR=/jit-cache/inductor \
  "${EARGS[@]}" "$IMG" "${ARGS[@]}" >/dev/null
t0=$(date +%s); echo "$t0" >"$D/start_epoch"
nohup "$S/tools/memwatch.sh" "$CN" "$D/mem.csv" 3072 >/dev/null 2>&1 &
while :; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  if ! docker ps --format '{{.Names}}' | grep -qx "$CN"; then
    echo "EXITED after $(( $(date +%s) - t0 ))s"; docker logs "$CN" >"$D/server.log" 2>&1 || true
    grep -E "Error|error|raise|Exception" "$D/server.log" | tail -20; exit 1
  fi
  if (( $(date +%s) - t0 > 1800 )); then echo "TIMEOUT"; exit 1; fi
  sleep 5
done
echo "READY after $(( $(date +%s) - t0 ))s" | tee -a "$D/meta.txt"
docker exec "$CN" pip install -q pandas >/dev/null 2>&1 || true
docker logs "$CN" >"$D/server.log" 2>&1
grep -E "Loading weights took|Model loading took|init engine|Setting attention block size|Padding mamba|padding layers|Available KV cache|Maximum concurrency|group sizes|NvFp4 MoE backend|for NVFP4 GEMM|FP8ScaledMM|attention backend|Free memory on device|override for|Using .* load|fastsafetensors" "$D/server.log" | cut -c1-260 | sort -u | head -30
echo "free after: $(free -m | awk '/Mem:/{print "avail="$7"MiB"} /Swap:/{print "swapused="$3"MiB"}' | tr '\n' ' ')" | tee -a "$D/meta.txt"
