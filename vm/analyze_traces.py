#!/usr/bin/env python3
"""Failure-mode analysis of harness traces (adk-eval-core trace_*.json) joined with the eval results.csv.

  python analyze_traces.py <eval_dir>          # eval_dir contains results.csv and agent_run/traces/
Prints one row per task plus aggregate failure-mode counts, and writes <eval_dir>/trace_analysis.csv.
"""
import csv, json, sys, collections, statistics
from pathlib import Path

EDIT_TOOLS = {"edit_file", "write_file"}


def analyse(trace_path):
    d = json.load(open(trace_path))
    calls, n_call = [], 0
    for s in d.get("steps", []):
        for tc in s.get("tool_calls") or []:
            n_call += 1
            obs = (s.get("observation") or {}).get("content") or ""
            try: o = json.loads(obs) if obs.startswith("{") else {}
            except Exception: o = {}
            calls.append({"i": n_call, "tool": tc.get("function_name"), "args": tc.get("arguments") or {},
                          "elapsed": (tc.get("extra") or {}).get("elapsed_s") or 0.0,
                          "status": o.get("status"), "error_type": o.get("error_type"), "obs_len": len(obs),
                          "thought_len": len(s.get("message") or "")})
    first_edit = next((c["i"] for c in calls if c["tool"] in EDIT_TOOLS and c["status"] != "error"), None)
    edit_err = sum(1 for c in calls if c["tool"] in EDIT_TOOLS and c["status"] == "error")
    cmd_err = sum(1 for c in calls if c["tool"] == "run_command" and c["status"] == "error")
    sig = [json.dumps([c["tool"], c["args"]], sort_keys=True) for c in calls]
    repeats = sum(1 for k, v in collections.Counter(sig).items() if v > 1 for _ in range(v - 1))
    cmds = [str(c["args"].get("command", "")) for c in calls if c["tool"] == "run_command"]
    tests = sum(1 for x in cmds if "pytest" in x or "unittest" in x)
    reads = sum(1 for c in calls if c["tool"] == "read_file") + sum(1 for x in cmds if x.lstrip().startswith(("cat ", "sed -n", "head ", "tail ")))
    searches = sum(1 for x in cmds if "grep" in x or "find " in x or "ls-files" in x)
    submitted = any(c["tool"] == "submit_patch" for c in calls)
    graph = sum(1 for c in calls if c["tool"] in ("get_code_neighbors", "search_similar_code", "get_code_subgraph"))
    lat = [c["elapsed"] for c in calls if c["elapsed"]]
    fm = d.get("final_metrics") or {}
    budget_warn = any("budget_warning" in json.dumps(s.get("observation") or {}) for s in d.get("steps", []))
    # edit-error kinds (what the lost-edit bucket is made of) and how the run ended
    kinds = []
    for s in d.get("steps", []):
        for tc in s.get("tool_calls") or []:
            if tc.get("function_name") in EDIT_TOOLS:
                obs = (s.get("observation") or {}).get("content") or ""
                if '"status": "error"' not in obs[:40]: continue
                low = obs.lower()
                k = ("after_budget" if "budgetexceeded" in low else "not_found" if "not found" in low
                     else "ambiguous" if ("occurrence" in low or "occurs" in low) else "path_traversal" if "path traversal" in low else "other")
                if k not in kinds: kinds.append(k)
    submits = [c for c in calls if c["tool"] == "submit_patch"]
    nonempty_submit = False
    for s in d.get("steps", []):
        if any(tc.get("function_name") == "submit_patch" for tc in s.get("tool_calls") or []):
            obs = (s.get("observation") or {}).get("content") or ""
            if '"status": "ok"' in obs and '"patch_size": 0' not in obs: nonempty_submit = True
    # the harness records continuation nudges as custom events (source "system", extra.event_type "continuation_nudge")
    nudges = sum(1 for s in d.get("steps", []) if (s.get("extra") or {}).get("event_type") == "continuation_nudge")
    exhausted = any(c["error_type"] == "BudgetExceeded" for c in calls)
    stop = ("submitted" if nonempty_submit else "submitted_empty" if submits else "calls_exhausted" if exhausted else "text_stop")
    return {"n_calls": len(calls), "first_edit": first_edit, "edit_err": edit_err, "cmd_err": cmd_err, "repeats": repeats,
            "tests": tests, "reads": reads, "searches": searches, "submitted": submitted, "graph": graph,
            "lat_med": round(statistics.median(lat), 1) if lat else None, "lat_max": round(max(lat), 1) if lat else None,
            "lat_sum": round(sum(lat), 1), "prompt_tok": fm.get("total_prompt_tokens"), "compl_tok": fm.get("total_completion_tokens"),
            "budget_warn": budget_warn, "edit_err_kind": "+".join(kinds), "stop_reason": stop, "nudges": nudges}


