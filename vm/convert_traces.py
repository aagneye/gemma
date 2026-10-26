#!/usr/bin/env python3
"""Parse harness traces (adk-eval-core ATIF-v1.7 `trace_<instance>.json`) into clean, resolved episodes for SFT.

Used by prepare_data.py (`--source harness-trace`); can also be run alone to print the filter statistics:
  python convert_traces.py "scratch/kev_*_out/eval" [--max-calls 24] [--per-task 3] [--teacher 31b]

An episode is kept iff (all measured against the eval's results.csv and the trace itself):
  * results.csv says resolved == True and the trace's model matches --teacher (default: the 31B);
  * it is cut after the first *successful* submit_patch (patch_size > 0) that follows the last edit, so the
    kept prefix produces exactly the graded patch; the real closing text is kept when nothing substantive
    followed that submit, otherwise a short closing sentence is synthesised;
  * no edit_file / write_file targets a protected file (tests/, test_*.py, *_test.py, conftest.py, pytest.ini,
    pyproject.toml, setup.cfg, tox.ini) - the grader discards those changes;
  * <= --max-calls tool calls (submit_patch is free in the harness and is not counted), >= 3 calls;
  * no identical consecutive calls, no multi-call steps, no harness continuation nudges (those add user turns);
  * at most --per-task episodes per task (the shortest ones).
Per step the parser records whether the model turn is *masked* for training: its result was a tool rejection
(FileEditError, FileWriteError, FileReadError, ValueError, BudgetExceeded, ADK "mandatory input parameters"
rejection, hallucinated tool name). The recovery turn that follows stays trainable.
"""
from __future__ import annotations
import argparse, collections, csv, glob, json, re
from pathlib import Path

# tests/ anywhere under the workspace (never /tmp scratch), plus the config files the grader resets
PROTECTED_RE = re.compile(r"^(?!/tmp/)(.*/)?(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|(^|/)pytest\.ini$"
                          r"|(^|/)pyproject\.toml$|(^|/)setup\.cfg$|(^|/)tox\.ini$|(^|/)setup\.py$")   # same set as prepare_data.PROTECTED_RE
BUDGET_FREE = {"submit_patch", "get_status"}   # not counted against max_tool_calls by the harness
MASK_ERROR_TYPES = {"FileEditError", "FileWriteError", "FileReadError", "ValueError", "BudgetExceeded"}
HARMLESS_TRAILING = re.compile(r"^\s*(git\s+(status|diff)|ls\b|cat\b|pwd\b)")


def norm_path(p: str) -> str:
    p = str(p or "")
    if p.startswith("/workspace/"): p = p[len("/workspace/"):]
    return p[2:] if p.startswith("./") else p


def classify_observation(tool: str, content: str, declared: set[str] | None):
    """-> (masked: bool, reason: str | None). content is the raw JSON string the model saw."""
    if declared is not None and tool not in declared: return True, "unknown_tool"
    if not content or not content.startswith("{"): return False, None
    try: o = json.loads(content)
    except Exception: return False, None
    if o.get("status") == "error":
        et = o.get("error_type")
        return (True, et) if et in MASK_ERROR_TYPES else (False, None)
    if "status" not in o and "error" in o:          # ADK parameter rejection: {"error": "Invoking `x()` failed as ..."}
        return True, "param_rejection"
    return False, None


