| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 41.1 | 45.2 | 400 ms | - | 4.57 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 37.8 | 38.9 | 348 ms | - | 4.12 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3247 ms | 2523 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13239 ms | 2475 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 64156 ms | 2043 | - | 0 |
