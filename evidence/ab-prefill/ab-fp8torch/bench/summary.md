| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 40.0 | 45.1 | 409 ms | - | 4.57 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 35.9 | 36.4 | 354 ms | - | 3.98 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3112 ms | 2632 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 12673 ms | 2586 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 61459 ms | 2133 | - | 0 |
