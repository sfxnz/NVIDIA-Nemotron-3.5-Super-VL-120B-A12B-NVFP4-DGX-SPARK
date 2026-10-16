# Evidence

Raw output behind every number in the top-level README, measured on one DGX Spark (spark1, GB10, driver 580.173.02) on 15–16 Oct 2026 with image `vllm/vllm-openai@sha256:cb9bc64f…` (nightly `3f1bcfd8`), model snapshot `82d9369`, drafter snapshot `7c7221a`. The ledger of hypotheses and verdicts is [`decisions.tsv`](decisions.tsv).

Each run directory holds what applies of: `run.out` (the `run.sh` transcript), `boot-lines.txt` (backend, block size, KV and memory lines from the server log), `server.log.gz`, `inspect.json` (`docker inspect`, env removed), `mem.csv` (MemAvailable/SwapFree once a second: epoch, avail MiB, free MiB, swapfree MiB), `free-*.txt`, `rss-*.txt` (`docker top`), `bench/` (`bench.sh` output: one `vllm bench serve` JSON and log per cell, `summary.md`, `summary.json`, `conditions.txt`), `test-*.out` (`test.sh`).

## Runs behind the README tables (final scripts)

| Directory | What | README numbers |
|---|---|---|
| `fv1-default/` | `./run.sh` defaults, first boot of the final scripts | 1-user rows (`bench-decode32/`), 8/24/32-user rows (`bench/`), functional suite (`test-full.out`, 34/35 + PC1 prefix-cache turns), 600-image probe (`image-cache-probe.out`), drain stop (`stop-under-load.txt`), lowest free memory 7.2 GiB (`mem.csv`: 7406 MiB, while `bench.sh` ran), CUDA graphs 2.2 GiB (`boot-lines.txt`) |
| `fv2-default/` | `./run.sh` defaults, second boot | 1-user rows (`bench/decode_*`), full sweep 1–32, prefill 8K/32K/128K, free after boot 14.4 GiB |
| `tv1-throughput/` | `PROFILE=throughput ./run.sh` on the final scripts | throughput profile check (functional suite at 192, 1/32/192-user cells) |
| `f5-throughput/` | throughput profile, same compute flags (1M context and 256 sequences then) | throughput table: 1–192 users and prefill (`bench/`), 256 users (`bench-c256/`, TTFT 39.7 s: queueing) |
| `text1m-default/` | `IMAGES_PER_PROMPT=0 MAX_MODEL_LEN=1048576 ./run.sh` | text-only 1M mode: 30/30 executed checks, 68.4 GiB weights without the vision tower |
| `f1-default/` | default compute flags at `MAX_MODEL_LEN=1048576` (prefix-match flags still on) | 966,500-token needle (`needle-1m.out`, `needle-1m.json`: 3/3, 1178 s), 1M decode 45.4 tok/s vs 262K 45.2 (`f2-default-262k/`) |
| `f4-final-default/` | default compute flags at 1M (prefix-match flags still on) | 30-minute soak (`soak/`: 866 requests, 0 failures, lowest 7431 MiB = 7.3 GiB), memory-plan base (soak footprint 106.9 GiB); `mem.csv` dips to 6581 MiB = 6.4 GiB during the `bench.sh decode` run right after the soak (the bench client container) |
| `apikey-bind/` | `API_KEY=<random> BIND=0.0.0.0 ./run.sh` | key path: smoke, `test.sh` (33/34 executed, D1 soft) and `bench.sh` through the key; 401 without it; key absent from `docker inspect` args and the process list (checked live) |
| `firstrun-fallback/` | `./run.sh` with an empty Hugging Face cache for the drafter and no `hf` on PATH | the Docker `hf download` fallback (`run.out`), downloaded files owned by the user (`drafter-file-owners.txt`), `thinking_token_budget` probe and the C7 check |
| `card-baseline/` | the model card's Spark command verbatim (`card_baseline.sh`) | card column: decode, prefill, 430 s load, swap |
| `mtp5/` | `./run.sh` defaults with MTP-5 instead of LiLiCorr (block 64) | MTP-5 column, 10.02× vs 8.19× pool capacity (`boot-lines.txt`) |

## Experiment trail

| Directory | Decision |
|---|---|
| `e0-card/` | D01: first look at the card command (first harness; see note) |
| `e1-no-spec/` | D02, D03: fastsafetensors load time; no speculative decoding |
| `fp8-gemm-microbench/` | D04: FP8 GEMM backends at this model's shapes, decode sizes (`output.txt`) and prefill sizes (`output-prefill-sizes.txt`) |
| `e2-default-mnbt9216/` | D05, D06, D07, D08: block 256, LiLiCorr under load, per-position acceptance (`metrics-final.txt`), the long-prefill memory plateau |
| `e3-throughput-v1/` | D11, D12: first throughput profile (14 GiB pool, chunk 8192) |
| `e4-mnbt4608/` | D09: one-block prefill chunk |
| `f0-dummy-uncapped/` | D10: 8.0 GiB free after boot with the uncapped profiling image |
| `f2-default-262k/`, `f3-default-seqs24/` | D13: context length and sequence cap do not change decode |
| `ab-prefill/` | known limit: eight prefill A/B boots against the card's faster prefill (`ab-fp8torch`, `ab-fp8flashinfer`, `ab-mnbt8192`, `ab-seqs1`, `ab-loadauto`, `ab-bs64`, `ab-cardlike`, `ab-freshcache`) |
| `tools-used/` | the scratch tools behind the experiments (`exp.sh`, `bexp.py`, `variant.py`, `boot_variant.sh`, `card_baseline.sh`, `memwatch.sh`, `stop_under_load.py`, `collect_evidence.sh`, the `v_*.sh` variant commands) |

## Notes

- `e0-card/` and `e1-no-spec/` used the first harness (`tools-used/bexp.py`). Its SPEED-Bench cells applied the chat template on the client and again on the server, ran thinking on, and sampled at T=1. They are kept for the decisions they support (load time, step time, memory), not for decode tok/s.
- The filtered 369-prompt file first ran in `f5-throughput/bench-c256/`; every later run uses it. Earlier runs used the unfiltered file (vLLM dropped the long prompts at load, in a different order). `fv1-default/bench/` still had 16- and 8-prompt decode cells; `fv1-default/bench-decode32/` re-ran them with 32 and 16, the size every later run uses. Compare 1-user decode only within the same set and cell size.
- Greedy decoding is not bit-exact on this stack (stochastic rounding in the Mamba cache), so acceptance length and single-user speed move a few percent between boots for the same prompts.
- MiB to GiB is /1024 throughout.
