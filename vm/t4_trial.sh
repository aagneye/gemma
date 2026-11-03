#!/usr/bin/env bash
# 31B LoRA trial on the VM's 4 T4s (user decision 2026-11-03: train on the T4s after the agent tests, not on Kaggle).
# Waits for the agent-test tmux session to end, stops the vLLM server, runs a 20-step trial with the pipeline split over
# the 4 cards at 8k context (fp16; a fit probe first, retrying shorter on OOM), then restarts the 31B server with LoRA
# hot-swap. Stop and start are chained so the GPUs never sit free (the VM is shared).
#   bash t4_trial.sh [wait_session=rep_sw] [max_len=8192]
set -u
WAIT=${1:-rep_sw}; LEN=${2:-8192}
R=/mnt/biohub/kdata/gemma4; cd $R; OUT=runs/31b_t4_trial
bash ~/gemma4_vm/after_session.sh $WAIT
echo "$(date -u) stopping vLLM for the T4 trial"; tmux kill-session -t vllm 2>/dev/null; sleep 10
rm -rf $OUT; mkdir -p $OUT
timeout 9000 .venv/bin/python ~/gemma4_vm/train_qlora.py --model models/gemma-4-31B-it-qat-q4_0-unquantized \
  --data scratch/k31b/tok_31b_16k_smoke --out $OUT --pipeline 4 --attn qchunk --max-len $LEN --rank 32 --lr 1e-4 \
  --optim adamw --max-steps 20 --grad-accum 1 --log-every 1 --fit-probe --deadline-min 120 > $OUT/train.log 2>&1
echo "$(date -u) trial exit $?; restarting vLLM"
MODEL=gemma-4-31b-it-qat-w4a16-ct LORA_DYNAMIC=1 bash ~/gemma4_vm/wait_vllm.sh
grep -E "fit_probe|summary|Error|error" $OUT/train.log | tail -6 | cut -c1-300
echo "$(date -u) t4_trial done"
