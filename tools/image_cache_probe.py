#!/usr/bin/env python3
"""Send N distinct images and record how host memory moves (vLLM keeps image embeddings cached until its encoder
cache budget, max-model-len tokens of 8 KiB, is full). Needs Pillow. Prints one CSV line per 25 images and a summary.

usage: image_cache_probe.py [--base URL] [--model NAME] [--images 300] [--concurrency 8]
"""
import argparse, base64, concurrent.futures as cf, io, json, os, random, time, urllib.request

from PIL import Image, ImageDraw


def avail_mib():
    with open("/proc/meminfo") as f:
        return next(int(l.split()[1]) // 1024 for l in f if l.startswith("MemAvailable:"))


def image(i):
    rnd = random.Random(i)
    im = Image.new("RGB", (1024, 768), tuple(rnd.randint(0, 255) for _ in range(3)))
    d = ImageDraw.Draw(im)
    for _ in range(40):  # distinct content, so every image has its own cache entry
        x, y = rnd.randint(0, 1000), rnd.randint(0, 740)
        d.rectangle((x, y, x + rnd.randint(10, 200), y + rnd.randint(10, 200)), fill=tuple(rnd.randint(0, 255) for _ in range(3)))
    d.text((20, 20), f"image {i}", fill=(0, 0, 0))
    b = io.BytesIO(); im.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def ask(a, i):
    body = {"model": a.model, "max_tokens": 8, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image(i)}},
                                                      {"type": "text", "text": "One word: main color?"}]}]}
    req = urllib.request.Request(a.base + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))["usage"]["prompt_tokens"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--model", default="nemotron-3.5-super-vl")
    p.add_argument("--images", type=int, default=300)
    p.add_argument("--concurrency", type=int, default=8)
    a = p.parse_args()
    start = avail_mib(); lowest = start; tokens = 0; t0 = time.time()
    print("images,prompt_tokens_total,avail_mib", flush=True)
    with cf.ThreadPoolExecutor(a.concurrency) as ex:
        for n, pt in enumerate(ex.map(lambda i: ask(a, i), range(a.images)), 1):
            tokens += pt
            lowest = min(lowest, avail_mib())
            if n % 25 == 0:
                print(f"{n},{tokens},{avail_mib()}", flush=True)
    time.sleep(5)
    print(json.dumps({"images": a.images, "image_prompt_tokens": tokens, "avail_start_mib": start,
                      "avail_lowest_mib": lowest, "avail_end_mib": avail_mib(), "drop_mib": start - avail_mib(),
                      "secs": round(time.time() - t0, 1)}), flush=True)


if __name__ == "__main__":
    main()
