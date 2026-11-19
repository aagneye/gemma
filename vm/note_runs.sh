#!/usr/bin/env bash
# Note runs (Nov 19, round-2 plan steps 2 and 3): Budget-Fit V5 on practice tasks through the note relay
# (takeover_proxy.py), with the internet cut off (netns_run.sh). One call = one pool and one task list.
#   TAG=r2_pilot_train POOL=rebench LIST=results/lists/r2_pilot_train.txt HINTS=datasets/r2/hints_train.jsonl \
#     [POSITION=A] [DEADLINE=12] [CONC=4] [RELAY_PORT=8100] [SCALE=9] bash note_runs.sh
# rebench2 tasks run with VENV=scorer-host-venv-plus (their soundness was measured with it); set from POOL.
# Two pools can run side by side on different RELAY_PORTs (share the concurrency between them).
# Output: results/replica/$TAG (the run, with notes.md), results/takeover/$TAG (the relay's journal: every request and
# reply, events.jsonl), results/requests/$TAG (request log), logs/$TAG.relay.log. The plain server on :8000 must be up.
# A reused TAG is overwritten (run_replica.sh removes the run folder; the journal folder is removed here).
set -u
R=/mnt/biohub/kdata/gemma4; cd $R
TAG=${TAG:?}; POOL=${POOL:?rebench or rebench2}; LIST=${LIST:?}; HINTS=${HINTS:?}
POSITION=${POSITION:-A}; DEADLINE=${DEADLINE:-12}; CONC=${CONC:-4}; RP=${RELAY_PORT:-8100}; SCALE=${SCALE:-9}
curl -s -m 10 http://127.0.0.1:8000/v1/models | grep -q gemma-4-31b || { echo "no model server on :8000"; exit 1; }
J=results/takeover/$TAG; rm -rf $J; mkdir -p $J
python3 ~/gemma4_vm/takeover_proxy.py --listen $RP --upstream 127.0.0.1:8000 --hints $HINTS --journal $J \
  --position $POSITION --deadline $DEADLINE > logs/$TAG.relay.log 2>&1 &
RELAY=$!; trap 'kill $RELAY 2>/dev/null' EXIT
for i in $(seq 1 20); do curl -s -m 5 http://127.0.0.1:$RP/v1/models | grep -q gemma-4-31b && break; sleep 1; done
curl -s -m 5 http://127.0.0.1:$RP/v1/models | grep -q gemma-4-31b || { echo "the relay does not answer on :$RP"; exit 1; }
# one tiny request through the relay to the model: a broken relay must stop the run here, not after an hour
curl -s -m 300 http://127.0.0.1:$RP/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model": "gemma-4-31b-it-qat-w4a16-ct", "messages": [{"role": "user", "content": "Say ok."}], "max_tokens": 4}' | grep -q '"choices"' \
  || { echo "the relay does not pass a request to the model"; exit 1; }
[ "$POOL" = rebench2 ] && export VENV=scorer-host-venv-plus
echo "$(date -u) note_runs $TAG: pool $POOL, list $LIST ($(grep -vc '^#' $LIST) tasks), position $POSITION, deadline $DEADLINE, concurrency $CONC"
PORT=$RP ROOT=data/$POOL ORDER_CSV=results/${POOL}_soundness.csv TMPDIR=$R/tmp/replica TASK_LIST=$LIST REPLICA_TIME_SCALE=$SCALE \
  REQ_DUMP=$R/results/requests/$TAG bash ~/gemma4_vm/netns_run.sh bash ~/gemma4_vm/run_replica.sh submissions/budgetfit_v5 $TAG 0 auto $CONC | tail -1
python3 ~/gemma4_vm/note_report.py $TAG --hints $HINTS > results/replica/$TAG/notes.md 2>&1
head -14 results/replica/$TAG/notes.md
echo "$(date -u) note_runs $TAG done"
