| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 40.5 | 45.3 | 401 ms | - | 4.49 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 38.0 | 37.3 | 340 ms | - | 4.09 | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 37.5 | 42.4 | 318 ms | - | 4.07 | 0 |
| sweep, max-concurrency 2, greedy, thinking off | 50.6 | 31.1 | 532 ms | - | 4.19 | 0 |
| sweep, max-concurrency 4, greedy, thinking off | 70.0 | 22.4 | 774 ms | - | 4.41 | 0 |
| sweep, max-concurrency 8, greedy, thinking off | 101.8 | 17.9 | 1006 ms | - | 4.47 | 0 |
| sweep, max-concurrency 16, greedy, thinking off | 146.0 | 13.1 | 1338 ms | - | 4.63 | 0 |
| sweep, max-concurrency 24, greedy, thinking off | 180.3 | 10.9 | 1554 ms | - | 4.6 | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 190.9 | 10.5 | 7501 ms | - | 4.56 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3269 ms | 2506 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13287 ms | 2466 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 64199 ms | 2042 | - | 0 |
