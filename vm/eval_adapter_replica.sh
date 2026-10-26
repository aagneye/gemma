#!/usr/bin/env bash
# Evaluate a LoRA adapter on the VM replica (cross-fit): package it into a bundle, serve the base model WITH the
# adapter on one free T4 (vLLM --lora-modules, like the scorer), run the Kaggle-sound tasks of the held-out repo,
# and print the paired comparison against the base bundle's replica run.
#   GPU=1 PORT=8001 REPO_FILTER=rich BASE=submissions/e4b_v5 BASELINE=results/replica/e4b_v5 \
#     bash eval_adapter_replica.sh <peft_adapter_dir> <tag> [scale=3]
# Gates (CLAUDE.md): adopt only on >= +3 tasks paired with no time regression; this script only measures.
set -u
ADAPTER=${1:?peft adapter dir}; TAG=${2:?tag}; SCALE=${3:-3}
GPU=${GPU:-1}; PORT=${PORT:-8001}; REPO_FILTER=${REPO_FILTER:-rich}; BASE=${BASE:-submissions/e4b_v5}; BASELINE=${BASELINE:-results/replica/e4b_v5}
MODEL=${MODEL:-gemma-4-e4b-it-qat-w4a16-ct}
R=/mnt/biohub/kdata/gemma4; cd $R; LOG=logs/eval_adapter_$TAG.log
log() { echo "$(date -u) | $*" | tee -a $LOG; }
# 1. package (G0 checks inside make_submission.py) and validate
source harness-venv/bin/activate
python ~/gemma4_vm/make_submission.py --bundle $BASE --model $MODEL --adapter $ADAPTER --out submissions/$TAG 2>&1 | tail -3 | tee -a $LOG
python ~/gemma4_vm/make_submission.py --validate submissions/$TAG 2>&1 | tail -1 | tee -a $LOG
grep -q "^adapter: main_lora" submissions/$TAG/agent.yaml || { log "bundle has no adapter line; abort"; exit 1; }
deactivate
# 2. serve base + adapter on the chosen GPU. If a LoRA-enabled server already runs on PORT (started with LORA_DYNAMIC=1),
#    hot-swap the adapter through the runtime API instead of restarting: a restart frees the GPU for about a minute and
#    on this shared VM another project takes free cards within minutes. Otherwise restart: vLLM's workers keep the GPU
#    memory for a while after the tmux session dies, so wait until the card is really free. Never touch GPU 0.
[ "$GPU" = 0 ] && { log "GPU 0 belongs to another project; abort"; exit 1; }
AP=$R/submissions/$TAG/adapters/main_lora
if curl -s -m 10 http://127.0.0.1:$PORT/v1/models | grep -q "\"$MODEL\"" && [ -n "${HOT_SWAP:-1}" ]; then
  curl -s -m 30 -X POST http://127.0.0.1:$PORT/v1/unload_lora_adapter -H "Content-Type: application/json" -d '{"lora_name": "main_lora"}' > /dev/null 2>&1
  resp=$(curl -s -m 120 -X POST http://127.0.0.1:$PORT/v1/load_lora_adapter -H "Content-Type: application/json" -d "{\"lora_name\": \"main_lora\", \"lora_path\": \"$AP\"}")
  if curl -s -m 10 http://127.0.0.1:$PORT/v1/models | grep -q '"main_lora"'; then
    log "hot-loaded adapter $AP as main_lora on the running server (port $PORT)"
    PORT=$PORT REPLICA_TIME_SCALE=$SCALE REPO_FILTER=$REPO_FILTER FIRST=${FIRST:-} bash -c '
      if [ -n "$FIRST" ]; then bash ~/gemma4_vm/run_replica.sh submissions/'"$TAG"' '"$TAG"' $FIRST auto 1; else bash ~/gemma4_vm/run_replica.sh submissions/'"$TAG"' '"$TAG"' 71 auto 1; fi' 2>&1 | tail -1 | tee -a $LOG
    python3 ~/gemma4_vm/compare_runs.py $BASELINE results/replica/$TAG 2>&1 | tee -a $LOG
    python3 ~/gemma4_vm/analyze_traces.py results/replica/$TAG 2>/dev/null | grep -E "^MODES|stop reasons|edit-error" | tee -a $LOG
    log "done $TAG"; exit 0
  fi
  log "hot load failed (server answer: ${resp:0:200}); falling back to a restart"
fi
tmux kill-session -t vllm_$PORT 2>/dev/null
for i in $(seq 1 36); do
  used=$(nvidia-smi -i $GPU --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
  [ "${used:-99999}" -lt 1000 ] && break
  if [ $i -eq 12 ]; then
    for p in $(nvidia-smi -i $GPU --query-compute-apps=pid --format=csv,noheader | tr -d ' '); do
      ps -o cmd= -p $p 2>/dev/null | grep -qi "vllm" && { log "killing lingering vLLM pid $p on GPU $GPU"; kill $p 2>/dev/null; }
    done
  fi
  sleep 5
done
log "GPU $GPU memory used before start: ${used:-?} MiB"
if [ "${used:-99999}" -ge 1000 ]; then
  for p in $(nvidia-smi -i $GPU --query-compute-apps=pid --format=csv,noheader | tr -d ' '); do log "  holder pid $p: $(ps -o etime=,cmd= -p $p 2>/dev/null | cut -c1-120)"; done
  log "GPU $GPU is not free (another job holds it); abort instead of starting vLLM on a busy card"; exit 1
fi
MODEL=$MODEL TP=1 GPUS=$GPU PORT=$PORT LORA_DYNAMIC=1 ADAPTER=submissions/$TAG/adapters/main_lora bash ~/gemma4_vm/wait_vllm.sh 2>&1 | tail -3 | tee -a $LOG
curl -s -m 10 http://127.0.0.1:$PORT/v1/models | grep -q '"main_lora"' && log "adapter main_lora is served on port $PORT" || { log "adapter NOT listed by vLLM on port $PORT; abort"; exit 1; }
# 3. replica run on the held-out repo (or FIRST=n tasks in the standard order for a smoke test), then the paired comparison
if [ -n "${FIRST:-}" ]; then
  PORT=$PORT REPLICA_TIME_SCALE=$SCALE bash ~/gemma4_vm/run_replica.sh submissions/$TAG $TAG $FIRST auto 1 2>&1 | tail -1 | tee -a $LOG
else
  PORT=$PORT REPLICA_TIME_SCALE=$SCALE REPO_FILTER=$REPO_FILTER bash ~/gemma4_vm/run_replica.sh submissions/$TAG $TAG 71 auto 1 2>&1 | tail -1 | tee -a $LOG
fi
python3 ~/gemma4_vm/compare_runs.py $BASELINE results/replica/$TAG 2>&1 | tee -a $LOG
python3 ~/gemma4_vm/analyze_traces.py results/replica/$TAG 2>/dev/null | grep -E "^MODES|stop reasons|edit-error" | tee -a $LOG
log "done $TAG"
