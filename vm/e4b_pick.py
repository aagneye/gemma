#!/usr/bin/env python3
"""E4B side track (research/PLAN_E4B.md): the rules of the screens and the runtime rule, applied to finished runs.

  e4b_pick.py screen --base <dir>... --arm <bundle>=<dir>,<dir>... [--arm ...] [--gain 2] [--per 64] [--moved] [--out f]
      Base run i is paired with run i of every arm (same task list), on the tasks both finished.
      gain = (arm solved - base solved) per --per tasks, over all pairs. The arm with the largest gain is picked when
      its gain reaches --gain; with --moved also only when its failed edit_file calls per task are at most 0.8 x the
      base's (the target behaviour of the two E1+R1 lines; from autopsy.jsonl). Last line: "PICK <bundle>" or "PICK base".
  e4b_pick.py runtime --dirs <dir>... [--scale 3] [--max 270]
      Mean task time in Kaggle-seconds (replica seconds / clock scale). 270 s = 9 h for 120 tasks, under the 12-h cap.
      Last line: "RUNTIME OK ..." or "RUNTIME ASK ...".
  e4b_pick.py pace --dirs <dir>...
      Mean replica seconds per task of the runs that exist (the chain's time-box arithmetic). Prints one number.
A run dir is results/replica/<tag> (agent_run/task_results.jsonl, autopsy.jsonl).
"""
import argparse, json, os, sys


def load(d):
    out, p = {}, os.path.join(d, "agent_run", "task_results.jsonl")
    if not os.path.exists(p): return out
    for line in open(p):
        if not line.strip(): continue
        r = json.loads(line)
        out[r["instance_id"]] = dict(res=bool(r.get("resolved")), sec=float(r.get("duration_seconds") or 0),
                                     calls=int(r.get("tool_calls") or 0), err=bool(r.get("error")))
    return out


def failed_edits(d):
    """instance_id -> failed edit_file calls (garbled + other errors), or None when the run has no run log."""
    p = os.path.join(d, "autopsy.jsonl")
    if not os.path.exists(p): return None
    out = {}
    for line in open(p):
        if not line.strip(): continue
        r = json.loads(line)
        out[r.get("instance_id") or r.get("id")] = int(r.get("garbled_edits") or 0) + int(r.get("edit_errors_other") or 0)
    return out


def screen(a):
    base = [load(d) for d in a.base]
    rows, best = [], None
    bs = sum(sum(v["res"] for v in b.values()) for b in base); bn = sum(len(b) for b in base)
    rows.append(f"| base | {bs} of {bn} | | | {sum(v['err'] for b in base for v in b.values())} | |")
    for spec in a.arm:
        name, dirs = spec.split("=", 1); dirs = dirs.split(",")
        assert len(dirs) == len(a.base), f"{name}: {len(dirs)} runs for {len(a.base)} base runs"
        gain = n = solved = errs = 0; fe_arm = fe_base = 0; fe_known = True
        for bd, ad, b in zip(a.base, dirs, base):
            arm = load(ad); common = sorted(set(b) & set(arm))
            gain += sum(arm[i]["res"] - b[i]["res"] for i in common); n += len(common)
            solved += sum(arm[i]["res"] for i in common); errs += sum(arm[i]["err"] for i in common)
            fa, fb = failed_edits(ad), failed_edits(bd)
            if fa is None or fb is None: fe_known = False
            else: fe_arm += sum(fa.get(i, 0) for i in common); fe_base += sum(fb.get(i, 0) for i in common)
        per = gain / n * a.per if n else 0.0
        moved = fe_known and n > 0 and fe_arm <= 0.8 * fe_base
        note = (f"{fe_arm / n:.2f} against {fe_base / n:.2f} per task" + ("" if moved else " (not moved)")) if fe_known and n else "no run log"
        ok = n > 0 and per >= a.gain and (moved or not a.moved)
        rows.append(f"| {name} | {solved} of {n} | {gain:+d} | {per:+.1f} | {errs} | {note} |")
        if ok and (best is None or per > best[1]): best = (name, per)
    text = "\n".join([f"Screen: gain per {a.per} tasks against the base, paired; bar +{a.gain:g}" + (" and failed edits <= 0.8 x" if a.moved else ""),
                      "", "| arm | solved | gain | per %d | task errors | failed edit_file calls |" % a.per, "|---|---|---|---|---|---|"] + rows)
    print(text)
    if a.out: open(a.out, "w").write(text + "\n\nPICK " + (best[0] if best else "base") + "\n")
    print("PICK " + (best[0] if best else "base"))


def runtime(a):
    secs = [v["sec"] for d in a.dirs for v in load(d).values()]
    if not secs: print("RUNTIME ASK: no finished task"); return
    k = sum(secs) / len(secs) / a.scale
    print(f"RUNTIME {'OK' if k <= a.max else 'ASK'}: {k:.0f} Kaggle-seconds per task over {len(secs)} task runs "
          f"(replica seconds / {a.scale:g}); {k * 120 / 3600:.1f} h for 120 tasks (rule: at most {a.max:g} s, 9 h)")


def pace(a):
    secs = [v["sec"] for d in a.dirs for v in load(d).values()]
    print(f"{sum(secs) / len(secs):.0f}" if secs else "0")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("screen"); s.add_argument("--base", nargs="+", required=True); s.add_argument("--arm", action="append", required=True)
    s.add_argument("--gain", type=float, default=2); s.add_argument("--per", type=int, default=64)
    s.add_argument("--moved", action="store_true"); s.add_argument("--out")
    r = sub.add_parser("runtime"); r.add_argument("--dirs", nargs="+", required=True)
    r.add_argument("--scale", type=float, default=3); r.add_argument("--max", type=float, default=270)
    p = sub.add_parser("pace"); p.add_argument("--dirs", nargs="+", required=True)
    a = ap.parse_args()
    {"screen": screen, "runtime": runtime, "pace": pace}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
