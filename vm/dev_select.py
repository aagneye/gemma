#!/usr/bin/env python3
"""Pick the dev tasks for instruction screens (Nov 11 plan) from the training pool, never from the EVAL tasks.

Four groups of --per-group tasks, taken from Budget-Fit's run on the pool (results/replica/bf5_train):
  loop     3 or more garbled edit_file calls ("mandatory input parameters are not present")
  partial  unsolved; the patch edits some but not all of the gold patch's non-test .py files
  narrow   unsolved; the patch edits every gold file, yet target tests still fail (a test log exists)
  solved   solved at temperature 0.2 and again at 0.6 (results/replica/bf5t06_train2)
Within a group, tasks whose tests fit the issue (test_score <= 1) and with difficulty >= 1 come first; at most
--per-repo tasks per repo over the whole set; seeded shuffle. Writes <out>.txt (ids) and <out>.csv (instance_id,group).

  python3 dev_select.py --out results/lists/dev48
"""
import argparse, csv, json, os, random, re


def patch_files(text):
    return {p for p in re.findall(r"^diff --git a/(\S+) b/", text or "", re.M)}


def is_test(p):
    b = p.rsplit("/", 1)[-1]
    return b.startswith("test_") or b.endswith("_test.py") or "/tests/" in "/" + p or "/test/" in "/" + p or b == "conftest.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="results/replica/bf5_train"); ap.add_argument("--rerun", default="results/replica/bf5t06_train2")
    ap.add_argument("--tasks", default="data/rebench/tasks.jsonl"); ap.add_argument("--build-log", default="data/rebench/build_log.csv")
    ap.add_argument("--out", required=True); ap.add_argument("--per-group", type=int, default=12)
    ap.add_argument("--per-repo", type=int, default=3); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    tasks = {json.loads(l)["instance_id"]: json.loads(l) for l in open(a.tasks)}
    meta = {r["instance_id"]: r for r in csv.DictReader(open(a.build_log))}
    rerun = {json.loads(l)["instance_id"]: bool(json.loads(l).get("resolved")) for l in open(f"{a.rerun}/agent_run/task_results.jsonl")}
    groups = {"loop": [], "partial": [], "narrow": [], "solved": []}
    for l in open(f"{a.run}/agent_run/task_results.jsonl"):
        r = json.loads(l); iid = r["instance_id"]; res = bool(r.get("resolved"))
        garbled = 0
        for s in json.load(open(f"{a.run}/agent_run/traces/trace_{iid}.json")).get("steps", []):
            for c in (s.get("tool_calls") or []):
                o = (s.get("observation") or {}).get("content")
                if c.get("function_name") == "edit_file" and "mandatory input parameters are not present" in (o if isinstance(o, str) else json.dumps(o)):
                    garbled += 1
        gold = {p for p in patch_files(tasks[iid]["patch"]) if p.endswith(".py") and not is_test(p)}
        pp = f"{a.run}/agent_run/patches/{iid}.patch"
        mine = {p for p in patch_files(open(pp, errors="replace").read()) if p.endswith(".py") and not is_test(p)} if os.path.exists(pp) else set()
        has_log = os.path.exists(f"{a.run}/agent_run/test_outputs/{iid}.log")
        if garbled >= 3: groups["loop"].append(iid)
        elif not res and mine and gold and (mine & gold) and not gold <= mine: groups["partial"].append(iid)
        elif not res and gold and gold <= mine and has_log: groups["narrow"].append(iid)
        elif res and rerun.get(iid): groups["solved"].append(iid)
    rng = random.Random(a.seed); per_repo = {}; rows = []
    for g, ids in groups.items():
        rng.shuffle(ids)
        ids.sort(key=lambda i: (int(meta[i]["test_score"]) > 1, int(meta[i]["difficulty"]) < 1))   # stable: exam-like first
        n = 0
        for i in ids:
            repo = meta[i]["repo"]
            if per_repo.get(repo, 0) >= a.per_repo: continue
            per_repo[repo] = per_repo.get(repo, 0) + 1; rows.append((i, g)); n += 1
            if n == a.per_group: break
        print(f"{g}: {len(ids)} candidates -> {n} picked")
    with open(a.out + ".csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["instance_id", "group"]); w.writerows(rows)
    open(a.out + ".txt", "w").write(f"# dev tasks for instruction screens (dev_select.py, seed {a.seed}): " + ", ".join(f"{g} {sum(1 for _, x in rows if x == g)}" for g in groups)
                                    + "\n" + "\n".join(i for i, _ in rows) + "\n")
    hl = sum(1 for i, _ in rows if int(meta[i]["test_score"]) <= 1 and int(meta[i]["difficulty"]) >= 1)
    print(f"{len(rows)} tasks from {len(per_repo)} repos; exam-like (test_score<=1, difficulty>=1): {hl} -> {a.out}.txt / .csv")


if __name__ == "__main__":
    main()
