#!/usr/bin/env python3
"""Clock ledger for replica runs: where a run's moves and minutes go, and which losses are clock or move losses.

  python3 clock_ledger.py <run_dir>... [--scale 9] [--thinking 4096] [--out <file.md>] [--tasks ...] [--build-log ...]

<run_dir> is results/replica/<tag>/. One run dir gives that run's ledger. Several run dirs are read as passes of one
bundle over the same tasks: every table then counts the tasks that all passes have finished, and the pass table is added
(tasks solved in every pass, in some, in none). Prints markdown; --out also writes it to a file. CPU only, Python 3.10
standard library. The per-task records come from autopsy.py (same folder); the traces give the tokens and times of every
model step. It writes nothing into the run dirs except the --out file you name. Works on a run in progress.

Words used in the report
  game        one task run.
  move        a tool call the harness counts (harness_tool_calls): get_status, submit_patch and garbled calls are free.
  minute      Kaggle-equivalent: run seconds / --scale / 60 (the replica runs on a stretched clock, REPLICA_TIME_SCALE).
  loss type   first match: solved; harness error; out of time (session timeout or turn cap); blank answer (empty patch,
              a patch with only scratch files, or no source .py file in it); wrong fix on the last moves (the call cap
              was reached, wrong patch); wrong fix inside the budget (everything else).
  clock-or-move loss   out of time, blank answer, or wrong fix on the last moves.
  source edit          autopsy.py's rule: an edit_file that succeeded, or a write_file over a file read or edited before.
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopsy as A  # noqa: E402

LOSS_TYPES = ["solved", "wrong fix inside the budget", "blank answer", "out of time", "wrong fix on the last moves", "harness error"]
CLOCK_LOSSES = ("blank answer", "out of time", "wrong fix on the last moves")
MOVE_GROUP = {"read_file": "read", "shell_read": "read", "search": "search", "edit_file": "edit", "write_file": "edit",
              "shell_write": "edit", "test": "check", "repro": "check", "submit_patch": "submit"}
MOVE_NAMES = {"read_file": "read a file", "search": "search", "repro": "run Python", "test": "run tests", "edit_file": "edit a file",
              "write_file": "write a file", "submit_patch": "submit", "get_status": "ask the status", "shell_read": "read with the shell",
              "shell_write": "edit with the shell", "git": "git", "other_cmd": "other command", None: "text only, no tool call"}
MINUTE_BUCKETS = [("under 3", 0, 3), ("3 to 5", 3, 5), ("5 to 7", 5, 7), ("7 or more", 7, 1e9)]              # lo <= x < hi
EDIT_BUCKETS = [("1-6", 1, 6), ("7-12", 7, 12), ("13-18", 13, 18), ("19 or later", 19, 10 ** 6)]               # lo <= x <= hi
TOKEN_BUCKETS = [("under 4,000", 0, 4000), ("4,000 to 8,000", 4000, 8000), ("8,000 to 12,000", 8000, 12000),
                 ("12,000 or more", 12000, 10 ** 9)]                                                           # lo <= x < hi


def loss_type(r):
    if r["resolved"]:
        return "solved"
    if r["outcome"] == "harness error":
        return "harness error"
    if r["outcome"] in ("session timeout", "turn cap"):
        return "out of time"
    if not r["patch_chars"] or r["scratch_only_patch"] or r["file_match"] == "no edit":
        return "blank answer"
    if r["hit_call_cap"] or r["outcome"] == "call cap":
        return "wrong fix on the last moves"
    return "wrong fix inside the budget"


def _obj(x):
    """Trace fields are objects; tolerate a JSON string."""
    if isinstance(x, str):
        try:
            return json.loads(x)
        except ValueError:
            return {}
    return x or {}


def read_steps(path):
    """-> one dict per model step that wrote tokens: written and prompt tokens, model seconds (from the end of the step
    before to this answer), the kind of its first tool call, the seconds its tool calls ran, the size of the first answer."""
    d = json.load(open(path, errors="replace"))
    out, prev_end = [], None
    for s in d.get("steps", []):
        el = _obj(s.get("extra")).get("elapsed_s")
        el = float(el) if el is not None else None
        if s.get("source") != "agent":
            if el is not None:
                prev_end = el
            continue
        tcs, obs = _obj(s.get("tool_calls")) or [], _obj(s.get("observation")) or []
        tcs = [tcs] if isinstance(tcs, dict) else tcs
        obs = [obs] if isinstance(obs, dict) else obs
        end, kind, tool_s, answer_chars = el, None, 0.0, 0
        for k, tc in enumerate(tcs):
            if not isinstance(tc, dict):
                continue
            ob = obs[k] if k < len(obs) and isinstance(obs[k], dict) else {}
            start, stop = _obj(tc.get("extra")).get("elapsed_s"), _obj(ob.get("extra")).get("elapsed_s")
            if start is not None and stop is not None:
                tool_s += max(0.0, float(stop) - float(start))
                end = max(end or 0.0, float(stop))
            if k == 0:
                tool = tc.get("function_name") or "?"
                args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
                kind = A.classify_cmd(str(args.get("command", ""))) if tool == "run_command" else tool
                content = ob.get("content")
                answer_chars = 0 if content is None else len(content if isinstance(content, str) else json.dumps(content))
        written = int(_obj(s.get("metrics")).get("completion_tokens") or 0)
        if written:                                   # the closing "final" event repeats the last step without metrics
            out.append({"written": written, "prompt": int(_obj(s.get("metrics")).get("prompt_tokens") or 0),
                        "model_s": el - prev_end if (el is not None and prev_end is not None and el >= prev_end) else None,
                        "kind": kind, "calls": len(tcs), "tool_s": tool_s, "answer_chars": answer_chars})
        if end is not None:
            prev_end = end
    return out


def load_pass(run_dir, tasks, labels):
    """-> {instance_id: autopsy record + steps, the move of the first budget warning, the move after it, the loss type}."""
    recs = {}
    for r in A.autopsy_run(run_dir, tasks, labels):
        iid = r["instance_id"]
        tp = os.path.join(run_dir, "agent_run", "traces", "trace_" + iid.replace("/", "__") + ".json")
        r["steps"], r["warn_move"], r["next_after_warning"] = [], None, None
        if os.path.exists(tp):
            try:
                r["steps"] = read_steps(tp)
                calls = A.parse_trace(tp)[0]
            except (ValueError, OSError):
                calls = []
            w = next((c for c in calls if c["warned"]), None)
            if w is not None:
                nxt = calls[w["idx"] + 1] if w["idx"] + 1 < len(calls) else None
                r["warn_move"] = w["n"]
                r["next_after_warning"] = MOVE_GROUP.get(nxt["kind"], "other") if nxt else "nothing"
        r["loss"] = loss_type(r)
        recs[iid] = r
    return recs


def won(rs):
    return sum(1 for r in rs if r["resolved"])


def share_row(label, rs):
    return [label, len(rs), won(rs), A.pct(won(rs), len(rs))]


def quant(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else 0


def move_buckets(m):
    """Inclusive ranges of moves used; the last one is the most moves any game used (the call cap, when a game reached it)."""
    out, lo = [], 0
    for e in (10, 15, 20):
        if e < m - 1:
            out.append((f"{lo}-{e}" if lo else f"up to {e}", lo, e))
            lo = e + 1
    if lo <= m - 1:
        out.append((f"{lo}-{m - 1}" if lo else f"up to {m - 1}", lo, m - 1))
    out.append((f"{m} (the most any game used)", m, 10 ** 6))
    return out


def fit(steps, scale):
    """Least squares: Kaggle-equivalent seconds of a model step = a + b * prompt tokens / 1000 + c * written tokens / 100.
    -> ((a, b, c), number of steps) or None."""
    pts = [(1.0, s["prompt"] / 1000.0, s["written"] / 100.0, s["model_s"] / scale) for s in steps if s["model_s"] is not None]
    if len(pts) < 10:
        return None
    a = [[sum(p[i] * p[j] for p in pts) for j in range(3)] for i in range(3)]
    b = [sum(p[i] * p[3] for p in pts) for i in range(3)]
    for i in range(3):
        piv = a[i][i]
        if abs(piv) < 1e-12:
            return None
        a[i] = [v / piv for v in a[i]]
        b[i] /= piv
        for r in range(3):
            if r != i:
                f = a[r][i]
                a[r] = [v - f * w for v, w in zip(a[r], a[i])]
                b[r] -= f * b[i]
    return tuple(b), len(pts)


def ledger(dirs, passes, ids, scale, thinking):
    names = [os.path.basename(os.path.normpath(d)) for d in dirs]
    n_pass = len(passes)
    games = [p[i] for p in passes for i in ids]
    for g in games:
        g["minutes"] = g["duration_s"] / scale / 60.0
        g["moves"] = g["harness_tool_calls"] or 0
    solved_in = {i: sum(1 for p in passes if p[i]["resolved"]) for i in ids}
    sometimes = {i for i in ids if 0 < solved_in[i] < n_pass}
    lost = [g for g in games if not g["resolved"]]
    clock = [g for g in lost if g["loss"] in CLOCK_LOSSES]
    per_pass = (lambda x: f"{x / n_pass:.2f}") if n_pass > 1 else str

    L = ["# Clock ledger", "",
         "- Runs: " + ", ".join(f"`{d}`" for d in dirs) + ".",
         f"- Tasks counted: **{len(ids)}**" + (" (finished in every pass)" if n_pass > 1 else "") + f". Games: {len(games)}.",
         "- Solved: " + ", ".join(f"{n} {won([p[i] for i in ids])}" for n, p in zip(names, passes))
         + (f" (mean {won(games) / n_pass:.2f} per pass)." if n_pass > 1 else "."),
         f"- A minute is Kaggle-equivalent: run seconds / {scale:g} / 60. A move is a tool call the harness counts.",
         "- Loss types, first match: out of time (session timeout or turn cap); blank answer (empty patch, only scratch files, or "
         "no source file in the patch); wrong fix on the last moves (call cap reached, wrong patch); wrong fix inside the budget (the rest).",
         "", "## 1. How the games end"]
    head = ["Outcome"] + (names + ["Mean per pass", "Of these, on tasks solved in some passes only (per pass)"] if n_pass > 1
                          else ["Games", "Share"])
    rows = []
    for t in LOSS_TYPES:
        per = [sum(1 for i in ids if p[i]["loss"] == t) for p in passes]
        if not sum(per):
            continue
        if n_pass > 1:
            some = sum(1 for p in passes for i in sometimes if p[i]["loss"] == t)
            rows.append([t.capitalize()] + per + [f"{sum(per) / n_pass:.2f}", f"{some / n_pass:.2f}"])
        else:
            rows.append([t.capitalize(), per[0], A.pct(per[0], len(ids))])
    L += A.table(head, rows)
    L += ["", f"- Clock-or-move losses: **{per_pass(len(clock))} of {per_pass(len(lost))} losses" + (" per pass" if n_pass > 1 else "")
          + f"** ({A.pct(len(clock), len(lost))})."]
    if n_pass > 1:
        cs = [g for g in clock if g["instance_id"] in sometimes]
        inside = [g for g in games if g["instance_id"] in sometimes and g["loss"] in ("solved", "wrong fix inside the budget")]
        L += [f"- On tasks solved in some passes only: {len(cs) / n_pass:.2f} clock-or-move losses per pass. "
              "That is the most that better clock play could win back."]
        if inside:
            L += [f"- Games on those tasks that stay inside the budget are solved {won(inside)} of {len(inside)} times "
                  f"({A.pct(won(inside), len(inside))}). At that rate the clock-or-move losses are worth about "
                  f"+{len(cs) / n_pass * won(inside) / len(inside):.1f} solved per pass."]

    L += ["", "## 2. Wins are quick", "", "**By minutes used**"]
    L += A.table(["Minutes", "Games", "Solved", "Share solved"],
                 [share_row(lab, [g for g in games if lo <= g["minutes"] < hi]) for lab, lo, hi in MINUTE_BUCKETS])
    L += ["", "**By moves used**"]
    L += A.table(["Moves", "Games", "Solved", "Share solved"],
                 [share_row(lab, [g for g in games if lo <= g["moves"] <= hi]) for lab, lo, hi in move_buckets(max(g["moves"] for g in games))])
    L += ["", "**By the move number of the first source edit**"]
    rows = [share_row(lab, [g for g in games if g["first_source_edit_call"] is not None and lo <= g["first_source_edit_call"] <= hi])
            for lab, lo, hi in EDIT_BUCKETS]
    rows.append(share_row("no source edit by a tool call", [g for g in games if g["first_source_edit_call"] is None]))
    L += A.table(["First source edit at move", "Games", "Solved", "Share solved"], rows)
    L += ["", "**A typical game (medians)**"]
    rows = [[lab, len(rs), f"{A.med(g['moves'] for g in rs):g}", f"{A.med(g['minutes'] * 60 for g in rs):.0f}",
             f"{A.med(g['output_tokens'] for g in rs):.0f}", f"{A.med(g['first_source_edit_call'] for g in rs):g}"]
            for lab, rs in (("Solved", [g for g in games if g["resolved"]]), ("Not solved", lost))]
    L += A.table(["Games", "Count", "Moves", "Seconds", "Written tokens", "First source edit at move"], rows)

    steps = [(g, s) for g in games for s in g["steps"]]
    L += ["", "## 3. The clock"]
    dur = sum(g["duration_s"] for g in games)
    if dur and steps:
        L += [f"- Share of the game time: model steps {A.pct(sum(s['model_s'] for g, s in steps if s['model_s'] is not None), dur)}, "
              f"tools {A.pct(sum(s['tool_s'] for g, s in steps), dur)}."]
    f = fit([s for g, s in steps], scale)
    if f:
        (a0, b, c), n = f
        sign = lambda v: "+" if v >= 0 else "-"  # noqa: E731
        L += [f"- Fit on {n} model steps: seconds per step = {a0:.1f} {sign(b)} {abs(b):.2f} per 1,000 prompt tokens "
              f"{sign(c)} {abs(c):.2f} per 100 written tokens. One written token costs about {c * 10:.0f} ms."]
    rows = []
    for lab, flag in (("Solved games", True), ("Unsolved games", False)):
        xs = [s["written"] for g, s in steps if g["resolved"] == flag]
        tot = sum(xs)
        rows.append([lab, len(xs), quant(xs, .5), quant(xs, .9), quant(xs, .99), max(xs or [0]),
                     f"{sum(1 for x in xs if x >= 1000)} ({A.pct(sum(x for x in xs if x >= 1000), tot)})",
                     f"{sum(1 for x in xs if x >= 2000)} ({A.pct(sum(x for x in xs if x >= 2000), tot)})"])
    L += ["", "**Written tokens per model step**"]
    L += A.table(["Games", "Steps", "Median", "90th percentile", "99th percentile", "Largest",
                  "Steps of 1,000+ (their share of all tokens)", "Steps of 2,000+ (their share of all tokens)"], rows)
    if thinking:
        capped = [g for g in games if any(s["written"] >= thinking for s in g["steps"])]
        L += ["", f"- Steps that write {thinking:,} tokens or more (the thinking budget is used up): "
              f"{sum(1 for g, s in steps if s['written'] >= thinking)}, in {len(capped)} games "
              f"(solved: {won(capped)} of {len(capped)}, {A.pct(won(capped), len(capped))})."]
    L += ["", "**By written tokens per game**"]
    L += A.table(["Written tokens", "Games", "Solved", "Share solved"],
                 [share_row(lab, [g for g in games if lo <= (g["output_tokens"] or 0) < hi]) for lab, lo, hi in TOKEN_BUCKETS])

    L += ["", "## 4. What a move costs (model steps with one tool call or none; medians)"]
    by = collections.defaultdict(list)
    for g, s in steps:
        if s["calls"] <= 1 and s["model_s"] is not None:
            by[s["kind"]].append(s)
    L += A.table(["Move", "Steps", "Written tokens", "Seconds", "Size of the tool's answer (characters)"],
                 [[MOVE_NAMES.get(k, k), len(v), f"{A.med(s['written'] for s in v):.0f}", f"{A.med(s['model_s'] for s in v) / scale:.1f}",
                   f"{A.med(s['answer_chars'] for s in v):.0f}"] for k, v in sorted(by.items(), key=lambda kv: -len(kv[1]))])

    L += ["", "## 5. The budget warning"]
    warned = [g for g in games if g["warn_move"] is not None]
    if not warned:
        L += ["No game saw a budget warning."]
    else:
        edited = lambda g: g["first_source_edit_call"] is not None and g["first_source_edit_call"] <= g["warn_move"]  # noqa: E731
        has, hasnt = [g for g in warned if edited(g)], [g for g in warned if not edited(g)]
        L += [f"- Games that saw it: {len(warned)} of {len(games)}. It first appears at move {A.med(g['warn_move'] for g in warned):g} (median).", ""]
        L += A.table(["At the first warning", "Games", "Solved", "Share solved"],
                     [share_row("A source edit is already made", has), share_row("No source edit yet", hasnt)])
        if hasnt:
            nxt = collections.defaultdict(list)
            for g in hasnt:
                nxt[g["next_after_warning"]].append(g)
            L += ["", "**No source edit yet: the next move**"]
            L += A.table(["Next move", "Games", "Solved", "Share solved"],
                         [share_row(k, v) for k, v in sorted(nxt.items(), key=lambda kv: -len(kv[1]))])
            L += ["", f"- Of these {len(hasnt)} games, {sum(1 for g in hasnt if g['loss'] == 'blank answer')} end as a blank answer."]

    sec = 6
    if n_pass > 1:
        dist = collections.Counter(solved_in.values())
        pure = [i for i in sorted(sometimes) if all(p[i]["resolved"] or p[i]["loss"] in CLOCK_LOSSES for p in passes)]
        L += ["", "## 6. Across the passes",
              f"- Solved in every pass: {dist[n_pass]} tasks. In no pass: {dist[0]}. In some: {len(sometimes)} ("
              + ", ".join(f"{dist[k]} in {k} of {n_pass}" for k in range(1, n_pass)) + ").",
              f"- Tasks solved in some passes whose every loss is a clock-or-move loss: {len(pure)}."]
        L += [f"  - `{i}` (solved in {solved_in[i]} of {n_pass}): " + " / ".join(p[i]["loss"] for p in passes) + "." for i in pure]
        sec = 7
    L += ["", f"## {sec}. Clock-or-move losses, one line each"]
    if not clock:
        L += ["None."]
    for n, p in zip(names, passes):
        for i in ids:
            g = p[i]
            if g["loss"] in CLOCK_LOSSES:
                tail = f", solved in {solved_in[i]} of {n_pass} passes" if n_pass > 1 else ""
                L += [f"- `{i}` ({n}{tail}): {g['loss']}; {g['moves']} moves, {g['minutes']:.1f} minutes, "
                      f"{g['output_tokens'] or 0} written tokens. {g['why']}"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", nargs="+")
    ap.add_argument("--scale", type=float, default=9.0, help="clock stretch of the run (REPLICA_TIME_SCALE); 1 for Kaggle traces")
    ap.add_argument("--thinking", type=int, default=None, help="the bundle's thinking budget: also counts the steps that use it up")
    ap.add_argument("--out", default=None, help="also write the markdown to this file")
    ap.add_argument("--tasks", default=A.DEFAULT_TASKS)
    ap.add_argument("--build-log", default=A.DEFAULT_BUILD_LOG)
    a = ap.parse_args()
    if a.scale <= 0:
        sys.exit("--scale must be above 0")
    tasks, labels = A.load_tasks(a.tasks), A.load_labels(a.build_log)
    dirs = [A.resolve(d) for d in a.run_dir]
    passes = [load_pass(d, tasks, labels) for d in dirs]
    ids = [i for i in passes[0] if all(i in p for p in passes[1:])]          # the first run's order
    if not ids:
        sys.exit("no task is finished in every run yet")
    text = ledger(dirs, passes, ids, a.scale, a.thinking)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
