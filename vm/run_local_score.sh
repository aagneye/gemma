#!/usr/bin/env bash
# Score one submission package locally on the sound public tasks (per-repo images/wheels), like the Kaggle scorer.
#   bash run_local_score.sh <submission_dir> <tag> [time_minutes] [concurrency]
set -u
SUB=$1; TAG=$2; T=${3:-30}; C=${4:-3}
R=/mnt/biohub/kdata/gemma4; cd $R; source harness-venv/bin/activate
export LOCAL_INFERENCE_URL=http://127.0.0.1:8000/v1
sound() { python3 -c "import csv,sys; print(' '.join(r['instance_id'] for r in csv.DictReader(open('results/gold_soundness.csv')) if r['sound']=='True' and r['repo']==sys.argv[1]))" "$1"; }
FA=$(sound fastapi); RE=$(sound requests); HX=$(sound httpx)
OUT=results/local/$TAG; mkdir -p $OUT
python ~/gemma4_vm/local_score.py --root data/grader     --image swebench-sandbox-fa:latest  --submission $SUB --results $OUT/fa --time $T --concurrency $C --task-ids $FA
python ~/gemma4_vm/local_score.py --root data/grader_req --image swebench-sandbox-req:latest --submission $SUB --results $OUT/req --time $T --concurrency $C --task-ids $RE
python ~/gemma4_vm/local_score.py --root data/grader     --image swebench-sandbox:latest     --submission $SUB --results $OUT/hx --time $T --concurrency 1 --task-ids $HX
python3 - "$OUT" <<'PY'
import json, sys, glob
rows = {}
for f in glob.glob(sys.argv[1] + "/*/task_results.jsonl"):
    for l in open(f):
        r = json.loads(l); rows[r["instance_id"]] = r
res = sum(1 for r in rows.values() if r.get("resolved"))
print(json.dumps({"tag": sys.argv[1], "resolved": res, "total": len(rows), "resolution_rate": round(res / max(1, len(rows)), 4),
                  "no_patch": sum(1 for r in rows.values() if not r.get("agent_patch_size")),
                  "mean_tool_calls": round(sum(r.get("tool_calls", 0) for r in rows.values()) / max(1, len(rows)), 1),
                  "resolved_ids": sorted(i for i, r in rows.items() if r.get("resolved"))}))
PY
echo LOCAL_SCORE_DONE
