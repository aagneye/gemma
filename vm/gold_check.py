#!/usr/bin/env python3
"""Gold-patch soundness check for the public tasks using the real swegemma verifier.

For every task the 'agent' patch is the reference patch (task.patch) and, in a second mode, an empty patch.
A task is SOUND iff gold passes AND empty fails. Results go to results/gold_soundness.csv.

  python gold_check.py --root /mnt/biohub/kdata/gemma4/data/grader --out results/gold_soundness.csv --mode gold --concurrency 6
  python gold_check.py ... --mode empty
Run inside harness-venv with the Docker daemon available to the user.
"""
import argparse, asyncio, csv, json, os, sys, time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="dir containing tasks.jsonl, snapshots/, wheels/")
    ap.add_argument("--out", required=True); ap.add_argument("--mode", choices=["gold", "empty"], default="gold")
    ap.add_argument("--concurrency", type=int, default=4); ap.add_argument("--task-ids", nargs="*", default=None)
    ap.add_argument("--verification-timeout", type=int, default=600); ap.add_argument("--image", default="swebench-sandbox:latest")
    ap.add_argument("--sandbox", choices=["subprocess", "docker"], default="docker"); ap.add_argument("--stub", default=None)
    a = ap.parse_args()
    root = Path(a.root)

    from adk_eval_core.tracing import SessionTrace
    from swegemma.config import EvalConfig
    from swegemma.evaluate import Evaluator
    from swegemma.models import load_tasks
    from adk_submission import ModelRegistry

    tasks = load_tasks(root / "tasks.jsonl")
    if a.task_ids: tasks = [t for t in tasks if t.instance_id in set(a.task_ids)]
    gold = {t.instance_id: t.patch for t in tasks}
    results_dir = Path(a.out).parent / f"gold_run_{a.mode}"; results_dir.mkdir(parents=True, exist_ok=True)

    cfg = EvalConfig(tasks_path=root / "tasks.jsonl", snapshots_dir=root / "snapshots", results_dir=results_dir,
                     submission_dir=Path(a.stub) if a.stub else root / "submission_stub", models=ModelRegistry(), sandbox=a.sandbox,
                     **({"image": a.image} if a.sandbox == "docker" else {}),
                     wheels_dir=root / "wheels", verification_timeout_seconds=a.verification_timeout,
                     task_ids=[t.instance_id for t in tasks], concurrency=a.concurrency, display_mode="quiet",
                     graph_dir=str(root / "graphs"), embeddings_dir=str(root / "embeddings"))

    class GoldEvaluator(Evaluator):
        async def _run_agent_sandbox(self, task, snapshot_path, task_index, total_tasks, **kw):
            return (gold[task.instance_id] if a.mode == "gold" else ""), None, SessionTrace()

    ev = GoldEvaluator(cfg)
    t0 = time.time()
    res = asyncio.run(ev.run())
    print(f"{a.mode}: resolved {res.resolved}/{res.total} in {(time.time()-t0)/60:.1f} min")
    rows = []
    for line in open(results_dir / "task_results.jsonl"):
        r = json.loads(line); rows.append(r)
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["instance_id", "repo", "mode", "resolved", "exit_code", "error"])
        for r in rows:
            iid = r.get("instance_id") or r.get("id")
            w.writerow([iid, iid.split("_")[0], a.mode, r.get("resolved"), r.get("test_exit_code"), (r.get("error") or "")[:160].replace("\n", " ")])
    print("wrote", a.out)


if __name__ == "__main__":
    main()
