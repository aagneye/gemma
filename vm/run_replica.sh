#!/usr/bin/env bash
# Replica of the public scorer on the VM: scorer-host-venv (Kaggle host packages) + subprocess sandbox + vLLM on T4s.
#   [PORT=8000] [REPLICA_TIME_SCALE=k] bash run_replica.sh <submission_dir> <tag> [first=50] [time_min=36] [concurrency=3]
# Same task order as the Kaggle-environment notebooks (Kaggle-sound, round-robin by repo). time_min scales the
# 8-min budget for T4 speed (31B decodes ~3.5x slower than on L4); prefer time_min = the bundle's own
# max_time_minutes plus REPLICA_TIME_SCALE (clock scaling, see patch_replica_clock.py). PORT selects the vLLM server
# (one per GPU for E4B experiments). Output: results/replica/<tag>/{results.csv,agent_run/,run.log}
set -u
SUB=$1; TAG=$2; N=${3:-50}; T=${4:-36}; C=${5:-3}
if [ "$T" = auto ]; then T=$(grep -E "max_time_minutes:" "$SUB/eval_config.yaml" | head -1 | sed "s/.*: *//"); fi   # the bundle's own budget
R=/mnt/biohub/kdata/gemma4; cd $R; source scorer-host-venv/bin/activate
export REPLICA_TIME_SCALE=${REPLICA_TIME_SCALE:-1}   # replica-only clock scaling (patch_replica_clock.py)
export LOCAL_INFERENCE_URL=http://127.0.0.1:${PORT:-8000}/v1
OUT=results/replica/$TAG; rm -rf $OUT; mkdir -p $OUT
echo "$(date -u) run_replica sub=$SUB tag=$TAG n=$N time=$T conc=$C scale=$REPLICA_TIME_SCALE url=$LOCAL_INFERENCE_URL" > $OUT/run.log
python ~/gemma4_vm/local_score.py --root data/comp --sandbox subprocess --submission $SUB --results $OUT/agent_run \
  --time $T --concurrency $C --order-csv results/kaggle_soundness.csv --first $N >> $OUT/run.log 2>&1
python3 - "$OUT" <<'PY'
import csv, json, sys
out = sys.argv[1]; rows = [json.loads(l) for l in open(out + "/agent_run/task_results.jsonl")]
with open(out + "/results.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["instance_id", "repo", "resolved", "exit_code", "patch_chars", "tool_calls", "duration_s", "error"])
    for r in rows:
        w.writerow([r["instance_id"], r["instance_id"].split("_")[0], bool(r.get("resolved")), r.get("test_exit_code"),
                    r.get("agent_patch_size") or 0, r.get("tool_calls"), r.get("duration_seconds"), (r.get("error") or "")[:160]])
print("REPLICA_DONE", out, "resolved", sum(1 for r in rows if r.get("resolved")), "/", len(rows))
PY
