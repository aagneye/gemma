#!/usr/bin/env bash
# Download competition data, wheelhouse and model weights onto the VM. Resumable.
#   bash download_data.sh            # everything
#   bash download_data.sh small      # tasks/readme/sample_submission/docker/sandbox/wheels only (no snapshots)
set -euo pipefail
ROOT=/data/biohub/kdata/gemma4; cd "$ROOT"; source .venv/bin/activate
MODE=${1:-all}

echo "== competition files =="
mkdir -p data/comp && cd data/comp
# Kaggle CLI downloads one file at a time with -f; list first, then fetch what we need.
kaggle competitions files -c gemma-4-developer-agent -v > files.csv || { echo "Join the competition + accept rules on kaggle.com first"; exit 1; }
for f in tasks.jsonl HARNESS_README.md; do kaggle competitions download -c gemma-4-developer-agent -f "$f" -p . -o || true; done
# directories come as zips when fetched by prefix via the full download; for 'small' we pull the whole
# archive only if it is not already here (22 GB) -- prefer selective fetches:
grep -E '^(sample_submission|docker|sandbox|wheels)/' files.csv | cut -d, -f1 | while read -r f; do
  kaggle competitions download -c gemma-4-developer-agent -f "$f" -p "$(dirname "$f")" -o || true
done
if [ "$MODE" = all ]; then
  grep -E '^(graphs|embeddings|snapshots)/' files.csv | cut -d, -f1 | while read -r f; do
    kaggle competitions download -c gemma-4-developer-agent -f "$f" -p "$(dirname "$f")" -o || true
  done
fi
find . -name '*.zip' -exec sh -c 'unzip -oq "$1" -d "$(dirname "$1")" && rm "$1"' _ {} \;
cd "$ROOT"

echo "== wheelhouse (harness packages: swegemma, adk-submission, adk-eval-core, vllm 0.19.1 cu128) =="
mkdir -p data/wheelhouse && kaggle datasets download -d metric/gemma-4-developer-agent-wheelhouse -p data/wheelhouse --unzip -o || echo "WARN wheelhouse download failed"

echo "== model weights (bf16 QAT exports for training; w4a16 for serving on Ampere+ only) =="
# Training bases (bf16 weights from the QAT pipeline -> minimal train/serve mismatch):
hf download google/gemma-4-12B-it-qat-q4_0-unquantized --local-dir models/gemma-4-12B-it-qat-q4_0-unquantized --exclude "*.gguf"
if [ "$MODE" = all ]; then
  hf download google/gemma-4-31B-it-qat-q4_0-unquantized --local-dir models/gemma-4-31B-it-qat-q4_0-unquantized --exclude "*.gguf"
  hf download google/gemma-4-E4B-it-qat-q4_0-unquantized --local-dir models/gemma-4-E4B-it-qat-q4_0-unquantized --exclude "*.gguf"
fi
du -sh models/* data/* 2>/dev/null
