| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| decode, max-concurrency 1, greedy, thinking off | 40.9 | 44.3 | 434 ms | - | 4.66 | 0 |
| decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on | 36.6 | 36.6 | 342 ms | - | 4.08 | 0 |
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 2802 ms | 2924 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 11279 ms | 2905 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 55816 ms | 2348 | - | 0 |
