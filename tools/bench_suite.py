"""Benchmark set behind ./bench.sh. Runs inside a throwaway client container on the host network.

Each cell is one `vllm bench serve` call. Acceptance length is vLLM's own figure for the measured requests; preemptions
come from /metrics read before and after the cell (warmup requests included). Results: one JSON per cell, plus
summary.json and summary.md in --out.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

FAILED = []
COUNTERS = ("spec_decode_num_drafts_total", "spec_decode_num_accepted_tokens_total", "num_preemptions_total",
            "prefix_cache_hits_total")


def scrape(base):
    txt = urllib.request.urlopen(f"{base}/metrics", timeout=10).read().decode()
    out = {}
    for k in COUNTERS:
        m = re.search(rf"^vllm:{k}{{[^}}]*}} ([0-9.e+]+)$", txt, re.M)
        out[k] = float(m.group(1)) if m else 0.0
    return out


def bench(a, name, extra):
    cmd = ["vllm", "bench", "serve", "--base-url", a.base_url, "--model", a.model, "--tokenizer", a.tokenizer,
           "--trust-remote-code", "--percentile-metrics", "ttft,tpot,itl,e2el", "--metric-percentiles", "50,90,99",
           "--save-result", "--result-dir", a.out, "--result-filename", f"{name}.json"] + extra
    m0 = scrape(a.base_url)
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    m1 = scrape(a.base_url)
    with open(os.path.join(a.out, f"{name}.log"), "w") as f:
        f.write(" ".join(cmd) + "\n\n" + p.stdout + "\n--- stderr (tail) ---\n" + p.stderr[-8000:])
    if p.returncode != 0:
        print(f"{name}: FAILED (see {name}.log)", flush=True)
        FAILED.append(name)
        return None
    with open(os.path.join(a.out, f"{name}.json")) as f:
        r = json.load(f)
    d = {k: m1[k] - m0[k] for k in COUNTERS}
    row = {"cell": name, "wall_s": round(time.time() - t0, 1), "completed": r["completed"], "failed": r["failed"],
           "output_tok_s": round(r["output_throughput"], 1), "ttft_p50_ms": round(r["median_ttft_ms"]),
           "ttft_p99_ms": round(r["p99_ttft_ms"]), "tpot_p50_ms": round(r["median_tpot_ms"], 2),
           "preemptions": int(d["num_preemptions_total"])}
    if r["median_tpot_ms"]:
        row["per_user_tok_s"] = round(1000 / r["median_tpot_ms"], 1)
    # vLLM's own figure covers the measured requests only; the /metrics delta also counts the warmup requests.
    if r.get("spec_decode_acceptance_length"):
        row["accept_len"] = round(r["spec_decode_acceptance_length"], 2)
    elif d["spec_decode_num_drafts_total"]:
        row["accept_len"] = round(1 + d["spec_decode_num_accepted_tokens_total"] / d["spec_decode_num_drafts_total"], 2)
    print(json.dumps(row), flush=True)
    return row, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--levels", default="1,2,4,8,16")
    ap.add_argument("--sets", default="decode,sweep,prefill")
    ap.add_argument("--max-model-len", type=int, default=262144)
    ap.add_argument("--output-len", type=int, default=512)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sets = a.sets.split(",")
    rows = []
    n_prompts = len(json.load(open(a.prompts)))
    print(f"{n_prompts} distinct prompts; sweep cells needing more reuse them", flush=True)
    chat = ["--backend", "openai-chat", "--endpoint", "/v1/chat/completions", "--dataset-name", "sharegpt",
            "--dataset-path", a.prompts, "--sharegpt-output-len", str(a.output_len), "--seed", "7"]
    no_think = ["--extra-body", '{"chat_template_kwargs":{"enable_thinking":false}}', "--temperature", "0"]

    if "decode" in sets:
        # Single stream, real prompts, greedy, thinking off: the headline decode number.
        res = bench(a, "decode_c1_greedy", chat + no_think + ["--num-prompts", "32", "--max-concurrency", "1",
                                                              "--num-warmups", "2"])
        if res:
            res[0]["label"] = "decode, max-concurrency 1, greedy, thinking off"; rows.append(res[0])
        # The model card's sampling (T=1.0, top_p 0.95) with thinking on: what a chat client sees by default.
        res = bench(a, "decode_c1_card_sampling", chat + ["--extra-body", '{"chat_template_kwargs":{"enable_thinking":true}}',
                                                          "--temperature", "1.0", "--top-p", "0.95", "--num-prompts", "16",
                                                          "--max-concurrency", "1", "--num-warmups", "1"])
        if res:
            res[0]["label"] = "decode, max-concurrency 1, T=1.0 top_p 0.95, thinking on"; rows.append(res[0])

    if "sweep" in sets:
        for c in (int(x) for x in a.levels.split(",")):
            res = bench(a, f"sweep_c{c}", chat + no_think + ["--num-prompts", str(max(8, 3 * c)),
                                                             "--max-concurrency", str(c), "--num-warmups", "1"])
            if res:
                reuse = " (prompts reused)" if max(8, 3 * c) > n_prompts else ""
                res[0]["label"] = f"sweep, max-concurrency {c}, greedy, thinking off{reuse}"; rows.append(res[0])

    if "prefill" in sets:
        for inl, n in ((8192, 3), (32768, 2), (131072, 1)):
            if inl + 16 > a.max_model_len:
                continue
            res = bench(a, f"prefill_{inl // 1024}k", ["--backend", "openai", "--endpoint", "/v1/completions",
                                                        "--dataset-name", "random", "--random-input-len", str(inl),
                                                        "--random-output-len", "1", "--random-range-ratio", "0",
                                                        "--seed", str(int(time.time())), "--num-prompts", str(n),
                                                        "--max-concurrency", "1", "--num-warmups", "0"])
            if res:
                row, r = res
                row["label"] = f"prefill, {inl} random tokens, max-concurrency 1"
                row["prefill_tok_s"] = round(inl / (r["median_ttft_ms"] / 1000))
                rows.append(row)

    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(rows, f, indent=1)
    lines = ["| Cell | Output tok/s (all users) | Per-user tok/s (1/TPOT p50) | TTFT p50 | Prefill tok/s | Accept len | Preempt |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['label']} | {r['output_tok_s']} | {r.get('per_user_tok_s', '-')} | {r['ttft_p50_ms']} ms | "
                     f"{r.get('prefill_tok_s', '-')} | {r.get('accept_len', '-')} | {r['preemptions']} |")
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if FAILED:
        print(f"failed cells: {', '.join(FAILED)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
