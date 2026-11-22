#!/usr/bin/env bash
# E4B side track (user, Nov 22; research/PLAN_E4B.md): the small-model tests on the four T4s, behind round 2.
#   tmux new -d -s e4b_chain "bash ~/gemma4_vm/e4b_chain.sh"
# 0  Wait until round 2 has ended BY ITS OWN WORD: tmux r2chain and r2notes are gone, none of its processes is alive,
#    and logs/r2_chain.log holds "ROUND STOPPED:" after its last start line or ends with "chain_r2 done". A missing
#    session without that word (a restart, a crash) starts nothing. Free memory is never the signal: round 2 frees
#    the cards itself between its steps and stops (releasing the Kaggle hold) if it then finds them taken.
# 1  Take the cards: after a stop or a REJECT at once; after an ADOPT GRACE_MIN (30) minutes later and not while
#    results/e4b_wait.txt exists (the main track keeps its 31B server); never while a test still runs against that
#    server. The idle server (tmux =vllm) is ended and one E4B server starts per free card (e4b_serve4.sh). From
#    then on a watchdog gives the cards back at once when a main-track session (r2chain, r2notes, vllm) appears or
#    results/e4b_yield exists.
# 2  Screen 1, the thinking ladder: e4b_bf5 (4,096) / _t1k / _t256 / _t0 on the dev halves A and B (64 + 64 tasks the
#    31B solves). The best level becomes the base when it is +2 solved per 64 tasks over e4b_bf5 (e4b_pick.py).
# 3  Screen 2, only when it and the confirmation fit the time box: the base against the base with the two approved
#    E1+R1 lines, two copies each, on both halves. E1+R1 joins at +2 per 64 with failed edit_file calls <= 0.8 x.
# 4  Nothing reached the bar: STOP. Cards released, nothing sent, the E4B stays parked.
# 5  Confirmation on the 77 EVAL tasks: e4b_bf5 against the stack, 4 paired passes in two waves (cards swapped in the
#    second). verdict.py --gain 3; runtime rule: at most 270 Kaggle-seconds per task (9 h for 120 tasks).
# 6  PASS: e4b_ship.sh in tmux e4b_ship (one Kaggle run through the dated schedule line; it asks when the adapter
#    holds the queue). Result: results/replica/e4b_confirm_verdict.txt; log: logs/e4b_chain.log.
# Time box BOX_END (Nov 27 18:00 UTC): a stage starts only if it can end before it at the pace measured in screen 1.
# Finished arms are kept: a restart goes on behind them. e4b_stop.sh ends the chain and gives the cards back.
# ROUND2_OVER=1 skips step 0 (for a person who knows round 2 was ended by hand and left no word in its log).
# Without GPUs: FIXTURE=<log> [FIXTURE_VERDICT=<file>] bash e4b_chain.sh ending     (which ending does that log show?)
#               DRY=1 [DRY_PORTS="8001 8002"] [DRY_PICK1=e4b_bf5_t0] [DRY_PICK2=base] [DRY_NOW=2026-11-27T10:00] [PACE=400] bash e4b_chain.sh
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; S=submissions; L=results/lists; RP=results/replica
DRY=${DRY:-}; SCALE=3; BOX_END=${BOX_END:-2026-11-27T18:00}; GRACE_MIN=${GRACE_MIN:-30}
if [ -n "$DRY" ]; then W=tmp/e4b_dry; LOG=tmp/e4b_dry/chain.log; rm -rf $W; else W=results/e4b; LOG=logs/e4b_chain.log; fi
mkdir -p $W logs tmp
log() { echo "$(date -u) | $*" | tee -a $LOG; }
now_s() { if [ -n "${DRY_NOW:-}" ]; then date -u -d "$DRY_NOW" +%s; else date -u +%s; fi; }
box_s() { date -u -d "$BOX_END" +%s; }

