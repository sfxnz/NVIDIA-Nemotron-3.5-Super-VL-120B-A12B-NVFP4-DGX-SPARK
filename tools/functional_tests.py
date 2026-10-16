#!/usr/bin/env python3
"""Functional / acceptance suite for nemotron-3.5-super-vl served by vLLM.

Stdlib only (PIL optional: enables text-in-image checks; ffmpeg optional: video).
Usage:
  python3 functional_tests.py --base http://127.0.0.1:8000 \
      --model nemotron-3.5-super-vl --concurrency 8 [--image-limit 4] \
      [--long-tokens 110000] [--skip-long] [--video] [--only C1,T1]
Exit code 0 iff every HARD test passed. Writes JSON summary to --out.
"""
import argparse, base64, concurrent.futures as cf, io, json, os, random, re
import shutil, struct, subprocess, sys, tempfile, threading, time, urllib.error
import urllib.request, zlib, http.server, functools

A = None  # parsed args
RESULTS = []
LOCK = threading.Lock()

# ----------------------------------------------------------------- HTTP utils
def call(path, body=None, timeout=900):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Content-Type": "application/json"}
    if A.api_key:
        hdr["Authorization"] = f"Bearer {A.api_key}"
    req = urllib.request.Request(A.base + path, data=data, headers=hdr,
                                 method="POST" if data is not None else "GET")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, code = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    dt = time.time() - t0
    try:
        js = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        js = None
    return code, js, raw, dt


def chat(body, timeout=900):
    body = {"model": A.model, **body}
    return call("/v1/chat/completions", body, timeout)


