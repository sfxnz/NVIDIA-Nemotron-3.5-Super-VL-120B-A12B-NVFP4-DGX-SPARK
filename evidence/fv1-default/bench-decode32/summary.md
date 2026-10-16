| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 42.1 | 50.4 | 398 ms | - | 4.65 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 36.8 | 37.8 | 342 ms | - | 3.96 | 0 |
