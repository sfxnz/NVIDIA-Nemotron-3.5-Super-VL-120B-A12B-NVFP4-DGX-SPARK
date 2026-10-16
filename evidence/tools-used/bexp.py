#!/usr/bin/env python3
"""Experiment bench driver (host side, stdlib only). Runs `vllm bench serve` inside the serving container.

usage: bexp.py TAG SCENARIO [SCENARIO ...]
  decode:C:N:OUT[:think|nothink][:TEMP]  SPEED-Bench qualitative prompts (server-side chat template, client template
                                          skipped), max-concurrency C, N prompts, max_tokens OUT, default nothink, TEMP 0
  prefill:IN:N[:C]                        random completions, unique prompts, input IN, output 1, max-concurrency C (1)
  rand:C:N:IN:OUT                         random completions IN/OUT, ignore_eos, temperature 0, max-concurrency C
Writes vllm bench JSON to RESULTS/TAG/ and appends one summary line per scenario to RESULTS/summary.jsonl.
"""
import json, os, re, subprocess, sys, threading, time, urllib.request

NAME = os.environ.get("NAME", "nemotron-exp")
MODEL = os.environ.get("SERVED", "nemotron-3.5-super-vl")
TOK = os.environ.get("TOK", "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4")
RESULTS = os.environ.get("RESULTS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results"))
PORT = os.environ.get("PORT", "8000")
COUNTERS = ("spec_decode_num_drafts_total", "spec_decode_num_draft_tokens_total", "spec_decode_num_accepted_tokens_total",
            "prompt_tokens_total", "generation_tokens_total", "num_preemptions_total",
            "prefix_cache_queries_total", "prefix_cache_hits_total")


def scrape():
    return urllib.request.urlopen(f"http://127.0.0.1:{PORT}/metrics", timeout=10).read().decode()


def metrics():
    txt = scrape()
    out = {}
    for k in COUNTERS:
        m = re.search(rf"^vllm:{k}{{[^}}]*}} ([0-9.e+]+)$", txt, re.M)
        out[k] = float(m.group(1)) if m else 0.0
    for m in re.finditer(r'^vllm:spec_decode_num_accepted_tokens_per_pos_total{[^}]*position="(\d+)"[^}]*} ([0-9.e+]+)$', txt, re.M):
        out[f"pos{m.group(1)}"] = float(m.group(2))
    return out


def gauge(txt, name):
    m = re.search(rf"^vllm:{name}{{[^}}]*}} ([0-9.e+]+)$", txt, re.M)
    return float(m.group(1)) if m else 0.0


def meminfo():
    with open("/proc/meminfo") as f:
        d = {l.split(":")[0]: int(l.split()[1]) for l in f}
    with open("/proc/vmstat") as f:
        v = {l.split()[0]: int(l.split()[1]) for l in f}
    return d["MemAvailable"] // 1024, d["SwapFree"] // 1024, v.get("pswpin", 0)