def stream_chat(body, timeout=900):
    """Return (http_code, chunks:list[dict], saw_done:bool, bad_lines:list, ttft)."""
    body = {"model": A.model, "stream": True, **body}
    hdr = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if A.api_key:
        hdr["Authorization"] = f"Bearer {A.api_key}"
    req = urllib.request.Request(A.base + "/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers=hdr)
    chunks, bad, done, ttft, t0 = [], [], False, None, time.time()
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        return e.code, [], False, [e.read()[:300]], None
    with r:
        for raw in r:
            line = raw.decode("utf-8").rstrip("\r\n")
            if not line or line.startswith(":"):
                continue  # blank separators / keep-alive comments are legal SSE
            if not line.startswith("data: "):
                bad.append(line[:200]); continue
            payload = line[6:]
            if payload == "[DONE]":
                done = True; continue
            if done:
                bad.append("data after [DONE]"); continue
            try:
                c = json.loads(payload)
            except json.JSONDecodeError:
                bad.append(payload[:200]); continue
            if ttft is None and c.get("choices"):
                d = c["choices"][0].get("delta", {})
                if d.get("content") or d.get("reasoning") or d.get("tool_calls"):
                    ttft = time.time() - t0
            chunks.append(c)
    return r.status, chunks, done, bad, ttft


def msg(js):
    return js["choices"][0]["message"]


LEAK_RE = re.compile(r"<think>|</think>|<tool_call>|</tool_call>|<\|im_start\|>|<\|im_end\|>|<function=|�")


# -------------------------------------------------------------- test harness
class Fail(Exception):
    pass


def expect(cond, what):
    if not cond:
        raise Fail(what)


def test(tid, hard=True, retries=0):
    def deco(fn):
        @functools.wraps(fn)
        def run():
            if A.only and tid not in A.only:
                return
            attempt, t0 = 0, time.time()
            while True:
                try:
                    detail = fn() or ""
                    ok = True
                except Fail as e:
                    ok, detail = False, str(e)
                except Exception as e:  # harness/transport error
                    ok, detail = False, f"{type(e).__name__}: {e}"
                if ok or attempt >= retries:
                    break
                attempt += 1
            skipped = ok and str(detail).startswith("skipped")
            rec = {"id": tid, "name": (fn.__doc__ or fn.__name__).split("\n")[0], "hard": hard,
                   "ok": ok, "skipped": skipped, "retries": attempt, "secs": round(time.time() - t0, 2),
                   "detail": str(detail)[:600]}
            with LOCK:
                RESULTS.append(rec)
            tag = "SKIP" if skipped else ("PASS" if ok else ("FAIL" if hard else "WARN"))
            print(f"[{tag}] {tid:4s} {rec['name']} ({rec['secs']}s) {rec['detail'][:200]}",
                  flush=True)
        TESTS.append(run)
        return run
    return deco


TESTS = []

# ----------------------------------------------------------------- fixtures
def _png_bytes_plain(w, h, draw):
    """Pure-python RGB PNG; draw(x,y)->(r,g,b)."""
    rows = b"".join(b"\x00" + bytes(c for x in range(w) for c in draw(x, y)) for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def make_image(text="NEMOTRON 42", bg=(255, 255, 255), shapes=True, size=(1024, 768)):
    """Returns (png_bytes, has_text). Red circle left, blue square right, black text top."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        im = Image.new("RGB", size, bg)
        d = ImageDraw.Draw(im)
        if shapes:
            d.ellipse((100, 300, 400, 600), fill=(220, 0, 0))
            d.rectangle((620, 300, 920, 600), fill=(0, 0, 220))
        font = None
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
            if os.path.exists(p):
                font = ImageFont.truetype(p, 110); break
        if font is None:
            font = ImageFont.load_default(size=110)
        d.text((size[0] // 2, 150), text, fill=(0, 0, 0), font=font, anchor="mm")
        buf = io.BytesIO(); im.save(buf, "PNG")
        return buf.getvalue(), True
    except Exception:
        w, h = 512, 384
        def px(x, y):
            if (x - 125) ** 2 + (y - 220) ** 2 < 75 ** 2: return (220, 0, 0)
            if 310 <= x <= 460 and 145 <= y <= 295: return (0, 0, 220)
            return bg
        return _png_bytes_plain(w, h, px), False


def data_url(png):
    return "data:image/png;base64," + base64.b64encode(png).decode()


TOOLS = [{"type": "function", "function": {
    "name": "get_weather",
    "description": "Get the current weather for a city.",
    "parameters": {"type": "object", "properties": {
        "city": {"type": "string", "description": "City name, e.g. Paris"},
        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        "days": {"type": "integer", "description": "Forecast days, 1-7"}},
        "required": ["city"], "additionalProperties": False}}}]
OFF = {"enable_thinking": False}


def check_tool_call(m, want_name="get_weather"):
    tcs = m.get("tool_calls") or []
    expect(len(tcs) >= 1, f"no tool_calls; content={str(m.get('content'))[:200]!r}")
    tc = tcs[0]
    expect(tc.get("type") == "function", f"type={tc.get('type')}")
    expect(isinstance(tc.get("id"), str) and tc["id"], "missing tool_call id")
    expect(tc["function"]["name"] == want_name, f"name={tc['function']['name']}")
    args = json.loads(tc["function"]["arguments"])
    expect(isinstance(args, dict), "arguments not a JSON object")
    expect(set(args) <= {"city", "unit", "days"}, f"unexpected keys {set(args)}")
    expect("city" in args and isinstance(args["city"], str), f"bad city {args}")
    if "unit" in args:
        expect(args["unit"] in ("celsius", "fahrenheit"), f"unit not in enum: {args['unit']}")
    if "days" in args:
        expect(isinstance(args["days"], int), f"days not coerced to int: {args['days']!r}")
    c = m.get("content") or ""
    expect(not LEAK_RE.search(c), f"markup leaked into content: {c[:200]!r}")
    return tc, args


# =================================================================== TESTS
@test("H1")
def t_health():
    """GET /health -> 200"""
    code, _, _, _ = call("/health", timeout=10)
    expect(code == 200, f"/health {code}")


@test("H2")
def t_models():
    """GET /v1/models lists served name (+max_model_len)"""
    code, js, _, _ = call("/v1/models", timeout=10)
    expect(code == 200, f"code {code}")
    ids = [d["id"] for d in js["data"]]
    expect(A.model in ids, f"{A.model} not in {ids}")
    d = next(d for d in js["data"] if d["id"] == A.model)
    A.max_model_len = d.get("max_model_len")
    if A.expect_max_model_len:
        expect(d.get("max_model_len") == A.expect_max_model_len, f"max_model_len={d.get('max_model_len')}")
    return f"max_model_len={d.get('max_model_len')}"


@test("H3", hard=False)
def t_version_metrics():
    """GET /version and /metrics"""
    c1, js, _, _ = call("/version", timeout=10)
    c2, _, raw, _ = call("/metrics", timeout=10)
    expect(c1 == 200 and c2 == 200, f"/version {c1} /metrics {c2}")
    expect(b"vllm:kv_cache_usage_perc" in raw, "kv_cache_usage_perc metric missing")
    return f"version={js.get('version') if js else None}"


@test("R1")
def t_template_render():
    """/tokenize: template suffix <think>\\n (on) vs <think></think> (off), medium_effort marker"""
    base = {"model": A.model, "messages": [{"role": "user", "content": "ping"}], "return_token_strs": True}
    c, on, _, _ = call("/tokenize", base)
    expect(c == 200, f"/tokenize {c}")
    c, off, _, _ = call("/tokenize", {**base, "chat_template_kwargs": OFF})
    c, med, _, _ = call("/tokenize", {**base, "chat_template_kwargs": {"enable_thinking": True, "medium_effort": True}})
    THINK, ENDTHINK = 12, 13  # tokenizer.json added_tokens ids
    expect(on["tokens"][-2] == THINK and on["tokens"][-1] != ENDTHINK, f"on suffix {on['token_strs'][-4:]}")
    expect(off["tokens"][-2:] == [THINK, ENDTHINK], f"off suffix {off['token_strs'][-4:]}")
    expect("efficient" in "".join(med["token_strs"][-20:]), f"medium marker missing {med['token_strs'][-20:]}")


@test("C1", retries=1)
def t_pong_off():
    """thinking off: exact 'pong', no reasoning, no markup"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "Reply with exactly the single word: pong"}],
                        "max_tokens": 32, "temperature": 0, "chat_template_kwargs": OFF})
    expect(c == 200, f"http {c}")
    m = msg(js)
    expect(js["choices"][0]["finish_reason"] == "stop", f"finish {js['choices'][0]['finish_reason']}")
    expect((m.get("content") or "").strip().strip(".!").lower() == "pong", f"content={m.get('content')!r}")
    expect(not m.get("reasoning"), f"reasoning present: {m.get('reasoning')!r}")
    expect(not LEAK_RE.search(m["content"]), "markup leak")