def mode(r):
    """Failure bucket. Timeouts come from the harness error column ("Agent exceeded session timeout") because wall-clock
    duration includes verification and, on the VM replica, is scaled by REPLICA_TIME_SCALE; the 470 s rule is only a
    fallback for result files without an error column."""
    res = r["resolved"] == "True"; patch = int(r["patch_chars"] or 0)
    if "error" in r:
        timeout = "exceeded session timeout" in (r.get("error") or "").lower()
    else:
        timeout = float(r["duration_s"] or 0) >= 470
    if res: return "RESOLVED"
    if patch == 0: return "NO_PATCH_TIMEOUT" if timeout else "NO_PATCH_CALLS"
    return "WRONG_PATCH_TIMEOUT" if timeout else "WRONG_PATCH"


def main():
    ev = Path(sys.argv[1]); rows = list(csv.DictReader(open(ev / "results.csv")))
    out = []
    for r in rows:
        t = ev / "agent_run" / "traces" / f"trace_{r['instance_id']}.json"
        a = analyse(t) if t.exists() else {}
        out.append({**r, **a, "mode": mode(r)})
    cols = ["instance_id", "mode", "resolved", "patch_chars", "duration_s", "tool_calls", "first_edit", "edit_err", "cmd_err", "repeats",
            "tests", "reads", "searches", "submitted", "graph", "lat_med", "lat_max", "lat_sum", "prompt_tok", "compl_tok", "budget_warn",
            "edit_err_kind", "stop_reason", "nudges"]
    with open(ev / "trace_analysis.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(out)
    print(" | ".join(cols[1:]))
    for o in out: print(" | ".join(str(o.get(c, "")) for c in cols))
    print("\nMODES", dict(collections.Counter(o["mode"] for o in out)))
    def grp(key, f):
        g = collections.defaultdict(list)
        for o in out: g[f(o)].append(o["resolved"] == "True")
        return {k: f"{sum(v)}/{len(v)}" for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}
    print("resolve by first-edit call:", grp("fe", lambda o: "none" if o.get("first_edit") is None else ("<=6" if o["first_edit"] <= 6 else "7-10" if o["first_edit"] <= 10 else "11-14" if o["first_edit"] <= 14 else ">14")))
    print("resolve by tests run:", grp("t", lambda o: min(o.get("tests") or 0, 3)))
    print("resolve by submit:", grp("s", lambda o: o.get("submitted")))
    print("resolve by repo:", grp("r", lambda o: o["instance_id"].split("_")[0]))
    print("resolve by edit errors:", grp("e", lambda o: min(o.get("edit_err") or 0, 3)))
    print("resolve by repeats:", grp("p", lambda o: min(o.get("repeats") or 0, 3)))
    print("edit-error kinds:", dict(collections.Counter(k for o in out for k in (o.get("edit_err_kind") or "").split("+") if k)))
    print("stop reasons:", dict(collections.Counter(o.get("stop_reason") for o in out)), "| runs with nudges:", sum(1 for o in out if (o.get("nudges") or 0) > 0))
    lm = [o["lat_med"] for o in out if o.get("lat_med")]
    print("median per-call latency s: median", statistics.median(lm), "max-of-medians", max(lm))
    print("timeouts with <=15 calls:", sum(1 for o in out if float(o["duration_s"] or 0) >= 470 and (o.get("n_calls") or 0) <= 15))


if __name__ == "__main__":
    main()
