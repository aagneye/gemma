#!/usr/bin/env bash
# Hands an adapter bundle to the daily shipper so that it is submitted at once (Nov 22; round 2: chain_r2.sh calls it
# after VERDICT ADOPT with RUNTIME OK; by hand: bash ship_adapter.sh [bundle]). Every step must hold:
#   1  the bundle validates in the harness and names its adapter
#   2  the CPU submission notebook is written from it (make_notebook.py: text files inside, adapter by sha256)
#   3  the adapter files are a private Kaggle dataset (a new version when the dataset exists)
#   4  the notebook is pushed and has finished, and its submission.zip unzips to the validated bundle, file by file
#   5  only then: results/ship_once.txt gets the line "owner/kernel version message". daily_ship.py submits that line
#      first, once, as soon as no run is pending, also inside a hold window (results/ship_hold.txt).
# A step that fails ends the script with nothing handed over (the hold then runs out by itself).
#   DRY=1            steps 1 and 2 only; nothing is sent to Kaggle and nothing is handed over
#   CHECK_ZIP=<zip>  only compares that zip with the bundle (the test of step 4's comparison)
#   SKIP_DS=1        step 3 is left out: the dataset named in DS is used as it is
#   NO_HANDOVER=1    stops after step 4 (the end-to-end test of Nov 22 ran with a throwaway kernel name and both switches)
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; K=$R/.venv/bin/kaggle; LOG=logs/ship_adapter.log
BUNDLE=${1:-submissions/budgetfit_v5_lora2}; BUNDLE=${BUNDLE%/}; NAME=$(basename $BUNDLE)
DS=${DS:-aagneye/gemma4-31b-lora2-adapter}; NB=${NB:-aagneye/gemma4-31b-budgetfit-v5-lora2}; TITLE=${TITLE:-Gemma4 31B Budgetfit V5 Lora2}
MSG=${MSG:-"$NAME: Budget-Fit V5 + round-2 adapter (rank 16); ADOPT on the 77 EVAL tasks, runtime rule OK (chain_r2)"}
S=tmp/ship_$NAME; mkdir -p $S logs
log() { echo "$(date -u) | $*" | tee -a $LOG; }
fail() { log "NOT HANDED OVER: $*"; exit 1; }
same_as_bundle() {   # same_as_bundle <zip>: the zip holds the bundle's files, nothing else, byte for byte
  rm -rf $S/unz $S/diff.txt; mkdir -p $S/unz
  unzip -q "$1" -d $S/unz 2> $S/diff.txt || return 1
  diff -r $BUNDLE $S/unz > $S/diff.txt 2>&1
}

if [ -n "${CHECK_ZIP:-}" ]; then
  same_as_bundle "$CHECK_ZIP" && echo "SAME: $CHECK_ZIP holds exactly $BUNDLE" || { echo "DIFFERENT (first lines of $S/diff.txt):"; head -5 $S/diff.txt; }
  exit 0
fi

# 1 the validated bundle
{ [ -f $BUNDLE/agent.yaml ] && grep -q "^adapter: main_lora" $BUNDLE/agent.yaml; } || fail "$BUNDLE has no adapter line"
[ -f $BUNDLE/adapters/main_lora/adapter_model.safetensors ] || fail "$BUNDLE has no adapter file"
( source harness-venv/bin/activate; python $V/make_submission.py --validate $BUNDLE 2>&1 | tail -1 ) | cut -c1-200 > $S/validate.txt
log "bundle $BUNDLE: $(cat $S/validate.txt)"
grep -q "^VALID" $S/validate.txt || fail "the harness does not validate $BUNDLE"

# 2 the notebook, written locally
rm -rf $S/nb
python3 $V/make_notebook.py $BUNDLE $S/nb $NB "$TITLE" --adapter-dataset $DS > $S/notebook.txt 2>&1 || fail "make_notebook.py: $(tail -1 $S/notebook.txt | cut -c1-200)"
log "notebook written: $(grep -o 'hash [0-9a-f]*' $S/notebook.txt | tail -1), dataset $DS, kernel $NB"
if [ -n "${DRY:-}" ]; then log "DRY: stopped before anything was sent to Kaggle"; exit 0; fi

# 3 the adapter as a private dataset
if [ -z "${SKIP_DS:-}" ]; then
  rm -rf $S/ds && mkdir -p $S/ds && cp $BUNDLE/adapters/main_lora/* $S/ds/
  printf '{"title": "%s", "id": "%s", "licenses": [{"name": "other"}]}\n' ${DS#*/} $DS > $S/ds/dataset-metadata.json
  if $K datasets status $DS 2>/dev/null | grep -qi ready; then
    $K datasets version -p $S/ds -m "$NAME $(date -u +%F)" 2>&1 | grep -v Warning | tail -1 | cut -c1-200 | tee -a $LOG
    sleep 60                                       # the new version takes a moment to show as the current one
  else
    $K datasets create -p $S/ds 2>&1 | grep -v Warning | tail -1 | cut -c1-200 | tee -a $LOG
  fi
  for i in $(seq 1 60); do $K datasets status $DS 2>/dev/null | grep -qi ready && break; sleep 30; done
fi
$K datasets status $DS 2>/dev/null | grep -qi ready || fail "the dataset $DS is not ready"

# 4 push, wait, compare (the notebook stops by itself when an adapter file's sha256 is not the bundle's)
$K kernels push -p $S/nb 2>&1 | grep -v Warning | tail -1 | cut -c1-240 > $S/push.txt; log "push: $(cat $S/push.txt)"
VER=$(grep -o "version [0-9]*" $S/push.txt | grep -o "[0-9]*" | tail -1)
[ -n "$VER" ] || fail "the push did not report a kernel version"
st=""; for i in $(seq 1 60); do sleep 30; st=$($K kernels status $NB 2>&1 | grep -v Warning | tail -1); echo "$st" | grep -qiE "complete|error|cancel" && break; done
log "notebook v$VER: $(echo "$st" | cut -c1-160)"
echo "$st" | grep -qi complete || fail "the notebook did not finish (see it on Kaggle)"
rm -rf $S/out; $K kernels output $NB -p $S/out > /dev/null 2>&1
[ -f $S/out/submission.zip ] || fail "the notebook's output has no submission.zip"
same_as_bundle $S/out/submission.zip || fail "the notebook's zip is not the validated bundle (first difference: $(head -1 $S/diff.txt | cut -c1-160))"
log "the notebook's submission.zip ($(du -m $S/out/submission.zip | cut -f1) MB) unzips to the validated bundle"

# 5 hand over
if [ -n "${NO_HANDOVER:-}" ]; then log "NO_HANDOVER: every check passed for $NB v$VER; nothing was handed over"; exit 0; fi
echo "$NB $VER $MSG" > results/ship_once.txt
log "HANDED OVER: $NB v$VER is in results/ship_once.txt; daily_ship.py submits it as soon as no run is pending"
