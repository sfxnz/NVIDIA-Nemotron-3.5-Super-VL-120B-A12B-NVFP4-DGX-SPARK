#!/usr/bin/env bash
# The model card's 1x DGX Spark vLLM command, verbatim, in a container bench.sh can find (name + label).
# Only additions: --revision (pins the same snapshot; bench.sh reads it for the tokenizer path), host port/HF cache
# mounts, and the JIT cache mount (startup time only).
set -euo pipefail
docker run -d --name nemotron-3.5-super-vl --label ai-lab.recipe=nemotron-3.5-super-vl-spark --label ai-lab.profile=card \
  --gpus all --ipc host --oom-score-adj 1000 --ulimit core=1 -p 127.0.0.1:8000:8000 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -v /home/sfxnz/projects/data/nemotron-super-vl-jit-cache/9dfef102a162:/jit-cache \
  -e HF_HUB_OFFLINE=1 -e VLLM_CACHE_ROOT=/jit-cache/vllm -e FLASHINFER_WORKSPACE_BASE=/jit-cache/flashinfer \
  -e TRITON_CACHE_DIR=/jit-cache/triton -e TORCHINDUCTOR_CACHE_DIR=/jit-cache/inductor \
  vllm/vllm-openai@sha256:cb9bc64f0f038c2c2ebf13b31248fb87aca40c356c3d20f363be087cfcff1fcd \
  nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 --revision 82d93699acd3be9e4617c53360fe5b3f5dbeb1b3 \
  --host 0.0.0.0 --port 8000 \
  --served-model-name nemotron-3.5-super-vl \
  --max-num-seqs 1 \
  --trust-remote-code \
  --gpu-memory-utilization 0.75 \
  --max-num-batched-tokens 8192 \
  --speculative_config.model nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-LiLiCorr \
  --speculative_config.num_speculative_tokens 7 \
  --speculative_config.method dflash \
  --mamba-backend flashinfer \
  --mamba-ssm-cache-dtype float16 \
  --enable-mamba-cache-stochastic-rounding \
  --mamba-cache-philox-rounds 5 \
  --enable-mamba-shared-prefix-checkpoint \
  --video-pruning-rate 0.5 \
  --media-io-kwargs '{"video": {"fps": 2, "num_frames": 256}}' \
  --block-size 64 \
  --prefix-match-unit 64 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser nemotron_v3