class Poller(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.stop = False; self.max_running = 0; self.max_waiting = 0; self.max_kv = 0.0; self.min_avail = 10**9

    def run(self):
        while not self.stop:
            try:
                t = scrape()
                self.max_running = max(self.max_running, gauge(t, "num_requests_running"))
                self.max_waiting = max(self.max_waiting, gauge(t, "num_requests_waiting"))
                self.max_kv = max(self.max_kv, gauge(t, "kv_cache_usage_perc"))
            except Exception:
                pass
            self.min_avail = min(self.min_avail, meminfo()[0])
            time.sleep(1)


def run(tag, scen):
    parts = scen.split(":")
    kind = parts[0]
    fname = scen.replace(":", "_").replace(".", "p") + ".json"
    os.makedirs(os.path.join(RESULTS, tag), exist_ok=True)
    try:
        os.chmod(os.path.join(RESULTS, tag), 0o777)
    except PermissionError:
        pass
    base = ["docker", "exec", "-e", "HF_HUB_OFFLINE=1", NAME, "vllm", "bench", "serve",
            "--model", MODEL, "--tokenizer", TOK, "--trust-remote-code",
            "--base-url", "http://127.0.0.1:8000",
            "--save-result", "--result-dir", f"/results/{tag}", "--result-filename", fname,
            "--percentile-metrics", "ttft,tpot,itl,e2el", "--metric-percentiles", "50,90,99"]
    inl = None
    if kind == "decode":
        c, n, out = int(parts[1]), int(parts[2]), int(parts[3])
        think = (parts[4] if len(parts) > 4 else "nothink") == "think"
        temp = parts[5] if len(parts) > 5 else "0"
        cmd = base + ["--backend", "openai-chat", "--endpoint", "/v1/chat/completions",
                      "--dataset-name", "speed_bench", "--dataset-path", "/bench/speed-bench",
                      "--speed-bench-dataset-subset", "qualitative", "--speed-bench-output-len", str(out),
                      "--skip-chat-template", "--seed", "7",
                      "--extra-body", json.dumps({"chat_template_kwargs": {"enable_thinking": think}}),
                      "--temperature", temp, "--num-prompts", str(n), "--max-concurrency", str(c), "--num-warmups", "1"]
        if temp != "0":
            cmd += ["--top-p", "0.95"]
    elif kind == "prefill":
        inl, n = int(parts[1]), int(parts[2])
        c = int(parts[3]) if len(parts) > 3 else 1
        cmd = base + ["--backend", "openai", "--endpoint", "/v1/completions",
                      "--dataset-name", "random", "--random-input-len", str(inl), "--random-output-len", "1",
                      "--random-range-ratio", "0", "--seed", str(int(time.time()) % 100000),
                      "--num-prompts", str(n), "--max-concurrency", str(c), "--num-warmups", "0"]
    elif kind == "rand":
        c, n, inl2, out = map(int, parts[1:5])
        cmd = base + ["--backend", "openai", "--endpoint", "/v1/completions",
                      "--dataset-name", "random", "--random-input-len", str(inl2), "--random-output-len", str(out),
                      "--random-range-ratio", "0", "--seed", str(int(time.time()) % 100000), "--temperature", "0",
                      "--ignore-eos", "--num-prompts", str(n), "--max-concurrency", str(c), "--num-warmups", "1"]
    else:
        raise SystemExit(f"bad scenario {scen}")

    m0 = metrics(); a0 = meminfo(); t0 = time.time()
    pol = Poller(); pol.start()
    p = subprocess.run(cmd, capture_output=True, text=True)
    pol.stop = True; pol.join(timeout=3)
    t1 = time.time(); m1 = metrics(); a1 = meminfo()
    with open(os.path.join(RESULTS, tag, fname.replace(".json", ".log")), "w") as f:
        f.write(" ".join(cmd) + "\n\n" + p.stdout + "\n--- stderr ---\n" + p.stderr[-20000:])
    d = {k: m1.get(k, 0) - m0.get(k, 0) for k in m1}
    rec = {"tag": tag, "scenario": scen, "rc": p.returncode, "wall_s": round(t1 - t0, 1),
           "mem_avail_min_mib": pol.min_avail, "mem_avail_after_mib": a1[0], "swapfree_after_mib": a1[1],
           "swapin_pages": a1[2] - a0[2], "max_running": pol.max_running, "max_waiting": pol.max_waiting,
           "max_kv_usage": round(pol.max_kv, 3), "preemptions": d["num_preemptions_total"],
           "prefix_hits": d["prefix_cache_hits_total"], "prefix_queries": d["prefix_cache_queries_total"]}
    if d["spec_decode_num_drafts_total"] > 0:
        dr = d["spec_decode_num_drafts_total"]
        rec["accept_len"] = round(1 + d["spec_decode_num_accepted_tokens_total"] / dr, 3)
        rec["per_pos"] = [round(d[k] / dr, 3) for k in sorted((k for k in d if k.startswith("pos")), key=lambda x: int(x[3:]))]
    try:
        with open(os.path.join(RESULTS, tag, fname)) as f:
            r = json.load(f)
        for k in ("completed", "failed", "duration", "total_input_tokens", "total_output_tokens",
                  "request_throughput", "output_throughput", "total_token_throughput", "max_concurrency",
                  "median_ttft_ms", "p90_ttft_ms", "p99_ttft_ms", "median_tpot_ms", "p90_tpot_ms", "p99_tpot_ms",
                  "median_itl_ms", "p99_itl_ms", "median_e2el_ms"):
            if k in r and r[k] is not None:
                rec[k] = round(r[k], 2) if isinstance(r[k], float) else r[k]
        if kind == "prefill" and r.get("median_ttft_ms"):
            rec["prefill_tok_s_median"] = round(inl / (r["median_ttft_ms"] / 1000), 1)
            rec["prefill_agg_tok_s"] = round(r["total_input_tokens"] / r["duration"], 1)
        if r.get("median_tpot_ms"):
            rec["per_user_tok_s"] = round(1000 / r["median_tpot_ms"], 2)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}; stderr tail: {p.stderr[-600:]}"
    with open(os.path.join(RESULTS, "summary.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    keys = ("scenario", "rc", "completed", "output_throughput", "per_user_tok_s", "median_ttft_ms", "p99_ttft_ms",
            "median_itl_ms", "prefill_tok_s_median", "prefill_agg_tok_s", "accept_len", "max_running", "max_waiting",
            "preemptions", "prefix_hits", "mem_avail_min_mib", "swapin_pages", "error")
    print(json.dumps({k: rec[k] for k in keys if k in rec}), flush=True)
    return rec


if __name__ == "__main__":
    tag = sys.argv[1]
    for s in sys.argv[2:]:
        run(tag, s)
