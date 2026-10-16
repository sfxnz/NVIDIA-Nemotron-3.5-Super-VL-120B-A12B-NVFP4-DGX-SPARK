import json, urllib.request, threading, time, subprocess, sys
res = {}
def req(i, max_tokens):
    body = {"model": "nemotron-3.5-super-vl", "messages": [{"role": "user", "content": f"Write about topic {i}: the history of bridges."}],
            "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False}}
    t = time.time()
    try:
        js = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=600))
        res[i] = f"completed finish={js['choices'][0]['finish_reason']} tokens={js['usage']['completion_tokens']} after {time.time()-t:.1f}s"
    except Exception as e:
        res[i] = f"error {type(e).__name__}: {str(e)[:100]} after {time.time()-t:.1f}s"
# two short requests (finish inside the 45 s drain) and two long ones (cut at the drain limit)
ts = [threading.Thread(target=req, args=(i, mt)) for i, mt in enumerate([300, 300, 4000, 4000])]
[t.start() for t in ts]
time.sleep(10)
t0 = time.time()
out = subprocess.run(["./stop.sh"], capture_output=True, text=True)
print("stop.sh rc", out.returncode, "took", round(time.time() - t0, 1), "s"); print(out.stdout.strip(), out.stderr.strip())
[t.join(timeout=120) for t in ts]
for i in sorted(res): print("client", i, res[i])
