#!/usr/bin/env bash
# Queue runner for the VM replica scorer. The VM is shared: wait until the GPUs this server needs have enough free
# memory, start vLLM (wait_vllm.sh), then run the queue one bundle at a time (concurrency 1 = like the scorer, clock
# scaled by REPLICA_TIME_SCALE). Defaults = the 31B on all four GPUs (TP=4, port 8000, scale 10); for the E4B run one
# queue per free T4:  MODEL=gemma-4-e4b-it-qat-w4a16-ct TP=1 GPUS=2 PORT=8002 REPLICA_TIME_SCALE=3 NEED_MIB=15000 \
#                     bash opportunistic_replica.sh results/e4b_queue_8002.txt
#   bash opportunistic_replica.sh <queue_file>     # queue lines: "<bundle_dir> <tag> <n_tasks>"; done lines get "#DONE"
# The time budget of each run is the bundle's own max_time_minutes (run_replica.sh "auto"); CONC = tasks in parallel.
Q=${1:?queue file}; R=/mnt/biohub/kdata/gemma4; cd $R
MODEL=${MODEL:-gemma-4-31b-it-qat-w4a16-ct}; TP=${TP:-4}; GPUS=${GPUS:-}; PORT=${PORT:-8000}; CONC=${CONC:-1}
NEED_MIB=${NEED_MIB:-12200}; MEM=${MEM:-}; export REPLICA_TIME_SCALE=${REPLICA_TIME_SCALE:-10} PORT
LOG=logs/opportunistic_$PORT.log; [ "$PORT" = 8000 ] && LOG=logs/opportunistic.log
# GPU 0 belongs to another project: never use it unless GPUS names it explicitly. With GPUS empty, take every other GPU;
# refuse to start when fewer GPUs remain than TP needs (the 31B with TP=4 cannot run on this shared VM).
EXCLUDE_GPUS=${EXCLUDE_GPUS:-0}
if [ -z "$GPUS" ]; then
  GPUS=$(nvidia-smi --query-gpu=index --format=csv,noheader | tr -d ' ' | grep -vxF -f <(echo "$EXCLUDE_GPUS" | tr ',' '\n') | paste -sd,)
fi
if [ "$(echo "$GPUS" | tr ',' '\n' | grep -c .)" -lt "$TP" ]; then
  echo "$(date -u) refusing to start $MODEL: TP=$TP needs more GPUs than allowed ($GPUS; excluded $EXCLUDE_GPUS)" >> $LOG; exit 2
fi
case "$MODEL" in *31b*) KEY=31b;; *12b*) KEY=12b;; *e4b*) KEY=e4b;; *e2b*) KEY=e2b;; *) KEY=$MODEL;; esac
free_ok() {   # every GPU we will use (GPUS, or all) must have >= NEED_MIB free
  nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits | tr -d ' ' |
    awk -F, -v n=$NEED_MIB -v g="$GPUS" 'BEGIN{split(g,a,","); for(i in a) want[a[i]]=1} (g==""||($1 in want)) && $2<n{bad=1} END{exit bad}'
}
served() { curl -s -m 5 http://127.0.0.1:$PORT/v1/models | grep -q "$KEY"; }
while grep -qv '^#' "$Q"; do
  line=$(grep -v '^#' "$Q" | head -1); set -- $line; B=$1; TAG=$2; N=${3:-50}
  if ! served; then
    until free_ok; do sleep 300; done
    echo "$(date -u) GPUs ${GPUS:-all} free -> starting $MODEL (TP $TP, port $PORT, MEM ${MEM:-default})" >> $LOG
    MODEL=$MODEL TP=$TP GPUS=$GPUS PORT=$PORT MEM=$MEM bash ~/gemma4_vm/wait_vllm.sh >> $LOG 2>&1
    served || { echo "$(date -u) vLLM start failed; retry in 10 min" >> $LOG; sleep 600; continue; }
  fi
  echo "$(date -u) replica $TAG ($B, $N tasks, scale $REPLICA_TIME_SCALE, conc $CONC, port $PORT)" >> $LOG
  bash ~/gemma4_vm/run_replica.sh "$B" "$TAG" "$N" auto $CONC >> $LOG 2>&1
  if grep -q "REPLICA_DONE results/replica/$TAG " $LOG && [ -f results/replica/$TAG/results.csv ]; then
    sed -i "s|^$B $TAG|#DONE $B $TAG|" "$Q"
    echo "$(date -u) done $TAG: $(tail -1 results/replica/$TAG/run.log | cut -c1-160)" >> $LOG
  else
    echo "$(date -u) replica $TAG incomplete (vLLM lost?); will retry" >> $LOG; sleep 300
  fi
done
echo "$(date -u) queue empty" >> $LOG