@test("C2", retries=1)
def t_pong_effort_none():
    """reasoning_effort='none' maps to enable_thinking=false"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "Reply with exactly the single word: pong"}],
                        "max_tokens": 32, "temperature": 0, "reasoning_effort": "none"})
    expect(c == 200, f"http {c}")
    m = msg(js)
    expect((m.get("content") or "").strip().strip(".!").lower() == "pong", f"content={m.get('content')!r}")
    expect(not m.get("reasoning"), "reasoning present")


def _math(kw=None, extra=None):
    body = {"messages": [{"role": "user", "content": "What is 17 * 23? Give the final answer as just the number."}],
            "max_tokens": 8192, "temperature": 0.6, "top_p": 0.95, "seed": 7}
    if kw is not None:
        body["chat_template_kwargs"] = kw
    body.update(extra or {})
    return chat(body)


@test("C3", retries=1)
def t_thinking_on():
    """thinking on (template default): reasoning populated, content correct"""
    c, js, _, _ = _math()
    expect(c == 200, f"http {c}")
    ch, m = js["choices"][0], msg(js)
    expect(ch["finish_reason"] == "stop", f"finish {ch['finish_reason']}")
    expect(isinstance(m.get("reasoning"), str) and len(m["reasoning"]) >= 20, "reasoning empty")
    expect("391" in (m.get("content") or ""), f"content={m.get('content')!r}")
    expect(not LEAK_RE.search(m["content"]) and "</think>" not in m["reasoning"], "think markup leaked")
    rt = (js.get("usage") or {}).get("completion_tokens_details", {}) or {}
    expect(rt.get("reasoning_tokens", 0) > 0, f"usage.completion_tokens_details={rt}")
    A.high_rt = rt.get("reasoning_tokens")
    return f"reasoning_tokens={A.high_rt}"


@test("C4", retries=1)
def t_medium_effort():
    """medium_effort: still correct + reasoning present (token count logged)"""
    c, js, _, _ = _math({"enable_thinking": True, "medium_effort": True})
    expect(c == 200, f"http {c}")
    m = msg(js)
    expect("391" in (m.get("content") or ""), f"content={m.get('content')!r}")
    expect(m.get("reasoning"), "reasoning empty")
    rt = js["usage"].get("completion_tokens_details", {}).get("reasoning_tokens")
    return f"reasoning_tokens medium={rt} high={getattr(A, 'high_rt', None)}"


@test("C5")
def t_force_nonempty():
    """force_nonempty_content: truncated thinking is promoted to content (nemotron_v3)"""
    prompt = [{"role": "user", "content": "Prove there are infinitely many primes, very carefully."}]
    c, js, _, _ = chat({"messages": prompt, "max_tokens": 48, "temperature": 0,
                        "chat_template_kwargs": {"enable_thinking": True}})
    expect(c == 200 and js["choices"][0]["finish_reason"] == "length", "baseline not truncated")
    expect(not msg(js).get("content") and msg(js).get("reasoning"), "baseline: expected reasoning only")
    c, js, _, _ = chat({"messages": prompt, "max_tokens": 48, "temperature": 0,
                        "chat_template_kwargs": {"enable_thinking": True, "force_nonempty_content": True}})
    m = msg(js)
    expect(c == 200 and (m.get("content") or "").strip(), f"content empty with force flag: {m}")
    expect(not m.get("reasoning"), "reasoning should have been swapped into content")


@test("C6")
def t_include_reasoning_false():
    """include_reasoning=false hides reasoning, keeps content"""
    c, js, _, _ = _math(extra={"include_reasoning": False})
    m = msg(js)
    expect(c == 200 and "391" in (m.get("content") or ""), f"content={m.get('content')!r}")
    expect(not m.get("reasoning"), "reasoning returned despite include_reasoning=false")


@test("C7", retries=1)
def t_thinking_budget():
    """thinking_token_budget caps reasoning (the proof prompt reasons for hundreds of tokens unbounded); an answer follows"""
    q = [{"role": "user", "content": "Prove that the square root of 2 is irrational, then give the final verdict in one word."}]
    c, js, _, _ = chat({"messages": q, "max_tokens": 4096, "temperature": 0, "thinking_token_budget": 32})
    expect(c == 200, f"http {c} {str(js)[:200]}")
    rt = js["usage"].get("completion_tokens_details", {}).get("reasoning_tokens", 0)
    expect(rt <= 32, f"reasoning_tokens={rt} > budget 32")
    expect((msg(js).get("content") or "").strip(), "no answer after the budget")
    return f"reasoning_tokens={rt} with budget 32"


@test("T1", retries=1)
def t_tool_auto():
    """tool_choice=auto: finish tool_calls, valid JSON args, reasoning present"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "What's the weather in Paris right now? Use the tool."}],
                        "tools": TOOLS, "tool_choice": "auto", "max_tokens": 4096, "temperature": 0.6, "top_p": 0.95})
    expect(c == 200, f"http {c}")
    expect(js["choices"][0]["finish_reason"] == "tool_calls", f"finish {js['choices'][0]['finish_reason']}")
    m = msg(js)
    tc, args = check_tool_call(m)
    expect("paris" in args["city"].lower(), f"city={args['city']}")
    A.tool_turn = m  # reused by T4
    return f"args={args}"


