#!/usr/bin/env bash
# Instruction program queue (Nov 11 plan). Waits for the adapter test (tmux gate1), then, with no gap:
#   Screen A   Budget-Fit, C1, E1+R1, D1 on the 48 dev tasks (4 arms x concurrency 1, scale 9, no internet, request log)
#   probes     ~/gemma4_vm/probe_round1.sh if it has been deployed by then (GPU gap between the screens)
#   Screen B   Budget-Fit, P1, T2, T1 on the same dev tasks
#   filler     a second pass of Screen A; stop it by hand (tmux kill-session -t instr) when the stack is ready
# Each screen's arms share one base run; results/replica/<tag>/, request dumps in results/requests/<screen>/.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; S=submissions
COMMON="ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=results/lists/dev48.txt GROUPS_CSV=results/lists/dev48.csv SCALE=9 CONC=1"
screen() {   # <name> <sub> <tag> ...
  local name=$1; shift
  env $COMMON REQ_DUMP=$R/results/requests/$name bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_arms.sh "$@" 2>&1 | tee logs/$name.log
}
bash ~/gemma4_vm/after_session.sh ${WAIT:-gate1}
screen screenA $S/budgetfit_v5 sA_base $S/budgetfit_c1 sA_c1 $S/budgetfit_e1r1 sA_e1r1 $S/budgetfit_d1 sA_d1
[ -f ~/gemma4_vm/probe_round1.sh ] && bash ~/gemma4_vm/probe_round1.sh 2>&1 | tee logs/probe_round1.log
screen screenB $S/budgetfit_v5 sB_base $S/budgetfit_p1 sB_p1 $S/budgetfit_t2 sB_t2 $S/budgetfit_t1 sB_t1
screen screenA2 $S/budgetfit_v5 sA2_base $S/budgetfit_c1 sA2_c1 $S/budgetfit_e1r1 sA2_e1r1 $S/budgetfit_d1 sA2_d1
echo "$(date -u) chain_instr done"
