#!/usr/bin/env bash
# Start serve_vllm.sh in tmux "vllm" and wait until it is ready or dead. Prints READY/DIED and key log lines.
R=/mnt/biohub/kdata/gemma4; cd $R
tmux kill-session -t vllm 2>/dev/null; sleep 3; : > logs/vllm_serve.log
tmux new-session -d -s vllm "MODEL=${MODEL:-} ADAPTER=${ADAPTER:-} MODE=${MODE:-graphs} MEM=${MEM:-0.84} ATTN=${ATTN:-} bash ~/gemma4_vm/serve_vllm.sh 2>&1 | tee logs/vllm_serve.log"
sleep 15
for i in $(seq 1 70); do
  if grep -q "Application startup complete" logs/vllm_serve.log; then echo READY; break; fi
  if ! tmux has-session -t vllm 2>/dev/null; then echo DIED; break; fi
  sleep 10
done
grep -E "KV cache size|Maximum concurrency|out of memory|OutOfResources|Loaded new LoRA|error" logs/vllm_serve.log | grep -v "multiproc_executor.py:949" | tail -6 | cut -c1-200
