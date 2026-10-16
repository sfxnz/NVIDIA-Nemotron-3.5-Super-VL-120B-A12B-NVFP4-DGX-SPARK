| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 41.9 | 45.7 | 403 ms | - | 4.66 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 37.0 | 36.9 | 351 ms | - | 4.0 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3182 ms | 2574 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 12944 ms | 2532 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 62752 ms | 2089 | - | 0 |
