| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 38.3 | 40.7 | 385 ms | - | 4.32 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 33.3 | 32.6 | 360 ms | - | 3.65 | 0 |
| sweep, max-concurrency 8, greedy, thinking off | 92.7 | 14.5 | 948 ms | - | 4.1 | 0 |
| sweep, max-concurrency 24, greedy, thinking off | 178.4 | 10.4 | 1557 ms | - | 4.33 | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 211.4 | 9.3 | 1665 ms | - | 4.29 | 0 |
