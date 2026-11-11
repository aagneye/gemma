#!/usr/bin/env bash
# Kaggle 4xL4 runtime check of an adapter bundle before it takes a daily slot (user approvals 2026-11-10 and 2026-11-11).
# Default: waits for the gate's tmux session and applies the Gate 1 rule with vm/verdict.py (>= +3 on the 77
# test_score <= 1 EVAL tasks; not negative on all 109; practice swing set >= -1; calls and output tokens <= x1.08).
# FORCE=1 skips the gate (user decision 2026-11-11: the adapter goes to Kaggle after the runtime check, whatever the gate).
# Then: uploads the adapter as a private dataset (once), pushes the speed notebook (vm/make_kaggle_speed.py: the plain
# server as the scorer serves Budget-Fit vs the LoRA server with the adapter; no agent runs), waits, and applies the
# runtime rule: decode slowdown at 1 and 4 requests <= MAX_SLOW (1.125: with the adapter's x0.96 output tokens its
# generation time stays <= x1.08 of Budget-Fit's, the cost rule every bundle meets; v6 at +14 % tokens exceeded 12 h).
# On GO, if SHIP_LINE_FILE exists (written only after the submission notebook's output was checked against the
# validated bundle), its line "owner/kernel version message" is scheduled for the next daily slot in ship_schedule.txt.
#   FORCE=1 bash l4_speed_check.sh none [bundle=submissions/budgetfit_v5_lora1] [cand_eval=lora1_eval] [cand_swing=lora1_sw]
set -u
GATE=${1:-gate1}; BUNDLE=${2:-submissions/budgetfit_v5_lora1}; CE=${3:-lora1_eval}; CS=${4:-lora1_sw}
R=/mnt/biohub/kdata/gemma4; cd $R; K=$R/.venv/bin/kaggle; RR=results/replica; S=tmp/speedcheck
DS=aagneye/gemma4-31b-lora1-adapter; NB=aagneye/gemma4-31b-lora-speed
MAX_SLOW=${MAX_SLOW:-1.125}; SHIP_LINE_FILE=${SHIP_LINE_FILE:-results/lists/adapter_ship_line.txt}
if [ "${FORCE:-0}" != 1 ]; then
  bash ~/gemma4_vm/after_session.sh $GATE
  { python3 ~/gemma4_vm/verdict.py --base $RR/bf5_eval --cand $RR/$CE --tasks results/lists/eval_ts01.txt --gain 3 --cost 1.08 --cost-keys calls,tok
    python3 ~/gemma4_vm/verdict.py --base $RR/bf5_eval --cand $RR/$CE --gain 0 --cost 1.08 --cost-keys calls,tok
    python3 ~/gemma4_vm/verdict.py --base $RR/bf5_sw1 $RR/bf5_sw2 --cand $RR/$CS $RR/$CS --gain -1 --cost 9 --cost-keys calls; } | tee $RR/${CE}_gate.txt
  n=$(grep -c "^VERDICT ADOPT" $RR/${CE}_gate.txt)
  echo "$(date -u) gate parts passed: $n of 3"
  [ "$n" -eq 3 ] || { echo "gate not won: no Kaggle speed check"; exit 0; }
else
  echo "$(date -u) FORCE=1: gate skipped (user decision 2026-11-11)"
fi
if $K datasets status $DS 2>/dev/null | grep -qi ready; then
  echo "dataset $DS already exists"
else
  rm -rf $S/ds && mkdir -p $S/ds && cp $BUNDLE/adapters/main_lora/* $S/ds/
  printf '{"title": "gemma4-31b-lora1-adapter", "id": "%s", "licenses": [{"name": "other"}]}\n' $DS > $S/ds/dataset-metadata.json
  $K datasets create -p $S/ds 2>&1 | grep -v Warning | tail -1
  for i in $(seq 1 60); do $K datasets status $DS 2>/dev/null | grep -qi ready && break; sleep 30; done
  echo "$(date -u) dataset status: $($K datasets status $DS 2>&1 | grep -v Warning | tail -1)"
fi
python3 ~/gemma4_vm/make_kaggle_speed.py $S/nb $NB "Gemma4 31B LoRA speed" --bundle $BUNDLE --adapter-dataset $DS || exit 1
$K kernels push -p $S/nb --accelerator NvidiaL4 -t 5400 2>&1 | grep -v Warning | tail -1
st=""; for i in $(seq 1 75); do sleep 120; st=$($K kernels status $NB 2>&1 | grep -v Warning); echo "$st" | grep -qiE "complete|error|cancel" && break; done
echo "$(date -u) $st"
rm -rf $S/out && $K kernels output $NB -p $S/out > /dev/null 2>&1
python3 - "$S/out" "$MAX_SLOW" <<'EOF' | tee $RR/lora1_l4_speed.txt
import glob, json, sys
f = sorted(glob.glob(sys.argv[1] + '/**/speed.json', recursive=True))
if not f: print('RUNTIME UNKNOWN: no speed.json (see the notebook log)'); sys.exit()
r = json.load(open(f[0])); lim = float(sys.argv[2])
print({k: v for k, v in r.items() if k.startswith(('slowdown', 'lora_server', 'vllm_up', 'gpu', 'tp'))})
worst = max(r['slowdown_decode_c1'], r['slowdown_decode_c4'])
print(f"RUNTIME {'GO' if worst <= lim else 'HOLD'}: worst decode slowdown {worst:.3f} (limit {lim}); generation time x{0.96 * worst:.3f} of Budget-Fit's")
EOF
if grep -q "^RUNTIME GO" $RR/lora1_l4_speed.txt; then
  if [ -s $SHIP_LINE_FILE ]; then
    day=$(date -u -d "+1 day" +%F); [ "$(date -u +%H%M)" -lt 0005 ] && day=$(date -u +%F)
    echo "$day $(head -1 $SHIP_LINE_FILE)" >> results/ship_schedule.txt
    echo "$(date -u) scheduled for $day: $(head -1 $SHIP_LINE_FILE)"
  else
    echo "$(date -u) GO, but no checked submission notebook ($SHIP_LINE_FILE missing): nothing scheduled"
  fi
else
  echo "$(date -u) adapter not scheduled (runtime check did not pass)"
fi
echo "$(date -u) l4_speed_check done"
