#!/usr/bin/env bash
# Round 2 after the note runs (Nov 21; steps 4-8 of research/PLAN_ROUND2.md with their stop rules):
#   4  examples from the note runs and round 1's wins; floor check
#   5  fit test, tokens, training (rank 16, alpha 32, one pass, one update per 4 examples, checkpoint every 10 updates)
#   6  sanity check on held-out dev examples (heldout_loss.py); bundle, server with the adapter, effect check
#   7  test pass 1 on the 77 EVAL tasks: the 43 tasks Budget-Fit does not always solve first (11 needed to reach 45)
#   8  test pass 2; verdict.py over all pairs with Budget-Fit's four passes; runtime rule
#   [WAIT_FOR=r2notes] [EXTRA_TAGS="r2_pilot_train_c r2_pilot_rb2_c"] [RANK=16] [ALPHA=32] [T4_SLOW=2.279] [L4_SLOW=1.128] bash chain_r2.sh
# A rule that fails stops the chain, stops our model server (the GPUs are free again) and writes the reason to
# logs/r2_chain.log. START_AT=5|6|7|8 resumes at a later step. Shared VM: it starts work only on free cards and never
# touches jobs other than its own tmux session `vllm`.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; PY=$R/.venv/bin/python; LOG=logs/r2_chain.log; D=datasets/r2
RANK=${RANK:-16}; ALPHA=${ALPHA:-$((RANK * 2))}; T4_SLOW=${T4_SLOW:-2.279}; L4_SLOW=${L4_SLOW:-1.128}; START_AT=${START_AT:-4}
FLOOR_EX=${FLOOR_EX:-60}; FLOOR_TASKS=${FLOOR_TASKS:-45}; MODEL=gemma-4-31b-it-qat-w4a16-ct; BASE=models/gemma-4-31B-it-qat-q4_0-unquantized
RUN=runs/31b_r2_r$RANK; BUNDLE=submissions/budgetfit_v5_lora2
log() { echo "$(date -u) | $*" | tee -a $LOG; }
stop() { log "ROUND STOPPED: $*"; tmux kill-session -t vllm 2>/dev/null; exit 0; }
free() { for u in $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits); do [ "$u" -lt 1000 ] || return 1; done; }
wait_free() { for i in $(seq 1 60); do free && return 0; sleep 5; done; return 1; }
solved() { python3 -c "import csv,sys; print(sum(r['resolved']=='True' for d in sys.argv[1:] for r in csv.DictReader(open('results/replica/'+d+'/results.csv'))))" "$@"; }
[ -n "${WAIT_FOR:-}" ] && bash $V/after_session.sh $WAIT_FOR
log "chain_r2 start at step $START_AT: rank $RANK, alpha $ALPHA, T4 slowdown $T4_SLOW, L4 slowdown $L4_SLOW"

if [ $START_AT -le 4 ]; then   # ---- 4: examples ----------------------------------------------------------------
  NOTES="$(ls -d results/replica/r2_tk_train_* results/replica/r2_tk_rb2_* 2>/dev/null | xargs -r -n1 basename | tr '\n' ' ')${EXTRA_TAGS:-}"
  DEVT="$(ls -d results/replica/r2_tk_dev_* 2>/dev/null | xargs -r -n1 basename | tr '\n' ' ')"
  log "note runs: $NOTES | held out: $DEVT"
  $PY $V/exact_data.py build --notes $NOTES --hints $D/hints_train.jsonl $D/hints_rb2.jsonl --own results/replica/bf5_train results/replica/bf5t06_train2 \
    --exclude results/lists/dev48.txt --out $D/all.jsonl 2>&1 | grep -v Warning | tee -a $LOG
  read EX TK < <(python3 -c "import json; s=json.load(open('$D/all.stats.json')); print(s['stats'].get('clean note runs', 0), len(s['note_tasks']))")
  log "floor check: $EX clean note runs from $TK tasks (floor $FLOOR_EX from $FLOOR_TASKS)"
  { [ "${EX:-0}" -ge $FLOOR_EX ] && [ "${TK:-0}" -ge $FLOOR_TASKS ]; } || stop "too few clean examples (plan step 4)"
  rm -f $D/heldout.jsonl
  [ -n "$DEVT" ] && $PY $V/exact_data.py build --notes $DEVT --hints $D/hints_train.jsonl --only results/lists/dev48.txt --out $D/heldout.jsonl 2>&1 | grep -v Warning | head -3 | tee -a $LOG
fi

