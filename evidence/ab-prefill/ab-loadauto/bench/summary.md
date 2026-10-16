| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3293 ms | 2488 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13165 ms | 2489 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 63713 ms | 2057 | - | 0 |