@test("T1b", retries=1)
def t_tool_auto_off():
    """tool_choice=auto with thinking off"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "Weather in Tokyo for the next 3 days, please."}],
                        "tools": TOOLS, "max_tokens": 512, "temperature": 0, "chat_template_kwargs": OFF})
    expect(c == 200 and js["choices"][0]["finish_reason"] == "tool_calls", f"http {c} {str(js)[:300]}")
    tc, args = check_tool_call(msg(js))
    expect("tokyo" in args["city"].lower(), f"city={args}")
    return f"args={args}"


@test("T1c", retries=1)
def t_tool_auto_force_nonempty():
    """cookbook pattern: tools + thinking on + force_nonempty_content still yields parsed tool_calls"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "My bill is $50. Get the weather in Oslo for 2 days."}],
                        "tools": TOOLS, "max_tokens": 4096, "temperature": 1.0, "top_p": 0.95,
                        "chat_template_kwargs": {"enable_thinking": True, "force_nonempty_content": True}})
    expect(c == 200 and js["choices"][0]["finish_reason"] == "tool_calls", f"http {c} {str(js)[:300]}")
    tc, args = check_tool_call(msg(js))
    expect("oslo" in args["city"].lower(), f"args={args}")


@test("T2", retries=1)
def t_tool_required():
    """tool_choice=required forces a call even for chit-chat"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "Hi! How are you today?"}],
                        "tools": TOOLS, "tool_choice": "required", "max_tokens": 4096,
                        "temperature": 0.6, "top_p": 0.95})
    expect(c == 200, f"http {c} {str(js)[:300]}")
    expect(js["choices"][0]["finish_reason"] == "tool_calls", f"finish {js['choices'][0]['finish_reason']}")
    check_tool_call(msg(js))


@test("T3", retries=1)
def t_tool_named():
    """named tool_choice: correct function, finish_reason 'stop' (OpenAI semantics)"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "Tell me a joke about Berlin."}],
                        "tools": TOOLS, "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
                        "max_tokens": 4096, "temperature": 0.6, "top_p": 0.95})
    expect(c == 200, f"http {c} {str(js)[:300]}")
    expect(js["choices"][0]["finish_reason"] == "stop", f"finish {js['choices'][0]['finish_reason']}")
    check_tool_call(msg(js))


@test("T4", retries=1)
def t_tool_followup():
    """tool result turn: answer uses tool output, no further call"""
    m = getattr(A, "tool_turn", None)
    expect(m is not None, "T1 did not produce a tool turn")
    tc = m["tool_calls"][0]
    asst = {"role": "assistant", "content": m.get("content"), "tool_calls": m["tool_calls"]}
    if m.get("reasoning"):
        asst["reasoning"] = m["reasoning"]  # interleaved thinking round-trip
    msgs = [{"role": "user", "content": "What's the weather in Paris right now? Use the tool."}, asst,
            {"role": "tool", "tool_call_id": tc["id"],
             "content": json.dumps({"city": "Paris", "temp_c": 18, "condition": "sunny"})}]
    c, js, _, _ = chat({"messages": msgs, "tools": TOOLS, "max_tokens": 4096, "temperature": 0.6, "top_p": 0.95})
    expect(c == 200, f"http {c} {str(js)[:300]}")
    out = msg(js)
    expect(js["choices"][0]["finish_reason"] == "stop" and not out.get("tool_calls"), "unexpected extra tool call")
    t = (out.get("content") or "").lower()
    expect("18" in t and "sunny" in t, f"content={t[:300]!r}")


@test("T5", hard=False)
def t_parallel_tools():
    """parallel tool calls (2 cities) and parallel_tool_calls=false -> exactly 1"""
    q = [{"role": "user", "content": "What's the weather in Paris and in Tokyo? Call the tool for each city."}]
    c, js, _, _ = chat({"messages": q, "tools": TOOLS, "max_tokens": 4096, "chat_template_kwargs": OFF, "temperature": 0})
    n = len(msg(js).get("tool_calls") or [])
    c2, js2, _, _ = chat({"messages": q, "tools": TOOLS, "max_tokens": 4096, "chat_template_kwargs": OFF,
                          "temperature": 0, "parallel_tool_calls": False})
    n2 = len(msg(js2).get("tool_calls") or [])
    expect(n == 2 and n2 == 1, f"parallel={n} single={n2}")


@test("T6", retries=1)
def t_tool_stream():
    """streaming tool call: name in first tool delta, args concat -> valid JSON"""
    code, chunks, done, bad, _ = stream_chat({"messages": [{"role": "user", "content": "Weather in Rome? Use the tool."}],
                                              "tools": TOOLS, "max_tokens": 4096, "temperature": 0.6, "top_p": 0.95})
    expect(code == 200 and done and not bad, f"http {code} done={done} bad={bad[:2]}")
    name, args, fins = None, "", []
    for ch in chunks:
        for c in ch.get("choices", []):
            for tc in c.get("delta", {}).get("tool_calls") or []:
                if tc.get("function", {}).get("name"):
                    name = name or tc["function"]["name"]
                args += tc.get("function", {}).get("arguments") or ""
            if c.get("finish_reason"):
                fins.append(c["finish_reason"])
    expect(name == "get_weather", f"name={name}")
    a = json.loads(args)
    expect("rome" in a.get("city", "").lower(), f"args={args}")
    expect(fins == ["tool_calls"], f"finish_reasons={fins}")