if [ $START_AT -le 5 ]; then   # ---- 5: fit test, tokens, training ------------------------------------------------
  log "stopping the model server for training"; tmux kill-session -t vllm 2>/dev/null
  wait_free || stop "the GPUs are not free (another job holds them); nothing of theirs was touched"
  $PY $V/exact_data.py tokenize $D/all.jsonl --max-len 15360 --out $D/tok_probe 2>&1 | grep "^== " | tee -a $LOG
  $PY $V/train_qlora.py --model $BASE --data $D/tok_probe --out runs/31b_r2_probe --pipeline 4 --attn qchunk --max-len 15360 --rank $RANK --alpha $ALPHA \
    --fit-probe --fit-ladder 15360,14336,13312,12288 --probe-only > logs/r2_probe.log 2>&1
  grep fit_probe logs/r2_probe.log | cut -c1-240 | tee -a $LOG
  FIT=$(grep -o '"fit": [0-9]*' logs/r2_probe.log | tail -1 | grep -o '[0-9]*$')
  { [ -n "${FIT:-}" ] && [ "$FIT" -ge 12288 ]; } || stop "the fit test found no length that fits (logs/r2_probe.log)"
  echo $FIT > $D/fit.txt; log "length limit: $FIT tokens"
  $PY $V/exact_data.py tokenize $D/all.jsonl --max-len $FIT --out $D/tok_31b 2>&1 | grep -v Warning | tee -a $LOG
  [ -f $D/heldout.jsonl ] && $PY $V/exact_data.py tokenize $D/heldout.jsonl --max-len $FIT --first-step-only --w-first 1 --out $D/tok_heldout 2>&1 | grep "^== " | tee -a $LOG
  rm -rf $RUN; mkdir -p $RUN; wait_free || stop "the GPUs are not free before training"
  train() { timeout $((1200 * 60 + 3600)) $PY $V/train_qlora.py --model $BASE --data $D/tok_31b --out $RUN --pipeline 4 --attn qchunk --max-len $FIT \
      --rank $RANK --alpha $ALPHA --lr 1e-4 --optim adamw --epochs 1 --grad-accum 4 --log-every 1 --save-every 10 \
      --fit-probe --fit-ladder $FIT,$((FIT - 1024)) --deadline-min 1200 "$@" >> $RUN/train.log 2>&1; }
  train; log "training exit $?"
  if [ ! -f $RUN/final/adapter_model.safetensors ]; then       # one restart from the newest checkpoint
    CK=$(ls -d $RUN/ckpt_* 2>/dev/null | sort -t_ -k2 -n | tail -1)
    [ -n "$CK" ] && { log "no final adapter: one restart from $CK"; wait_free; train --resume $CK; log "training exit $? after the restart"; }
  fi
  grep -E '"summary"|saved ->' $RUN/train.log | tail -2 | cut -c1-320 | tee -a $LOG
  [ -f $RUN/final/adapter_model.safetensors ] || stop "training left no adapter ($RUN/train.log)"
fi
FIT=$(cat $D/fit.txt)

if [ $START_AT -le 6 ]; then   # ---- 6: sanity check, bundle, server, effect ----------------------------------------
  if [ -f $D/tok_heldout/train.parquet ]; then
    wait_free || stop "the GPUs are not free for the held-out check"
    $PY $V/heldout_loss.py --adapter $RUN/final --more $(ls -d $RUN/ckpt_10 $RUN/ckpt_20 2>/dev/null | tr '\n' ' ') --data $D/tok_heldout --max-len $FIT \
      --rank $RANK --out results/r2_heldout.json > logs/r2_heldout.log 2>&1
    grep -E "step loss|SANITY" logs/r2_heldout.log | cut -c1-200 | tee -a $LOG
    grep -q "^SANITY FAIL" logs/r2_heldout.log && stop "the held-out check failed (plan step 6)"
    grep -q "^SANITY PASS" logs/r2_heldout.log || log "WARNING: the held-out check did not finish (logs/r2_heldout.log); the test goes on and decides"
  else
    log "WARNING: no held-out rows; the test goes on and decides"
  fi
  source harness-venv/bin/activate
  python $V/make_submission.py --bundle submissions/budgetfit_v5 --model $MODEL --adapter $RUN/final --out $BUNDLE 2>&1 | tail -2 | cut -c1-300 | tee -a $LOG
  python $V/make_submission.py --validate $BUNDLE 2>&1 | tail -1 | cut -c1-200 | tee -a $LOG
  deactivate
  grep -q "^adapter: main_lora" $BUNDLE/agent.yaml || stop "the bundle has no adapter line"
fi

