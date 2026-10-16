"""FP8 per-tensor W8A8 GEMM micro-benchmark on this model's decode shapes (run inside the vLLM image)."""
import torch

torch.manual_seed(0)
dev = "cuda"
SHAPES = {  # name: (K, N)  y[M,N] = x[M,K] @ W[N,K]^T
    "mamba.in_proj": (4096, 18560),
    "mamba.out_proj": (8192, 4096),
    "attn.qkv": (4096, 4608),
    "attn.o": (4096, 4096),
    "lm_head": (4096, 131072),
}
COUNT = {"mamba.in_proj": 40, "mamba.out_proj": 40, "attn.qkv": 8, "attn.o": 8, "lm_head": 1}
MS = [int(x) for x in __import__("os").environ.get("MS", "1,2,4,8,16,32,64,128").split(",")]


def bench(fn, iters=200, warm=20):
    for _ in range(warm):
        fn()
    torch.cuda.synchronize()
    s, e = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    # flush L2 between reps is unnecessary: weights (>=16 MB) exceed GB10 L2 (24 MB) only for big shapes; report as-is
    s.record()
    for _ in range(iters):
        fn()
    e.record(); torch.cuda.synchronize()
    return s.elapsed_time(e) / iters * 1000  # us


backends = {}
backends["torch"] = lambda a, bt, sa, sb: torch._scaled_mm(a, bt, scale_a=sa, scale_b=sb, out_dtype=torch.bfloat16)
try:
    from vllm import _custom_ops as ops
    backends["cutlass"] = lambda a, bt, sa, sb: ops.cutlass_scaled_mm(a, bt, sa, sb, torch.bfloat16)
except Exception as ex:
    print("cutlass unavailable", ex)
try:
    import flashinfer
    from flashinfer.gemm import bmm_fp8

    def fi(a, bt, sa, sb):
        return bmm_fp8(a.unsqueeze(0), bt.unsqueeze(0), sa, sb, torch.bfloat16, backend="auto")
    backends["flashinfer_auto"] = fi
    for be in ("cutlass", "cublas"):
        def mk(be):
            return lambda a, bt, sa, sb: bmm_fp8(a.unsqueeze(0), bt.unsqueeze(0), sa, sb, torch.bfloat16, backend=be)
        backends[f"flashinfer_{be}"] = mk(be)
except Exception as ex:
    print("flashinfer unavailable", ex)

totals = {b: {m: 0.0 for m in MS} for b in backends}
for name, (K, N) in SHAPES.items():
    w = (torch.randn(N, K, device=dev) * 0.05).to(torch.float8_e4m3fn)
    bt = w.t()  # [K,N] column-major view
    sb = torch.tensor(0.02, device=dev, dtype=torch.float32)
    sa = torch.tensor(0.05, device=dev, dtype=torch.float32)
    for M in MS:
        a = (torch.randn(M, K, device=dev)).to(torch.float8_e4m3fn)
        row = []
        for b, fn in backends.items():
            try:
                us = bench(lambda: fn(a, bt, sa, sb))
                gbs = (N * K) / (us * 1e-6) / 1e9
                totals[b][M] += us * COUNT[name]
                row.append(f"{b}={us:8.1f}us({gbs:5.0f}GB/s)")
            except Exception as ex:
                totals[b][M] = float("nan")
                row.append(f"{b}=ERR({type(ex).__name__})")
        print(f"{name:15s} M={M:4d} " + " ".join(row), flush=True)
print("\nPer-decode-step FP8 total (ms) by M:")
for b in backends:
    print(f"  {b:18s} " + " ".join(f"M{m}={totals[b][m]/1000:6.2f}" for m in MS))