def _stream_text(body):
    code, chunks, done, bad, ttft = stream_chat(body)
    expect(code == 200, f"http {code} {bad[:1]}")
    expect(done, "no data: [DONE]")
    expect(not bad, f"malformed SSE lines: {bad[:3]}")
    ids = {c.get("id") for c in chunks}
    expect(len(ids) == 1, f"chunk ids differ: {ids}")
    expect(all(c.get("object") == "chat.completion.chunk" for c in chunks), "bad object type")
    reasoning = "".join(c["choices"][0]["delta"].get("reasoning") or "" for c in chunks if c.get("choices"))
    content = "".join(c["choices"][0]["delta"].get("content") or "" for c in chunks if c.get("choices"))
    fins = [c["choices"][0]["finish_reason"] for c in chunks if c.get("choices") and c["choices"][0].get("finish_reason")]
    expect(len(fins) == 1, f"finish_reason chunks={fins}")
    usage = [c["usage"] for c in chunks if c.get("usage") and not c.get("choices")]
    expect(usage and usage[-1]["completion_tokens"] > 0, "missing include_usage final chunk")
    expect(not LEAK_RE.search(content) and "</think>" not in reasoning, "markup leaked in stream")
    return reasoning, content, fins[0], ttft


@test("S1", retries=1)
def t_stream_reasoning():
    """SSE well-formed; reasoning deltas then content deltas; usage chunk"""
    r, c, f, ttft = _stream_text({"messages": [{"role": "user", "content": "Name the three primary colors of light. One short line."}],
                                  "max_tokens": 4096, "temperature": 0.6, "top_p": 0.95,
                                  "stream_options": {"include_usage": True}})
    expect(r.strip() and c.strip(), f"reasoning={len(r)} content={len(c)}")
    expect(f == "stop", f"finish={f}")
    low = c.lower()
    expect("red" in low and "green" in low and "blue" in low, f"content={c[:200]!r}")
    return f"ttft={ttft:.2f}s" if ttft else ""


@test("S2", retries=1)
def t_stream_off():
    """SSE thinking off: content only, no reasoning deltas"""
    r, c, f, _ = _stream_text({"messages": [{"role": "user", "content": "Reply with exactly the single word: pong"}],
                               "max_tokens": 32, "temperature": 0, "chat_template_kwargs": OFF,
                               "stream_options": {"include_usage": True}})
    expect(not r, f"unexpected reasoning {r[:100]!r}")
    expect(c.strip().strip(".!").lower() == "pong", f"content={c!r}")


SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}, "birth_year": {"type": "integer"},
          "city": {"type": "string"}}, "required": ["name", "birth_year", "city"], "additionalProperties": False}
RF = {"type": "json_schema", "json_schema": {"name": "person", "strict": True, "schema": SCHEMA}}
JQ = [{"role": "user", "content": "Extract the person from: 'Ada Lovelace was born in 1815 in London.' Return JSON."}]


def _check_person(js):
    m = msg(js)
    o = json.loads((m.get("content") or "").strip())
    expect(set(o) == {"name", "birth_year", "city"}, f"keys={set(o)}")
    expect(isinstance(o["birth_year"], int) and o["birth_year"] == 1815, f"year={o['birth_year']!r}")
    expect("ada" in o["name"].lower() and "london" in o["city"].lower(), f"obj={o}")
    return m


@test("J1")
def t_json_off():
    """response_format json_schema, thinking off (grammar from token 0)"""
    c, js, _, _ = chat({"messages": JQ, "response_format": RF, "max_tokens": 512, "temperature": 0,
                        "chat_template_kwargs": OFF})
    expect(c == 200, f"http {c} {str(js)[:300]}")
    _check_person(js)


@test("J2", retries=1)
def t_json_on():
    """response_format json_schema, thinking on (grammar applies after </think>)"""
    c, js, _, _ = chat({"messages": JQ, "response_format": RF, "max_tokens": 8192, "temperature": 0.6, "top_p": 0.95})
    expect(c == 200, f"http {c} {str(js)[:300]}")
    m = _check_person(js)
    expect(m.get("reasoning"), "no reasoning with thinking on")


@test("J3")
def t_json_object_and_choice():
    """response_format json_object + structured_outputs.choice"""
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "Give a JSON object with keys a=1 and b=2."}],
                        "response_format": {"type": "json_object"}, "max_tokens": 256, "temperature": 0,
                        "chat_template_kwargs": OFF})
    expect(c == 200 and isinstance(json.loads(msg(js)["content"]), dict), f"{str(js)[:300]}")
    c, js, _, _ = chat({"messages": [{"role": "user", "content": "Sentiment of 'I love this!'?"}],
                        "structured_outputs": {"choice": ["positive", "negative", "neutral"]},
                        "max_tokens": 16, "temperature": 0, "chat_template_kwargs": OFF})
    expect(c == 200 and msg(js)["content"] == "positive", f"{str(js)[:300]}")


IMG_Q = ("What text is written in this image, and what shapes and colors do you see? "
         "Answer in one or two sentences.")


def _vision(url, has_text):
    if not A.image_limit:
        return "skipped (vision off: --image-limit 0)"
    c, js, _, _ = chat({"messages": [{"role": "user", "content": [
        {"type": "text", "text": IMG_Q}, {"type": "image_url", "image_url": {"url": url}}]}],
        "max_tokens": 512, "temperature": 0, "chat_template_kwargs": OFF})
    expect(c == 200, f"http {c} {str(js)[:300]}")
    t = (msg(js).get("content") or "").lower()
    if has_text:
        expect("nemotron" in t and "42" in t, f"text not read: {t[:300]!r}")
    else:
        t += " (PIL missing: text reading not checked)"
    expect("red" in t and "blue" in t, f"colors: {t[:300]!r}")
    expect("circle" in t and ("square" in t or "rectangle" in t), f"shapes: {t[:300]!r}")
    expect(js["usage"]["prompt_tokens"] >= 256, f"prompt_tokens={js['usage']['prompt_tokens']} (image tokens missing?)")
    return f"prompt_tokens={js['usage']['prompt_tokens']}" + ("" if has_text else " (PIL missing: text not checked)")


