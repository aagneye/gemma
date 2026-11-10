#!/usr/bin/env bash
# One self-training round on the VM (Phase 3 of the Nov 3 plan; 31B training on the T4s per the user, Nov 3):
# optional extra generation pass (no internet) -> episodes from the policy's own resolved runs -> 31B windows ->
# data-floor check (pre-registered: >= 100 episodes from >= 50 tasks, else no training) -> LoRA training on the 4 T4s
# with the vLLM server stopped -> vLLM restarted with LoRA hot-swap. Stop and start are chained (shared VM).
#   [EXTRA_SUB=submissions/budgetfit_v5_t06 EXTRA_TAG=bf5t06_train2 EXTRA_LIST=results/lists/bf5_train_solved.txt] \
#   TRACES='results/replica/bf5*_train*' BUNDLE=submissions/budgetfit_v5 TAG=bf5_v2 MAX_LEN=12288 bash rft_round.sh
set -u
R=/mnt/biohub/kdata/gemma4; cd $R
TRACES=${TRACES:?glob of eval dirs}; BUNDLE=${BUNDLE:?policy bundle}; TAG=${TAG:?tag}; MAX_LEN=${MAX_LEN:-12288}
PER_TASK=${PER_TASK:-3}; DEADLINE_MIN=${DEADLINE_MIN:-720}   # round 2: PER_TASK=2 DEADLINE_MIN=1380 (Nov 10 plan)
DATA=datasets/own_$TAG; OUT=runs/31b_${TAG}_r32
if [ -n "${EXTRA_SUB:-}" ]; then
  echo "$(date -u) extra pass $EXTRA_SUB on $EXTRA_LIST"
  ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=$EXTRA_LIST REPLICA_TIME_SCALE=9 \
    bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_replica.sh $EXTRA_SUB $EXTRA_TAG 0 auto 4 | tail -1
fi
rm -rf $DATA
.venv/bin/python ~/gemma4_vm/prepare_data.py --source harness-trace --traces "$TRACES" --bundle $BUNDLE --max-calls 24 --per-task $PER_TASK --out $DATA | grep "split all" | cut -c1-120
.venv/bin/python ~/gemma4_vm/prepare_data.py --tokenize $DATA/all.jsonl --model models/gemma-4-31b-it-qat-w4a16-ct --max-len $MAX_LEN \
  --thought-cap 1000 --out $DATA/tok_31b | tail -2
read EP TK < <(python3 -c "import json;s=json.load(open('$DATA/stats.json'))['filter_stats'];print(s['kept_episodes'],s['kept_tasks'])")
echo "$(date -u) data floor check: $EP episodes from $TK tasks (floor 100 / 50)"
if [ "$EP" -lt 100 ] || [ "$TK" -lt 50 ]; then echo "below the floor: no training this round"; exit 0; fi
echo "$(date -u) stopping vLLM for training"; tmux kill-session -t vllm 2>/dev/null; sleep 10
rm -rf $OUT; mkdir -p $OUT
timeout $(( DEADLINE_MIN * 60 + 3600 )) .venv/bin/python ~/gemma4_vm/train_qlora.py --model models/gemma-4-31B-it-qat-q4_0-unquantized --data $DATA/tok_31b \
  --out $OUT --pipeline 4 --attn qchunk --max-len $MAX_LEN --rank 32 --lr 1e-4 --optim adamw --epochs 1 --grad-accum 8 \
  --log-every 1 --save-every 1000 --fit-probe --deadline-min $DEADLINE_MIN > $OUT/train.log 2>&1
echo "$(date -u) training exit $?; restarting vLLM"
MODEL=gemma-4-31b-it-qat-w4a16-ct LORA_DYNAMIC=1 bash ~/gemma4_vm/wait_vllm.sh | head -1
grep -E "fit_probe|summary|saved ->|Error" $OUT/train.log | tail -5 | cut -c1-300
echo "$(date -u) rft_round $TAG done"
