#!/usr/bin/env python3
"""Curated SFT subset v4: short, clean trajectories only.
Keeps a trajectory (all of its windows) iff: <=30 tool steps, <=2 tool errors across the trajectory, at least one
edit_file, and at least one verification command (pytest or python). Rationale: SWE-Gym/R2E-Gym show the first few
hundred good trajectories carry most of the gain, and our first adapter learned the teacher's exploration volume.
  python build_v4_short.py --src datasets/sft_v3 --out datasets/sft_v4_short/all.jsonl [--max-steps 30] [--max-errors 2]
"""
import argparse, json, collections, os

ap = argparse.ArgumentParser(); ap.add_argument("--src", default="datasets/sft_v3"); ap.add_argument("--out", default="datasets/sft_v4_short/all.jsonl")
ap.add_argument("--max-steps", type=int, default=30); ap.add_argument("--max-errors", type=int, default=2)
a = ap.parse_args()
keep = {}; stats = collections.Counter()
for src in ("swe_hero", "nebius"):
    for l in open(f"{a.src}/{src}.jsonl", encoding="utf-8"):
        r = json.loads(l); key = (src, r["instance_id"], r["n_steps"])
        if r["n_steps"] > a.max_steps: stats["too_long"] += 1; continue
        msgs = r["messages"]
        errs = sum(1 for m in msgs if m["role"] == "tool" and '"status": "error"' in m["content"])
        calls = [c["function"]["name"] for m in msgs if m["role"] == "assistant" for c in m.get("tool_calls", [])]
        cmds = " ".join(json.dumps(c["function"]["arguments"]) for m in msgs if m["role"] == "assistant"
                        for c in m.get("tool_calls", []) if c["function"]["name"] == "run_command")
        k = keep.setdefault(key, {"errs": 0, "edit": False, "verify": False, "rows": []})
        k["errs"] += errs; k["edit"] |= "edit_file" in calls; k["verify"] |= ("pytest" in cmds or "python" in cmds); k["rows"].append(l)
os.makedirs(os.path.dirname(a.out), exist_ok=True)
n_traj = n_win = 0; repos = set()
with open(a.out, "w", encoding="utf-8") as out:
    for key, k in keep.items():
        if k["errs"] > a.max_errors: stats["too_many_errors"] += 1; continue
        if not k["edit"]: stats["no_edit"] += 1; continue
        if not k["verify"]: stats["no_verify"] += 1; continue
        for l in k["rows"]: out.write(l); n_win += 1
        n_traj += 1; repos.add(json.loads(k["rows"][0])["repo"])
print(f"kept trajectories {n_traj}, windows {n_win}, repos {len(repos)} | rejected {dict(stats)} -> {a.out}")
