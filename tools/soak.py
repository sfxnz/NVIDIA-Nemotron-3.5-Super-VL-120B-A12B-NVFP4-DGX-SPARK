#!/usr/bin/env python3
"""Mixed-load soak against a running server (stdlib only).

N client threads loop for --minutes over a mix of request kinds: short chat (thinking off), reasoning (thinking on),
tool call, image, and a 16K-32K token prompt. Every reply is checked. A sampler thread logs MemAvailable, SwapFree,
/health and the engine counters every 2 s, and flags a stall: requests running while generation_tokens_total stays
flat for 120 s. Writes soak.json (summary) and soak_mem.csv. Exit 1 on any failed request, unhealthy sample or stall.
"""
import argparse, base64, json, os, random, re, sys, threading, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from functional_tests import make_image  # noqa: E402  (PIL optional; falls back to a pure-Python PNG)

A = None
LOCK = threading.Lock()
STATS = {}
FAILS = []
STOP = threading.Event()
TOOLS = [{"type": "function", "function": {"name": "get_weather", "description": "Current weather for a city.",
          "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
WORDS = "amber basil cedar delta ember fable garnet harbor indigo juniper kettle lantern meadow nickel orchard".split()


def post(body, timeout=1800):
    hdr = {"Content-Type": "application/json"}
    if A.api_key:
        hdr["Authorization"] = f"Bearer {A.api_key}"
    req = urllib.request.Request(A.base + "/v1/chat/completions", json.dumps({"model": A.model, **body}).encode(), hdr)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def one(kind, rnd):
    off = {"enable_thinking": False}
    if kind == "short":
        a, b = rnd.randint(100, 999), rnd.randint(100, 999)
        js = post({"messages": [{"role": "user", "content": f"What is {a} + {b}? Reply with the number only."}],
                   "max_tokens": 32, "temperature": 0, "chat_template_kwargs": off})
        ok = str(a + b) in (js["choices"][0]["message"]["content"] or "")
    elif kind == "reason":
        a, b = rnd.randint(11, 99), rnd.randint(11, 99)
        js = post({"messages": [{"role": "user", "content": f"What is {a} * {b}? End with the number."}],
                   "max_tokens": 4096, "temperature": 0.6, "top_p": 0.95})
        m = js["choices"][0]["message"]
        ok = str(a * b) in (m.get("content") or "") and bool(m.get("reasoning"))
    elif kind == "tool":
        city = rnd.choice(["Paris", "Tokyo", "Lima", "Oslo", "Cairo"])
        js = post({"messages": [{"role": "user", "content": f"Weather in {city}? Use the tool."}], "tools": TOOLS,
                   "max_tokens": 1024, "temperature": 0, "chat_template_kwargs": off})
        tcs = js["choices"][0]["message"].get("tool_calls") or []
        ok = bool(tcs) and city.lower() in json.loads(tcs[0]["function"]["arguments"]).get("city", "").lower()
    elif kind == "image":
        png, _ = make_image()
        url = "data:image/png;base64," + base64.b64encode(png).decode()
        js = post({"messages": [{"role": "user", "content": [{"type": "text", "text": "What colors are the shapes?"},
                                                             {"type": "image_url", "image_url": {"url": url}}]}],
                   "max_tokens": 128, "temperature": 0, "chat_template_kwargs": off})
        t = (js["choices"][0]["message"]["content"] or "").lower()
        ok = "red" in t and "blue" in t
    else:  # long
        n = rnd.randint(16000, 32000)
        key = f"{rnd.choice(WORDS)}-{rnd.randint(1000, 9999)}"
        filler = " ".join(f"{rnd.choice(WORDS)} {rnd.randint(0, 99999)}." for _ in range(n // 4))
        cut = len(filler) // 2
        text = filler[:cut] + f" The key is {key}. " + filler[cut:]
        js = post({"messages": [{"role": "user", "content": text + "\n\nWhat is the key? Reply with the key only."}],
                   "max_tokens": 32, "temperature": 0, "chat_template_kwargs": off})
        ok = key in (js["choices"][0]["message"]["content"] or "")
    return ok, js["usage"]["completion_tokens"]


def worker(i):
    rnd = random.Random(1000 + i)
    kinds = ["short"] * 4 + ["reason"] * 2 + ["tool"] * 2 + ["image"] + ["long"]
    while not STOP.is_set():
        kind = rnd.choice(kinds)
        t0 = time.time()
        try:
            ok, toks = one(kind, rnd)
            err = "" if ok else "bad reply"
        except Exception as e:  # transport or HTTP error
            ok, toks, err = False, 0, f"{type(e).__name__}: {str(e)[:200]}"
        with LOCK:
            s = STATS.setdefault(kind, {"ok": 0, "fail": 0, "secs": 0.0, "tokens": 0})
            s["ok" if ok else "fail"] += 1
            s["secs"] += time.time() - t0
            s["tokens"] += toks
            if not ok:
                FAILS.append({"t": round(time.time()), "kind": kind, "err": err})


def metric(txt, name):
    m = re.search(rf"^vllm:{name}{{[^}}]*}} ([0-9.e+]+)$", txt, re.M)
    return float(m.group(1)) if m else 0.0


def sampler(path, out):
    last_gen, last_change, out["min_avail_mib"], out["unhealthy"], out["stall"] = None, time.time(), 10**9, 0, False
    with open(path, "w") as f:
        f.write("epoch,avail_mib,swapfree_mib,running,waiting,gen_tokens,health\n")
        while not STOP.is_set():
            mi = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
            avail, swap = mi["MemAvailable"] // 1024, mi["SwapFree"] // 1024
            try:
                h = urllib.request.urlopen(A.base + "/health", timeout=10).status
                txt = urllib.request.urlopen(A.base + "/metrics", timeout=10).read().decode()
                run, wait, gen = metric(txt, "num_requests_running"), metric(txt, "num_requests_waiting"), metric(txt, "generation_tokens_total")
            except Exception:
                h, run, wait, gen = 0, -1, -1, -1
            if h != 200:
                out["unhealthy"] += 1
            if gen != last_gen:
                last_gen, last_change = gen, time.time()
            elif run > 0 and time.time() - last_change > 120:
                out["stall"] = True
            out["min_avail_mib"] = min(out["min_avail_mib"], avail)
            f.write(f"{int(time.time())},{avail},{swap},{run},{wait},{gen},{h}\n"); f.flush()
            time.sleep(2)


def main():
    global A
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--model", default="nemotron-3.5-super-vl")
    p.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY", ""))
    p.add_argument("--clients", type=int, default=16)
    p.add_argument("--minutes", type=float, default=30)
    p.add_argument("--out", default=".")
    A = p.parse_args()
    os.makedirs(A.out, exist_ok=True)
    mem = {}
    threading.Thread(target=sampler, args=(os.path.join(A.out, "soak_mem.csv"), mem), daemon=True).start()
    ws = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(A.clients)]
    for w in ws:
        w.start()
    t_end = time.time() + A.minutes * 60
    while time.time() < t_end:
        time.sleep(30)
        with LOCK:
            done = sum(s["ok"] + s["fail"] for s in STATS.values())
            bad = sum(s["fail"] for s in STATS.values())
        print(f"{time.strftime('%H:%M:%S')} requests={done} failed={bad} min_avail={mem.get('min_avail_mib')}MiB "
              f"stall={mem.get('stall')}", flush=True)
    STOP.set()
    for w in ws:
        w.join(timeout=1800)
    summary = {"clients": A.clients, "minutes": A.minutes, "by_kind": STATS, "failures": FAILS[:50],
               "failed": len(FAILS), "min_avail_mib": mem.get("min_avail_mib"), "unhealthy_samples": mem.get("unhealthy"),
               "stall": mem.get("stall")}
    json.dump(summary, open(os.path.join(A.out, "soak.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))
    sys.exit(1 if (FAILS or mem.get("unhealthy") or mem.get("stall")) else 0)


if __name__ == "__main__":
    main()
