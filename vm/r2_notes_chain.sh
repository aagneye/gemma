#!/usr/bin/env bash
# Round-2 note runs in order, inside a fixed time box (Nov 19, plan step 3). Every group is cut into chunks; the box
# is checked before each chunk, so the chain ends at most one chunk after the box closes. A chunk that already has
# results is skipped, so the chain can be started again after a stop.
#   [POSITION=A] [BOX_HOURS=40 | BOX_END=<epoch seconds>] [CHUNK=40] [WAIT_FOR=<tmux session>] bash r2_notes_chain.sh
#   DRY=1 prints the chunks in order and runs nothing (own tmp folder; LOG=/tmp/x.log keeps the real log clean).
# Groups, in this order (results/lists/r2_tk_<name>.txt; the plan: small fixes of both pools first):
#   train      failed TRAIN tasks where the note comes on the recorded run, tasks 1-60 of the list
#              (its 55 clean small fixes come first)                            (pool rebench)
#   dev        failed dev tasks, held out for the check after training          (pool rebench)
#              (second since Nov 21: the plan's held-out check needs these rows even if the box closes early)
#   rb2_clean  rebench2 tasks with a clean small fix, never run before          (pool rebench2)
#   train_big  tasks 61-84 of the train list, the larger fixes (behind the small fixes since Nov 21: at the measured
#              6 tasks an hour the box holds about 180 runs, and a small fix gives more clean examples per run)
#   rb2_rest   the other rebench2 tasks with blocks                             (pool rebench2)
# Output per chunk: results/replica/r2_tk_<name>_<nn>, results/takeover/r2_tk_<name>_<nn>; log logs/r2_notes.log.
# Shared VM: the server is started only when all four cards are free; other jobs are never touched.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; POS=${POSITION:-A}; BOX=${BOX_HOURS:-40}; CHUNK=${CHUNK:-40}; LOG=${LOG:-logs/r2_notes.log}
MODEL=gemma-4-31b-it-qat-w4a16-ct
[ -n "${WAIT_FOR:-}" ] && bash ~/gemma4_vm/after_session.sh $WAIT_FOR
log() { echo "$(date -u) | $*" | tee -a $LOG; }
up() { curl -s -m 10 http://127.0.0.1:8000/v1/models | grep -q "$MODEL"; }
free() { for u in $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits); do [ "$u" -lt 1000 ] || return 1; done; }
ensure_server() {
  up && return 0
  log "the model server is down"
  free || { log "a GPU is held by another job: the chain stops (nothing of theirs was touched)"; return 1; }
  [ "$(MODEL=$MODEL bash ~/gemma4_vm/wait_vllm.sh | head -1)" = READY ] && up
}
END=${BOX_END:-$(( $(date +%s) + BOX * 3600 ))}          # BOX_END=<epoch seconds> keeps the box's end after a restart
log "note runs start: position $POS, box until $(date -u -d @$END), chunks of $CHUNK"
T=tmp/r2; [ -n "${DRY:-}" ] && T=tmp/r2dry; mkdir -p $T
# group = name, pool, hints file, first and last task of the list (the list is r2_tk_<name without _big>.txt)
for g in "train rebench hints_train 1 60" "dev rebench hints_train" "rb2_clean rebench2 hints_rb2" \
         "train_big rebench hints_train 61" "rb2_rest rebench2 hints_rb2"; do
  set -- $g; name=$1; pool=$2; hints=datasets/r2/$3.jsonl; from=${4:-1}; to=${5:-100000}
  rm -f $T/chunk_${name}_[0-9]*
  grep -v '^#' results/lists/r2_tk_${name%_big}.txt | sed -n "${from},${to}p" | split -l $CHUNK -d - $T/chunk_${name}_
  for c in $T/chunk_${name}_[0-9]*; do
    [ $(date +%s) -lt $END ] || { log "the time box is closed: stop before $c"; break 2; }
    tag=r2_tk_${name}_${c##*_}
    [ -f results/replica/$tag/results.csv ] && { log "$tag has results: skipped"; continue; }
    [ -n "${DRY:-}" ] && { echo "$tag $pool $hints $(wc -l < $c) tasks, first $(head -1 $c)"; continue; }
    ensure_server || exit 1
    TAG=$tag POOL=$pool LIST=$c HINTS=$hints POSITION=$POS bash ~/gemma4_vm/note_runs.sh > logs/$tag.log 2>&1
    log "$tag: $(grep -E 'REPLICA_DONE|Clean examples|Note given' logs/$tag.log | tr '\n' ' ' | cut -c1-300)"
  done
done
log "note runs done"