@test("V1", retries=1)
def t_image_dataurl():
    """image via base64 data URL"""
    png, has_text = make_image()
    return _vision(data_url(png), has_text)


@test("V2", retries=1)
def t_image_http():
    """image via http URL (local http.server; needs container --network host)"""
    png, has_text = make_image()
    d = tempfile.mkdtemp()
    open(os.path.join(d, "probe.png"), "wb").write(png)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = functools.partial(Quiet, directory=d)
    srv = http.server.ThreadingHTTPServer((A.http_bind, 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        host = A.http_host or A.http_bind
        return _vision(f"http://{host}:{srv.server_address[1]}/probe.png", has_text)
    finally:
        srv.shutdown()


@test("V3", retries=1)
def t_multi_image():
    """two images in one prompt, order preserved"""
    if not A.image_limit:
        return "skipped (vision off: --image-limit 0)"
    a, ok1 = make_image("APPLE", shapes=False)
    b, ok2 = make_image("BANANA", bg=(255, 240, 120), shapes=False)
    if not (ok1 and ok2):
        return "skipped (PIL missing)"
    c, js, _, _ = chat({"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url(a)}},
        {"type": "image_url", "image_url": {"url": data_url(b)}},
        {"type": "text", "text": "What word is written in each image? Answer exactly as 'Image 1: X, Image 2: Y'."}]}],
        "max_tokens": 64, "temperature": 0, "chat_template_kwargs": OFF})
    expect(c == 200, f"http {c} {str(js)[:300]}")
    t = msg(js)["content"].upper()
    expect("APPLE" in t and "BANANA" in t and t.index("APPLE") < t.index("BANANA"), f"content={t!r}")


@test("V4")
def t_image_limit():
    """exceeding --limit-mm-per-prompt image count -> HTTP 400"""
    if not A.image_limit:
        return "skipped (--image-limit not given)"
    png, _ = make_image(shapes=False)
    parts = [{"type": "image_url", "image_url": {"url": data_url(png)}}] * (A.image_limit + 1)
    c, js, raw, _ = chat({"messages": [{"role": "user", "content": parts + [{"type": "text", "text": "hi"}]}],
                          "max_tokens": 8, "chat_template_kwargs": OFF})
    expect(c == 400 and b"may be provided in one prompt" in raw, f"http {c} {raw[:300]!r}")


@test("V5", hard=False)
def t_video():
    """video_url data URL (8s: red then blue) -- only if --video"""
    if not A.video:
        return "skipped (--video not given)"
    expect(shutil.which("ffmpeg"), "ffmpeg missing")
    out = os.path.join(tempfile.mkdtemp(), "v.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=640x360:d=4:r=10",
                    "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=4:r=10", "-filter_complex",
                    "[0][1]concat=n=2:v=1[v]", "-map", "[v]", "-pix_fmt", "yuv420p", "-c:v", "libx264", out], check=True)
    url = "data:video/mp4;base64," + base64.b64encode(open(out, "rb").read()).decode()
    c, js, _, _ = chat({"messages": [{"role": "user", "content": [
        {"type": "text", "text": "What solid colors does the video show, in order? Answer briefly."},
        {"type": "video_url", "video_url": {"url": url}}]}], "max_tokens": 128, "temperature": 0,
        "chat_template_kwargs": OFF}, timeout=1200)
    expect(c == 200, f"http {c} {str(js)[:300]}")
    t = msg(js)["content"].lower()
    expect("red" in t and "blue" in t and t.index("red") < t.index("blue"), f"content={t!r}")
    return f"prompt_tokens={js['usage']['prompt_tokens']}"


WORDS = ("amber basil cedar delta ember fable garnet harbor indigo juniper kettle lantern meadow nickel "
         "orchard pepper quarry raven saddle timber umber velvet willow yonder zephyr granite tundra "
         "copper marble thistle brook falcon maple onyx prairie quartz river sable thicket").split()


def haystack(n_chars, seed=1234):
    rnd, out, n = random.Random(seed), [], 0
    while n < n_chars:
        s = (f"The {rnd.choice(WORDS)} {rnd.choice(WORDS)} near the {rnd.choice(WORDS)} {rnd.choice(WORDS)} "
             f"was recorded as item {rnd.randint(1000, 99999)} in ledger {rnd.choice(WORDS)}. ")
        out.append(s); n += len(s)
    return out


