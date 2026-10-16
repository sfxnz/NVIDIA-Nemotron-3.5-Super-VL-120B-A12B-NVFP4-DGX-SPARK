| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 19.7 | 20.0 | 292 ms | - | - | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 19.8 | 20.0 | 281 ms | - | - | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 19.6 | 20.0 | 293 ms | - | - | 0 |
| sweep, max-concurrency 8, greedy, thinking off | 55.5 | 7.8 | 616 ms | - | - | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 104.9 | 3.7 | 1089 ms | - | - | 0 |
| sweep, max-concurrency 64, greedy, thinking off | 156.3 | 2.8 | 1264 ms | - | - | 0 |
| sweep, max-concurrency 96, greedy, thinking off | 198.2 | 2.4 | 1492 ms | - | - | 0 |
| sweep, max-concurrency 128, greedy, thinking off | 243.5 | 2.2 | 1650 ms | - | - | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3310 ms | 2475 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13986 ms | 2343 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 67582 ms | 1939 | - | 0 |
