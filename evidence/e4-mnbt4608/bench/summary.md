| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 41.4 | 48.9 | 366 ms | - | 4.48 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 42.3 | 47.7 | 361 ms | - | 4.52 | 0 |
| sweep, max-concurrency 24, greedy, thinking off | 190.4 | 10.5 | 1543 ms | - | 4.5 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3297 ms | 2485 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13518 ms | 2424 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 65409 ms | 2004 | - | 0 |
