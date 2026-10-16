| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 19.2 | 19.5 | 291 ms | - | - | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 19.3 | 19.5 | 285 ms | - | - | 0 |
| sweep, max-concurrency 1, greedy, thinking off | 19.1 | 19.5 | 292 ms | - | - | 0 |
| sweep, max-concurrency 32, greedy, thinking off | 104.3 | 3.6 | 1097 ms | - | - | 0 |
| sweep, max-concurrency 64, greedy, thinking off | 158.2 | 2.8 | 1271 ms | - | - | 0 |
| sweep, max-concurrency 128, greedy, thinking off | 242.4 | 2.2 | 1588 ms | - | - | 0 |
| sweep, max-concurrency 192, greedy, thinking off | 303.5 | 1.8 | 1882 ms | - | - | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3094 ms | 2648 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13521 ms | 2423 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 64927 ms | 2019 | - | 0 |
