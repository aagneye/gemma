#!/usr/bin/env bash
# E4B screen 3 (Nov 26; user: "find what is losing us, fix it, re-run it, submit"): the compile checker.
# The base loses 17 of 384 dev runs to its own edit breaking the file (IndentationError 9, SyntaxError 8; note 20 and
# research/ledger/e4b_track.md). e4b_chk = the base prompt as a solver that hands over, then a checker agent that runs
# py_compile on the edited files, fixes a syntax error and submits. Arms on the 128 dev tasks (halves A and B): the
# checker x3 and the base x1 (a fresh copy, to see drift), paired against the base's three earlier passes as well.
#   tmux new -d -s e4b_s3 "bash ~/gemma4_vm/e4b_screen3.sh"
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; S=submissions; RP=results/replica; L=results/lists; LOG=logs/e4b_screen3.log
log() { echo "$(date -u) | $*" | tee -a $LOG; }
P=$(bash $V/e4b_serve4.sh up 2>&1 | tee -a $LOG | grep "^UP" | tail -1 | sed 's/^UP *//')
log "servers: $P"; [ -n "$P" ] || { log "no server"; exit 1; }
for h in A B; do
  ARMS=($S/e4b_chk e4b_s3_chk1_$h $S/e4b_chk e4b_s3_chk2_$h $S/e4b_chk e4b_s3_chk3_$h $S/e4b_bf5 e4b_s3_base_$h)
  todo=(); i=0; while [ $i -lt ${#ARMS[@]} ]; do [ -s $RP/${ARMS[$((i+1))]}/results.csv ] || { rm -rf $RP/${ARMS[$((i+1))]}; todo+=(${ARMS[$i]} ${ARMS[$((i+1))]}); }; i=$((i+2)); done
  [ ${#todo[@]} -gt 0 ] && { log "half $h: ${todo[*]}"; LIST=$L/e4b_dev$h.txt PORTS="$P" bash $V/e4b_arms.sh "${todo[@]}" >> $LOG 2>&1; }
done
python3 $V/e4b_pick.py screen --base $RP/e4b_s1_base_A $RP/e4b_s2_base1_A $RP/e4b_s2_base2_A $RP/e4b_s1_base_B $RP/e4b_s2_base1_B $RP/e4b_s2_base2_B \
  --arm e4b_chk=$RP/e4b_s3_chk1_A,$RP/e4b_s3_chk2_A,$RP/e4b_s3_chk3_A,$RP/e4b_s3_chk1_B,$RP/e4b_s3_chk2_B,$RP/e4b_s3_chk3_B \
  --gain 2 --per 64 --out results/e4b/screen3.md 2>&1 | tee -a $LOG
python3 $V/e4b_pick.py screen --base $RP/e4b_s1_base_A $RP/e4b_s1_base_B --arm fresh_base=$RP/e4b_s3_base_A,$RP/e4b_s3_base_B --gain 99 2>&1 | tail -6 | tee -a $LOG
python3 $V/e4b_pick.py runtime --dirs $RP/e4b_s3_chk1_A $RP/e4b_s3_chk1_B $RP/e4b_s3_chk2_A $RP/e4b_s3_chk2_B 2>&1 | tee -a $LOG
bash $V/e4b_serve4.sh down >> $LOG 2>&1
log "screen 3 done"
