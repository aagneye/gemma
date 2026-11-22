#!/usr/bin/env bash
# E4B side track (research/PLAN_E4B.md, "How it is checked"): the checks that need no GPU. Run on the VM after
# e4b_build.sh and e4b_dev_select.py:
#   bash e4b_selftest.sh             task list, picker rules, round-2 endings, dry runs of the chain, the ship script's dry run
#   PLUMB=1 bash e4b_selftest.sh     also 2 arms x 2 tasks against stand-in servers on ports 8001 and 8002 (a few
#                                    minutes; only while no E4B server runs): each arm reaches only its own port, the
#                                    internet is cut off, and the requests carry the bundle's thinking setting
# Prints ok / FAIL lines and ends with "SELFTEST PASSED" or "SELFTEST FAILED".
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; T=tmp/e4b_selftest; rm -rf $T; mkdir -p $T; FAIL=0
ok() { echo "ok   $*"; }; bad() { echo "FAIL $*"; FAIL=1; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1: got '$2', wanted '$3'"; fi; }   # check <what> <got> <wanted>

echo "== task list"
python3 $V/e4b_dev_select.py --prefix $T/d1_ > $T/sel.txt 2>&1 || bad "e4b_dev_select.py: $(tail -1 $T/sel.txt)"
python3 $V/e4b_dev_select.py --prefix $T/d2_ > /dev/null 2>&1
cmp -s $T/d1_128.txt $T/d2_128.txt && ok "the same draw twice" || bad "two draws differ"
check "half A" "$(grep -vc '^#' $T/d1_A.txt)" 64; check "half B" "$(grep -vc '^#' $T/d1_B.txt)" 64
check "tasks in both halves" "$(cat $T/d1_A.txt $T/d1_B.txt | grep -v '^#' | sort | uniq -d | wc -l)" 0
check "EVAL tasks in the list" "$(grep -v '^#' $T/d1_128.txt | grep -cxFf <(grep -v '^#' results/lists/rebench_eval.txt))" 0
check "tasks outside the 31B-solved pool" "$(grep -v '^#' $T/d1_128.txt | grep -vcxFf <(grep -v '^#' results/lists/bf5_train_solved.txt))" 0
if [ -s results/lists/e4b_dev128.txt ]; then
  cmp -s <(grep -v '^#' results/lists/e4b_dev128.txt) <(grep -v '^#' $T/d1_128.txt) && ok "the installed list is this draw" || bad "the installed list differs from this draw"
else bad "results/lists/e4b_dev128.txt is not installed (python3 e4b_dev_select.py)"; fi
tail -1 $T/sel.txt

echo "== picker rules (made-up runs)"
mk() { python3 - "$@" <<'PY'
import json, os, sys
d, n, k = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
fe = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0; sec = float(sys.argv[5]) if len(sys.argv) > 5 else 300.0
os.makedirs(d + "/agent_run", exist_ok=True)
with open(d + "/agent_run/task_results.jsonl", "w") as f, open(d + "/autopsy.jsonl", "w") as g:
    for i in range(n):
        f.write(json.dumps({"instance_id": f"t_{i}", "resolved": i < k, "duration_seconds": sec, "tool_calls": 10}) + "\n")
        g.write(json.dumps({"instance_id": f"t_{i}", "garbled_edits": 0, "edit_errors_other": 1 if i < fe * n else 0}) + "\n")
PY
}
P=$T/p; mk $P/bA 64 12; mk $P/bB 64 12; mk $P/xA 64 14; mk $P/xB 64 15; mk $P/yA 64 13; mk $P/yB 64 13; mk $P/zA 64 16; mk $P/zB 64 16
pick() { python3 $V/e4b_pick.py "$@" | tail -1; }
check "+2.5 per 64 is picked" "$(pick screen --base $P/bA $P/bB --arm x=$P/xA,$P/xB --arm y=$P/yA,$P/yB)" "PICK x"
check "+1.0 per 64 is not" "$(pick screen --base $P/bA $P/bB --arm y=$P/yA,$P/yB)" "PICK base"
check "the larger gain wins" "$(pick screen --base $P/bA $P/bB --arm x=$P/xA,$P/xB --arm z=$P/zA,$P/zB)" "PICK z"
check "exactly +2.0 per 64 is picked" "$(pick screen --base $P/bA $P/bB --arm w=$P/xA,$P/xA)" "PICK w"
mk $P/eA 64 16 1.0; mk $P/eB 64 16 1.0; mk $P/gA 64 16 0.5; mk $P/gB 64 16 0.5
check "gain without the behaviour: not picked with --moved" "$(pick screen --base $P/bA $P/bB --arm e=$P/eA,$P/eB --moved)" "PICK base"
check "gain with failed edits halved: picked with --moved" "$(pick screen --base $P/bA $P/bB --arm g=$P/gA,$P/gB --moved)" "PICK g"
mk $P/half 30 9; check "an unfinished arm is judged on the common tasks" "$(pick screen --base $P/bA --arm h=$P/half)" "PICK base"
mk $P/fast 77 20 1 600; mk $P/slow 77 20 1 900
check "600 replica seconds at scale 3" "$(pick runtime --dirs $P/fast | cut -d: -f1)" "RUNTIME OK"
check "900 replica seconds at scale 3" "$(pick runtime --dirs $P/slow | cut -d: -f1)" "RUNTIME ASK"
check "pace" "$(pick pace --dirs $P/fast $P/slow $P/none)" 750

echo "== which ending does round 2's log show"
S0="Sun Nov 22 19:00:00 UTC 2026 | chain_r2 start at step 4: rank 16, alpha 32"
printf '%s\n%s\n' "$S0" "x | floor check: 80 clean note runs from 60 tasks" > $T/f_run.log
printf '%s\n%s\n%s\n' "$S0" "x | ROUND STOPPED: too few clean examples (plan step 4)" "x | Kaggle hold released: the round stopped" > $T/f_stop.log
printf '%s\n%s\n%s\n' "$S0" "x | Kaggle hold released: the verdict is not ADOPT (VERDICT REJECT)" "x | chain_r2 done; the server with the adapter stays up" > $T/f_done.log
printf '%s\n%s\n%s\n%s\n' "$S0" "x | ROUND STOPPED: the GPUs are not free before training" "x | chain_r2 start at step 5: rank 16" "x | training exit 0" > $T/f_again.log
echo "VERDICT REJECT" > $T/v_reject.txt; echo "VERDICT ADOPT" > $T/v_adopt.txt
end() { FIXTURE=$1 FIXTURE_VERDICT=${2:-$T/none} bash $V/e4b_chain.sh ending; }
check "round 2 still running" "$(end $T/f_run.log)" RUNNING
check "no log yet" "$(end $T/f_none.log)" RUNNING
check "a stop" "$(end $T/f_stop.log)" STOP
check "done with REJECT" "$(end $T/f_done.log $T/v_reject.txt)" REJECT
check "done with ADOPT" "$(end $T/f_done.log $T/v_adopt.txt)" ADOPT
check "done, no verdict file" "$(end $T/f_done.log)" REJECT
check "stopped, then started again" "$(end $T/f_again.log)" RUNNING
LIVE=$(bash $V/e4b_chain.sh ending); echo "     live state now: $LIVE"
if tmux has-session -t =r2chain 2>/dev/null || tmux has-session -t =r2notes 2>/dev/null; then check "round 2's sessions exist, so the live state is" "$LIVE" RUNNING; fi

echo "== dry runs of the chain"
dry() { env "$@" DRY=1 bash $V/e4b_chain.sh > $T/dry.out 2>&1; }
dry A=1; check "full path: arms printed" "$(grep -c '^DRY arm' $T/dry.out)" 16
check "full path: both screens and both waves" "$(grep -cE 'screen 1, half|screen 2, half|confirmation, wave' $T/dry.out)" 6
grep -q "e4b_chain done: dry run" $T/dry.out && ok "full path ends at the verdict" || bad "full path: $(tail -1 $T/dry.out)"
check "wave 2 swaps the cards" "$(grep 'DRY arm e4b_cf_cand_c' $T/dry.out | grep -c 'port 8001')" 1
dry DRY_PICK1=base DRY_PICK2=base; grep -q "no arm reached the bar" $T/dry.out && ok "nothing reached the bar: stop, no confirmation" || bad "stop rule: $(tail -1 $T/dry.out)"
check "stop rule: no confirmation arm" "$(grep -c 'e4b_cf_' $T/dry.out)" 0
dry DRY_PICK1=base DRY_PICK2=e4b_bf5_e1r1; grep -q "stack after the screens: e4b_bf5_e1r1" $T/dry.out && ok "E1+R1 alone can be the stack" || bad "stack: $(grep stack $T/dry.out)"
dry DRY_PORTS="8001 8002"; check "two cards: arms in batches of two" "$(grep -c 'e4b_arms: 2 arms' $T/dry.out)" 8
dry DRY_NOW=2026-11-26T20:00 PACE=400; grep -q "screen 2 is left out" $T/dry.out && grep -q "confirmation, wave 1" $T/dry.out && ok "22 h left: screen 2 left out, confirmation runs" || bad "time box (22 h): $(tail -2 $T/dry.out)"
dry DRY_NOW=2026-11-27T12:00 PACE=400; grep -q "the confirmation does not fit the time box" $T/dry.out && ok "6 h left: no confirmation" || bad "time box (6 h): $(tail -1 $T/dry.out)"
[ -e results/replica/e4b_confirm_verdict.txt ] && bad "a dry run wrote results/replica/e4b_confirm_verdict.txt" || ok "dry runs wrote no verdict file"

echo "== the watchdog gives the cards back (stand-in session, stand-in arm; no real session or server is touched)"
wt() { MAIN_SESSIONS=e4b_selftest_main PGID_FILE=$T/arms.pgid YIELD_FILE=$T/yield DOWN_CMD="touch $T/down_called" bash $V/e4b_chain.sh watchtest $T/watch.log > /dev/null 2>&1 & echo $!; }
tmux kill-session -t =e4b_selftest_main 2>/dev/null
WP=$(wt); sleep 8; AP=$(cat $T/arms.pgid 2>/dev/null)
kill -0 $WP 2>/dev/null && kill -0 ${AP:-0} 2>/dev/null && ok "no main-track session: chain and arm keep running" || bad "the chain or its arm ended without a reason"
tmux new-session -d -s e4b_selftest_main "sleep 60"; sleep 9
kill -0 $WP 2>/dev/null && bad "a main-track session appeared but the chain still runs" || ok "a main-track session appeared: the chain ended"
kill -0 ${AP:-0} 2>/dev/null && bad "the arm still runs" || ok "its arm was ended"
[ -e $T/down_called ] && ok "the servers were told to end" || bad "the servers were not told to end"
grep -q "YIELD: tmux session e4b_selftest_main is back" $T/watch.log && ok "the log says why" || bad "no YIELD line in the log"
tmux kill-session -t =e4b_selftest_main 2>/dev/null; rm -f $T/down_called
WP=$(wt); sleep 8; touch $T/yield; sleep 9
kill -0 $WP 2>/dev/null && bad "the yield file did not end the chain" || ok "the yield file ends the chain too"
[ -e $T/yield ] && bad "the yield file was left behind" || ok "the yield file is removed"

echo "== servers and ship script (nothing started, nothing sent)"
bash $V/e4b_serve4.sh status
DRY=1 bash $V/e4b_ship.sh submissions/e4b_bf5_t0 > $T/ship.out 2>&1
grep -q "DRY: stopped before anything was sent" $T/ship.out && ok "ship dry run: bundle valid, notebook written" || bad "ship dry run: $(tail -1 $T/ship.out)"
check "kernel id and privacy" "$(python3 -c "import json; m = json.load(open('tmp/ship_e4b_bf5_t0/nb/kernel-metadata.json')); print(m['id'], m['is_private'], m['enable_internet'])" 2>&1)" "aagneye/gemma4-e4b-bf5-t0 True False"

if [ -n "${PLUMB:-}" ]; then
  echo "== plumbing: 2 arms x 2 tasks against stand-in servers"
  for p in 8001 8002; do curl -s -m 3 http://127.0.0.1:$p/v1/models > /dev/null && { bad "port $p is in use: plumbing test left out"; PLUMB=""; }; done
fi
if [ -n "${PLUMB:-}" ]; then
  python3 $V/e4b_fake_server.py 8001 $T/fake_8001.log & F1=$!; python3 $V/e4b_fake_server.py 8002 $T/fake_8002.log & F2=$!
  trap 'kill $F1 $F2 2>/dev/null' EXIT; sleep 2
  check "own port reachable, the other not, internet cut off" \
    "$(PORT=8001 bash $V/netns_run.sh bash -c 'curl -s -m 5 -o /dev/null http://127.0.0.1:8001/v1/models; a=$?; curl -s -m 5 -o /dev/null http://127.0.0.1:8002/v1/models; b=$?; curl -s -m 8 -o /dev/null https://huggingface.co; c=$?; echo "$a $([ $b -ne 0 ] && echo closed) $([ $c -ne 0 ] && echo cut)"' 2>/dev/null | tail -1)" "0 closed cut"
  { head -1 results/lists/e4b_devA.txt; grep -v '^#' results/lists/e4b_devA.txt | head -2; } > $T/two.txt
  rm -rf results/replica/e4b_selftest_a results/replica/e4b_selftest_b results/requests/e4b_selftest_a results/requests/e4b_selftest_b
  LIST=$T/two.txt PORTS="8001 8002" bash $V/e4b_arms.sh submissions/e4b_bf5 e4b_selftest_a submissions/e4b_bf5_t0 e4b_selftest_b > $T/arms.out 2>&1
  tail -4 $T/arms.out
  for x in a b; do check "arm $x finished its 2 tasks" "$(grep -c . results/replica/e4b_selftest_$x/agent_run/task_results.jsonl 2>/dev/null)" 2; done
  req() { python3 - $1 <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if '"/v1/chat/completions"' in l]
k = {(json.dumps(r["chat_template_kwargs"], sort_keys=True), r["thinking_token_budget"], len(r["tools"]), "get_code_subgraph" in r["tools"]) for r in rows}
print(len(rows) > 0, sorted(k))
PY
  }
  check "arm a (thinking 4096): what the server was sent" "$(req $T/fake_8001.log)" "True [('{\"enable_thinking\": true}', 4096, 6, False)]"
  check "arm b (thinking 0): what the server was sent" "$(req $T/fake_8002.log)" "True [('{\"enable_thinking\": false}', None, 6, False)]"
  for x in a b; do
    grep -q " scale=3 " results/replica/e4b_selftest_$x/run.log && grep -q "model request timeout 1800" results/replica/e4b_selftest_$x/run.log && ok "arm $x: scale 3 and the 1,800-s request limit" || bad "arm $x: $(head -3 results/replica/e4b_selftest_$x/run.log | cut -c1-200)"
    [ -n "$(ls results/requests/e4b_selftest_$x 2>/dev/null | head -1)" ] && ok "arm $x: request log written" || bad "arm $x: no request log"
    [ -s results/replica/e4b_selftest_$x/clock.md ] && ok "arm $x: clock ledger written" || bad "arm $x: no clock ledger"
  done
  kill $F1 $F2 2>/dev/null; trap - EXIT
  rm -rf results/replica/e4b_selftest_a results/replica/e4b_selftest_b results/requests/e4b_selftest_a results/requests/e4b_selftest_b logs/rep_e4b_selftest_a.out logs/rep_e4b_selftest_b.out
fi
[ $FAIL -eq 0 ] && echo "SELFTEST PASSED" || echo "SELFTEST FAILED"
exit $FAIL