ending() {   # STOP | REJECT | ADOPT, or nothing while round 2 runs or its end is not certain
  local lg=${FIXTURE:-logs/r2_chain.log} vd=${FIXTURE_VERDICT:-$RP/r2_verdict.txt} from part
  if [ -z "${FIXTURE:-}" ]; then
    tmux has-session -t =r2chain 2>/dev/null && return 0
    tmux has-session -t =r2notes 2>/dev/null && return 0
    # round 2's own processes; the tmux server and clients are left out (their command line can quote a script's name for good)
    ps -eo comm=,args= | grep -v "^tmux" | grep -Eq "[c]hain_r2\.sh|[r]2_notes_chain\.sh|[n]ote_runs\.sh|[t]rain_qlora\.py|[r]2_gpu_smoke\.sh" && return 0
  fi
  [ -f "$lg" ] || return 0
  from=$(grep -n "chain_r2 start" "$lg" | tail -1 | cut -d: -f1)
  part=$(tail -n +${from:-1} "$lg")
  if echo "$part" | grep -q "ROUND STOPPED:"; then echo STOP
  elif echo "$part" | tail -1 | grep -q "chain_r2 done"; then
    if grep -q "^VERDICT ADOPT" "$vd" 2>/dev/null; then echo ADOPT; else echo REJECT; fi
  fi
  return 0
}
if [ "${1:-}" = ending ]; then E=$(ending); echo "${E:-RUNNING}"; exit 0; fi

wait_round2() {
  log "waiting for round 2 to end by its own word (logs/r2_chain.log)"
  local e prev=""
  while :; do
    e=$(ending); [ -n "$e" ] && [ "$e" = "$prev" ] && break     # the same ending on two looks, 10 s apart
    prev=$e; sleep 10
  done
  log "round 2 has ended: $e"
  if [ "$e" = ADOPT ] && [ ! -e $W/taken ]; then
    log "ADOPT: the main track comes first. Waiting $GRACE_MIN minutes, and as long as results/e4b_wait.txt exists"
    sleep $((GRACE_MIN * 60)); while [ -e results/e4b_wait.txt ]; do sleep 60; done
    [ -n "$(ending)" ] || { log "round 2 runs again"; wait_round2; }
  fi
}