def parse_trace(path):
    """-> dict(system, task_prompt, model, turns, final_text, final_thought, nudges, multi, texts) or None.
    turns: [{thought, text, tool, args, obs, masked, mask_reason}] in order. A tool-call step takes the thought /
    visible text of the thinking / text steps logged just before it (same LLM response)."""
    d = json.load(open(path, encoding="utf-8"))
    steps = d.get("steps") or []
    system = task = None; model = None; turns = []; nudges = 0; multi = 0; texts = 0
    pending_thought = ""; pending_text = ""; final_text = None; final_thought = ""
    for s in steps:
        et = (s.get("extra") or {}).get("event_type"); src = s.get("source"); msg = s.get("message") or ""
        if s.get("model_name"): model = s["model_name"]
        tcs = s.get("tool_calls") or []
        if et == "system_instruction":
            if system is None: system = msg
            continue
        if et == "task_prompt":
            if task is None: task = msg
            continue
        if et == "continuation_nudge" or (src == "system" and not tcs and et not in ("thinking", "text", "final")):
            nudges += 1; pending_thought = ""; pending_text = ""; continue
        if tcs:
            if len(tcs) > 1: multi += 1
            tc = tcs[0]
            thought = msg if et == "thinking" else pending_thought
            obs = ((s.get("observation") or {}).get("content")) or ""
            turns.append({"thought": thought or "", "text": pending_text or "", "tool": tc.get("function_name") or "",
                          "args": tc.get("arguments") or {}, "obs": obs, "masked": False, "mask_reason": None})
            pending_thought = ""; pending_text = ""
            continue
        if et == "thinking":          # thought without a call in this step: belongs to the next call or the final text
            pending_thought = (pending_thought + "\n" + msg).strip() if pending_thought else msg
        elif et == "text":
            pending_text = (pending_text + "\n" + msg).strip() if pending_text else msg; texts += 1
        elif et == "final":
            final_text = msg; final_thought = pending_thought; pending_thought = ""; pending_text = ""
    # workflow (SequentialAgent) traces log no system_instruction step; the bundle prompt replaces it anyway
    if task is None or not turns: return None
    return {"system": system or "", "task_prompt": task, "model": model or "", "turns": turns, "final_text": final_text or "",
            "final_thought": final_thought, "nudges": nudges, "multi": multi, "texts": texts}


def _ok(t):
    try: return json.loads(t["obs"]).get("status") == "ok"
    except Exception: return False


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FALLBACK_PARAMS = {"run_command": {"command"}, "read_file": {"filepath", "start_line", "end_line"}, "write_file": {"filepath", "content"},
                    "edit_file": {"filepath", "old_string", "new_string", "allow_multiple"}, "get_status": set(), "submit_patch": set()}


def declared_params():
    """tool -> parameter names, from vm/tool_declarations.json (what ADK declares) or the fallback table."""
    p = Path(__file__).resolve().parent / "tool_declarations.json"
    try:
        return {t["function"]["name"]: set((t["function"].get("parameters") or {}).get("properties", {})) for t in json.load(open(p, encoding="utf-8"))}
    except Exception:
        return dict(_FALLBACK_PARAMS)


def sanitize_args(tool, args, params):
    """Drop malformed keys (the 31B sometimes emits `end_line"`; vLLM's parser keeps them and ADK silently ignores them).
    Returns (clean_args, was_malformed): a malformed call is never trained on, but its cleaned form stays in context."""
    if not isinstance(args, dict): return {}, True
    known = params.get(tool)
    bad = [k for k in args if not _IDENT.fullmatch(str(k)) or (known is not None and k not in known)]
    return {k: v for k, v in args.items() if k not in bad}, bool(bad)


def cut_episode(ep: dict, max_calls: int, declared):
    """Apply the filters; returns (kept_episode | None, reason)."""
    turns = ep["turns"]
    if ep["multi"]: return None, "multi_call_step"
    if ep["nudges"]: return None, "continuation_nudge"
    params = declared_params()
    for t in turns:
        t["masked"], t["mask_reason"] = classify_observation(t["tool"], t["obs"], declared)
        t["args"], malformed = sanitize_args(t["tool"], t["args"], params)
        if malformed and not t["masked"]: t["masked"], t["mask_reason"] = True, "malformed_args"
    edits = [i for i, t in enumerate(turns) if t["tool"] in ("edit_file", "write_file") and _ok(t)]
    if not edits: return None, "no_successful_edit"
    last_edit = edits[-1]
    submit = None
    for i, t in enumerate(turns):
        if i > last_edit and t["tool"] == "submit_patch" and _ok(t):
            try: ps = int(json.loads(t["obs"]).get("patch_size") or 0)
            except Exception: ps = 0
            if ps > 0: submit = i; break
    if submit is None: return None, "no_submit_after_last_edit"
    kept = turns[:submit + 1]; trailing = turns[submit + 1:]
    for t in kept:
        fp = t["args"].get("filepath") if isinstance(t["args"], dict) else None
        if t["tool"] in ("edit_file", "write_file") and fp and PROTECTED_RE.search(norm_path(fp)): return None, "protected_file_edit"
    n_calls = sum(1 for t in kept if t["tool"] not in BUDGET_FREE)
    if n_calls > max_calls: return None, f"over_{max_calls}_calls"
    if n_calls < 3: return None, "under_3_calls"
    sig = [(t["tool"], json.dumps(t["args"], sort_keys=True)) for t in kept]
    if any(sig[i] == sig[i + 1] for i in range(len(sig) - 1)): return None, "identical_consecutive_calls"
    harmless = all(t["tool"] in ("get_status", "submit_patch") or
                   (t["tool"] == "run_command" and HARMLESS_TRAILING.match(str(t["args"].get("command", "")))) for t in trailing)
    if harmless and ep["final_text"].strip():
        final_text, final_thought, synth = ep["final_text"].strip(), ep["final_thought"], False
    else:
        files = []
        for t in kept:
            fp = t["args"].get("filepath") if isinstance(t["args"], dict) else None
            if t["tool"] in ("edit_file", "write_file") and fp and norm_path(fp) not in files: files.append(norm_path(fp))
        final_text, final_thought, synth = f"Submitted the fix: edited {', '.join(files[:4])}.", "", True
    out = dict(ep); out.update(turns=kept, final_text=final_text, final_thought=final_thought, n_calls=n_calls,
                               n_masked=sum(1 for t in kept if t["masked"]), synth_final=synth, n_trailing=len(trailing))
    return out, "kept"


