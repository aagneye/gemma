#!/usr/bin/env bash
# T4 side of the round-2 speed test (Nov 19, plan step 1). For each rank: serve the 31B with the LoRA kernels sized to
# that rank (MAX_LORA_RANK, as the scorer does for a bundle whose adapter has that rank), hot-load the adapter and
# measure generation speed with and without it (lora_speed.py). Ends with a plain server (LoRA off): its speed is the
# reference, and it stays up for the note runs.
#   bash t4_lora_speed.sh ["16:submissions/budgetfit_v5_spd16 8:submissions/budgetfit_v5_spd8 32:submissions/budgetfit_v5_lora1"]
# Output: results/speed/t4_r<rank>.json, results/speed/t4_plain.json; log logs/t4_lora_speed.log.
# Shared VM: it starts only when all four cards are free, stops when another job holds one, and never touches
# processes other than its own tmux session `vllm`.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; mkdir -p results/speed; LOG=logs/t4_lora_speed.log
MODEL=gemma-4-31b-it-qat-w4a16-ct
log() { echo "$(date -u) | $*" | tee -a $LOG; }
free() { for u in $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits); do [ "$u" -lt 1000 ] || return 1; done; }
serve() {   # serve [max_lora_rank]; without a rank: plain server
  for try in 1 2 3; do
    tmux kill-session -t vllm 2>/dev/null
    for i in $(seq 1 36); do free && break; sleep 5; done
    free || { log "a GPU is held by another job: stop (nothing of theirs was touched)"; return 1; }
    if [ -n "${1:-}" ]; then st=$(MODEL=$MODEL LORA_DYNAMIC=1 MAX_LORA_RANK=$1 bash ~/gemma4_vm/wait_vllm.sh | head -1)
    else st=$(MODEL=$MODEL bash ~/gemma4_vm/wait_vllm.sh | head -1); fi
    [ "$st" = READY ] && return 0
    log "server start: ${st:-no answer} (try $try)"; sleep 20
  done
  return 1
}
for pair in ${1:-16:submissions/budgetfit_v5_spd16 8:submissions/budgetfit_v5_spd8 32:submissions/budgetfit_v5_lora1}; do
  rank=${pair%%:*}; bundle=${pair#*:}; ap=$R/$bundle/adapters/main_lora
  [ -f $ap/adapter_model.safetensors ] || { log "rank $rank: no adapter in $bundle, skipped"; continue; }
  serve $rank || exit 1
  resp=$(curl -s -m 300 -X POST http://127.0.0.1:8000/v1/load_lora_adapter -H "Content-Type: application/json" -d "{\"lora_name\": \"main_lora\", \"lora_path\": \"$ap\"}")
  curl -s -m 10 http://127.0.0.1:8000/v1/models | grep -q '"main_lora"' || { log "rank $rank: adapter not loaded (${resp:0:200})"; continue; }
  log "rank $rank: server up with max_lora_rank $rank, adapter of $bundle loaded"
  python3 ~/gemma4_vm/lora_speed.py --arms base=$MODEL adapter=main_lora --out results/speed/t4_r$rank.json \
    --note "T4 x4, max_lora_rank $rank, $bundle" 2>&1 | tail -1 | tee -a $LOG
done
serve || exit 1
python3 ~/gemma4_vm/lora_speed.py --arms base=$MODEL --out results/speed/t4_plain.json --note "T4 x4, plain server (LoRA off)" 2>&1 | tail -1 | tee -a $LOG
log "t4_lora_speed done; the plain server stays up"
