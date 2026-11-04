#!/usr/bin/env python3
"""Split the sound SWE-rebench tasks by repo into EVAL (never trained on) and TRAIN lists for run_replica.sh TASK_LIST.

EVAL takes whole repos in a seeded random order until it holds --eval-tasks tasks; a repo with more than --max-per-repo
sound tasks or a snapshot over --max-mb is left out of both lists (one repo must not dominate; giant snapshots make every
run slow). Lists are written round-robin by repo, the order the replica runs them.

  python3 rebench_split.py --sound results/rebench_soundness.csv --build data/rebench/build_log.csv --out results/lists
"""
import argparse, csv, random


def round_robin(tasks):
    by = {}
    for t in tasks: by.setdefault(t["repo"], []).append(t["instance_id"])
    qs, out = list(by.values()), []
    while any(qs):
        for q in qs:
            if q: out.append(q.pop(0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sound", required=True); ap.add_argument("--build", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--eval-tasks", type=int, default=100); ap.add_argument("--max-per-repo", type=int, default=10)
    ap.add_argument("--max-mb", type=float, default=300); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    meta = {r["instance_id"]: r for r in csv.DictReader(open(a.build))}
    sound = [dict(meta[r["instance_id"]], gold_sec=r["gold_sec"]) for r in csv.DictReader(open(a.sound)) if r["sound"] == "True"]
    by = {}
    for t in sound: by.setdefault(t["repo"], []).append(t)
    keep = {r: ts for r, ts in by.items() if len(ts) <= a.max_per_repo and max(float(t["snapshot_mb"]) for t in ts) <= a.max_mb}
    repos = sorted(keep); random.Random(a.seed).shuffle(repos)
    ev, n = [], 0
    for r in repos:
        if n >= a.eval_tasks: break
        ev.append(r); n += len(keep[r])
    tr = [r for r in repos if r not in ev]
    for name, rs in (("rebench_eval", ev), ("rebench_train", tr)):
        tasks = [t for r in rs for t in keep[r]]
        ids = round_robin(tasks)
        open(f"{a.out}/{name}.txt", "w").write(f"# {name}: {len(ids)} sound SWE-rebench tasks from {len(rs)} repos (rebench_split.py, seed {a.seed})\n" + "\n".join(ids) + "\n")
        diff = {}
        for t in tasks: diff[t["difficulty"]] = diff.get(t["difficulty"], 0) + 1
        print(f"{name}: {len(ids)} tasks from {len(rs)} repos | difficulty {dict(sorted(diff.items()))}")
    left = {r: len(ts) for r, ts in by.items() if r not in keep}
    print(f"left out (over {a.max_per_repo} tasks or {a.max_mb} MB): {left}")


if __name__ == "__main__":
    main()
