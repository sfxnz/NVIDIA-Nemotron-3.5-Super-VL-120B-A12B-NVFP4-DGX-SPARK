| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 40.9 | 45.2 | 368 ms | - | 4.46 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 41.9 | 45.6 | 366 ms | - | 4.45 | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 39.4 | 42.7 | 364 ms | - | 4.33 | 0 |
| sweep, max-concurrency 8, greedy, thinking off | 106.3 | 15.5 | 992 ms | - | 4.7 | 0 |
| sweep, max-concurrency 16, greedy, thinking off | 148.6 | 12.0 | 1318 ms | - | 4.48 | 0 |
| sweep, max-concurrency 24, greedy, thinking off | 186.0 | 10.6 | 1553 ms | - | 4.5 | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 204.6 | 9.5 | 4628 ms | - | 4.4 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3276 ms | 2500 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13322 ms | 2460 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 64590 ms | 2029 | - | 0 |
