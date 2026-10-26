#!/usr/bin/env bash
# Rebuild the E4B training data after the 2026-10-26 pipeline fixes (supervised <|tool_response> stop token, masking at
# conversion time, long trajectories cut before the first budget warning, get_status budget-free, same protected-file
# set everywhere) under the SHIPPED header (submissions/v5_1), then launch E4B LoRA v1 on one free T4 (not GPU 0).
# CPU-bound except the final launch; run in tmux: tmux new -d -s e4b_v2 "bash ~/gemma4_vm/build_e4b_v2_data.sh"
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; source .venv/bin/activate
B=submissions/v5_1; M=models/gemma-4-E4B-it-qat-q4_0-unquantized; LOG=logs/build_e4b_v2_data.log
log() { echo "$(date -u) | $*" | tee -a $LOG; }
log "start"
# 1. own 31B traces (masking complete: observations are verbatim), split by repo for cross-fit
python ~/gemma4_vm/prepare_data.py --bundle $B --source harness-trace --traces "scratch/kev_*_out/eval" --max-calls 24 --per-task 3 \
  --teacher 31b --split-by-repo --out datasets/traces_31b_v2 >> $LOG 2>&1 || { log "traces conversion FAILED"; exit 1; }
# 2. external windows re-rendered under v5.1 with the pre-warning cut (same filters as ext36)
python ~/gemma4_vm/prepare_data.py --bundle $B --rerender datasets/sft_v4_wide/all.jsonl --max-steps 36 --first-edit-by 14 --min-tests 1 \
  --repo-cap 20 --per-instance 2 --out datasets/sft_v5_ext/ext36b.jsonl >> $LOG 2>&1 || { log "rerender FAILED"; exit 1; }
# 3. tokenize for the E4B (thought cap 600 tokens; traces at 8k so fewer windows are dropped)
python ~/gemma4_vm/prepare_data.py --tokenize datasets/sft_v5_ext/ext36b.jsonl --model $M --max-len 7168 --thought-cap 600 \
  --out datasets/sft_v5_ext/tok_e4b_7k_ext36b >> $LOG 2>&1 || { log "tokenize ext36b FAILED"; exit 1; }
for s in fastapi rich all; do
  python ~/gemma4_vm/prepare_data.py --tokenize datasets/traces_31b_v2/$s.jsonl --model $M --max-len 8192 --thought-cap 600 \
    --out datasets/traces_31b_v2/tok_e4b_8k_$s >> $LOG 2>&1 || { log "tokenize traces $s FAILED"; exit 1; }
done
# 4. mixes: fitA = external + fastapi traces x3 (evaluate on rich); fitB = external + rich traces x3 (evaluate on fastapi)
mkdir -p datasets/e4b_v2
python ~/gemma4_vm/merge_tokenized.py --out datasets/e4b_v2/tok_fitA datasets/sft_v5_ext/tok_e4b_7k_ext36b=1 datasets/traces_31b_v2/tok_e4b_8k_fastapi=3 >> $LOG 2>&1 || { log "merge fitA FAILED"; exit 1; }
python ~/gemma4_vm/merge_tokenized.py --out datasets/e4b_v2/tok_fitB datasets/sft_v5_ext/tok_e4b_7k_ext36b=1 datasets/traces_31b_v2/tok_e4b_8k_rich=3 >> $LOG 2>&1 || { log "merge fitB FAILED"; exit 1; }
# 5. sanity: the <|tool_response> stop token (id 50) must now carry a supervised label after tool calls
python - <<'PY' | tee -a $LOG
import pyarrow.parquet as pq, numpy as np
t = pq.read_table("datasets/e4b_v2/tok_fitA/train.parquet", columns=["input_ids", "labels"]).to_pandas()
sup50 = tot50 = 0
for ids, lab in zip(t["input_ids"].head(300), t["labels"].head(300)):
    ids = np.asarray(ids); lab = np.asarray(lab); m = ids == 50
    tot50 += int(m.sum()); sup50 += int((lab[m] != -100).sum())
print(f"sanity: <|tool_response> tokens in first 300 windows: {tot50}, supervised {sup50} (expect ~all tool-call turns supervised, >0)")
PY
log "data ready: $(python -c "import json;d=json.load(open('datasets/e4b_v2/tok_fitA/stats.json'));print(d['windows'],'windows',d['tokens'],'tokens',d['supervised'],'supervised')")"
# 6. launch v1 on one free T4 (GPU 0 excluded by start_train_free.sh)
nohup bash ~/gemma4_vm/start_train_free.sh --model $M --data datasets/e4b_v2/tok_fitA --run e4b_r32_v1 --max-len 8192 --epochs 1 \
  --rank 32 --lr 1e-4 --alpha 64 --max-gpus 1 1 > logs/start_e4b_r32_v1.log 2>&1 < /dev/null &
log "launcher started (see logs/start_train_free.log and logs/e4b_r32_v1.log)"