@test("L1")
def t_long_needle():
    """long-context needle retrieval (3 needles at 10/50/90% depth)"""
    if A.skip_long:
        return "skipped"
    target = A.long_tokens
    if A.max_model_len:
        target = min(target, A.max_model_len - 2048)
    c, tk, _, _ = call("/tokenize", {"model": A.model, "prompt": " ".join(haystack(40000))})
    cpt = 40000 / max(tk["count"], 1)  # chars per token for this filler
    sents = haystack(int(target * cpt * 0.97))
    codes = {k: f"{k.lower()}-{random.Random(k).randint(1000, 9999)}-{random.Random(k + 'x').choice(WORDS)}"
             for k in ("ALPHA", "BRAVO", "CHARLIE")}
    for depth, k in zip((0.1, 0.5, 0.9), codes):
        sents.insert(int(len(sents) * depth), f"The secret passphrase for vault {k} is {codes[k]}. ")
    q = ("".join(sents) + "\n\nWhat are the secret passphrases for vaults ALPHA, BRAVO and CHARLIE? "
         "Answer exactly as: ALPHA=<p>, BRAVO=<p>, CHARLIE=<p>")
    code, chunks, done, bad, ttft = stream_chat({"messages": [{"role": "user", "content": q}], "max_tokens": 128,
                                                 "temperature": 0, "chat_template_kwargs": OFF,
                                                 "stream_options": {"include_usage": True}}, timeout=3600)
    expect(code == 200 and done, f"http {code} {bad[:1]}")
    text = "".join(c["choices"][0]["delta"].get("content") or "" for c in chunks if c.get("choices"))
    usage = [c["usage"] for c in chunks if c.get("usage")][-1]
    expect(usage["prompt_tokens"] >= int(target * 0.9), f"prompt_tokens={usage['prompt_tokens']} < target")
    miss = [k for k, v in codes.items() if v not in text]
    expect(not miss, f"missed {miss}: {text[:300]!r}")
    ttft = ttft or float("nan")
    return f"prompt_tokens={usage['prompt_tokens']} ttft={ttft:.1f}s prefill~{usage['prompt_tokens'] / ttft:.0f} tok/s"


def _one_conc(i, mode):
    rnd = random.Random(1000 + i)
    a, b = rnd.randint(1000, 9999), rnd.randint(1000, 9999)
    code = f"REQ-{i:04d}-{rnd.randint(0, 0xFFFF):04X}"
    content = f"First repeat this code exactly: {code}. Then on a new line give the sum {a} + {b} as digits only."
    body = {"messages": [{"role": "user", "content": content}], "temperature": 0,
            "max_tokens": 64, "chat_template_kwargs": OFF}
    if mode == "think":
        body.update(max_tokens=4096, chat_template_kwargs={"enable_thinking": True})
    if mode == "image":
        body["max_tokens"] = 1024  # with an image the model sometimes reasons aloud before answering, even thinking off
        png, _ = make_image(shapes=True)
        body["messages"][0]["content"] = [{"type": "image_url", "image_url": {"url": data_url(png)}},
                                          {"type": "text", "text": content}]
    if mode == "stream":
        code_, chunks, done, bad, _ = stream_chat(body)
        ok = code_ == 200 and done and not bad
        text = "".join(c["choices"][0]["delta"].get("content") or "" for c in chunks if c.get("choices"))
        fin = next((c["choices"][0]["finish_reason"] for c in chunks if c.get("choices") and c["choices"][0].get("finish_reason")), None)
    else:
        code_, js, _, _ = chat(body)
        ok = code_ == 200
        text = (msg(js).get("content") or "") if ok else ""
        fin = js["choices"][0]["finish_reason"] if ok else None
    return {"i": i, "mode": mode, "http_ok": ok, "fin": fin, "code": code, "sum": str(a + b), "text": text}


def _conc_eval(res, all_codes):
    errs = []
    for r in res:
        others = [c for c in all_codes if c != r["code"] and c in r["text"]]
        if not r["http_ok"]: errs.append(f"{r['i']}:{r['mode']}:http")
        elif r["fin"] != "stop": errs.append(f"{r['i']}:{r['mode']}:finish={r['fin']}")
        elif r["code"] not in r["text"]: errs.append(f"{r['i']}:{r['mode']}:own-code-missing")
        elif others: errs.append(f"{r['i']}:{r['mode']}:CROSSTALK{others}")
        elif r["sum"] not in r["text"].replace(",", ""): errs.append(f"{r['i']}:{r['mode']}:wrong-sum")
        elif LEAK_RE.search(r["text"]): errs.append(f"{r['i']}:{r['mode']}:markup-leak")
    return errs


@test("P1")
def t_concurrency():
    """N parallel requests (N=--concurrency): all 200, own code echoed, exact sums, no crosstalk"""
    n = A.concurrency
    with cf.ThreadPoolExecutor(n) as ex:
        res = list(ex.map(lambda i: _one_conc(i, "plain"), range(n)))
    errs = _conc_eval(res, [r["code"] for r in res])
    expect(not errs, f"{len(errs)}/{n} bad: {errs[:8]}")
    return f"{n}/{n} ok"


@test("P2")
def t_concurrency_mixed():
    """2N mixed (plain/stream/think/image) oversubscribed: all correct, server healthy after"""
    n = 2 * A.concurrency
    kinds = ("plain", "stream", "think", "image") if A.image_limit else ("plain", "stream", "think")
    modes = [kinds[i % len(kinds)] for i in range(n)]
    pre = _metric("vllm:num_preemptions_total")
    with cf.ThreadPoolExecutor(n) as ex:
        res = list(ex.map(lambda im: _one_conc(1000 + im[0], im[1]), enumerate(modes)))
    errs = _conc_eval(res, [r["code"] for r in res])
    hc, _, _, _ = call("/health", timeout=10)
    expect(hc == 200, "server unhealthy after burst")
    expect(not errs, f"{len(errs)}/{n} bad: {errs[:8]}")
    post = _metric("vllm:num_preemptions_total")
    return f"{n}/{n} ok; preemptions delta={None if pre is None or post is None else post - pre}"


