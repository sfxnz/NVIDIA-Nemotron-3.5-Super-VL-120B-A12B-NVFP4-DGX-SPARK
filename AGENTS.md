# AGENTS.md — Nemotron 3.5 Super VL 120B-A12B NVFP4 · 1× DGX Spark

Serve `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4` (snapshot `82d9369`) on one DGX Spark with vLLM nightly `3f1bcfd8` (`vllm/vllm-openai@sha256:cb9bc64f…`, the image the model card names). Default profile: LiLiCorr drafter (`…-LiLiCorr`, snapshot `7c7221a`), 7 draft tokens, 32 sequences, 19 GiB KV pool, 262144 context. `PROFILE=throughput`: no drafter, no prefix caching, 192 sequences, 20 GiB pool. Container `nemotron-3.5-super-vl`, label `ai-lab.recipe=nemotron-3.5-super-vl-spark`, port 8000 on 127.0.0.1.

Humans read [README.md](README.md). Numbers there come from `evidence/`; [`evidence/README.md`](evidence/README.md) maps them to files and [`evidence/decisions.tsv`](evidence/decisions.tsv) is the ledger.

## Standing orders

1. **PR only** after the initial publish. Commit on `agent/**` branches, open a PR against `main`. Never push `main`, never merge, never force-push.
2. **Evidence.** Every number in `README.md` has a file under `evidence/`. No file, no number. Never gitignore `evidence/`.
3. **Validate first.** `VALIDATE_ONLY=1 ./run.sh` (no Docker) before any serve. CI runs it with the refusal cases.
4. **Voice.** Short sentences. Numbers first. No marketing language. No emojis.
5. **Secrets.** Never commit tokens, Tailscale IPs or auth headers.

## Working rules

- One node, one GPU serve. `run.sh` refuses to start next to another GPU container and never removes it. Stop other serves with their own stop scripts.
- Read unified memory with `free -h` or `/proc/meminfo`. Never `nvidia-smi` VRAM (it reports "Not Supported" on GB10). Convert MiB with /1024.
- Pins: image digest, model and drafter snapshot SHAs. Do not float tags. Bumping the image means measuring again.
- **Memory plan** (`run.sh`): MemAvailable at start must cover base + KV pool + image-embedding cache budget + 4 GiB reserve. Base is 88 GiB (default) / 86 GiB (throughput): the worst measured footprint minus the pool. The image-cache budget is max-model-len × 8 KiB (2 GiB at 262144, 8 GiB at 1M), because vLLM keeps image embeddings until that budget is full. When the default pool does not fit, `run.sh` shrinks it and says so; an explicit `KV_CACHE_GIB` that does not fit is refused. Change a base only with a new worst-case measurement (soak with long prompts and images) in `evidence/`.
- `--gpu-memory-utilization 0.75` is only vLLM's start gate. Pinning `--kv-cache-memory-bytes` skips vLLM's activation profiling, so the activation peak comes out of host headroom. That is what the base covers.
- Keep `--block-size 256` with the LiLiCorr drafter. At the card's 64 the drafter's 64-token sliding-window pages are padded to the full 4544-token page size.
- Keep `--max-num-batched-tokens 4608` (one cache block). Against 9216 it prefilled faster and left about 5 GiB more host memory at the long-prefill plateau.
- Keep the profiling dummy image capped (`"image":{"count":N,"width":1824,"height":1824}`). Uncapped, vLLM sizes it to fill the context (8184×8184 px at 1M) and the buffers stay resident: 15.3 GiB free after boot capped versus 8.0 uncapped at 1M. Real images are clipped to 13,312 patches by the model's processor either way.
- Keep `--mamba-ssm-cache-dtype float16`: the NemotronH hook that sets the SSM dtype does not fire for this architecture name, so `auto` silently becomes bf16. Keep `--mamba-backend flashinfer`: stochastic rounding on the Triton backend needs SM100.
- Keep `fp8_w8a8: cutlass` in `--kernel-config`: fastest FP8 GEMM at decode shapes in the micro-benchmark, and it avoids the FlashInfer FP8 path of vLLM #61007.
- Keep `--shutdown-timeout 45` below `STOP_TIMEOUT` (60): vLLM's default 0 aborts running requests and the container then sat until Docker's kill.
- `--prefix-match-unit` and `--enable-mamba-shared-prefix-checkpoint` are not used: with the drafter's sliding-window group vLLM cannot do sub-block lookups, and the unit would round hits down to 4608-token blocks. Without them hits land on 1152-token boundaries (19,584 of ~21K tokens by turn 3).
- Do not set `--linear-backend torch` globally (it breaks NVFP4 linears on SM12x), `--use-replayssm` or `enable_adaptive_verification` (both refuse this VL architecture), or the removed env vars `VLLM_USE_FLASHINFER_MOE_FP4`, `VLLM_NVFP4_GEMM_BACKEND`, `VLLM_ATTENTION_BACKEND`.
- Video is off (`"video":0`). The card's Spark row lists text and image only.
- `IMAGES_PER_PROMPT=0` switches to `--language-model-only` (vision tower not loaded, no image cache). That is the way to run 1M context without the 8 GiB image-cache budget.
- `API_KEY` covers only `/v1`, `/v2`, `/inference`, `/cohere` in this vLLM; `/invocations`, `/tokenize`, `/metrics` stay open. Never document `BIND=0.0.0.0` with a key as safe; say firewall or reverse proxy.
- Benchmarks: `./bench.sh` only. Thinking off and greedy for the sweep, label max-concurrency as passed, one bench at a time, do not merge tables. Single-user decode varies about ±7% from boot to boot; publish a median of boots.
- Greedy output is not bit-exact (stochastic rounding of the Mamba state draws a fresh seed per update). Do not add hard determinism checks.
- Thinking is on by default in the chat template. Short calls need `"chat_template_kwargs": {"enable_thinking": false}` or a large `max_tokens`.

## Verify

```bash
VALIDATE_ONLY=1 ./run.sh
shellcheck -S style run.sh stop.sh bench.sh test.sh tools/memguard.sh
python3 -m py_compile tools/*.py
./run.sh            # ready gate: /v1/models, then a thinking-off "pong"
./test.sh           # functional suite; exit 0 = every hard check passed
./bench.sh decode   # single-user decode
./stop.sh
```

## Never touch

- Live HF tokens
- An unpinned image, model or drafter revision
- Raising `KV_CACHE_GIB`, a profile's pool or `BASE_GIB` margins without a fresh worst-case memory measurement in `evidence/`
- Advertising a context window, concurrency level or speed that was not run here
