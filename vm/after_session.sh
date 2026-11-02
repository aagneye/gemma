#!/usr/bin/env bash
# Block until a tmux session has ended. Chains replica rounds on the one vLLM server without a gap (the vLLM server keeps
# the GPUs between rounds, so the other project cannot take them), e.g.
#   tmux new -d -s rep_r4 "bash ~/gemma4_vm/after_session.sh rep_r3 && SCALE=9 bash ~/gemma4_vm/run_pair.sh ... 2>&1 | tee logs/run_pair_r4.log"
# Exact-name match (=name): a session whose name merely starts with <name> does not keep it waiting.
set -u
S=${1:?tmux session to wait for}
echo "$(date -u) waiting for tmux session $S to end"
while tmux has-session -t "=$S" 2>/dev/null; do sleep 120; done
echo "$(date -u) $S has ended"
