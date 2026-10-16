"""variant.py OUT.sh LABEL [--fp8 BACKEND|none] [--mtp K] : run.sh's default docker command with one change."""
import json, shlex, subprocess, sys, os
out, label = sys.argv[1], sys.argv[2]
opts = dict(zip(sys.argv[3::2], sys.argv[4::2]))
env = dict(os.environ, VALIDATE_ONLY="1")
cmd = shlex.split(subprocess.run(["./run.sh"], env=env, capture_output=True, text=True, check=True).stdout.splitlines()[-1])
res, i = [], 0
while i < len(cmd):
    a = cmd[i]
    if a == "--kernel-config" and "--fp8" in opts:
        i += 2
        if opts["--fp8"] != "none":
            res += [a, json.dumps({"linear_backend_per_quant": {"fp8_w8a8": opts["--fp8"]}})]
        continue
    if "--mtp" in opts and a == "--speculative-config":
        res += [a, json.dumps({"method": "mtp", "num_speculative_tokens": int(opts["--mtp"])})]; i += 2; continue
    if "--mtp" in opts and a == "--block-size":
        res += [a, "64"]; i += 2; continue
    if "--mtp" in opts and a == "--max-num-batched-tokens":
        res += [a, "4416"]; i += 2; continue
    if a == "ai-lab.profile=default":
        res.append(f"ai-lab.profile={label}"); i += 1; continue
    res.append(a); i += 1
open(out, "w").write("#!/usr/bin/env bash\n# run.sh default with: " + " ".join(sys.argv[3:]) + "\nset -euo pipefail\n" + " ".join(shlex.quote(x) for x in res) + "\n")
