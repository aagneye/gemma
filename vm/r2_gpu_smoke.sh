#!/usr/bin/env bash
# GPU test of the round-2 training steps, run at a break of the note runs (Nov 21). The steps of chain_r2.sh that need
# the cards had never run in this form, and the chain runs them unattended a day later. It stops the note chains and our
# model server and runs
#   B  the fit test, one run per entry of FIT_TRY, longest first ("N:a,b,c,d" = length N with its own layer split);
#   C  a short training at that length and split: a checkpoint per update, one full-length row after the first update
#      and one row that cannot fit; then a restart from a checkpoint;
#   D  the held-out check (heldout_loss.py) on three rows.
# Then it ALWAYS starts the note runs and the chain again (also when a test fails or the script dies), and writes the
# entry that passed B and C to datasets/r2/fit_try.txt, which chain_r2.sh reads.
#   BOX_END=<epoch seconds> [POSITION=C] [FIT_TRY="15360:9,18,18,15 15360 14336:9,18,18,15 14336 13312 12288"] bash r2_gpu_smoke.sh
# Data (built on CPU before, smoke_rows.py): datasets/r2/tok_len_16384, tok_smoke_<N>, tok_heldout_smoke.
# New versions of the two chain scripts are taken from <script>.new once the chains are stopped.
# Log: logs/r2_smoke.log, last line SMOKE_DONE. Shared VM: it stops only our own tmux sessions and note-run processes.
set -u
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; PY=$R/.venv/bin/python; LOG=logs/r2_smoke.log; D=datasets/r2
BASE=models/gemma-4-31B-it-qat-q4_0-unquantized; RANK=${RANK:-16}; ALPHA=${ALPHA:-32}; OUT=runs/r2_smoke; POS=${POSITION:-C}
BOX_END=${BOX_END:?epoch seconds at which the time box of the note runs closes}
FIT_TRY=${FIT_TRY:-"15360:9,18,18,15 15360 14336:9,18,18,15 14336 13312 12288"}
log() { echo "$(date -u) | $*" | tee -a $LOG; }
free() { for u in $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits); do [ "$u" -lt 1000 ] || return 1; done; }
wait_free() { for i in $(seq 1 60); do free && return 0; sleep 5; done; return 1; }
restart() {
  trap - EXIT
  wait_free || log "WARNING: a card is still in use at the end of the test"
  tmux new -d -s r2notes "POSITION=$POS BOX_END=$BOX_END CHUNK=20 bash $V/r2_notes_chain.sh"
  sleep 2
  tmux new -d -s r2chain "WAIT_FOR=r2notes EXTRA_TAGS=\"r2_pilot_train_c r2_pilot_rb2_c\" bash $V/chain_r2.sh"
  log "note runs and chain started again (fit_try.txt: $(cat $D/fit_try.txt 2>/dev/null || echo none))"; log SMOKE_DONE
}
trap restart EXIT

log "smoke test start: stopping the note chains and the model server"
tmux kill-session -t r2chain 2>/dev/null; tmux kill-session -t r2notes 2>/dev/null; sleep 3
for p in $(pgrep -u "$(id -u)" -f 'takeover_proxy\.py|netns_bridge\.py|local_score\.py|run_replica\.sh|note_runs\.sh|netns_run\.sh'); do kill $p 2>/dev/null; done
for f in chain_r2.sh r2_notes_chain.sh; do [ -f $V/$f.new ] && mv $V/$f.new $V/$f && log "installed the new $f"; done
tmux kill-session -t vllm 2>/dev/null
wait_free || { log "SMOKE FAIL: the cards are not free (another job holds them); nothing of theirs was touched"; exit 1; }

# ---- B: the longest length that fits ----------------------------------------------------------------------------------
FIT=""; SPLIT=""; WIN=""
for T in $FIT_TRY; do
  N=${T%%:*}; SPL=""; [ "$T" != "$N" ] && SPL="--layers-per-gpu ${T#*:}"; P=logs/r2_smoke_probe_$(echo $T | tr ':,' '_-').log
  timeout 1500 $PY $V/train_qlora.py --model $BASE --data $D/tok_len_16384 --out runs/r2_smoke_probe --pipeline 4 --attn qchunk --max-len $N \
    --rank $RANK --alpha $ALPHA $SPL --fit-probe --fit-ladder $N --probe-only > $P 2>&1
  grep -h "fit_probe\|layers per GPU" $P | cut -c1-300 | tee -a $LOG
  if [ "$(grep -o '"fit": [0-9]*' $P | tail -1 | grep -o '[0-9]*$')" = "$N" ]; then
    FIT=$N; WIN=$T; SPLIT=$(grep -o "layers per GPU \[[0-9, ]*\]" $P | tail -1 | tr -d ' ' | grep -o "[0-9,]*" | tail -1); break
  fi
  log "B: $T does not fit"; wait_free || { log "SMOKE FAIL: the cards did not come free after a fit test"; exit 1; }
