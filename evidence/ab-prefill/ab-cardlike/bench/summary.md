| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 2892 ms | 2832 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13465 ms | 2434 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 66465 ms | 1972 | - | 0 |
