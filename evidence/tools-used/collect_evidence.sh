#!/usr/bin/env bash
# collect_evidence.sh SRC_EXP_DIR DEST_NAME : copy one run's raw outputs into the recipe's evidence/ folder.
set -euo pipefail
SRC="$1"; NAME="$2"
R=/home/sfxnz/projects/ai-lab/recipes/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-DGX-SPARK/evidence
D="$R/$NAME"; mkdir -p "$D"
shopt -s nullglob
for f in "$SRC"/*.txt "$SRC"/*.out "$SRC"/*.csv "$SRC"/*.json "$SRC"/*.md; do
  case "$(basename "$f")" in inspect.json) ;; *) cp "$f" "$D/" ;; esac
done
# docker inspect without the environment block (no secrets are set, but keep it tidy)
if [[ -f "$SRC/inspect.json" ]]; then
  python3 -c "
import json,sys
d=json.load(open('$SRC/inspect.json'))
for c in d: c.get('Config',{}).pop('Env',None)
json.dump(d,open('$D/inspect.json','w'),indent=1)"
fi
if [[ -f "$SRC/server.log" ]]; then
  # progress bars are \r-separated; keep the last frame of each line
  tr '\r' '\n' <"$SRC/server.log" | grep -v -E '^\s*$|it/s\]$|s/it\]$' | gzip -9 >"$D/server.log.gz"
  grep -E "non-default args|Loading weights took|Model loading took|init engine|Setting attention block size|Padding mamba|padding layers|Initial free memory|Available KV cache|Maximum concurrency|group sizes|NvFp4 MoE backend|for NVFP4 GEMM|override for|ScaledMMLinearKernel for|resolved query dtypes|Mamba SSU|Encoder cache will|Graph capturing finished|Starting vLLM|draft model|Speculative" "$SRC/server.log" \
    | cut -c1-400 | awk '!seen[$0]++' >"$D/boot-lines.txt" || true
fi
for sub in bench results; do
  if [[ -d "$SRC/$sub" ]]; then
    mkdir -p "$D/$sub"
    for f in "$SRC/$sub"/*; do
      case "$f" in *.log) gzip -9c "$f" >"$D/$sub/$(basename "$f").gz" ;; *) cp "$f" "$D/$sub/" ;; esac
    done
  fi
done
du -sh "$D"
