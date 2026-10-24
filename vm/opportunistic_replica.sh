#!/usr/bin/env bash
# The VM is shared: wait until every GPU has enough free memory for the 31B (TP=4), then start vLLM and run the
# replica queue one bundle at a time (concurrency 1 = like the scorer, clock scaled by REPLICA_TIME_SCALE).
#   bash opportunistic_replica.sh <queue_file>     # queue lines: "<bundle_dir> <tag> <n_tasks>"; done lines get "#DONE"
Q=${1:?queue file}; R=/mnt/biohub/kdata/gemma4; cd $R; LOG=logs/opportunistic.log
NEED_MIB=${NEED_MIB:-12200}; MEM=${MEM:-0.76}; export REPLICA_TIME_SCALE=${REPLICA_TIME_SCALE:-10}
free_ok() { nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | awk -v n=$NEED_MIB '$1<n{bad=1} END{exit bad}'; }
while grep -qv '^#' "$Q"; do
  line=$(grep -v '^#' "$Q" | head -1); set -- $line; B=$1; TAG=$2; N=${3:-50}
  if ! curl -s -m 5 http://127.0.0.1:8000/v1/models | grep -q 31b; then
    until free_ok; do sleep 300; done
    echo "$(date -u) GPUs free -> starting 31B (MEM $MEM)" >> $LOG
    MODEL=gemma-4-31b-it-qat-w4a16-ct MEM=$MEM bash ~/gemma4_vm/wait_vllm.sh >> $LOG 2>&1
    curl -s -m 5 http://127.0.0.1:8000/v1/models | grep -q 31b || { echo "$(date -u) vLLM start failed; retry in 10 min" >> $LOG; sleep 600; continue; }
  fi
  echo "$(date -u) replica $TAG ($B, $N tasks, scale $REPLICA_TIME_SCALE)" >> $LOG
  bash ~/gemma4_vm/run_replica.sh "$B" "$TAG" "$N" 8 1 >> $LOG 2>&1
  if grep -q "REPLICA_DONE" $LOG && [ -f results/replica/$TAG/results.csv ]; then
    sed -i "s|^$B $TAG|#DONE $B $TAG|" "$Q"
  else
    echo "$(date -u) replica $TAG incomplete (vLLM lost?); will retry" >> $LOG; sleep 300
  fi
done
echo "$(date -u) queue empty" >> $LOG