def _metric(name):
    try:
        _, _, raw, _ = call("/metrics", timeout=10)
        tot = 0.0; seen = False
        for line in raw.decode().splitlines():
            if line.startswith(name):
                tot += float(line.rsplit(" ", 1)[1]); seen = True
        return tot if seen else None
    except Exception:
        return None


@test("PC1", hard=False)
def t_prefix_cache_multiturn():
    """multi-turn chat over a ~20K-token document: prefix-cache hit tokens and latency per turn (logged)"""
    rnd = random.Random(int(time.time()))
    doc = " ".join(f"{rnd.choice(WORDS)} {rnd.randint(0, 99999)}." for _ in range(2500))
    msgs = [{"role": "user", "content": "Here is a log:\n" + doc + "\n\nWhat is the first word of the log?"}]
    out = []
    for turn in range(3):
        h0 = _metric("vllm:prefix_cache_hits_total") or 0.0
        t0 = time.time()
        c, js, _, _ = chat({"messages": msgs, "max_tokens": 48, "temperature": 0, "chat_template_kwargs": OFF})
        dt = time.time() - t0
        expect(c == 200, f"http {c}")
        hits = (_metric("vllm:prefix_cache_hits_total") or 0.0) - h0
        out.append(f"turn{turn}: prompt={js['usage']['prompt_tokens']} hit={hits:.0f} e2e={dt:.1f}s")
        msgs += [{"role": "assistant", "content": msg(js)["content"]},
                 {"role": "user", "content": f"Now tell me word number {turn + 2} of the log."}]
    expect(any(" hit=0 " not in o for o in out[1:]), "no prefix-cache hits on later turns (expected with "
           "PROFILE=throughput, which turns prefix caching off): " + "; ".join(out))
    return "; ".join(out)

@test("D1", hard=False)
def t_determinism():
    """temperature 0 x5 sequential: logged only. Not bit-exact by design: --enable-mamba-cache-stochastic-rounding
    draws a fresh seed on every Mamba state update, so greedy replies can part at near-tied tokens."""
    outs = []
    for _ in range(5):
        c, js, _, _ = chat({"messages": [{"role": "user", "content": "Write a four-line poem about the ocean."}],
                            "max_tokens": 128, "temperature": 0, "chat_template_kwargs": OFF})
        expect(c == 200, f"http {c}")
        outs.append(msg(js)["content"])
    pref = min(len(os.path.commonprefix([outs[0], o])) for o in outs)
    identical = sum(o == outs[0] for o in outs)
    expect(pref >= 32, f"outputs diverge early (common prefix {pref} chars)")
    return f"identical={identical}/5 common_prefix={pref} chars"


@test("E1")
def t_errors():
    """bad model -> 404; tool_choice without tools -> 400; server stays healthy"""
    c, _, _, _ = call("/v1/chat/completions", {"model": "nope", "messages": [{"role": "user", "content": "x"}]})
    expect(c == 404, f"unknown model -> {c}")
    c, _, _, _ = chat({"messages": [{"role": "user", "content": "x"}], "tool_choice": "required"})
    expect(c == 400, f"tool_choice without tools -> {c}")
    c, _, _, _ = call("/health", timeout=10)
    expect(c == 200, "unhealthy after errors")


@test("M1", hard=False)
def t_spec_metrics():
    """speculative decoding active: mean acceptance length from /metrics"""
    d, a = _metric("vllm:spec_decode_num_drafts_total"), _metric("vllm:spec_decode_num_accepted_tokens_total")
    expect(d and d > 0, "no spec-decode drafts recorded")
    return f"mean_acceptance_length={1 + a / d:.2f}"


def main():
    global A
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--model", default="nemotron-3.5-super-vl")
    p.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY", ""))
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--image-limit", type=int, default=0)
    p.add_argument("--expect-max-model-len", type=int, default=0)
    p.add_argument("--long-tokens", type=int, default=110000)
    p.add_argument("--skip-long", action="store_true")
    p.add_argument("--video", action="store_true")
    p.add_argument("--http-bind", default="127.0.0.1")
    p.add_argument("--http-host", default="")
    p.add_argument("--only", default="")
    p.add_argument("--out", default="functional_results.json")
    A = p.parse_args()
    A.only = set(filter(None, A.only.split(",")))
    A.max_model_len = None
    for t in TESTS:
        t()
    hard_fail = [r for r in RESULTS if r["hard"] and not r["ok"]]
    ran = [r for r in RESULTS if not r["skipped"]]
    summary = {"passed": sum(r["ok"] for r in ran), "executed": len(ran),
               "skipped": [r["id"] for r in RESULTS if r["skipped"]],
               "soft_warnings": [r["id"] for r in ran if not r["hard"] and not r["ok"]],
               "hard_failures": [r["id"] for r in hard_fail], "results": RESULTS}
    json.dump(summary, open(A.out, "w"), indent=2)
    print(f"\n{summary['passed']}/{summary['executed']} executed checks passed; skipped: {summary['skipped']}; "
          f"soft warnings: {summary['soft_warnings']}; hard failures: {summary['hard_failures']}")
    sys.exit(1 if hard_fail else 0)


if __name__ == "__main__":
    main()
