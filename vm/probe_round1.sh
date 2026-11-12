#!/bin/bash
# Probe round 1 (Loop 1 of the Nov 11 instruction plan). Run it in the GPU gap right after Screen A:
#   1. calibration: replay 150 edit points + 150 read points of bf5_train under the UNCHANGED Budget-Fit V5 prompt and
#      compare the garbled-edit and range-less-read shares with the recorded ones (pass = within 5 points);
#   2. comparison: the same points under budgetfit_e1r1 and budgetfit_d1 (the V5 column reuses step 1).
# Output: $MD (default results/probes/round1.md) and the raw replies in $OUT/results.jsonl. Re-running resumes.
#
#   bash ~/gemma4_vm/probe_round1.sh [N=150 points per kind] [CONC=4]
#   env: OUT, MD, RUN (results/replica/bf5_train), PROBE (probe.py), BUDGET_MIN (170: stops sending after this many
#        minutes so the round ends within 3 h), ALLOW (tmux sessions that are not test runs; the chain runs in `instr`),
#        LEDGER (request ledger for the 30/hour rule), MIN_POINTS (calibration needs this many points per rate; default
#        90% of N, so a few failed or late requests do not fail it on the count alone).
# While a test run is alive (tmux gate1 / rep_* / instr unless listed in ALLOW, or any run_arms.sh / run_replica.sh /
# run_pair.sh process, which catches a screen inside `instr`) probe.py drops to concurrency 1 and 30 requests per hour
# by itself, so starting this script too early is harmless: it reports a partial table.
# Exit code: 0 = calibration passed, 3 = calibration failed (the table is then not to be used for decisions).
set -u
R=${GEMMA_ROOT:-/mnt/biohub/kdata/gemma4}; cd "$R" || exit 1
N=${1:-150}; CONC=${2:-4}
PROBE=${PROBE:-$HOME/gemma4_vm/probe.py}
RUN=${RUN:-results/replica/bf5_train}
OUT=${OUT:-$R/results/probes/round1}; MD=${MD:-$R/results/probes/round1.md}
BUDGET_MIN=${BUDGET_MIN:-170}; ALLOW=${ALLOW:-instr}; LEDGER=${LEDGER:-$R/results/probes/rate_ledger.txt}
MIN_POINTS=${MIN_POINTS:-$((N * 9 / 10))}
BASE=submissions/budgetfit_v5/prompts/system.md
START=$(date +%s); END=$((START + BUDGET_MIN * 60)); CAL_END=$((START + BUDGET_MIN * 24))   # calibration gets 40% of the time
mkdir -p "$OUT" "$(dirname "$MD")"
for f in $BASE submissions/budgetfit_e1r1/prompts/system.md submissions/budgetfit_d1/prompts/system.md; do
  [ -s "$f" ] || { echo "missing $f"; exit 1; }
done

[ -s "$OUT/points.jsonl" ] || python3 "$PROBE" points --run "$RUN" --bundle submissions/budgetfit_v5 --kinds edit,read --n "$N" \
  --out "$OUT/points.jsonl" | tee "$OUT/points.log"

common="--points $OUT/points.jsonl --base $BASE --out $OUT --concurrency $CONC --allow-sessions $ALLOW --ledger $LEDGER"
echo "$(date -u) step 1: calibration (unchanged prompt)"
python3 "$PROBE" replay $common --variant v5=$BASE --deadline-epoch $CAL_END 2>&1 | tee -a "$OUT/replay.log"
python3 "$PROBE" calibrate --out "$OUT" --variant v5 --min-points "$MIN_POINTS" | tee -a "$OUT/replay.log"

echo "$(date -u) step 2: comparison (e1r1, d1)"
python3 "$PROBE" replay $common --variant e1r1=submissions/budgetfit_e1r1/prompts/system.md \
  --variant d1=submissions/budgetfit_d1/prompts/system.md --deadline-epoch $END 2>&1 | tee -a "$OUT/replay.log"
# whatever step 1 could not send within its share of the time
python3 "$PROBE" replay $common --variant v5=$BASE --deadline-epoch $END 2>&1 | tee -a "$OUT/replay.log"

{ echo "# Probe round 1: $(date -u '+%Y-%m-%d %H:%M UTC')"; echo
  echo "Run: $RUN. $(head -1 "$OUT/points.log" 2>/dev/null)"; echo; } > "$MD"
python3 "$PROBE" calibrate --out "$OUT" --variant v5 --min-points "$MIN_POINTS" --md "$MD" --append > /dev/null; CAL=$?
[ $CAL -eq 0 ] || { echo "**Calibration did not pass: do not use the comparison below for decisions.**"; echo; } >> "$MD"
python3 "$PROBE" score --out "$OUT" --variants v5,e1r1,d1 --base-name v5 --md "$MD" --append > /dev/null
echo "Elapsed: $(( ($(date +%s) - START) / 60 )) min. Raw replies: $OUT/results.jsonl." >> "$MD"
cat "$MD"
exit $CAL
