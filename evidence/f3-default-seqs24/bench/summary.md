| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 40.6 | 43.1 | 367 ms | - | 4.41 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 41.0 | 46.4 | 370 ms | - | 4.36 | 0 |
| sweep, max-concurrency 24, greedy, thinking off | 186.5 | 10.6 | 1552 ms | - | 4.47 | 0 |
