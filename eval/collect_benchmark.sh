#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH=${MODEL_PATH:-sshleifer/tiny-gpt2}
TMP_JSON=$(mktemp)

python -m earCrawler.eval.run_eval \
  --model-path "$MODEL_PATH" \
  --data-file eval/pilot_items.jsonl \
  --output-file "$TMP_JSON"

python - "$TMP_JSON" <<'PY' > benchmark.md
import json, sys
with open(sys.argv[1]) as f:
    m = json.load(f)
print("| Accuracy | Avg Latency (s) | Peak GPU Memory (bytes) |")
print("|---------:|----------------:|-----------------------:|")
print(f"| {m['accuracy']:.4f} | {m['avg_latency']:.4f} | {int(m['peak_gpu_memory'])} |")
PY
