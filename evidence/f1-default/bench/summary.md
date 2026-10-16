| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 41.2 | 45.4 | 366 ms | - | 4.47 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 41.6 | 45.7 | 368 ms | - | 4.47 | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 38.4 | 37.9 | 369 ms | - | 4.22 | 0 |
| sweep, max-concurrency 2, greedy, thinking off | 48.9 | 32.3 | 546 ms | - | 4.37 | 0 |
| sweep, max-concurrency 4, greedy, thinking off | 65.3 | 22.9 | 711 ms | - | 4.23 | 0 |
| sweep, max-concurrency 8, greedy, thinking off | 101.8 | 15.0 | 995 ms | - | 4.49 | 0 |
| sweep, max-concurrency 16, greedy, thinking off | 152.8 | 11.7 | 1320 ms | - | 4.56 | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 195.0 | 10.1 | 8853 ms | - | 4.4 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3289 ms | 2491 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13444 ms | 2437 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 65060 ms | 2015 | - | 0 |
