# NVIDIA Nemotron 3.5 Super VL 120B-A12B NVFP4 · vLLM · 1× DGX Spark

Serve [nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4) on one NVIDIA DGX Spark (GB10) with vLLM. Text, images, tool calls, reasoning on or off, 32 concurrent sequences, 262K context (1M opt-in, verified).

```bash
./run.sh     # first run downloads 70 GiB of weights and a 26 GB image, then serves on 127.0.0.1:8000
./stop.sh
```

120B total / 12B active. Hybrid Mamba-2 + LatentMoE (512 experts, 22 active) + 8 attention layers, C-RADIO vision encoder. NVFP4 experts, FP8 Mamba projections and attention, FP8 KV cache. Speculative decoding with NVIDIA's [LiLiCorr drafter](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-LiLiCorr) (7 draft tokens). Pinned: image digest, model snapshot, drafter snapshot.

## Measured on 1× DGX Spark

spark1, 15–16 Oct 2026, `./run.sh` defaults, measured with `./bench.sh` (`vllm bench serve`; prompts drawn from 369 SPEED-Bench prompts, greedy, thinking off, up to 512 output tokens per request, which stop at EOS: about 265 on average) unless a row says otherwise. 1-user rows use 32 prompts (16 with the card's sampling); concurrency cells use 3 per user. Raw output for every number: [`evidence/`](evidence/) ([map](evidence/README.md)).

**Default profile** (`./run.sh`): LiLiCorr speculative decoding, up to 32 sequences.

| Load | Output tok/s (all users) | Per user, tok/s | TTFT p50 | Acceptance length |
|---|---:|---:|---:|---:|
| 1 user | 41 | **48** (2 boots: 50.4, 45.3) | 0.40 s | 4.5–4.7 |
| 1 user, the card's sampling (T=1.0, top_p 0.95), thinking on | 37 | 38 (37.8, 37.3) | 0.34 s | 4.0–4.1 |
| 2 users | 51 | 31 | 0.53 s | 4.2 |
| 4 users | 70 | 22 | 0.77 s | 4.4 |
| 8 users | 100 | 18 | 1.0 s | 4.5 |
| 16 users | 146 | 13 | 1.3 s | 4.6 |
| 24 users | 179 | 11 | 1.6 s | 4.6 |
| 32 users | 189 | 10.5 | 7.4 s (about 24 fit the pool at once; the rest wait) | 4.5 |

Rows 1, 2, 5, 7 and 8 are the mean of two boots (`evidence/fv1-default/`, `evidence/fv2-default/`; multi-user cells agreed within 4%); rows 3, 4 and 6 are the second boot. Greedy decoding is not bit-exact here (see [Known limits](#known-limits)), so the same prompts give slightly different replies and acceptance from boot to boot.

| Prefill, one request (random tokens) | 8K | 32K | 128K | 966K |
|---|---:|---:|---:|---:|
| Prompt tok/s | 2,506 | 2,466 | 2,042 | 820 (`MAX_MODEL_LEN=1048576`; needle test, 19.6 min) |

**Throughput profile** (`PROFILE=throughput ./run.sh`): no drafter, no prefix caching, up to 192 sequences.

| Load | Output tok/s (all users) | Per user, tok/s | TTFT p50 |
|---|---:|---:|---:|
| 1 user | 19 | 19.4 | 0.3 s |
| 32 users | 101 | 3.6 | 1.0 s |
| 64 users (note 1) | 158 | 2.8 | 1.3 s |
| 128 users (note 1) | 242 | 2.2 | 1.6 s |
| 192 users | **304** | 1.8 | 1.9 s |

| Prefill, one request (random tokens; note 1) | 8K | 32K | 128K |
|---|---:|---:|---:|
| Prompt tok/s | 2,648 | 2,423 | 2,019 |

Unmarked rows: the final scripts (`evidence/tv1-throughput/`, also 192 parallel requests and a 384-request mixed burst, all correct). 1. An earlier boot with the same compute flags at `MAX_MODEL_LEN=1048576` and a 256-sequence cap, on the unfiltered prompt file (`evidence/f5-throughput/`); its 1-, 32- and 192-user cells matched the final scripts within 4%. With that 256 cap, 256 users gave 324 tok/s at a 39.7 s TTFT: the 20 GiB pool holds about 200 sequences and the rest queued, which is why the cap is 192.

**Against the model card's Spark command** (same image and harness; `evidence/card-baseline/`, `evidence/mtp5/`):

| | This recipe (default) | The card's Spark command, verbatim | This recipe with MTP-5 instead (the card's deployment-table option) |
|---|---:|---:|---:|
| 1 user, greedy, thinking off | 48 tok/s (2 boots) | 44.3 (1 boot) | 40.7 (1 boot) |
| 1 user, the card's sampling, thinking on | 38 | 36.6 | 32.6 |
| 8 users: total / per user | **100 / 18** | serves 1 at a time | 93 / 14.5 |
| 24 users | **179 / 11** | 1 | 178 / 10.4 |
| 32 users | 189 / 10.5, TTFT 7.4 s (queueing) | 1 | **211 / 9.3**, TTFT 1.7 s |
| Prefill 8K / 32K / 128K, tok/s | 2,506 / 2,466 / 2,042 | **2,924 / 2,905 / 2,348** | not measured |
| Weight load | **16 s** | 430 s; swap ran out (15 of 15 GiB) during the load | 16 s |
| Free host memory after boot | 13.8–14.4 GiB | 14 GiB | 14 GiB |

At 1 user the three are within the boot-to-boot spread of this stack (about ±7%), the recipe ahead. LiLiCorr (default) leads at 8 users and ties at 24. MTP-5's smaller per-sequence state fits about 22% more sequences in the same pool (vLLM reports 10.0× against 8.2× 262K-token requests), so at 32 users it no longer queues. Above that, the throughput profile's total keeps growing to 304 tok/s at 192 users. The card's command prefills faster; see [Known limits](#known-limits).

**Host memory** (121.7 GiB unified; MemAvailable): 13.8–14.4 GiB free after `./run.sh`. Lowest point across both default boots' benchmarks, 600 distinct images, a 102K-token needle and the functional suite: **7.2 GiB**; across a 30-minute 24-client soak (866 mixed requests, 0 failures): **7.3 GiB**; swap not used. `bench.sh`'s own client container takes about 1 GiB more while it runs (6.4 GiB right after the soak). See [Memory](#memory).

**Functional suite** (`./test.sh`): 34 of 35 executed checks pass; the 35th is a soft check that records greedy output is not bit-exact. Video is skipped (off). Thinking on/off/medium, tool calls (auto, required, named, parallel, streaming, follow-up turn), JSON schema with and without reasoning, images by data URL and http URL, two images in order, the image limit, a 102K-token needle, multi-turn prefix caching, 32 parallel requests with no crosstalk, a 64-request oversubscribed mixed burst.

## Requirements

- One DGX Spark (GB10). Tested with driver 580.173.02 (CUDA 13.0).
- Docker with the NVIDIA Container Toolkit; your user in the `docker` group; `curl` and `python3` on the host.
- About 100 GiB free disk: 70 GiB weights + 1.2 GiB drafter + a 26 GB image.
- About 113 GiB of free unified memory at start for the full default pool (`run.sh` shrinks the pool if less is free, down to an 8 GiB pool at 102 GiB). Stop other GPU containers first; `run.sh` refuses to start next to one.
- Internet on first run only. The model is not gated; `HF_TOKEN` is optional (rate limits).

## Quick start

```bash
git clone https://github.com/sfxnz/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-DGX-SPARK.git
cd NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-DGX-SPARK
./run.sh
```

First run: pulls the image, downloads the model and drafter at their pinned revisions (resumable), checks memory, starts the container, waits for `/v1/models`, sends a thinking-off "pong", prints the endpoint. Starts take about 100 s once compiled kernels are cached in `./.cache`; the very first start takes about 5.5 minutes once the weights are on disk.

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "nemotron-3.5-super-vl",
  "messages": [{"role": "user", "content": "Say hello in one sentence."}],
  "max_tokens": 64,
  "chat_template_kwargs": {"enable_thinking": false}
}'
```

Stop with `./stop.sh`: vLLM stops taking requests, lets running ones finish for up to 45 s, then the container is removed.

## Profiles

| | `default` | `throughput` |
|---|---|---|
| Speculative decoding | LiLiCorr, 7 tokens | none |
| Max sequences | 32 (about 24 short ones fit the pool at once) | 192 |
| KV + Mamba pool | 19 GiB | 20 GiB |
| Prefix caching | on (a multi-turn chat reuses most of its history) | off (halves per-sequence state) |
| 1 user | 48 tok/s | 19.5 tok/s |
| Pick it for | interactive use, agents, up to about 24 parallel requests | many parallel clients or batch jobs where total tokens/s matters more than speed per user |

Up to about 24 users the default is better on both axes: 24 users get 179 tok/s total and 11 tok/s each; without the drafter, 32 users get 104 tok/s at 3.6 each. Speculative decoding helps at concurrency too because once a few tokens share a step, a decode step reads most of the 60 GiB of expert weights anyway: extra draft tokens ride along almost free. The limit is memory per sequence (about 0.8 GiB with the drafter, mostly Mamba state for 9 draft slots), not compute.

## What `run.sh` sets, and why

Every choice was measured on this Spark. Ledger: [`evidence/decisions.tsv`](evidence/decisions.tsv).

| Setting | Value | Why |
|---|---|---|
| Image | `vllm/vllm-openai@sha256:cb9bc64f…` (nightly `3f1bcfd8`, 0.32.0rc1) | The image the model card names. v0.31.0 lacks the hybrid-Mamba prefix-cache and LiLiCorr fixes this model needs. |
| `--speculative-config` | LiLiCorr `dflash`, 7 tokens, pinned revision | 48 tok/s for one user against 19.5–20 without it. |
| `--block-size 256` | default profile (card: 64; throughput profile: 64, no drafter) | At 64 the drafter's 64-token sliding-window pages are padded to the 4544-token page size. With the same 19 GiB pool vLLM reports 8.19× concurrency for 262K requests at 256 against 3.75× at 64, with the same prefill speed. |
| `--kv-cache-memory-bytes` | 19G (default), 20G (throughput) | A fixed pool, sized by the memory plan below. `--gpu-memory-utilization 0.75` stays as vLLM's start gate only. |
| `--max-num-batched-tokens` | 4608 (one cache block) | Against 9216: prefill faster (2,485/2,424/2,004 vs 2,346/2,137/1,848 tok/s at 8K/32K/128K) and about 5 GiB more host memory left at the long-prefill peak. |
| `--kernel-config` | `fp8_w8a8: cutlass` | FP8 GEMMs (Mamba projections, attention) are about half the bytes of a decode step. CUTLASS was the fastest FP8 GEMM at decode sizes in a micro-benchmark (20.2 ms per step vs 22.0 cuBLAS, 23.4 FlashInfer) and avoids the FlashInfer FP8 path of vLLM #61007. Trade-off measured: `torch` (cuBLAS) prefills about 5% faster (2,632/2,586/2,133 tok/s). |
| `--limit-mm-per-prompt` | 4 images, profiling dummy capped at 1824×1824 px, no video | vLLM profiles the vision encoder with a dummy image sized to the whole context (8184×8184 px at 1M) and the buffers stay resident: 8.0 GiB free after boot uncapped, 15.3 GiB capped (1M context). Real images are clipped to 13,312 patches (about 1824×1824 px) by the model's processor anyway. |
| `--max-model-len` | 262144 | vLLM keeps image embeddings until a cache budget of max-model-len tokens × 8 KiB is full, outside the KV pool: 2 GiB at 262K, 8 GiB at 1M. 600 distinct images moved free memory down 2.2 GiB and then it stayed flat. 1M is opt-in (see below). |
| `--load-format fastsafetensors` | | Weights load in 16 s instead of 409–430 s, with the same prefill speed, and swap stays untouched during load. |
| `--enable-prefix-caching` (no `--prefix-match-unit`) | default profile | A 3-turn chat over a 21K-token document reused 13,824 then 19,584 tokens (turn time 8.4 s, 3.4 s, 1.0 s): hits land on the drafter group's 1152-token boundaries. The card's `--prefix-match-unit 64` and shared-prefix checkpoint are left out: with the drafter's sliding-window group vLLM cannot do the sub-block lookups they enable, and the unit would round hits down to 4608-token blocks. |
| `--mamba-ssm-cache-dtype float16` + stochastic rounding, `--mamba-backend flashinfer` | card values | Set explicitly: for this architecture name `auto` silently becomes bf16. Stochastic rounding on GB10 needs the FlashInfer backend. |
| `--shutdown-timeout 45` | | vLLM's default 0 aborts running requests; with 45, `./stop.sh` let short and medium requests finish (48 s stop). |
| `--reasoning-parser nemotron_v3`, `--tool-call-parser qwen3_coder` | card values | Thinking off returns clean `content`; tool calls parse into OpenAI `tool_calls`. |
| HF cache mounted read-only, `--oom-score-adj 1000`, `--ulimit core=1`, memguard | | The server cannot write into your Hugging Face cache. If the host ever runs out of memory, the kernel kills this container first, not your desktop or agents. A 2 s watchdog stops the container when MemAvailable and SwapFree both stay under 2 GiB. No multi-GiB core dumps. |

The full command: `VALIDATE_ONLY=1 ./run.sh` prints it without touching Docker.

**Memory plan.** `run.sh` starts only when MemAvailable covers base + KV pool + image-embedding budget + 4 GiB reserve: 88 + 19 + 2 + 4 = 113 GiB for the default profile. Base is the measured worst-case footprint without the pool (the 30-minute soak). If less is free, the pool shrinks to fit and `run.sh` says so; an explicit `KV_CACHE_GIB` that does not fit is refused.

## Settings

Environment variables for `run.sh`:

| Variable | Default | Notes |
|---|---|---|
| `PROFILE` | `default` | `throughput`: no drafter, no prefix caching, 192 sequences. |
| `BIND` / `PORT` | `127.0.0.1` / `8000` | `BIND=0.0.0.0` (or one interface's IP) exposes the server to your network. `API_KEY` alone does not protect it (see below): firewall the port to trusted hosts or put an authenticating reverse proxy in front. |
| `API_KEY` | empty | Passed to vLLM as `VLLM_API_KEY`; clients send `Authorization: Bearer …`. Export it for `bench.sh` and `test.sh` too. vLLM checks it only under `/v1`, `/v2`, `/inference` and `/cohere`; `/invocations` (which generates), `/tokenize`, `/detokenize`, `/metrics` and `/health` stay open. |
| `MAX_MODEL_LEN` | `262144` | Up to `1048576`. With images on, 1M reserves an 8 GiB image-embedding budget, so the pool shrinks to fit (about 13 GiB on a typical Spark). For long-document text work use `IMAGES_PER_PROMPT=0 MAX_MODEL_LEN=1048576`. |
| `IMAGES_PER_PROMPT` | `4` | `0` serves text only (`--language-model-only`): the vision tower is not loaded and there is no image budget. |
| `MAX_NUM_SEQS` | 32 / 192 | Requests beyond what the pool holds wait in vLLM's queue. |
| `KV_CACHE_GIB` | 19 / 20 | Each LiLiCorr sequence takes about 0.8 GiB at short context. Lower it (for example 16) if other heavy services share the Spark. |
| `SERVED_NAME` | `nemotron-3.5-super-vl` | Model id in the API. |
| `HF_CACHE` | `~/.cache/huggingface` | Where weights live. |
| `CACHE_DIR` | `./.cache` | Compiled kernels and autotune results; makes restarts about 100 s. |
| `EXTRA_ARGS` | empty | Extra `vllm serve` flags. Flags `run.sh` sets are refused. |
| `VALIDATE_ONLY` | `0` | `1` checks settings and prints the command. |
| `FORCE_UNSAFE_MEMORY` | `0` | `1` lets an explicit `KV_CACHE_GIB` exceed the memory plan. |

## Using the API

OpenAI-compatible at `http://127.0.0.1:8000/v1`, model `nemotron-3.5-super-vl`.

- **Reasoning is on by default** (the chat template opens `<think>`). Reasoning comes back in `message.reasoning`, the answer in `message.content`. Give thinking-on requests a generous `max_tokens`; reasoning and answer share it.
- **Thinking off:** `"chat_template_kwargs": {"enable_thinking": false}` or `"reasoning_effort": "none"`.
- **Medium effort:** `"chat_template_kwargs": {"enable_thinking": true, "medium_effort": true}` (63 vs 114 reasoning tokens on the test's arithmetic prompt).
- **Always get an answer:** add `"force_nonempty_content": true` to `chat_template_kwargs`; if reasoning runs out of tokens, it is returned as content.
- **Reasoning budget:** `"thinking_token_budget": 512` caps reasoning tokens (`evidence/firstrun-fallback/thinking-budget-probe.txt`: a proof used 626 reasoning tokens unbounded, 63 with a budget of 64, 15 with 16, and answered each time).
- **Sampling:** the server applies the model's defaults (temperature 1.0, top_p 0.95) when a request sets none. The card suggests temperature 0.6 for vision.
- **Tools:** standard `tools` + `tool_choice` (`auto`, `required`, or a named function); streaming tool calls work.
- **JSON:** `response_format` `json_schema` or `json_object`; with thinking on, the grammar applies after reasoning ends.
- **Images:** `{"type": "image_url", "image_url": {"url": "data:image/png;base64,…"}}` or an `http(s)` URL, up to 4 per request. A 1024×768 image costs about 800 prompt tokens.

## Memory

The Spark's 121.7 GiB is shared by CPU and GPU. Default profile:

| | GiB |
|---|---:|
| Model weights + drafter | 70.0 |
| KV + Mamba pool (fixed) | 19.0 |
| CUDA graphs | 2.2 |
| Image-embedding cache, grows to its budget with distinct images | up to 2 |
| Activation workspace, grows to its peak under long prompts and mixed load, then stays | about 6–8 |
| vLLM processes on the CPU side (API server 2 GB, engine 5–6 GB) | about 7–8 |
| Left for the host (`MemAvailable`): after boot / lowest measured while serving | 13.8–14.4 / 7.2 |

If the Spark also runs heavy desktop or agent workloads, start with `KV_CACHE_GIB=16`: 3 GiB more headroom, about 4 fewer concurrent sequences.

## Benchmarks and tests

```bash
./bench.sh            # decode, concurrency sweep up to MAX_NUM_SEQS, prefill 8K/32K/128K (about 40 min; 60+ for throughput)
./bench.sh decode     # single-user decode only (about 12 min)
LEVELS=1,8,24 ./bench.sh sweep
./test.sh             # functional suite (about 4 min including a 102K-token needle)
./test.sh quick       # without the long-context needle
```

`bench.sh` runs `vllm bench serve` from a throwaway container on the host network, as your user; it never touches the serving container. It builds its prompt set once from [SPEED-Bench](https://huggingface.co/datasets/nvidia/SPEED-Bench): the 369 inline prompts of at most 1024 tokens (vLLM's ShareGPT loader drops longer ones), so the first run needs internet. Cells that need more than 369 prompts reuse them and say so. Results land in `bench-results/<time>/summary.md` with every raw JSON next to it. Run one bench at a time and compare cells only at the same concurrency.

## Known limits

- **Greedy output is not bit-exact run to run.** The Mamba state cache uses stochastic rounding (the card's setting, for accuracy over long contexts), which draws a fresh seed per update. Replies part at near-tied tokens; they stay correct. Speculative acceptance, and with it single-user speed, moves a few percent from boot to boot for the same prompts.
- **The card's single-user command prefills 15–18% faster** (2,924 vs 2,506 tok/s at 8K, 2,905 vs 2,466 at 32K, 2,348 vs 2,042 at 128K). Eight A/B boots did not isolate the cause: not the weight loader, FP8 backend, token budget, sequence cap, block size, prefix flags or a fresh compile cache (`evidence/ab-prefill/`). The card's command serves one sequence at a time and loads in 7 minutes.
- **With images and thinking off,** the model sometimes reasons aloud in `content` before answering. Allow a few hundred tokens.
- **Video is off.** The card lists text and image for Spark, and with video vLLM sizes the encoder cache at the full context length.
- **One serve per Spark.** Weights alone take 70 GiB.
- **Long prompts take time.** A 966K-token prompt took 19.6 minutes to prefill; other requests keep decoding meanwhile.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `another GPU container is running` | Stop it with its own stop script. This recipe never removes containers it did not start. |
| `only N GiB available; this profile needs at least M GiB` | Something holds memory: `free -h`, `docker ps`. Page cache counts as available. |
| `Only N GiB free: KV pool … instead of 19` | Working as designed: fewer concurrent sequences, same speed. Free memory and restart for the full pool. |
| `port 8000 is already in use` | `PORT=8001 ./run.sh`, or stop what holds it. |
| Container exits during startup | `run.sh` prints the last 60 log lines. `docker logs nemotron-3.5-super-vl` for all of it. |
| Empty `content`, `finish_reason: length` | Reasoning used the whole `max_tokens`. Raise it, turn thinking off, or set `force_nonempty_content`. |
| Clearing `./.cache` | The server writes it as root: `docker run --rm -v "$PWD/.cache:/c" alpine rm -rf /c/vllm /c/flashinfer /c/triton /c/inductor /c/hf-modules` |

Logs: `docker logs -f nemotron-3.5-super-vl`. Memory guard log: `.run-state/nemotron-3.5-super-vl.memguard.log`.

## Evidence

[`evidence/`](evidence/) holds the raw output behind every number: boot logs, `vllm bench serve` JSON, memory samples, functional and soak results, the FP8 GEMM micro-benchmark, the prefill A/B boots, and the decision ledger [`decisions.tsv`](evidence/decisions.tsv). [`evidence/README.md`](evidence/README.md) maps README numbers to files.

## License

Recipe scripts: MIT ([LICENSE](LICENSE)). Model and drafter weights: [OpenMDW-1.1](https://openmdw.ai/license/1-1/), per their Hugging Face cards. SPEED-Bench prompts are fetched at bench time under NVIDIA's evaluation dataset license and are not redistributed here.
