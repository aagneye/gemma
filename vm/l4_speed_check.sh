#!/usr/bin/env bash
# Kaggle 4xL4 speed check of an adapter (user approval 2026-11-10), run only when its gate is won.
# Waits for the gate's tmux session, applies the Gate 1 rule with vm/verdict.py (>= +3 on the 77 test_score <= 1 EVAL
# tasks; not negative on all 109; practice swing set >= -1; calls and output tokens <= x1.08), and only if all three
# parts pass: uploads the adapter as a private dataset, pushes the speed notebook (vm/make_kaggle_speed.py: base vs
# adapter tokens/s, no agent runs), waits for it and prints the slowdowns from speed.json.
#   bash l4_speed_check.sh [gate_session=gate1] [bundle=submissions/budgetfit_v5_lora1] [cand_eval=lora1_eval] [cand_swing=lora1_sw]
set -u
GATE=${1:-gate1}; BUNDLE=${2:-submissions/budgetfit_v5_lora1}; CE=${3:-lora1_eval}; CS=${4:-lora1_sw}
R=/mnt/biohub/kdata/gemma4; cd $R; K=$R/.venv/bin/kaggle; RR=results/replica; S=tmp/speedcheck
DS=aagneye/gemma4-31b-lora1-adapter; NB=aagneye/gemma4-31b-lora-speed
bash ~/gemma4_vm/after_session.sh $GATE
{ python3 ~/gemma4_vm/verdict.py --base $RR/bf5_eval --cand $RR/$CE --tasks results/lists/eval_ts01.txt --gain 3 --cost 1.08 --cost-keys calls,tok
  python3 ~/gemma4_vm/verdict.py --base $RR/bf5_eval --cand $RR/$CE --gain 0 --cost 1.08 --cost-keys calls,tok
  python3 ~/gemma4_vm/verdict.py --base $RR/bf5_sw1 $RR/bf5_sw2 --cand $RR/$CS $RR/$CS --gain -1 --cost 9 --cost-keys calls; } | tee $RR/${CE}_gate.txt
n=$(grep -c "^VERDICT ADOPT" $RR/${CE}_gate.txt)
echo "$(date -u) gate parts passed: $n of 3"
[ "$n" -eq 3 ] || { echo "gate not won: no Kaggle speed check"; exit 0; }
rm -rf $S/ds && mkdir -p $S/ds && cp $BUNDLE/adapters/main_lora/* $S/ds/
printf '{"title": "gemma4-31b-lora1-adapter", "id": "%s", "licenses": [{"name": "other"}]}\n' $DS > $S/ds/dataset-metadata.json
$K datasets create -p $S/ds 2>&1 | grep -v Warning | tail -1
for i in $(seq 1 60); do $K datasets status $DS 2>/dev/null | grep -qi ready && break; sleep 30; done
python3 ~/gemma4_vm/make_kaggle_speed.py $S/nb $NB "Gemma4 31B LoRA speed check" --bundle $BUNDLE --adapter-dataset $DS
$K kernels push -p $S/nb --accelerator NvidiaL4 -t 5400 2>&1 | grep -v Warning | tail -1
for i in $(seq 1 60); do st=$($K kernels status $NB 2>&1 | grep -v Warning); echo "$st" | grep -qiE "complete|error|cancel" && break; sleep 120; done
echo "$(date -u) $st"
rm -rf $S/out && $K kernels output $NB -p $S/out > /dev/null 2>&1
python3 -c "import json; r=json.load(open('$S/out/eval/speed.json')); print({k: v for k, v in r.items() if k.startswith('slowdown') or k in ('gpu', 'tp', 'vllm_up_min')})" 2>&1
echo "$(date -u) l4_speed_check done"
