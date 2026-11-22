#!/usr/bin/env bash
# E4B side track (research/PLAN_E4B.md): several bundles side by side, ONE SERVER PER ARM. The E4B fits one T4, so the
# arms do not share a server and the clock scale stays the one measured for a single stream (3: 69 of 71 tasks agree
# with Kaggle, research/ledger/e4b_track.md). run_arms.sh cannot do this: it sends every arm to one port.
# Each arm runs in its own no-internet namespace (netns_run.sh bridges its port) and keeps its own request log.
#   LIST=results/lists/e4b_devA.txt [SCALE=3] [PORTS="8001 8002 8003 8004"] [DRY=1] \
#     bash e4b_arms.sh <bundle1> <tag1> [<bundle2> <tag2> ...]         (arm i uses the i-th port; the first arm is the base)
# Tags must start with e4b_ and be new: run_replica.sh deletes the folder of the tag it is given.
# Output per arm: results/replica/<tag>/ (results.csv, run log, clock ledger), results/requests/<tag>/ (request log),
# logs/rep_<tag>.out; results/replica/<tag1>/arms.md (arms_report.py). An arm whose server stops answering (3 checks,
# a minute apart) is ended: its folder stays without results.csv, so the chain runs it again.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; MODEL=gemma-4-e4b-it-qat-w4a16-ct
LIST=${LIST:?task list}; SCALE=${SCALE:-3}; PORTS=(${PORTS:-8001 8002 8003 8004}); DRY=${DRY:-}
[ $# -ge 2 ] && [ $(( $# % 2 )) -eq 0 ] || { echo "usage: e4b_arms.sh <bundle> <tag> [<bundle> <tag> ...]"; exit 1; }
[ $(( $# / 2 )) -le ${#PORTS[@]} ] || { echo "$(( $# / 2 )) arms but ${#PORTS[@]} ports"; exit 1; }
[ -s "$LIST" ] || { echo "no task list $LIST"; exit 1; }
NT=$(grep -vc '^#' "$LIST")
SUBS=(); TAGS=(); APORTS=()
while [ $# -ge 2 ]; do SUBS+=(${1%/}); TAGS+=($2); APORTS+=(${PORTS[${#TAGS[@]}-1]}); shift 2; done

# every check before anything starts
for k in "${!TAGS[@]}"; do
  S=${SUBS[$k]}; T=${TAGS[$k]}; P=${APORTS[$k]}
  case "$T" in e4b_*) ;; *) echo "the tag $T does not start with e4b_"; exit 1;; esac
  [ "$(printf '%s\n' "${TAGS[@]}" | grep -cx "$T")" = 1 ] || { echo "the tag $T is given twice"; exit 1; }
  [ -e results/replica/$T ] && { echo "the tag $T exists already (results/replica/$T): choose a new one"; exit 1; }
  [ -s $S/agent.yaml ] || { echo "missing bundle $S"; exit 1; }
  grep -q "^model: $MODEL$" $S/agent.yaml || { echo "$S is not an E4B bundle"; exit 1; }
  if [ -z "$DRY" ]; then
    curl -s -m 10 http://127.0.0.1:$P/v1/models | grep -q "\"$MODEL\"" || { echo "no E4B server on port $P (arm $T)"; exit 1; }
  fi
done
echo "$(date -u) e4b_arms: ${#TAGS[@]} arms, one server each, scale $SCALE, $LIST ($NT tasks)"

PIDS=(); PROBE=""
cleanup() {   # each arm is its own process group (setsid): end the whole group, not only its first process
  [ -n "$PROBE" ] && kill $PROBE 2>/dev/null
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill -TERM -- -$p 2>/dev/null; kill -TERM $p 2>/dev/null; done
}
trap cleanup EXIT; trap 'exit 143' TERM INT
for k in "${!TAGS[@]}"; do
  S=${SUBS[$k]}; T=${TAGS[$k]}; P=${APORTS[$k]}
  if [ -n "$DRY" ]; then
    echo "DRY arm $T: port $P, PORT=$P ROOT=data/rebench TASK_LIST=$LIST REPLICA_TIME_SCALE=$SCALE REQ_DUMP=results/requests/$T netns_run.sh run_replica.sh $S $T 0 auto 1"
    continue
  fi
  # setsid: a background job of a script is not a group leader, so setsid does not fork and $! leads the new group
  setsid env PORT=$P ROOT=data/rebench ORDER_CSV=results/rebench_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=$LIST \
    REPLICA_TIME_SCALE=$SCALE REQ_DUMP=$R/results/requests/$T \
    bash $V/netns_run.sh bash $V/run_replica.sh $S $T 0 auto 1 > logs/rep_$T.out 2>&1 &
  PIDS+=($!); echo "arm $T: bundle $S, port $P, pid $!"
done
[ -n "$DRY" ] && { trap - EXIT; exit 0; }

( FAILS=(); for k in "${!PIDS[@]}"; do FAILS+=(0); done
  while sleep 60; do
    for k in "${!PIDS[@]}"; do
      kill -0 ${PIDS[$k]} 2>/dev/null || continue
      if curl -s -m 20 http://127.0.0.1:${APORTS[$k]}/v1/models | grep -q '"id"'; then FAILS[$k]=0; else FAILS[$k]=$(( ${FAILS[$k]} + 1 )); fi
      if [ ${FAILS[$k]} -ge 3 ]; then
        echo "$(date -u) ALERT: the server on port ${APORTS[$k]} does not answer; ending arm ${TAGS[$k]}"
        kill -TERM -- -${PIDS[$k]} 2>/dev/null; kill -TERM ${PIDS[$k]} 2>/dev/null
      fi
    done
  done ) &
PROBE=$!
wait "${PIDS[@]}"
kill $PROBE 2>/dev/null; PROBE=""; trap - EXIT

DIRS=()
for T in "${TAGS[@]}"; do
  if [ -s results/replica/$T/results.csv ]; then
    DIRS+=(results/replica/$T); tail -1 logs/rep_$T.out
    grep -q " scale=$SCALE " results/replica/$T/run.log || echo "WARNING: $T did not run at scale $SCALE"
    grep -q "model request timeout" results/replica/$T/run.log || echo "WARNING: $T shows no request-timeout line (run.log)"
  else
    echo "arm $T did NOT finish (no results.csv); last line: $(tail -1 logs/rep_$T.out | cut -c1-160)"
  fi
done
if [ ${#DIRS[@]} -ge 2 ] && [ -f $V/arms_report.py ]; then
  python3 $V/arms_report.py "${DIRS[@]}" --out ${DIRS[0]}/arms.md 2>&1 | tail -30
fi
echo "$(date -u) e4b_arms done"
