| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 38.6 | 40.4 | 341 ms | - | 4.25 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 35.4 | 37.3 | 323 ms | - | 3.79 | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 40.0 | 39.4 | 318 ms | - | 4.36 | 0 |
| sweep, max-concurrency 8, greedy, thinking off | 98.5 | 17.9 | 969 ms | - | 4.45 | 0 |
| sweep, max-concurrency 24, greedy, thinking off | 177.4 | 11.0 | 1554 ms | - | 4.59 | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 188.0 | 10.6 | 7326 ms | - | 4.46 | 0 |
