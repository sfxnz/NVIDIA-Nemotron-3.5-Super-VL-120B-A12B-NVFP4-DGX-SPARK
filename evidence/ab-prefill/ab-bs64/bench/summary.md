| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3149 ms | 2602 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13523 ms | 2423 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 65459 ms | 2002 | - | 0 |
