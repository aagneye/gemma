#!/usr/bin/env bash
# Run two bundles at the same time against ONE vLLM server (same tasks, same order, same clock scale, same load),
# then write their paired comparison. Both runs share the load, so the pairing stays fair.
# The 31B server on 4xT4 is close to saturated already at one request (~14 tok/s total at 1 running, ~17 at 4), so a
# pair does not finish more tasks per hour than a single run; it makes the two runs comparable. More load makes every
# request slower: measured 2026-11-02, a task takes ~5x its Kaggle time with 2 requests running and ~8-9x with 4,
# so SCALE must follow the total load (scale 5.5 at 4 requests timed out a task Kaggle finished in 325 s).
#   [PORT=8000] [SCALE=9] [N=50] [CONC=2] bash run_pair.sh <baseline_sub> <base_tag> <candidate_sub> <cand_tag>
# Output: results/replica/<tag>/ for both runs, results/replica/<cand_tag>/compare_pair.txt
set -u
BS=${1:?baseline submission}; BT=${2:?baseline tag}; CS=${3:?candidate submission}; CT=${4:?candidate tag}
PORT=${PORT:-8000}; SCALE=${SCALE:-9}; N=${N:-50}; CONC=${CONC:-2}
R=/mnt/biohub/kdata/gemma4; cd $R
curl -s -m 10 http://127.0.0.1:$PORT/v1/models | grep -q '"id"' || { echo "no vLLM server on port $PORT; abort"; exit 1; }
echo "$(date -u) run_pair $BT vs $CT port=$PORT scale=$SCALE n=$N conc=$CONC each"
PORT=$PORT REPLICA_TIME_SCALE=$SCALE bash ~/gemma4_vm/run_replica.sh $BS $BT $N auto $CONC > logs/rep_$BT.out 2>&1 &
PORT=$PORT REPLICA_TIME_SCALE=$SCALE bash ~/gemma4_vm/run_replica.sh $CS $CT $N auto $CONC > logs/rep_$CT.out 2>&1 &
wait
tail -1 logs/rep_$BT.out; tail -1 logs/rep_$CT.out
python3 ~/gemma4_vm/compare_runs.py results/replica/$BT results/replica/$CT > results/replica/$CT/compare_pair.txt 2>&1
head -6 results/replica/$CT/compare_pair.txt
echo "$(date -u) run_pair done"
