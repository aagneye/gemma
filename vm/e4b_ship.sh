#!/usr/bin/env bash
# E4B side track (research/PLAN_E4B.md, step 3; user approval Nov 22): ONE Kaggle run for an E4B bundle that passed
# the confirmation. e4b_chain.sh starts it in tmux e4b_ship after a PASS; by hand: bash e4b_ship.sh submissions/<bundle>
# Every step must hold; a step that fails ends the script with nothing handed over:
#   1  the bundle validates in the harness and declares the E4B
#   2  the CPU submission notebook is written from it (make_notebook.py: the text files are inside the notebook)
#   3  the notebook is pushed (private) and has finished; its submission.zip unzips to the validated bundle, file by file
#   4  hand-over through results/ship_schedule.txt, the file made for the E4B slot: a line for today's UTC date, renewed
#      every day until results/ledger.csv shows a run of this kernel, then removed. daily_ship.py is not changed: it
#      reads a schedule line after the once line and the follow-up, sends one run per UTC day and nothing in a hold.
# It hands nothing over while the round-2 adapter holds the queue (results/ship_once.txt or results/ship_followup.txt
# exists): then the user decides which run gives way (plan: "asked again when it comes up").
#   DRY=1          steps 1 and 2 only; nothing is sent to Kaggle
#   NO_HANDOVER=1  stops after step 3
#   UNTIL=2026-11-29   last UTC date a line is written for (a run sent later would not be scored before the picks)
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; K=$R/.venv/bin/kaggle; LOG=logs/e4b_ship.log; M=gemma-4-e4b-it-qat-w4a16-ct
BUNDLE=${1:?bundle dir}; BUNDLE=${BUNDLE%/}; NAME=$(basename $BUNDLE); UNTIL=${UNTIL:-2026-11-29}
NB=${NB:-aagneye/gemma4-${NAME//_/-}}; TITLE=${TITLE:-Gemma4 $(echo $NAME | tr '_' ' ' | sed 's/\b./\u&/g')}
MSG=${MSG:-"$NAME: small-model entry; beat e4b_bf5 (public Budget-Fit profile on the E4B) by +3 on the 77 EVAL tasks, runtime rule OK (e4b_chain)"}
SCHED=results/ship_schedule.txt; T=tmp/ship_$NAME; mkdir -p $T logs
log() { echo "$(date -u) | $*" | tee -a $LOG; }
fail() { log "NOT HANDED OVER: $*"; exit 1; }
adapter_holds() { [ -e results/ship_once.txt ] || [ -e results/ship_followup.txt ]; }
drop_line() { [ -f $SCHED ] && grep -q " $NB " $SCHED && { grep -v " $NB " $SCHED > $T/sched.new; cat $T/sched.new > $SCHED; }; return 0; }

# 1 the validated bundle
case "$NAME" in e4b_*) ;; *) fail "$NAME is not an e4b_ bundle";; esac
grep -q "^model: $M$" $BUNDLE/agent.yaml 2>/dev/null || fail "$BUNDLE does not declare the E4B"
[ -d $BUNDLE/adapters ] && fail "$BUNDLE holds an adapter; this script ships text bundles only"
$R/harness-venv/bin/python $V/make_submission.py --validate $BUNDLE 2>&1 | tail -1 | cut -c1-200 > $T/validate.txt
log "bundle $BUNDLE: $(cat $T/validate.txt)"
grep -q "^VALID" $T/validate.txt || fail "the harness does not validate $BUNDLE"

# 2 the notebook, written locally
rm -rf $T/nb
python3 $V/make_notebook.py $BUNDLE $T/nb $NB "$TITLE" > $T/notebook.txt 2>&1 || fail "make_notebook.py: $(tail -1 $T/notebook.txt | cut -c1-200)"
log "notebook written for kernel $NB (\"$TITLE\"): $(tail -1 $T/notebook.txt | cut -c1-160)"
if [ -n "${DRY:-}" ]; then log "DRY: stopped before anything was sent to Kaggle"; exit 0; fi

# 3 push, wait, compare
$K kernels push -p $T/nb 2>&1 | grep -v Warning | tail -1 | cut -c1-240 > $T/push.txt; log "push: $(cat $T/push.txt)"
VER=$(grep -o "version [0-9]*" $T/push.txt | grep -o "[0-9]*" | tail -1)
[ -n "$VER" ] || fail "the push did not report a kernel version"
st=""; for i in $(seq 1 60); do sleep 30; st=$($K kernels status $NB 2>&1 | grep -v Warning | tail -1); echo "$st" | grep -qiE "complete|error|cancel" && break; done
log "notebook v$VER: $(echo "$st" | cut -c1-160)"
echo "$st" | grep -qi complete || fail "the notebook did not finish (see it on Kaggle)"
rm -rf $T/out $T/unz; $K kernels output $NB -p $T/out > /dev/null 2>&1
[ -f $T/out/submission.zip ] || fail "the notebook's output has no submission.zip"
mkdir -p $T/unz; unzip -q $T/out/submission.zip -d $T/unz 2> $T/diff.txt || fail "the notebook's zip does not unzip"
diff -r $BUNDLE $T/unz > $T/diff.txt 2>&1 || fail "the notebook's zip is not the validated bundle (first difference: $(head -1 $T/diff.txt | cut -c1-160))"
log "the notebook's submission.zip unzips to the validated bundle, file by file"
if [ -n "${NO_HANDOVER:-}" ]; then log "NO_HANDOVER: every check passed for $NB v$VER; nothing was handed over"; exit 0; fi

# 4 hand-over: today's line, every day, until the run is in the ledger
while :; do
  if grep -q ",$NB,$VER," results/ledger.csv 2>/dev/null; then
    drop_line; log "SUBMITTED: $(grep ",$NB,$VER," results/ledger.csv | tail -1 | cut -c1-80); the schedule line is removed"; exit 0
  fi
  if adapter_holds; then
    drop_line; log "ASK: the round-2 adapter holds the queue (ship_once.txt or ship_followup.txt). $NB v$VER is ready and checked; nothing handed over. The user decides which run gives way"; exit 0
  fi
  D=$(date -u +%F)
  if [[ "$D" > "$UNTIL" ]]; then drop_line; fail "not submitted by $UNTIL (the queue was never free on a day with the line)"; fi
  if ! grep -q "^$D $NB $VER " $SCHED 2>/dev/null; then
    drop_line; echo "$D $NB $VER $MSG" >> $SCHED; log "HANDED OVER for $D: \"$D $NB $VER ...\" is in $SCHED"
  fi
  sleep 300
done
