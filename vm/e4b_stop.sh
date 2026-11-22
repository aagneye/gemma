#!/usr/bin/env bash
# E4B side track (research/PLAN_E4B.md): give the four cards back. Ends the chain (tmux e4b_chain), its running arms
# (their own process group, noted in tmp/e4b_arms.pgid) and the E4B servers (tmux e4b_srv_*). Exact names only:
# nothing of round 2, of the shipper or of another project is touched. Finished arms stay on disk, and
#   tmux new -d -s e4b_chain "bash ~/gemma4_vm/e4b_chain.sh"
# goes on behind them. The chain also stops by itself when a main-track session (r2chain, r2notes, vllm) appears or
# when results/e4b_yield exists.
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm
tmux kill-session -t =e4b_chain 2>/dev/null && echo "ended e4b_chain"
if [ -s tmp/e4b_arms.pgid ]; then kill -TERM -- -$(cat tmp/e4b_arms.pgid) 2>/dev/null && echo "ended the running arms"; rm -f tmp/e4b_arms.pgid; fi
sleep 3
bash $V/e4b_serve4.sh down
bash $V/e4b_serve4.sh status