PORTS=(); WD=""; MAIN=$$
main_busy() {   # a main-track test still runs against the 31B server (a replica run, a probe, a check): it is not idle
  ps -eo comm=,args= | grep -v "^tmux" | grep -Eq "[r]un_replica\.sh|[l]ocal_score\.py|[r]un_arms\.sh|[r]un_pair\.sh|[p]robe\.py|[h]eldout_loss\.py|[a]dapter_effect\.py"
}
take_cards() {
  local told=""
  while main_busy; do [ -z "$told" ] && { log "a test still runs against the 31B server; waiting for it to end"; told=1; }; sleep 60; done
  tmux kill-session -t =vllm 2>/dev/null && log "the idle 31B server (tmux vllm) is ended"
  watch_main & WD=$!          # from here on the cards go back the moment the main track asks, also while servers start
  while :; do
    PORTS=($(bash $V/e4b_serve4.sh up 2>&1 | tee -a $LOG | grep "^UP" | tail -1 | sed 's/^UP *//'))
    [ ${#PORTS[@]} -gt 0 ] && break
    [ $(now_s) -ge $(box_s) ] && { log "STOP: no card became free before the time box ended"; exit 0; }
    log "no card is free (another project holds them); trying again in 5 minutes"; sleep 300
  done
  log "E4B servers answer on ports: ${PORTS[*]}"; touch $W/taken
}
# The three names below are fixed in use; e4b_selftest.sh sets them (and DOWN_CMD) to stand-ins to test the watchdog.
MAIN_SESSIONS=${MAIN_SESSIONS:-r2chain r2notes vllm}; PGID_FILE=${PGID_FILE:-tmp/e4b_arms.pgid}; YIELD_FILE=${YIELD_FILE:-results/e4b_yield}
servers_down() { if [ -n "${DOWN_CMD:-}" ]; then eval "$DOWN_CMD"; else bash $V/e4b_serve4.sh down; fi; }
stop_arms() { [ -s $PGID_FILE ] && kill -TERM -- -$(cat $PGID_FILE) 2>/dev/null; rm -f $PGID_FILE; }
watch_main() {   # the main track is back: its sessions, its server on port 8000, or the yield file
  while sleep 5; do
    local why="" s
    for s in $MAIN_SESSIONS; do tmux has-session -t "=$s" 2>/dev/null && why="tmux session $s is back"; done
    [ -e $YIELD_FILE ] && why="$YIELD_FILE exists"
    [ -z "$why" ] && continue
    log "YIELD: $why. Ending the E4B arms and servers; the cards are the main track's again"
    stop_arms; servers_down >> $LOG 2>&1; rm -f $YIELD_FILE
    kill -TERM $MAIN 2>/dev/null; exit 0
  done
}
finish() { [ -n "$WD" ] && kill $WD 2>/dev/null; [ -z "$DRY" ] && servers_down 2>&1 | tee -a $LOG; log "e4b_chain done: $*"; exit 0; }
trap '[ -n "$WD" ] && kill $WD 2>/dev/null' EXIT
if [ "${1:-}" = watchtest ]; then   # e4b_selftest.sh: the watchdog must end a stand-in arm and this script when a named session appears
  LOG=${2:?log file}
  setsid bash -c 'echo $$ > "$0"; exec sleep 120' $PGID_FILE &
  watch_main & WD=$!
  sleep 120 & wait $!
  exit 1
fi

done_tag() { [ -s $RP/$1/results.csv ]; }
run_arms() {   # run_arms <list> <bundle> <tag> [...]: finished tags are kept; batches when the ports are fewer than the arms
  local list=$1 try todo per i; shift; local all=("$@")
  for try in 1 2 3; do
    todo=(); i=0
    while [ $i -lt ${#all[@]} ]; do
      if done_tag ${all[$((i + 1))]}; then :; else
        [ -z "$DRY" ] && [ -e $RP/${all[$((i + 1))]} ] && mv $RP/${all[$((i + 1))]} $RP/${all[$((i + 1))]}_cut$(date -u +%d%H%M%S)   # an arm cut off: set aside, run again
        todo+=(${all[$i]} ${all[$((i + 1))]})
      fi
      i=$((i + 2))
    done
    [ ${#todo[@]} -eq 0 ] && return 0
    if [ $try -gt 1 ]; then
      [ -n "$DRY" ] && return 0
      log "arms not finished: ${todo[*]}. Checking the servers, then once more (try $try of 3)"
      PORTS=($(bash $V/e4b_serve4.sh up 2>&1 | tee -a $LOG | grep "^UP" | tail -1 | sed 's/^UP *//'))
      [ ${#PORTS[@]} -gt 0 ] || { log "no E4B server answers"; sleep 300; continue; }
    fi
    per=$(( ${#PORTS[@]} * 2 )); i=0
    while [ $i -lt ${#todo[@]} ]; do
      if [ -n "$DRY" ]; then
        DRY=1 LIST=$list SCALE=$SCALE PORTS="${PORTS[*]}" bash $V/e4b_arms.sh "${todo[@]:$i:$per}" 2>&1 | tee -a $LOG
      else
        LIST=$list SCALE=$SCALE PORTS="${PORTS[*]}" setsid bash -c 'echo $$ > "$0"; exec bash "$@"' $PGID_FILE $V/e4b_arms.sh "${todo[@]:$i:$per}" >> $LOG 2>&1 &
        wait $!; rm -f $PGID_FILE
      fi
      i=$((i + per))
    done
  done
  log "STOP: arms still unfinished after three tries: ${todo[*]}"; finish "arms could not be finished"
}
fits() {   # fits <tasks one card has to run in a row>: can they end before the time box at the measured pace?
  local need; need=$(python3 -c "print(int($1 * ${PACE:-400}))"); [ $(( $(now_s) + need )) -le $(box_s) ]
}
batches() { echo $(( (3 + ${#PORTS[@]}) / ${#PORTS[@]} )); }     # 4 arms on that many cards: 1, 2 or 4 rounds

# ---- 0, 1: round 2 first, then the cards --------------------------------------------------------------------------
for b in e4b_bf5 e4b_bf5_t1k e4b_bf5_t256 e4b_bf5_t0; do [ -s $S/$b/agent.yaml ] || { echo "missing $S/$b (bash e4b_build.sh)"; exit 1; }; done
for f in $L/e4b_devA.txt $L/e4b_devB.txt $L/eval_ts01.txt; do [ -s $f ] || { echo "missing $f"; exit 1; }; done
log "e4b_chain start (time box $BOX_END UTC${DRY:+, DRY})"
if [ -n "$DRY" ]; then PORTS=(${DRY_PORTS:-8001 8002 8003 8004}); log "DRY: no wait, no servers; ports ${PORTS[*]}"; else
  # ROUND2_OVER=1: a person says round 2 is over (it was ended by hand and left no word in its log); no waiting
  if [ -n "${ROUND2_OVER:-}" ]; then log "ROUND2_OVER=1: not waiting for round 2's own word"; else wait_round2; fi
  take_cards
fi

# ---- 2: screen 1, the thinking ladder -----------------------------------------------------------------------------
B=$S/e4b_bf5; S1=""
for h in A B; do S1+=" $RP/e4b_s1_base_$h $RP/e4b_s1_t1k_$h $RP/e4b_s1_t256_$h $RP/e4b_s1_t0_$h"; done
if [ ! -s $W/pick1.txt ]; then
  for h in A B; do
    log "screen 1, half $h"
    run_arms $L/e4b_dev$h.txt $B e4b_s1_base_$h ${B}_t1k e4b_s1_t1k_$h ${B}_t256 e4b_s1_t256_$h ${B}_t0 e4b_s1_t0_$h
  done
  if [ -n "$DRY" ]; then echo "PICK ${DRY_PICK1:-e4b_bf5_t0}" > $W/pick1.txt; else
    python3 $V/e4b_pick.py screen --base $RP/e4b_s1_base_A $RP/e4b_s1_base_B \
      --arm e4b_bf5_t1k=$RP/e4b_s1_t1k_A,$RP/e4b_s1_t1k_B --arm e4b_bf5_t256=$RP/e4b_s1_t256_A,$RP/e4b_s1_t256_B \
      --arm e4b_bf5_t0=$RP/e4b_s1_t0_A,$RP/e4b_s1_t0_B --gain 2 --per 64 --out $W/screen1.md 2>&1 | tee -a $LOG | tail -1 > $W/pick1.txt
  fi
fi
P1=$(sed 's/^PICK //' $W/pick1.txt); case "$P1" in e4b_bf5_t1k|e4b_bf5_t256|e4b_bf5_t0) ;; *) P1=e4b_bf5;; esac
[ -z "$DRY" ] && PACE=$(python3 $V/e4b_pick.py pace --dirs $S1 2>/dev/null | tail -1)
PACE=${PACE:-400}; [ "$PACE" = 0 ] && PACE=400
log "screen 1: base for what follows = $P1; pace $PACE replica seconds per task"

# ---- 3: screen 2, the two approved E1+R1 lines on that base -------------------------------------------------------
STACK=$P1
if [ ! -s $W/pick2.txt ]; then
  if fits $(( (128 + 154) * $(batches) )); then
    E=${P1}_e1r1; THINK=$(grep -o "thinking_budget: [0-9]*" $S/$P1/configs/sampling.yaml | grep -o "[0-9]*$")
    if [ -n "$DRY" ]; then log "DRY: bash e4b_build.sh one $E budgetfit_e1r1 $THINK"; else bash $V/e4b_build.sh one $E budgetfit_e1r1 $THINK 2>&1 | tee -a $LOG; fi
    if [ -n "$DRY" ] || [ -s $S/$E/agent.yaml ]; then
      for h in A B; do
        log "screen 2, half $h"
        if [ -n "$DRY" ]; then log "DRY: arms $P1 e4b_s2_base1_$h, $E e4b_s2_e1r1a_$h, $P1 e4b_s2_base2_$h, $E e4b_s2_e1r1b_$h on ${PORTS[*]}"; else
          run_arms $L/e4b_dev$h.txt $S/$P1 e4b_s2_base1_$h $S/$E e4b_s2_e1r1a_$h $S/$P1 e4b_s2_base2_$h $S/$E e4b_s2_e1r1b_$h
        fi
      done
      if [ -n "$DRY" ]; then echo "PICK ${DRY_PICK2:-base}" > $W/pick2.txt; else
        python3 $V/e4b_pick.py screen --base $RP/e4b_s2_base1_A $RP/e4b_s2_base1_B $RP/e4b_s2_base2_A $RP/e4b_s2_base2_B \
          --arm $E=$RP/e4b_s2_e1r1a_A,$RP/e4b_s2_e1r1a_B,$RP/e4b_s2_e1r1b_A,$RP/e4b_s2_e1r1b_B \
          --gain 2 --per 64 --moved --out $W/screen2.md 2>&1 | tee -a $LOG | tail -1 > $W/pick2.txt
      fi
    else
      log "the E1+R1 bundle was not built; screen 2 is left out"; echo "PICK base" > $W/pick2.txt
    fi
  else
    log "screen 2 is left out: with the confirmation it does not fit the time box at $PACE s per task"; echo "PICK base" > $W/pick2.txt
  fi
fi
P2=$(sed 's/^PICK //' $W/pick2.txt); [ "$P2" = base ] || STACK=$P2
log "stack after the screens: $STACK"

# ---- 4: the stop rule ---------------------------------------------------------------------------------------------
if [ "$STACK" = e4b_bf5 ]; then
  [ -z "$DRY" ] && echo "STOP: no arm reached +2 solved per 64 tasks over e4b_bf5 (screens: $W/screen1.md, $W/screen2.md)" > $RP/e4b_confirm_verdict.txt
  finish "no arm reached the bar; no confirmation, nothing sent"
fi

# ---- 5: confirmation on the 77 EVAL tasks -------------------------------------------------------------------------
C=$S/$STACK; PASSES="a b"
fits $(( 77 * $(batches) )) || finish "the confirmation does not fit the time box; nothing sent (stack $STACK)"
log "confirmation, wave 1: e4b_bf5 against $STACK"
run_arms $L/eval_ts01.txt $B e4b_cf_base_a $C e4b_cf_cand_a $B e4b_cf_base_b $C e4b_cf_cand_b
if fits $(( 77 * $(batches) )); then
  log "confirmation, wave 2 (cards swapped)"
  run_arms $L/eval_ts01.txt $C e4b_cf_cand_c $B e4b_cf_base_c $C e4b_cf_cand_d $B e4b_cf_base_d; PASSES="a b c d"
else
  log "wave 2 does not fit the time box: the verdict stands on 2 passes"
fi
BASES=""; CANDS=""; for x in $PASSES; do BASES+=" $RP/e4b_cf_base_$x"; CANDS+=" $RP/e4b_cf_cand_$x"; done
[ -n "$DRY" ] && { log "DRY: verdict.py --base$BASES --cand$CANDS --tasks $L/eval_ts01.txt --gain 3 --cost 99 --cost-keys sec; then the 270-s rule; PASS -> tmux e4b_ship"; finish "dry run"; }
{ echo "E4B confirmation: e4b_bf5 against $STACK on the 77 EVAL tasks, passes: $PASSES"
  python3 $V/verdict.py --base $BASES --cand $CANDS --tasks $L/eval_ts01.txt --gain 3 --cost 99 --cost-keys sec 2>&1
  python3 $V/e4b_pick.py runtime --dirs $CANDS --scale $SCALE --max 270 2>&1; } > $RP/e4b_confirm_verdict.txt
tail -6 $RP/e4b_confirm_verdict.txt | tee -a $LOG

# ---- 6: a pass goes to Kaggle -------------------------------------------------------------------------------------
if grep -q "^VERDICT ADOPT" $RP/e4b_confirm_verdict.txt && grep -q "^RUNTIME OK" $RP/e4b_confirm_verdict.txt; then
  log "PASS: $STACK beats e4b_bf5 by the rule. One Kaggle run: tmux e4b_ship (logs/e4b_ship.log)"
  tmux new-session -d -s e4b_ship "bash $V/e4b_ship.sh $S/$STACK 2>&1 | tee -a logs/e4b_ship.log"
  finish "PASS, handed to e4b_ship.sh"
fi
finish "no pass; nothing sent"
