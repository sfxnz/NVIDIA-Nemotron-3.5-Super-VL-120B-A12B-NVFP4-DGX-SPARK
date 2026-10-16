| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 39.9 | 43.1 | 365 ms | - | 4.35 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 39.8 | 42.8 | 368 ms | - | 4.29 | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 39.1 | 43.0 | 365 ms | - | 4.28 | 0 |
| sweep, max-concurrency 2, greedy, thinking off | 48.8 | 34.2 | 578 ms | - | 4.32 | 0 |
| sweep, max-concurrency 4, greedy, thinking off | 65.8 | 23.0 | 731 ms | - | 4.37 | 0 |
| sweep, max-concurrency 8, greedy, thinking off | 100.2 | 14.0 | 1007 ms | - | 4.36 | 0 |
| sweep, max-concurrency 16, greedy, thinking off | 149.8 | 12.3 | 1343 ms | - | 4.5 | 0 |
| sweep, max-concurrency 24, greedy, thinking off | 187.8 | 10.5 | 1538 ms | - | 4.48 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3491 ms | 2346 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 15334 ms | 2137 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 70940 ms | 1848 | - | 0 |