serve_adapter() {
  curl -s -m 10 http://127.0.0.1:8000/v1/models | grep -q '"main_lora"' && return 0
  tmux kill-session -t vllm 2>/dev/null; wait_free || return 1
  [ "$(MODEL=$MODEL LORA_DYNAMIC=1 MAX_LORA_RANK=$RANK bash $V/wait_vllm.sh | head -1)" = READY ] || return 1
  curl -s -m 600 -X POST http://127.0.0.1:8000/v1/load_lora_adapter -H "Content-Type: application/json" \
    -d "{\"lora_name\": \"main_lora\", \"lora_path\": \"$R/$BUNDLE/adapters/main_lora\"}" > /dev/null
  curl -s -m 10 http://127.0.0.1:8000/v1/models | grep -q '"main_lora"'
}
SCALE=$(python3 -c "print(round(9 * $T4_SLOW / $L4_SLOW, 2))")
eval_run() {   # eval_run <tag> <task list>
  ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=$2 REPLICA_TIME_SCALE=$SCALE REQ_DUMP=$R/results/requests/$1 \
    bash $V/netns_run.sh bash $V/run_replica.sh $BUNDLE $1 0 auto 4 | tail -1 | tee -a $LOG
}

if [ $START_AT -le 6 ]; then
  serve_adapter || stop "the model server with the adapter did not come up"
  python3 $V/adapter_effect.py --examples $(ls $D/heldout.jsonl 2>/dev/null) $D/all.jsonl --out results/r2_effect.json 2>&1 | tail -2 | tee -a $LOG
  grep -q '"pass": true' results/r2_effect.json || stop "the adapter does not change the answers or breaks tool calls (effect check)"
fi

if [ $START_AT -le 7 ]; then   # ---- 7: test pass 1 -----------------------------------------------------------------
  serve_adapter || stop "the model server with the adapter did not come up"
  log "test pass 1 at clock scale $SCALE (9 x $T4_SLOW / $L4_SLOW)"
  eval_run r2_eval_a1 results/lists/r2_eval_uncertain43.txt
  S1=$(solved r2_eval_a1); log "pass 1, the 43 tasks Budget-Fit does not always solve: $S1 solved (Budget-Fit: 9.25; 11 needed to reach 45)"
  [ "$S1" -ge 11 ] || stop "test pass 1 cannot reach 45 solved: $S1 of the 43, 11 needed (plan step 7)"
  eval_run r2_eval_a2 results/lists/r2_eval_always34.txt
  rm -rf results/replica/r2_eval_a; mkdir -p results/replica/r2_eval_a/agent_run/traces
  cat results/replica/r2_eval_a1/agent_run/task_results.jsonl results/replica/r2_eval_a2/agent_run/task_results.jsonl > results/replica/r2_eval_a/agent_run/task_results.jsonl
  cp results/replica/r2_eval_a1/agent_run/traces/*.json results/replica/r2_eval_a2/agent_run/traces/*.json results/replica/r2_eval_a/agent_run/traces/
  SA=$(solved r2_eval_a1 r2_eval_a2); log "test pass 1: $SA of 77 solved (Budget-Fit: 41, 44, 44, 44)"
  [ "$SA" -ge 45 ] || stop "test pass 1 solved $SA of 77, 45 needed (plan step 7)"
fi

# ---- 8: test pass 2 and the verdict ---------------------------------------------------------------------------------
serve_adapter || stop "the model server with the adapter did not come up"
eval_run r2_eval_b results/lists/eval_ts01.txt
log "test pass 2: $(solved r2_eval_b) of 77 solved"
B="results/replica/cf1_base_a results/replica/cf1_base_b results/replica/cf2_base_a results/replica/cf2_base_b"
A4="results/replica/r2_eval_a results/replica/r2_eval_a results/replica/r2_eval_a results/replica/r2_eval_a"
B4="results/replica/r2_eval_b results/replica/r2_eval_b results/replica/r2_eval_b results/replica/r2_eval_b"
python3 $V/verdict.py --base $B $B --cand $A4 $B4 --tasks results/lists/eval_ts01.txt --gain 3 --cost 1.08 --cost-keys calls,tok | tee results/replica/r2_verdict.txt | tail -3 | tee -a $LOG
TOK=$(grep -o "tokens x[0-9.]*" results/replica/r2_verdict.txt | tail -1 | grep -o "[0-9.]*$")
python3 -c "
t = float('${TOK:-1}'); s = $L4_SLOW; p = round(s * t, 3)
print(f'RUNTIME {\"OK\" if p <= 1.05 else \"ASK\"}: L4 slowdown x{s} times output tokens x{t} = x{p} of Budget-Fit (rule: at most x1.05)')" | tee -a $LOG
log "chain_r2 done; the server with the adapter stays up"