def iter_eval_dirs(pattern: str):
    for ev in sorted(glob.glob(pattern)):
        rp = Path(ev) / "results.csv"
        if not rp.is_file(): continue
        rows = list(csv.DictReader(open(rp, encoding="utf-8")))
        if not rows or "resolved" not in rows[0]: continue          # controls runs have no resolved column
        yield ev, rows


def collect(pattern: str, max_calls: int = 24, per_task: int = 3, teacher: str = "31b", declared=None):
    """-> (episodes, stats). Each episode carries instance_id, repo, run, and the parsed fields."""
    stats = collections.Counter(); by_task = collections.defaultdict(list); tasks_seen = set()
    for ev, rows in iter_eval_dirs(pattern):
        run = Path(ev).parent.name
        for r in rows:
            iid = r["instance_id"]; tasks_seen.add(iid)
            if r.get("resolved") != "True": stats["unresolved"] += 1; continue
            tp = Path(ev) / "agent_run" / "traces" / f"trace_{iid}.json"
            if not tp.is_file(): stats["missing_trace"] += 1; continue
            ep = parse_trace(tp)
            if ep is None: stats["unparseable"] += 1; continue
            if teacher and teacher.lower() not in ep["model"].lower(): stats["other_model"] += 1; continue
            stats["resolved_candidates"] += 1
            kept, reason = cut_episode(ep, max_calls, declared)
            stats[reason] += 1
            if kept is None: continue
            kept.update(instance_id=iid, repo=r.get("repo") or iid.split("_")[0], run=run)
            by_task[iid].append(kept)
    episodes = []
    for iid, eps in sorted(by_task.items()):
        eps.sort(key=lambda e: (e["n_calls"], e["n_masked"], e["run"]))
        if len(eps) > per_task: stats["dropped_per_task_cap"] += len(eps) - per_task
        episodes += eps[:per_task]
    stats["kept_episodes"] = len(episodes); stats["kept_tasks"] = len(by_task); stats["tasks_seen"] = len(tasks_seen)
    stats["masked_turns"] = sum(e["n_masked"] for e in episodes); stats["synth_final"] = sum(1 for e in episodes if e["synth_final"])
    return episodes, stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern"); ap.add_argument("--max-calls", type=int, default=24); ap.add_argument("--per-task", type=int, default=3)
    ap.add_argument("--teacher", default="31b"); ap.add_argument("--tools", default="run_command,read_file,edit_file,write_file,get_status,submit_patch")
    a = ap.parse_args()
    eps, st = collect(a.pattern, a.max_calls, a.per_task, a.teacher, set(a.tools.split(",")))
    print(json.dumps(st, indent=1, sort_keys=True))
    print("per repo:", dict(collections.Counter(e["repo"].split("/")[-1] for e in eps)))
    print("calls:", sorted(e["n_calls"] for e in eps))
    print("mask reasons:", dict(collections.Counter(t["mask_reason"] for e in eps for t in e["turns"] if t["masked"])))
    print("tasks:", sorted(by_run := {e['instance_id'] for e in eps}))
