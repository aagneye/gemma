#!/usr/bin/env bash
# Gate 1 shortcut (Nov 11): when the adapter's EVAL run is complete, apply its main rule (>= +3 on the 77 EVAL tasks
# whose tests fit the issue; calls and tokens <= x1.08). If it fails, the 17-task practice re-check that follows in
# tmux gate1 cannot change the outcome, so end that session and let the next queue (tmux instr) start ~4 h earlier.
cd /mnt/biohub/kdata/gemma4
while tmux has-session -t =gate1 2>/dev/null; do
  if [ -f results/replica/lora1_eval/results.csv ]; then
    python3 ~/gemma4_vm/verdict.py --base results/replica/bf5_eval --cand results/replica/lora1_eval --tasks results/lists/eval_ts01.txt --gain 3 --cost 1.08 --cost-keys calls,tok | tee results/replica/lora1_eval/gate_main_rule.txt
    if grep -q "^VERDICT REJECT" results/replica/lora1_eval/gate_main_rule.txt; then
      echo "$(date -u) main rule failed: ending gate1 (practice re-check skipped)"; tmux kill-session -t =gate1
    else
      echo "$(date -u) main rule passed: gate1 continues with the practice re-check"
    fi
    exit 0
  fi
  sleep 60
done
