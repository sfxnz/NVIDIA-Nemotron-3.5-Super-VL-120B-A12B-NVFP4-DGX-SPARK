| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 19.0 | 19.4 | 315 ms | - | - | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 19.2 | 19.4 | 263 ms | - | - | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 19.1 | 19.4 | 239 ms | - | - | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 101.0 | 3.6 | 1047 ms | - | - | 0 |
| sweep, max-concurrency 192, greedy, thinking off (prompts reused) | 304.5 | 1.8 | 1935 ms | - | - | 0 |
