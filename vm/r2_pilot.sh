#!/usr/bin/env bash
# Round-2 pilot (Nov 19, plan step 2): the 12 pilot tasks through the note relay, 6 per pool side by side (2 at a time
# each, so the server sees the usual 4 requests). Budget-Fit V5 unchanged; the note text is the approved one.
#   [POSITION=A] [WAIT_FOR=<tmux session>] bash r2_pilot.sh
# Output: results/replica/r2_pilot_{train,rb2}_<a|b> (runs), results/takeover/... (journals), results/r2_pilot_<a|b>.md
# (the report with the model's first thinking after each note), a "done" line in logs/r2_pilot.log.
# Pilot rule (plan + review): the note position is good when the first block is applied within 2 model steps in
# >= 80 % of the noted runs and >= 60 % of the noted runs pass the tests; else position B is tried.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; POS=${POSITION:-A}; p=$(echo $POS | tr A-Z a-z)
[ -n "${WAIT_FOR:-}" ] && bash ~/gemma4_vm/after_session.sh $WAIT_FOR
echo "$(date -u) r2_pilot $POS start" | tee -a logs/r2_pilot.log
TAG=r2_pilot_train_$p POOL=rebench LIST=results/lists/r2_pilot_train.txt HINTS=datasets/r2/hints_train.jsonl POSITION=$POS CONC=2 RELAY_PORT=8100 \
  bash ~/gemma4_vm/note_runs.sh > logs/r2_pilot_train_$p.log 2>&1 &
TAG=r2_pilot_rb2_$p POOL=rebench2 LIST=results/lists/r2_pilot_rb2.txt HINTS=datasets/r2/hints_rb2.jsonl POSITION=$POS CONC=2 RELAY_PORT=8101 \
  bash ~/gemma4_vm/note_runs.sh > logs/r2_pilot_rb2_$p.log 2>&1 &
wait
python3 ~/gemma4_vm/note_report.py r2_pilot_train_$p r2_pilot_rb2_$p --hints datasets/r2/hints_train.jsonl datasets/r2/hints_rb2.jsonl \
  --thoughts 12 > results/r2_pilot_$p.md 2>&1
echo "$(date -u) r2_pilot $POS done" | tee -a logs/r2_pilot.log
