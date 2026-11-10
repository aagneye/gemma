#!/usr/bin/env bash
# Round-2 queue (Nov 10 plan; user approvals of Nov 10). Waits for Gate 1 (tmux gate1), then:
#   1. C1 paired test x2 on its 50 EVAL tasks (no internet) and the pre-registered verdict (vm/verdict.py);
#   2. T0.6 generation with the winning policy (Budget-Fit V5, or Budget-Fit + C1): the sound rebench2 tasks
#      (TRAIN-pool venv), then the round-1 TRAIN tasks still unsolved;
#   3. round-2 training on the T4s (rft_round.sh: <= 2 episodes per task, 23-h deadline), vLLM restarted;
#   4. the new adapter packaged, hot-loaded as main_lora and run alone on all 109 EVAL tasks at the stretched clock.
# Every step is chained so the GPUs never wait for a person; Gate 2's verdict is read by hand.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; T=$R/tmp/replica
bash ~/gemma4_vm/after_session.sh gate1
for p in 1 2; do
  ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$T TASK_LIST=results/lists/c1_eval.txt SCALE=9 \
    bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_pair.sh submissions/budgetfit_v5 c1base_p$p submissions/budgetfit_c1 c1_p$p
done
python3 ~/gemma4_vm/verdict.py --base results/replica/c1base_p1 results/replica/c1base_p2 --cand results/replica/c1_p1 results/replica/c1_p2 \
  | tee results/replica/c1_verdict.txt
grep -q "^VERDICT ADOPT" results/replica/c1_verdict.txt && POL=budgetfit_c1 || POL=budgetfit_v5
echo "$(date -u) round-2 policy: $POL"
ROOT=data/rebench2 ORDER_CSV=results/rebench2_soundness.csv VENV=scorer-host-venv-plus TMPDIR=$T REPLICA_TIME_SCALE=9 \
  bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_replica.sh submissions/${POL}_t06 gen2_train_rb2 1000 auto 4 | tail -1
ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$T TASK_LIST=results/lists/bf5_train_unsolved.txt REPLICA_TIME_SCALE=9 \
  bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_replica.sh submissions/${POL}_t06 gen2_train_unsolved 0 auto 4 | tail -1
TRACES='results/replica/*train*' BUNDLE=submissions/$POL TAG=r2 MAX_LEN=12288 PER_TASK=2 DEADLINE_MIN=1380 bash ~/gemma4_vm/rft_round.sh
[ -d runs/31b_r2_r32/final ] || { echo "$(date -u) no round-2 adapter; chain stops"; exit 0; }
source harness-venv/bin/activate
python ~/gemma4_vm/make_submission.py --bundle submissions/$POL --model gemma-4-31b-it-qat-w4a16-ct --adapter runs/31b_r2_r32/final --out submissions/${POL}_lora2 | tail -1
python ~/gemma4_vm/make_submission.py --validate submissions/${POL}_lora2 | tail -1
deactivate
AP=$R/submissions/${POL}_lora2/adapters/main_lora
curl -s -m 30 -X POST http://127.0.0.1:8000/v1/unload_lora_adapter -H "Content-Type: application/json" -d '{"lora_name": "main_lora"}' > /dev/null
curl -s -m 180 -X POST http://127.0.0.1:8000/v1/load_lora_adapter -H "Content-Type: application/json" -d "{\"lora_name\": \"main_lora\", \"lora_path\": \"$AP\"}"; echo
ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$T TASK_LIST=results/lists/rebench_eval_ts.txt REPLICA_TIME_SCALE=25 \
  bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_replica.sh submissions/${POL}_lora2 lora2_eval 0 auto 4 | tail -1
echo "$(date -u) chain_round2 done"
