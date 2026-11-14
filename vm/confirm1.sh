#!/usr/bin/env bash
# Confirmation 1 (Nov 11 plan, loop 3). The stack budgetfit_s2 = Budget-Fit V5 + the R1, T2 and E1 lines (word for word
# as screened: vm/prompts/budgetfit_s2.md) + thinking budget 2,048 (T1), against Budget-Fit V5 on the 77 EVAL tasks
# whose tests fit the issue (results/lists/eval_ts01.txt). Two passes side by side: 4 arms x concurrency 1, scale 9,
# no internet, request log. Then the pre-registered verdict (vm/verdict.py: mean gain >= +3 solved per pass; calls,
# output tokens and time each <= x1.08 of Budget-Fit's).
# Then a filler so the GPUs never wait: Budget-Fit, the stack, T1 and T2 once more on the 48 dev tasks (second draws of
# the parts with the thinnest evidence). Stop the filler by hand when Screen C is ready: tmux kill-session -t confirm1.
# Start only with no other test run on the server (one at a time):
#   tmux new -d -s confirm1 "bash ~/gemma4_vm/confirm1.sh"
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; S=submissions; STACK=${STACK:-budgetfit_s2}
for b in budgetfit_v5 $STACK budgetfit_t1 budgetfit_t2; do [ -s $S/$b/agent.yaml ] || { echo "missing $S/$b"; exit 1; }; done
EVAL="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/eval_ts01.txt SCALE=9 CONC=1 N=80"
env $EVAL REQ_DUMP=$R/results/requests/confirm1 bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 cf1_base_a $S/$STACK cf1_stack_a $S/budgetfit_v5 cf1_base_b $S/$STACK cf1_stack_b 2>&1 | tee logs/confirm1.log
python3 ~/gemma4_vm/verdict.py --base results/replica/cf1_base_a results/replica/cf1_base_b \
  --cand results/replica/cf1_stack_a results/replica/cf1_stack_b 2>&1 | tee results/replica/confirm1_verdict.txt
DEV="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/dev48.txt GROUPS_CSV=results/lists/dev48.csv SCALE=9 CONC=1"
env $DEV REQ_DUMP=$R/results/requests/screenS bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 sS_base $S/$STACK sS_stack $S/budgetfit_t1 sS_t1 $S/budgetfit_t2 sS_t2 2>&1 | tee logs/screenS.log
echo "$(date -u) confirm1 done"