done
[ -n "$FIT" ] || { log "SMOKE FAIL B: no length of FIT_TRY fits"; exit 1; }
log "SMOKE B: $FIT tokens fit with layers per card $SPLIT (entry $WIN)"

# ---- C: training with checkpoints, a full row, a row that cannot fit; then a restart ----------------------------------
rm -rf $OUT; mkdir -p $OUT; S=$D/tok_smoke_$FIT; SEED=$(cat $S/seed.txt)
train() { timeout 2400 $PY $V/train_qlora.py --model $BASE --data $S --out $OUT --pipeline 4 --attn qchunk --max-len 40000 --layers-per-gpu $SPLIT \
    --rank $RANK --alpha $ALPHA --lr 1e-4 --optim adamw --epochs 1 --grad-accum 1 --log-every 1 --save-every 1 --max-steps 4 --seed $SEED --deadline-min 40 "$@" >> $OUT/train.log 2>&1; }
wait_free; train; RC=$?
grep -h "oom_row\|first_micro\|\"step\"\|summary\|saved ->" $OUT/train.log | cut -c1-330 | tee -a $LOG
OOMS=$(grep -c '"oom_row"' $OUT/train.log); CK=$(ls -d $OUT/ckpt_* 2>/dev/null | wc -l)
if [ $RC -eq 0 ] && [ -f $OUT/final/adapter_model.safetensors ] && [ "$OOMS" = 1 ] && [ "$CK" -ge 4 ]; then
  log "SMOKE C PASS: 4 updates, $CK checkpoints, the full row trained, the row that cannot fit was left out"
  echo "$WIN $(for T in $FIT_TRY; do n=${T%%:*}; [ "$n" -lt "$FIT" ] && [ "$T" = "$n" ] && printf '%s ' $T; done)" > $D/fit_try.txt
else
  log "SMOKE C FAIL: exit $RC, checkpoints $CK, rows left out $OOMS (1 expected); see $OUT/train.log"
  # a full row that fits the fit test but not the training: the chain starts one length lower
  [ "$OOMS" -ge 2 ] && echo "$(for T in $FIT_TRY; do n=${T%%:*}; [ "$n" -lt "$FIT" ] && [ "$T" = "$n" ] && printf '%s ' $T; done)" > $D/fit_try.txt
fi
if [ -d $OUT/ckpt_3 ]; then
  wait_free; mv $OUT/final $OUT/final_first 2>/dev/null; echo "---- restart from ckpt_3 ----" >> $OUT/train.log; train --resume $OUT/ckpt_3; RC=$?
  sed -n '/---- restart from ckpt_3 ----/,$p' $OUT/train.log | grep -h "resumed\|resume:\|oom_row\|\"step\"\|summary\|saved ->" | cut -c1-330 | tee -a $LOG
  if [ $RC -eq 0 ] && [ -f $OUT/final/adapter_model.safetensors ] && sed -n '/---- restart from ckpt_3 ----/,$p' $OUT/train.log | grep -q "resume: skipping the first 3 rows"; then
    log "SMOKE C2 PASS: the restart went on at update 4 and skipped the rows trained before"
  else log "SMOKE C2 FAIL: exit $RC; see the end of $OUT/train.log"; fi
fi

# ---- D: the held-out check --------------------------------------------------------------------------------------------
A=$OUT/final; [ -d $A ] || A=$OUT/final_first
if [ -d $A ]; then
  wait_free
  timeout 1500 $PY $V/heldout_loss.py --adapter $A --more $(ls -d $OUT/ckpt_1 2>/dev/null) --data $D/tok_heldout_smoke --max-len $FIT --rank $RANK \
    --out results/r2_smoke_heldout.json > logs/r2_smoke_heldout.log 2>&1; RC=$?
  grep -E "step loss|SANITY" logs/r2_smoke_heldout.log | cut -c1-220 | tee -a $LOG
  if grep -q "^SANITY" logs/r2_smoke_heldout.log; then log "SMOKE D PASS: the held-out check runs (its verdict on a 4-update adapter means nothing)"
  else log "SMOKE D FAIL: exit $RC; see logs/r2_smoke_heldout.log"; tail -5 logs/r2_smoke_heldout.log | cut -c1-300 | tee -a $LOG; fi
else
  log "SMOKE D skipped: no adapter from C"
fi
