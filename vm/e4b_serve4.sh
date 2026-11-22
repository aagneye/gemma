#!/usr/bin/env bash
# E4B side track (research/PLAN_E4B.md): one E4B server per T4 (TP=1), GPU g on port 8001+g, in tmux e4b_srv_<port>,
# log logs/e4b_serve_<port>.log. serve_vllm.sh is used unchanged. Port 8000 and the tmux name `vllm` stay the main
# track's: chain_r2.sh and wait_vllm.sh end `-t vllm`, which would also match a lone session whose name starts with vllm.
#   bash e4b_serve4.sh up       start a server on every card of GPUS ("0 1 2 3") that is free (under 1000 MiB; a card
#                               that is still emptying gets FREE_WAIT seconds, default 40) and wait until each one
#                               answers or has died. Last line: "UP <ports that answer a request>"
#   bash e4b_serve4.sh down     end every e4b_srv_* session (exact names; nothing else is touched)
#   bash e4b_serve4.sh status
#   DRY=1 bash e4b_serve4.sh up    print what would start
# A card another project holds is left alone; the caller works with the ports it gets.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; MODEL=gemma-4-e4b-it-qat-w4a16-ct
CMD=${1:-status}; GPUS=${GPUS:-0 1 2 3}; DRY=${DRY:-}; FREE_WAIT=${FREE_WAIT:-40}
port() { echo $((8001 + $1)); }
used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $1 2>/dev/null | tr -d ' '; }
answers() { curl -s -m 10 http://127.0.0.1:$1/v1/models 2>/dev/null | grep -q "\"$MODEL\""; }
alive() { tmux has-session -t "=e4b_srv_$1" 2>/dev/null; }

case $CMD in
up)
  STARTED=(); TODO=($GPUS)
  for t in $(seq 0 $FREE_WAIT); do
    LEFT=()
    for g in ${TODO[@]+"${TODO[@]}"}; do
      p=$(port $g)
      if answers $p || alive $p; then STARTED+=($p); continue; fi          # serving or still starting
      u=$(used $g)
      if [ -n "$u" ] && [ "$u" -lt 1000 ]; then
        if [ -n "$DRY" ]; then echo "DRY: tmux e4b_srv_$p <- MODEL=$MODEL TP=1 GPUS=$g PORT=$p bash $V/serve_vllm.sh"; continue; fi
        : > logs/e4b_serve_$p.log
        tmux new-session -d -s e4b_srv_$p "MODEL=$MODEL TP=1 GPUS=$g PORT=$p bash $V/serve_vllm.sh 2>&1 | tee logs/e4b_serve_$p.log"
        STARTED+=($p)
      else
        LEFT+=($g)
      fi
    done
    TODO=(${LEFT[@]+"${LEFT[@]}"}); [ ${#TODO[@]} -eq 0 ] && break; [ -n "$DRY" ] && break; sleep 1
  done
  for g in ${TODO[@]+"${TODO[@]}"}; do echo "GPU $g holds $(used $g) MiB: left alone"; done
  [ -n "$DRY" ] && exit 0
  UP=()
  for i in $(seq 1 ${WAIT_ROUNDS:-120}); do       # a cold start takes about 6 minutes; give up after 20
    UP=(); PENDING=0
    for p in ${STARTED[@]+"${STARTED[@]}"}; do
      if answers $p; then UP+=($p); elif alive $p; then PENDING=1; fi
    done
    [ $PENDING -eq 0 ] && break; sleep 10
  done
  OK=()
  for p in ${UP[@]+"${UP[@]}"}; do
    if curl -s -m 300 http://127.0.0.1:$p/v1/chat/completions -H "Content-Type: application/json" \
        -d "{\"model\": \"$MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"Say ok.\"}], \"max_tokens\": 4}" | grep -q '"choices"'; then
      OK+=($p); grep -E "KV cache size|Maximum concurrency" logs/e4b_serve_$p.log 2>/dev/null | tail -2 | cut -c1-160
    else
      echo "port $p is up but does not answer a request"
    fi
  done
  for p in ${STARTED[@]+"${STARTED[@]}"}; do
    answers $p || { echo "port $p did not come up:"; grep -E "out of memory|OutOfResources|Error|error" logs/e4b_serve_$p.log 2>/dev/null | tail -2 | cut -c1-200; }
  done
  echo "UP ${OK[*]:-}";;
down)
  for g in 0 1 2 3; do p=$(port $g); alive $p && { tmux kill-session -t "=e4b_srv_$p"; echo "ended e4b_srv_$p"; }; done; exit 0;;
status)
  for g in 0 1 2 3; do
    p=$(port $g); echo "GPU $g: $(used $g) MiB | e4b_srv_$p: $(alive $p && echo session || echo none), $(answers $p && echo answers || echo silent)"
  done;;
*) echo "usage: e4b_serve4.sh up|down|status"; exit 1;;
esac
