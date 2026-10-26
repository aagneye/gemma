#!/usr/bin/env bash
# Recover the VM E4B track when the shared GPUs are all taken: poll until one of our allowed GPUs is free, start the
# E4B server there at once (LoRA-enabled, adapter mounted) and run the held-out evaluation; the server then stays up
# (hot-swap further adapters with eval_adapter_replica.sh) so the card is not released again.
#   ADAPTER_DIR=runs/e4b_r32_v1/final TAG=e4b_v5_lora1_rich REPO_FILTER=rich PORT=8002 bash grab_gpu_and_eval.sh
R=/mnt/biohub/kdata/gemma4; cd $R; LOG=logs/grab_gpu.log
ADAPTER_DIR=${ADAPTER_DIR:-runs/e4b_r32_v1/final}; TAG=${TAG:-e4b_v5_lora1_rich}; REPO_FILTER=${REPO_FILTER:-rich}; PORT=${PORT:-8002}
BASE=${BASE:-submissions/e4b_v5}; BASELINE=${BASELINE:-results/replica/e4b_v5}; ALLOWED=${ALLOWED:-1 2 3}
log() { echo "$(date -u) | $*" >> $LOG; }
log "waiting for a free GPU among: $ALLOWED (adapter $ADAPTER_DIR, tag $TAG)"
while true; do
  for g in $ALLOWED; do
    used=$(nvidia-smi -i $g --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
    apps=$(nvidia-smi -i $g --query-compute-apps=pid --format=csv,noheader | grep -c .)
    if [ "${used:-99999}" -lt 500 ] && [ "$apps" = 0 ]; then
      log "GPU $g is free -> starting the E4B server with the adapter (port $PORT)"
      [ -d submissions/$TAG/adapters/main_lora ] || { source harness-venv/bin/activate; python ~/gemma4_vm/make_submission.py --bundle $BASE --model gemma-4-e4b-it-qat-w4a16-ct --adapter $ADAPTER_DIR --out submissions/$TAG >> $LOG 2>&1; deactivate; }
      tmux kill-session -t vllm_$PORT 2>/dev/null
      MODEL=gemma-4-e4b-it-qat-w4a16-ct TP=1 GPUS=$g PORT=$PORT LORA_DYNAMIC=1 ADAPTER=submissions/$TAG/adapters/main_lora bash ~/gemma4_vm/wait_vllm.sh >> $LOG 2>&1
      if curl -s -m 10 http://127.0.0.1:$PORT/v1/models | grep -q '"main_lora"'; then
        log "server up on GPU $g with main_lora; running the $REPO_FILTER evaluation"
        PORT=$PORT REPLICA_TIME_SCALE=3 REPO_FILTER=$REPO_FILTER bash ~/gemma4_vm/run_replica.sh submissions/$TAG $TAG 71 auto 1 >> $LOG 2>&1
        python3 ~/gemma4_vm/compare_runs.py $BASELINE results/replica/$TAG >> $LOG 2>&1
        python3 ~/gemma4_vm/analyze_traces.py results/replica/$TAG 2>/dev/null | grep -E "^MODES|stop reasons|edit-error" >> $LOG
        log "done $TAG (server kept up on port $PORT, GPU $g)"; exit 0
      fi
      log "server did not come up on GPU $g (taken again?); keep waiting"
    fi
  done
  sleep 45
done
