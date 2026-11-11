#!/usr/bin/env bash
# Run several bundles side by side against ONE vLLM server (same tasks, same clock scale, same load), each at
# concurrency CONC, then print each arm's result line and, when the run-log tools are deployed, the side-by-side table.
# Generalises run_pair.sh: one shared base for several candidates (a "screen" of the Nov 11 plan: 4 arms x 48 dev tasks).
# The clock scale follows the TOTAL load: 4 requests -> SCALE 9 (measured Nov 2), so keep arms x CONC = 4.
#   [PORT=8000] [SCALE=9] [CONC=1] [N=50] [TASK_LIST=..] [ROOT=..] [ORDER_CSV=..] [VENV=..] [GROUPS_CSV=csv] \
#     bash run_arms.sh <sub1> <tag1> <sub2> <tag2> [<sub3> <tag3> ...]      (the first arm is the base)
# Output: results/replica/<tag>/ per arm; results/replica/<tag1>/arms.md when ~/gemma4_vm/arms_report.py exists.
set -u
[ $# -ge 4 ] && [ $(( $# % 2 )) -eq 0 ] || { echo "usage: run_arms.sh <sub> <tag> <sub> <tag> ..."; exit 1; }
PORT=${PORT:-8000}; SCALE=${SCALE:-9}; N=${N:-50}; CONC=${CONC:-1}
R=/mnt/biohub/kdata/gemma4; cd $R
curl -s -m 10 http://127.0.0.1:$PORT/v1/models | grep -q '"id"' || { echo "no vLLM server on port $PORT; abort"; exit 1; }
echo "$(date -u) run_arms $(( $# / 2 )) arms port=$PORT scale=$SCALE n=$N conc=$CONC each list=${TASK_LIST:-}"
TAGS=()
while [ $# -ge 2 ]; do
  S=$1; T=$2; shift 2; TAGS+=($T)
  PORT=$PORT REPLICA_TIME_SCALE=$SCALE bash ~/gemma4_vm/run_replica.sh $S $T $N auto $CONC > logs/rep_$T.out 2>&1 &
done
wait
for T in "${TAGS[@]}"; do tail -1 logs/rep_$T.out; done
if [ -f ~/gemma4_vm/arms_report.py ]; then
  DIRS=(); for T in "${TAGS[@]}"; do DIRS+=(results/replica/$T); done
  python3 ~/gemma4_vm/arms_report.py "${DIRS[@]}" ${GROUPS_CSV:+--groups $GROUPS_CSV} --out results/replica/${TAGS[0]}/arms.md 2>&1 | tail -40
fi
echo "$(date -u) run_arms done"
