| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |
|---|---:|---:|---:|---:|---:|---:|
| prefill, 8192 random tokens, max-concurrency 1 | 0.3 | - | 3254 ms | 2517 | - | 0 |
| prefill, 32768 random tokens, max-concurrency 1 | 0.1 | - | 13231 ms | 2477 | - | 0 |
| prefill, 131072 random tokens, max-concurrency 1 | 0.0 | - | 64324 ms | 2038 | - | 0 |
