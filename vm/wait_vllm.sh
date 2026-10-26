#!/usr/bin/env bash
# Start serve_vllm.sh in a tmux session and wait until it is ready or dead. Prints READY/DIED and key log lines.
# Same env knobs as serve_vllm.sh (MODEL, ADAPTER, MODE, MEM, ATTN, TP, GPUS, PORT, MAXSEQ). Port 8000 keeps the
# historical session name "vllm" and log logs/vllm_serve.log; any other port gets "vllm_<port>" and
# logs/vllm_serve_<port>.log, so several single-GPU servers can coexist (e.g. one E4B experiment per free T4).
R=/mnt/biohub/kdata/gemma4; cd $R
PORT=${PORT:-8000}
if [ "$PORT" = 8000 ]; then S=vllm; LOG=logs/vllm_serve.log; else S=vllm_$PORT; LOG=logs/vllm_serve_$PORT.log; fi
tmux kill-session -t $S 2>/dev/null; sleep 3; : > $LOG
tmux new-session -d -s $S "MODEL=${MODEL:-} ADAPTER=${ADAPTER:-} MODE=${MODE:-graphs} MEM=${MEM:-} ATTN=${ATTN:-} TP=${TP:-4} GPUS=${GPUS:-} PORT=$PORT MAXSEQ=${MAXSEQ:-8} bash ~/gemma4_vm/serve_vllm.sh 2>&1 | tee $LOG"
sleep 15
for i in $(seq 1 ${WAIT_ROUNDS:-70}); do
  if grep -q "Application startup complete" $LOG; then echo READY; break; fi
  if ! tmux has-session -t $S 2>/dev/null; then echo DIED; break; fi
  sleep 10
done
grep -E "KV cache size|Maximum concurrency|out of memory|OutOfResources|Loaded new LoRA|error" $LOG | grep -v "multiproc_executor.py:949" | tail -6 | cut -c1-200
