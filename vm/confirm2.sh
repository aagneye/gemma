#!/usr/bin/env bash
# Confirmation 2 (user go-ahead Nov 16): the public "LB 0.22" recipe (submissions/pub40 = Budget-Fit V5 + 40 tool calls,
# a one-word exit after submit_patch, submit at once when the call budget is used up, the issue text pinned at the end
# of the system prompt; research/raw/15_public_lb022_recipe.md) against Budget-Fit V5 on the 77 EVAL tasks whose tests
# fit the issue. Two passes side by side: 4 arms x concurrency 1, scale 9, no internet, request log. Then the
# pre-registered verdict (vm/verdict.py: mean gain >= +3 solved per pass; calls, output tokens and time <= x1.08).
# The user's condition: if the time per task rises by more than 8 %, report the numbers before any Kaggle slot.
# Then a filler so the GPUs never wait: Budget-Fit and pub40 twice more on the 48 dev tasks (more pairs, and how
# often the extra calls are used). Stop it by hand when the next test is ready: tmux kill-session -t confirm2.
#   tmux new -d -s confirm2 "bash ~/gemma4_vm/confirm2.sh"
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; S=submissions; CAND=${CAND:-pub40}
for b in budgetfit_v5 $CAND; do [ -s $S/$b/agent.yaml ] || { echo "missing $S/$b"; exit 1; }; done
EVAL="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/eval_ts01.txt SCALE=9 CONC=1 N=80"
env $EVAL REQ_DUMP=$R/results/requests/confirm2 bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 cf2_base_a $S/$CAND cf2_cand_a $S/budgetfit_v5 cf2_base_b $S/$CAND cf2_cand_b 2>&1 | tee logs/confirm2.log
python3 ~/gemma4_vm/verdict.py --base results/replica/cf2_base_a results/replica/cf2_base_b \
  --cand results/replica/cf2_cand_a results/replica/cf2_cand_b 2>&1 | tee results/replica/confirm2_verdict.txt
DEV="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/dev48.txt GROUPS_CSV=results/lists/dev48.csv SCALE=9 CONC=1"
env $DEV REQ_DUMP=$R/results/requests/screenP bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh \
  $S/budgetfit_v5 sP_base_a $S/$CAND sP_cand_a $S/budgetfit_v5 sP_base_b $S/$CAND sP_cand_b 2>&1 | tee logs/screenP.log
echo "$(date -u) confirm2 done"
