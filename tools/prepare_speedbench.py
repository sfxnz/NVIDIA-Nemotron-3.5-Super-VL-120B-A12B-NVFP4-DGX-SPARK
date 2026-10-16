"""Build the decode prompt set from SPEED-Bench (nvidia/SPEED-Bench, 'qualitative' split).

Rows whose text must be fetched from third-party sources are skipped; 386 of 880 prompts ship inline. vLLM's ShareGPT
loader drops prompts over 1024 tokens, so they are dropped here too and the count printed is what the bench really uses.
The output is the ShareGPT layout that `vllm bench serve --dataset-name sharegpt` reads without pandas.
usage: prepare_speedbench.py OUT.json TOKENIZER_DIR  (inside the bench client container; needs pandas and pyarrow)
"""
import json
import sys

import pandas as pd
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

REV = "454f88454792dfa3ccfd7ef15fff248efde44cd1"
PLACEHOLDER = "FULL BENCHMARK DATA SHOULD BE FETCHED"

path = hf_hub_download("nvidia/SPEED-Bench", "qualitative/test-00000-of-00001.parquet", repo_type="dataset",
                       revision=REV)
df = pd.read_parquet(path)
tok = AutoTokenizer.from_pretrained(sys.argv[2])
rows, too_long = [], 0
for _, r in df.iterrows():
    turns = list(r["turns"])
    if not turns or PLACEHOLDER in str(turns[0]):
        continue
    if len(tok(str(turns[0])).input_ids) > 1024:  # vLLM's is_valid_sequence limit for ShareGPT prompts
        too_long += 1
        continue
    # The second turn is only used by vLLM to size the output when --sharegpt-output-len is not given; bench.sh
    # always sets it, so its content does not matter.
    rows.append({"id": r["question_id"], "category": r["category"],
                 "conversations": [{"from": "human", "value": str(turns[0])}, {"from": "gpt", "value": "ok"}]})
with open(sys.argv[1], "w") as f:
    json.dump(rows, f)
print(f"{len(rows)} SPEED-Bench prompts of at most 1024 tokens -> {sys.argv[1]} ({too_long} longer ones dropped)")
