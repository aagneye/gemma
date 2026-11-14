#!/usr/bin/env bash
# Confirmation 1 (Nov 11 plan, loop 3). The stack budgetfit_s1 = Budget-Fit V5 + the E1+R1 lines (word for word as
# screened in Screen A) + thinking budget 2,048 (T1, Screen B), against Budget-Fit V5 on the 77 EVAL tasks whose tests
# fit the issue (results/lists/eval_ts01.txt). Two passes side by side: 4 arms x concurrency 1, scale 9, no internet,
# request log. Then the pre-registered verdict (vm/verdict.py: mean gain >= +3 solved per pass; calls, output tokens and
# time each <= x1.08 of Budget-Fit's).
# Then a filler so the GPUs never wait: Budget-Fit, the stack, T1 and E1+R1 once more on the 48 dev tasks (second draws
# of both parts). Stop the filler by hand when Screen C is ready: tmux kill-session -t confirm1.
# Start only after the user's go-ahead and with the earlier chain stopped (one test run at a time on the server):
#   tmux new -d -s confirm1 "bash ~/gemma4_vm/confirm_s1.sh"
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; S=submissions
for b in budgetfit_v5 budgetfit_s1 budgetfit_t1 budgetfit_e1r1; do [ -s $S/$b/agent.yaml ] || { echo "missing $S/$b"; exit 1; }; done
EVAL="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/eval_ts01.txt SCALE=9 CONC=1 N=80"
env $EVAL REQ_DUMP=$R/results/requests/confirm1 bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 cf1_base_a $S/budgetfit_s1 cf1_s1_a $S/budgetfit_v5 cf1_base_b $S/budgetfit_s1 cf1_s1_b 2>&1 | tee logs/confirm1.log
python3 ~/gemma4_vm/verdict.py --base results/replica/cf1_base_a results/replica/cf1_base_b \
  --cand results/replica/cf1_s1_a results/replica/cf1_s1_b 2>&1 | tee results/replica/confirm1_verdict.txt
DEV="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/dev48.txt GROUPS_CSV=results/lists/dev48.csv SCALE=9 CONC=1"
env $DEV REQ_DUMP=$R/results/requests/screenS bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 sS_base $S/budgetfit_s1 sS_s1 $S/budgetfit_t1 sS_t1 $S/budgetfit_e1r1 sS_e1r1 2>&1 | tee logs/screenS.log
echo "$(date -u) confirm_s1 done"
