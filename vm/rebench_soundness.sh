#!/usr/bin/env bash
# Gold/empty soundness of a task set built by build_rebench_tasks.py, run WITHOUT network (user decision 2026-11-03:
# third-party repo code runs on the VM with the internet cut off). Every gold_check.py run sits inside `unshare -rn`
# (new user + network namespace, loopback up) with TMPDIR on the data disk (the root disk has ~24 GB free).
# Sound = the gold patch resolves twice, the empty patch does not, and gold setup + grading takes <= MAX_SEC.
# Output: results/<tag>_soundness.csv (instance_id,repo,gold_pass,empty_pass,sound,gold_sec), usable as ORDER_CSV.
#   [CONC=16] [MAX_SEC=180] bash rebench_soundness.sh [root=data/rebench] [tag=rebench]
set -u
ROOT=${1:-data/rebench}; TAG=${2:-rebench}; CONC=${CONC:-16}; MAX_SEC=${MAX_SEC:-180}
R=/mnt/biohub/kdata/gemma4; cd $R
export TMPDIR=$R/tmp/sound_$TAG; mkdir -p $TMPDIR results/$TAG/pass1 results/$TAG/pass2
PY=$R/${VENV:-scorer-host-venv}/bin/python   # VENV=scorer-host-venv-plus only for TRAIN-pool task sets
check() {   # <mode> <out_dir> [task ids]
  unshare -rn sh -c "ip link set lo up && exec $PY $HOME/gemma4_vm/gold_check.py --root $ROOT --out $2/$1.csv --mode $1 \
    --sandbox subprocess --concurrency $CONC --stub data/grader/submission_stub --verification-timeout 300 ${3:+--task-ids $3}"
}
echo "$(date -u) soundness $ROOT ($(wc -l < $ROOT/tasks.jsonl) tasks) conc=$CONC, no network"
check gold results/$TAG/pass1; check empty results/$TAG/pass1
IDS=$(python3 -c "import csv;print(' '.join(r['instance_id'] for r in csv.DictReader(open('results/$TAG/pass1/gold.csv')) if r['resolved']=='True'))")
[ -n "$IDS" ] && check gold results/$TAG/pass2 "$IDS"
python3 - "$TAG" "$MAX_SEC" <<'PY'
import csv, json, os, sys
tag, max_sec = sys.argv[1], float(sys.argv[2])
def res(path): return {r["instance_id"]: r["resolved"] == "True" for r in csv.DictReader(open(path))} if os.path.exists(path) else {}
g1, e1, g2 = res(f"results/{tag}/pass1/gold.csv"), res(f"results/{tag}/pass1/empty.csv"), res(f"results/{tag}/pass2/gold.csv")
sec = {}
for l in open(f"results/{tag}/pass1/gold_run_gold/task_results.jsonl"):
    r = json.loads(l); sec[r["instance_id"]] = float(r.get("duration_seconds") or 0)
rows, n = [], 0
for iid in g1:
    gold = g1[iid] and g2.get(iid, False); empty = e1.get(iid, True)
    sound = gold and not empty and sec.get(iid, 1e9) <= max_sec; n += sound
    rows.append([iid, iid.split("_")[0], gold, empty, sound, round(sec.get(iid, 0), 1)])
with open(f"results/{tag}_soundness.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["instance_id", "repo", "gold_pass", "empty_pass", "sound", "gold_sec"]); w.writerows(rows)
print(f"sound {n}/{len(rows)} | gold pass1 {sum(g1.values())}, pass2 {sum(g2.values())} | empty passes {sum(e1.values())} -> results/{tag}_soundness.csv")
PY
echo "$(date -u) soundness done"
