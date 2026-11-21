#!/usr/bin/env bash
# Starts the GPU test (r2_gpu_smoke.sh) at the next break of the note runs: when r2_notes_chain.sh logs the next finished chunk.
#   tmux new -d -s r2smoke "BOX_END=<epoch seconds> bash ~/gemma4_vm/r2_smoke_trigger.sh"
cd /mnt/biohub/kdata/gemma4
n0=$(grep -c "| r2_tk_.*: " logs/r2_notes.log)
until [ "$(grep -c "| r2_tk_.*: " logs/r2_notes.log)" -gt "$n0" ] || ! tmux has-session -t r2notes 2>/dev/null; do sleep 10; done
tmux has-session -t r2notes 2>/dev/null || { echo "$(date -u) | the note chain ended before a break: no GPU test" >> logs/r2_smoke.log; exit 0; }
BOX_END=${BOX_END:?} bash ~/gemma4_vm/r2_gpu_smoke.sh
