#!/usr/bin/env bash
# Confirmation 3 (user go-ahead Nov 18): Patchsmith V7 (submissions/patchsmith_v7 = the exact files of Repair Lab's
# public 0.22 run "exp021", zip sha256 e3bd5f42..., Apache-2.0, LICENSE/NOTICE kept; research/raw/16_public_notebooks_nov18.md)
# against Budget-Fit V5 on the 77 EVAL tasks whose tests fit the issue. Same protocol as confirm2.sh: two passes side by
# side, 4 arms x concurrency 1, scale 9, no internet, request log, then the pre-registered verdict (vm/verdict.py: mean
# gain >= +3 solved per pass; calls, output tokens and time <= x1.08). Patchsmith's 60-s command limit applies unscaled.
# Then a filler so the GPUs never wait: Budget-Fit and Patchsmith twice more on the 48 dev tasks.
# Stop it by hand when the next job is ready: tmux kill-session -t confirm3.
#   tmux new -d -s confirm3 "bash ~/gemma4_vm/confirm3.sh"
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; S=submissions; CAND=${CAND:-patchsmith_v7}
for b in budgetfit_v5 $CAND; do [ -s $S/$b/agent.yaml ] || { echo "missing $S/$b"; exit 1; }; done
EVAL="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/eval_ts01.txt SCALE=9 CONC=1 N=80"
env $EVAL REQ_DUMP=$R/results/requests/confirm3 bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 cf3_base_a $S/$CAND cf3_cand_a $S/budgetfit_v5 cf3_base_b $S/$CAND cf3_cand_b 2>&1 | tee logs/confirm3.log
python3 ~/gemma4_vm/verdict.py --base results/replica/cf3_base_a results/replica/cf3_base_b \
  --cand results/replica/cf3_cand_a results/replica/cf3_cand_b 2>&1 | tee results/replica/confirm3_verdict.txt
DEV="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/dev48.txt GROUPS_CSV=results/lists/dev48.csv SCALE=9 CONC=1"
env $DEV REQ_DUMP=$R/results/requests/screenQ bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 sQ_base_a $S/$CAND sQ_cand_a $S/budgetfit_v5 sQ_base_b $S/$CAND sQ_cand_b 2>&1 | tee logs/screenQ.log
echo "$(date -u) confirm3 done"
