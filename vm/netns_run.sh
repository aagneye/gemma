#!/usr/bin/env bash
# Run a command with the internet cut off but the vLLM server reachable (user decision 2026-11-03: third-party repo
# code runs on the VM without internet). The command runs in a new user + network namespace (unshare -rn, loopback
# up); 127.0.0.1:$PORT inside it is bridged to the host's server through a unix socket (netns_bridge.py).
# REQ_DUMP=<dir> also saves every request the command sends to the model (the request log, see netns_bridge.py).
#   [PORT=8000] [REQ_DUMP=dir] bash netns_run.sh <command...>   e.g. TASK_LIST=... bash netns_run.sh bash ~/gemma4_vm/run_pair.sh ...
set -u
PORT=${PORT:-8000}; SOCK=/mnt/biohub/kdata/gemma4/tmp/vllm_bridge_${PORT}_$$.sock
python3 ~/gemma4_vm/netns_bridge.py host $SOCK 127.0.0.1:$PORT ${REQ_DUMP:-} & HOSTB=$!
trap 'kill $HOSTB 2>/dev/null; rm -f $SOCK' EXIT; trap 'exit 143' TERM INT
for i in $(seq 1 20); do [ -S $SOCK ] && break; sleep 0.5; done
unshare -rn -- bash -c 'ip link set lo up || exit 1
python3 "$HOME/gemma4_vm/netns_bridge.py" ns "$0" "$1" & B=$!
trap "kill $B 2>/dev/null" EXIT; trap "exit 143" TERM INT
sleep 1; shift; "$@"' "$PORT" "$SOCK" "$@"
