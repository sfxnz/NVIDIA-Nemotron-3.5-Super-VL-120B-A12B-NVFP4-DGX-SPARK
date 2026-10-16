| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3510 ms | 2334 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 14745 ms | 2222 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 69989 ms | 1873 | - | 0 |
