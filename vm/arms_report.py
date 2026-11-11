#!/usr/bin/env python3
"""Side-by-side table of several runs (arms) on the tasks that every arm has finished.

  python3 arms_report.py <base_run_dir> <cand_run_dir>... [--groups <csv: instance_id,group>] [--out <file>]
                         [--tasks ...] [--build-log ...]

The first run dir is the base. Rows: solved, wins and losses against the base, the behaviour measures of
vm/autopsy.py (as shares of the common tasks), garbled edit calls and looped tasks, the range-less read share, and
reads / calls / output tokens / duration per task with the ratio to the base. With --groups the same table is
printed per group (for example results/lists/dev48.csv). Prints markdown; --out also writes it to a file.
It reads the traces itself through autopsy.py (same folder) and writes nothing into the run dirs.
"""
import argparse, csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopsy as A  # noqa: E402


def share(recs, pred):
    n = len(recs)
    k = sum(1 for r in recs if pred(r))
    return f"{k} ({A.pct(k, n)})"


def per_task(recs, key, base_recs, digits=1):
    v, b = A.mean(r[key] for r in recs), A.mean(r[key] for r in base_recs)
    return f"{v:.{digits}f} (x{v / b:.2f})" if b else f"{v:.{digits}f}"


def arm_table(names, arms, ids):
    """arms: list of {instance_id: record}; ids: the tasks to count (finished by every arm)."""
    cols = [[a[i] for i in ids] for a in arms]
    base = cols[0]
    bsolved = {r["instance_id"] for r in base if r["resolved"]}
    rows = []

    def row(label, fn):
        rows.append([label] + [fn(c) for c in cols])
    row("Tasks", len)
    row("Solved", lambda c: f"{sum(r['resolved'] for r in c)} ({A.pct(sum(r['resolved'] for r in c), len(c))})")
    row("Wins against the base (solved here, not by the base)", lambda c: "-" if c is base else sum(1 for r in c if r["resolved"] and r["instance_id"] not in bsolved))
    row("Losses against the base (solved by the base, not here)", lambda c: "-" if c is base else sum(1 for r in c if not r["resolved"] and r["instance_id"] in bsolved))
    row("Tasks with a successful edit", lambda c: share(c, lambda r: r["edits_ok"] > 0))
    row("Tasks: a test or repro ran after the last edit", lambda c: share(c, lambda r: r["check_after_last_edit"]))
    for field, label in A.BEHAVIOURS:
        row("Tasks: " + label, lambda c, f=field: share(c, lambda r: r[f]))
    row("Tasks: py_compile used anywhere", lambda c: share(c, lambda r: r["py_compile_used"]))
    row("Tasks: syntax or indentation error seen", lambda c: share(c, lambda r: r["syntax_error_seen"]))
    row("edit_file calls", lambda c: sum(r["calls_by_kind"].get("edit_file", 0) for r in c))
    row("Garbled edit_file calls (share of edit_file calls)", lambda c: (lambda g, e: f"{g} ({A.pct(g, e)})")(sum(r["garbled_edits"] for r in c), sum(r["calls_by_kind"].get("edit_file", 0) for r in c)))
    row("Tasks with a garbled-edit loop (3 or more)", lambda c: share(c, lambda r: r["garbled_loop"]))
    row("read_file without a line range (share of read_file calls)", lambda c: (lambda g, e: f"{g} ({A.pct(g, e)})")(sum(r["rangeless_reads"] for r in c), sum(r["reads"] for r in c)))
    row("Tasks with identical consecutive calls", lambda c: share(c, lambda r: r["identical_consecutive"] > 0))
    row("Tasks with a session timeout", lambda c: share(c, lambda r: r["outcome"] == "session timeout"))
    row("read_file calls per task (ratio to base)", lambda c: per_task(c, "reads", base))
    row("Calls per task (ratio to base)", lambda c: per_task(c, "calls", base))
    row("Output tokens per task (ratio to base)", lambda c: per_task(c, "output_tokens", base, 0))
    row("Prompt tokens per task (ratio to base)", lambda c: per_task(c, "prompt_tokens", base, 0))
    row("Duration per task, seconds (ratio to base)", lambda c: per_task(c, "duration_s", base, 0))
    return A.table(["Measure"] + [n + (" (base)" if k == 0 else "") for k, n in enumerate(names)], rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_run_dir")
    ap.add_argument("cand_run_dir", nargs="+")
    ap.add_argument("--groups", default=None, help="csv with the columns instance_id,group")
    ap.add_argument("--out", default=None, help="also write the markdown to this file")
    ap.add_argument("--tasks", default=A.DEFAULT_TASKS)
    ap.add_argument("--build-log", default=A.DEFAULT_BUILD_LOG)
    a = ap.parse_args()
    tasks, labels = A.load_tasks(a.tasks), A.load_labels(a.build_log)
    dirs = [a.base_run_dir] + a.cand_run_dir
    names = [os.path.basename(os.path.normpath(d)) for d in dirs]
    arms = [{r["instance_id"]: r for r in A.autopsy_run(d, tasks, labels)} for d in dirs]
    ids = [i for i in arms[0] if all(i in arm for arm in arms[1:])]          # the base's run order
    if not ids:
        sys.exit("no task is finished in every arm yet")
    L = ["# Arms report", "",
         f"- Base: `{dirs[0]}`. Candidates: " + ", ".join(f"`{d}`" for d in dirs[1:]) + ".",
         f"- Tasks finished by every arm: **{len(ids)}** (finished per arm: " + ", ".join(f"{n} {len(arm)}" for n, arm in zip(names, arms)) + ").",
         "- Every number counts these common tasks only. Shares in brackets are shares of the common tasks, unless the row says otherwise.",
         "- A ratio like x1.05 means 5% more than the base.", "", "## All common tasks"] + arm_table(names, arms, ids)
    for k, n in enumerate(names[1:], 1):
        wins = [i for i in ids if arms[k][i]["resolved"] and not arms[0][i]["resolved"]]
        losses = [i for i in ids if not arms[k][i]["resolved"] and arms[0][i]["resolved"]]
        L += ["", f"### {n} against {names[0]}", f"- Wins ({len(wins)}): " + (", ".join(wins) or "none") + "."]
        L += [f"- Losses ({len(losses)}):" if losses else "- Losses (0): none."]
        L += [f"  - `{i}`: {arms[k][i]['why']}" for i in losses]
    if a.groups:
        grp = {}
        for r in csv.DictReader(open(A.resolve(a.groups), errors="replace")):
            grp.setdefault(r["group"], []).append(r["instance_id"])
        for g, members in grp.items():
            gids = [i for i in ids if i in set(members)]
            L += ["", f"## Group: {g} ({len(gids)} of {len(members)} tasks finished by every arm)"]
            L += arm_table(names, arms, gids) if gids else ["No common finished task in this group yet."]
        rest = [i for i in ids if not any(i in m for m in grp.values())]
        if rest:
            L += ["", f"## Tasks in no group ({len(rest)})"] + arm_table(names, arms, rest)
    text = "\n".join(L) + "\n"
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
