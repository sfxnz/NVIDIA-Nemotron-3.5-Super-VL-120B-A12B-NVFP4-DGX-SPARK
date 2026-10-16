| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 39.8 | 42.7 | 365 ms | - | 4.36 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 40.8 | 47.5 | 366 ms | - | 4.43 | 0 |
