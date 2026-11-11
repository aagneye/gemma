#!/usr/bin/env python3
"""Per-run failure log for replica runs: for every finished task, what went wrong and why, and which behaviours occurred.

  python3 autopsy.py <run_dir> [--tasks data/rebench/tasks.jsonl] [--build-log data/rebench/build_log.csv] [--out <dir>]

<run_dir> is results/replica/<tag>/ (results.csv, agent_run/{task_results.jsonl, traces/, test_outputs/, patches/}).
Writes into --out (default: the run dir):
  autopsy.jsonl  one record per finished task (fields: see research/raw/13_run_log.md)
  report.md      the full report for a human
  brief.md       at most 120 lines: headline, outcomes, rule compliance, largest fixable failure type, runtime
Works on a run that is still in progress (it uses the tasks finished so far). CPU only, Python 3.10 standard library.
vm/arms_report.py imports this module for the side-by-side table.
"""
import argparse, collections, csv, json, os, re, statistics, sys
from pathlib import PurePosixPath

ROOT = "/mnt/biohub/kdata/gemma4"
DEFAULT_TASKS = "data/rebench/tasks.jsonl,data/rebench2/tasks.jsonl"
DEFAULT_BUILD_LOG = "data/rebench/build_log.csv,data/rebench2/build_log.csv"

# run_command kinds: the first matching pattern wins
CMD_KINDS = [
    ("test", re.compile(r"\bpytest\b|unittest")),
    ("shell_write", re.compile(r"sed -i|cat\s*>|tee |>>|>\s*[\w./-]+\.py")),
    ("repro", re.compile(r"python3? -c|python3? [\w./-]+\.py|python3? -? ?<<")),
    ("search", re.compile(r"git grep|\bgrep\b|\brg\b|\bfind\b|\bls\b|git ls-files")),
    ("shell_read", re.compile(r"\bcat\b|\bhead\b|\btail\b|sed -n|\bwc\b")),
    ("git", re.compile(r"git (diff|status|log|show|checkout|stash)")),
]
KIND_ORDER = ["read_file", "edit_file", "write_file", "test", "repro", "search", "shell_read", "shell_write", "git",
              "other_cmd", "submit_patch", "get_status"]
UNCOUNTED = {"submit_patch", "get_status"}          # these do not advance the call number
GARBLED = "mandatory input parameters are not present"
GREP_RX = re.compile(r"git grep|\bgrep\b|\brg\b")
TEST_PATH_RX = re.compile(r"(^|[\s/'\"=])tests?/|\btest_\w+\.py|\w+_test\.py|\bconftest\.py")
SYNTAX_RX = re.compile(r"\b(SyntaxError|IndentationError|TabError)\b")
CASE_RX = re.compile(r"\bprint\s*\(|\bassert\b|^\s*def test_|\bself\.assert\w+\(", re.M)
PY_TOKEN_RX = re.compile(r"[\w./-]+\.py\b")
SHELL_CREATE_RX = re.compile(r"(?:cat\s*>+|tee(?:\s+-a)?|>)\s*([\w./-]+\.py)")
MISSING_NAME = [
    ("attribute", re.compile(r"has no attribute '(\w+)'")),
    ("parameter", re.compile(r"unexpected keyword argument '(\w+)'")),
    ("import", re.compile(r"cannot import name '(\w+)'")),
    ("import", re.compile(r"No module named '([\w.]+)'")),
    ("parameter", re.compile(r"missing \d+ required (?:positional|keyword-only) arguments?: '(\w+)'")),
    ("name", re.compile(r"NameError: name '(\w+)' is not defined")),
]
ERRTYPE_RX = re.compile(r"^E\s+((?:\w+\.)*\w*(?:Error|Exception|Warning|Exit|Interrupt|Failed))\b", re.M)
OUTCOMES = ["solved", "wrong patch", "no patch", "session timeout", "call cap", "turn cap", "harness error"]
GRADE_CATS = ["target tests not fixed only", "target tests not fixed + passing tests broken", "only passing tests broken",
              "collection-import-syntax error", "no test log", "other"]
BEHAVIOURS = [  # (record field, short label) - the per-candidate measures, all true/false per task
    ("b_check_py_compile", "check after the last edit contains py_compile (E1, D1)"),
    ("b_check_existing_test", "check after the last edit runs an existing test file with pytest (C1)"),
    ("b_check_3_cases", "check after the last edit exercises 3 or more cases (C1)"),
    ("b_sibling_grep", "a grep ran between the first source edit and submit (P1)"),
    ("b_test_before_edit", "a test file was read or grepped before the first source edit (T2)"),
]


# ---------------------------------------------------------------- small helpers
def is_protected(rel_path):
    """The harness's own rule (swegemma/harness/verification.py, _is_protected_test_or_config_path)."""
    p = PurePosixPath(str(rel_path).replace("\\", "/"))
    name = p.name
    if name in {"conftest.py", "pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg", ".pytest.ini", "sitecustomize.py",
                "usercustomize.py", "_swegemma_stubs.py"}:
        return True
    if name.endswith(".pth") or (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py"):
        return True
    parts = {part.lower() for part in p.parts[:-1]}
    return bool({"tests", "test", "testing"} & parts and name.endswith(".py"))


def classify_cmd(cmd):
    for kind, rx in CMD_KINDS:
        if rx.search(cmd):
            return kind
    return "other_cmd"


def norm_test_id(s):
    """'path::test[param] - message' -> 'path::test'. Only a closed trailing [...] is stripped: an id with a space
    inside the brackets is cut at the space in the test log and in the task lists alike, so it still matches itself."""
    return re.sub(r"\[.*\]$", "", s.split(" - ")[0].strip())


def patch_files(text):
    return set(re.findall(r"^diff --git a/(\S+) b/", text or "", re.M))


def clean_path(p):
    p = str(p or "").strip().replace("\\", "/")
    p = re.sub(r"^/workspace/", "", p)
    return re.sub(r"^\./", "", p)


def resolve(path):
    if os.path.exists(path) or os.path.isabs(path):
        return path
    alt = os.path.join(ROOT, path)
    return alt if os.path.exists(alt) else path


def load_tasks(spec):
    tasks = {}
    for f in (spec or "").split(","):
        f = resolve(f.strip())
        if f and os.path.exists(f):
            for line in open(f, errors="replace"):
                if line.strip():
                    t = json.loads(line)
                    tasks.setdefault(t["instance_id"], t)
    return tasks


def load_labels(spec):
    labels = {}
    for f in (spec or "").split(","):
        f = resolve(f.strip())
        if f and os.path.exists(f):
            for r in csv.DictReader(open(f, errors="replace")):
                labels.setdefault(r["instance_id"], r)
    return labels


def load_results(run_dir):
    """Finished tasks so far: agent_run/task_results.jsonl (appended per task), else results.csv."""
    rows = []
    p = os.path.join(run_dir, "agent_run", "task_results.jsonl")
    if os.path.exists(p):
        for line in open(p, errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:          # a half-written last line of a run in progress
                continue
            rows.append({"instance_id": r["instance_id"], "repo": r.get("repo"), "resolved": bool(r.get("resolved")),
                         "patch_chars": int(r.get("agent_patch_size") or 0), "test_exit_code": r.get("test_exit_code"),
                         "duration_s": float(r.get("duration_seconds") or 0), "error": r.get("error") or "",
                         "llm_calls": r.get("total_llm_calls"), "tool_calls": r.get("tool_calls")})
        return rows
    p = os.path.join(run_dir, "results.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, errors="replace")):
            code = r.get("exit_code")
            rows.append({"instance_id": r["instance_id"], "repo": r.get("repo"), "resolved": r.get("resolved") == "True",
                         "patch_chars": int(r.get("patch_chars") or 0), "test_exit_code": int(code) if code not in (None, "") else None,
                         "duration_s": float(r.get("duration_s") or 0), "error": r.get("error") or "", "llm_calls": None,
                         "tool_calls": int(r["tool_calls"]) if r.get("tool_calls") not in (None, "") else None})
    return rows


# ---------------------------------------------------------------- trace
def parse_trace(path):
    """-> (calls, meta). One call per agent step with a tool call, in order."""
    d = json.load(open(path, errors="replace"))
    calls, n, last_elapsed, nudges = [], 0, 0.0, 0
    for s in d.get("steps", []):
        ex = s.get("extra") or {}
        if ex.get("event_type") == "continuation_nudge":
            nudges += 1
        last_elapsed = max(last_elapsed, float(ex.get("elapsed_s") or 0))
        tcs = s.get("tool_calls") or []
        if not tcs:
            continue
        tc = tcs[0]
        ob = s.get("observation") or {}
        last_elapsed = max(last_elapsed, float((ob.get("extra") or {}).get("elapsed_s") or 0))
        content = ob.get("content")
        if not isinstance(content, str):
            content = json.dumps(content)
        try:
            o = json.loads(content)
            if not isinstance(o, dict):
                o = {}
        except ValueError:
            o = {}
        tool = tc.get("function_name") or "?"
        args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
        cmd = str(args.get("command", "")) if tool == "run_command" else ""
        if tool not in UNCOUNTED:
            n += 1
        calls.append({"idx": len(calls), "n": n, "tool": tool, "args": args, "cmd": cmd,
                      "kind": classify_cmd(cmd) if tool == "run_command" else tool,
                      "obs": content, "o": o, "ok": o.get("status") == "ok", "error_type": o.get("error_type"),
                      "garbled": GARBLED in content, "warned": "budget_warning" in o})
    fm = d.get("final_metrics") or {}
    return calls, {"prompt_tokens": fm.get("total_prompt_tokens"), "output_tokens": fm.get("total_completion_tokens"),
                   "last_elapsed_s": last_elapsed, "nudges": nudges}


def analyse_calls(calls):
    """Everything that is read from the calls alone."""
    r = {}
    kinds = collections.Counter(c["kind"] for c in calls)
    r["calls_by_kind"] = {k: kinds[k] for k in KIND_ORDER if kinds[k]}
    r["calls"] = sum(1 for c in calls if c["tool"] not in UNCOUNTED)
    r["tool_calls_all"] = len(calls)
    edits = [c for c in calls if c["tool"] in ("edit_file", "write_file") and c["ok"]]
    # a source edit: edit_file, or write_file over a file the agent has read or edited before (a new file is a scratch script)
    seen, src_edits = set(), []
    for c in calls:
        p = clean_path(c["args"].get("filepath"))
        if c["tool"] == "edit_file" and c["ok"]:
            src_edits.append(c)
        elif c["tool"] == "write_file" and c["ok"] and p in seen:
            src_edits.append(c)
        if c["tool"] in ("read_file", "edit_file") and c["ok"] and p:
            seen.add(p)
    r["edits_ok"] = len(edits)
    r["first_edit_call"] = edits[0]["n"] if edits else None
    r["last_edit_call"] = edits[-1]["n"] if edits else None
    r["first_source_edit_call"] = src_edits[0]["n"] if src_edits else None
    after = [c for c in calls if edits and c["idx"] > edits[-1]["idx"] and c["tool"] == "run_command"]
    r["check_after_last_edit"] = any(c["kind"] in ("test", "repro") for c in after)
    r["test_after_last_edit"] = any(c["kind"] == "test" for c in after)
    # edit and read problems
    ef = [c for c in calls if c["tool"] == "edit_file"]
    r["garbled_edits"] = sum(1 for c in ef if c["garbled"])
    r["garbled_loop"] = r["garbled_edits"] >= 3
    r["garbled_other_calls"] = sum(1 for c in calls if c["garbled"] and c["tool"] != "edit_file")
    other = collections.Counter()
    for c in ef:
        if c["garbled"] or c["ok"]:
            continue
        low = c["obs"].lower()
        other["after call cap" if c["error_type"] == "BudgetExceeded" else "old_string not found" if "not found" in low
              else "old_string not unique" if ("occurrence" in low or "multiple" in low or "unique" in low) else "other"] += 1
    r["edit_errors_other"] = sum(other.values())
    r["edit_error_kinds"] = dict(other)
    reads = [c for c in calls if c["tool"] == "read_file"]
    r["reads"] = len(reads)
    r["rangeless_reads"] = sum(1 for c in reads if "start_line" not in c["args"] and "end_line" not in c["args"])
    r["truncated_reads"] = sum(1 for c in reads if c["o"].get("is_truncated") is True)
    r["searches"] = kinds["search"]
    r["searches_with_head"] = sum(1 for c in calls if c["kind"] == "search" and re.search(r"\|\s*head\b", c["cmd"]))
    r["py_compile_used"] = any("py_compile" in c["cmd"] for c in calls)
    r["syntax_error_seen"] = any(c["tool"] == "run_command" and SYNTAX_RX.search(c["obs"]) for c in calls)
    # repeats, budget warning, submit
    r["identical_consecutive"] = sum(1 for a, b in zip(calls, calls[1:]) if a["tool"] == b["tool"] and a["args"] == b["args"]
                                     and b["tool"] not in UNCOUNTED)
    wi = next((c["idx"] for c in calls if c["warned"]), None)
    r["budget_warning_seen"] = wi is not None
    r["call_after_warning"] = (calls[wi + 1]["kind"] if wi + 1 < len(calls) else "none") if wi is not None else None
    r["hit_call_cap"] = any(c["error_type"] == "BudgetExceeded" for c in calls)
    subs = [c for c in calls if c["tool"] == "submit_patch"]
    r["submit_called"] = bool(subs)
    r["submit_count"] = len(subs)
    r["submit_empty"] = bool(subs) and not (subs[-1]["o"].get("patch_size") or 0)
    # protected files
    prot = []
    for c in calls:
        p = clean_path(c["args"].get("filepath"))
        if c["tool"] in ("edit_file", "write_file") and c["ok"] and p and is_protected(p) and p not in prot:
            prot.append(p)
    r["protected_writes"] = prot
    r["trace_edited_files"] = sorted({clean_path(c["args"].get("filepath")) for c in edits} - {""})
    # candidate behaviours
    written = {}                                     # files the agent created: path -> content ("" when made by the shell)
    for c in calls:
        if c["tool"] == "write_file" and c["ok"]:
            written[clean_path(c["args"].get("filepath"))] = str(c["args"].get("content", ""))
        for p in SHELL_CREATE_RX.findall(c["cmd"]):
            written.setdefault(clean_path(p), "")
    made = {os.path.basename(p) for p in written}
    r["b_check_py_compile"] = any("py_compile" in c["cmd"] for c in after)
    existing = False
    for c in after:
        if c["kind"] == "test" and re.search(r"\bpytest\b", c["cmd"]):
            toks = PY_TOKEN_RX.findall(c["cmd"])
            if not toks or any(os.path.basename(t) not in made for t in toks):
                existing = True
    r["b_check_existing_test"] = existing
    most = 0
    for c in after:
        if c["kind"] in ("test", "repro", "shell_write"):
            code = c["cmd"] + "".join("\n" + body for p, body in written.items() if os.path.basename(p) in c["cmd"])
            most = max(most, len(CASE_RX.findall(code)))
    r["check_cases"] = most
    r["b_check_3_cases"] = most >= 3
    fs = src_edits[0]["idx"] if src_edits else None
    last_sub = subs[-1]["idx"] if subs else len(calls)
    r["b_sibling_grep"] = fs is not None and any(fs < c["idx"] < last_sub and c["tool"] == "run_command" and GREP_RX.search(c["cmd"])
                                                 for c in calls)
    before = calls if fs is None else calls[:fs]
    r["b_test_before_edit"] = any(
        (c["tool"] == "read_file" and c["ok"] and is_protected(clean_path(c["args"].get("filepath")))
         and clean_path(c["args"].get("filepath")).endswith(".py"))
        or (c["kind"] in ("search", "shell_read") and TEST_PATH_RX.search(c["cmd"])) for c in before)
    return r


# ---------------------------------------------------------------- grading and files
def failure_sections(log_text):
    """pytest failure sections by test name: '____ TestA.test_b[param] ____' -> {'TestA.test_b': text}."""
    body = re.split(r"^=+ short test summary info =+$", log_text, flags=re.M)[0]
    parts = re.split(r"^_{3,} (.+?) _{3,}$", body, flags=re.M)
    secs = {}
    for name, text in zip(parts[1::2], parts[2::2]):
        key = re.sub(r"^ERROR (?:at \w+ of|collecting) ", "", name).split("[")[0].strip()
        secs[key] = secs.get(key, "") + text
    return secs


def section_key(test_id):
    """'path.py::TestA::test_b[param]' -> 'TestA.test_b' (the name pytest prints above a failure)."""
    return ".".join(test_id.split("[")[0].split("::")[1:])


def analyse_grading(log_text, task, exit_code):
    g = {"failed_f2p": [], "failed_p2p": [], "failed_p2p_only": 0, "failed_other": 0, "grade_category": None, "first_error_type": None,
         "fail_kind": None, "missing_name": None}
    if log_text is None:
        g["grade_category"] = "no test log"
        return g
    failed = []
    for m in re.finditer(r"^(FAILED|ERROR) (\S+)", log_text, re.M):
        t = norm_test_id(m.group(2))
        if t not in failed:
            failed.append(t)
    f2p = {norm_test_id(x) for x in (task or {}).get("FAIL_TO_PASS") or []}
    p2p = {norm_test_id(x) for x in (task or {}).get("PASS_TO_PASS") or []}   # a parametrised test can be in both lists
    g["failed_f2p"] = [t for t in failed if t in f2p]
    g["failed_p2p"] = [t for t in failed if t in p2p]
    g["failed_p2p_only"] = len([t for t in g["failed_p2p"] if t not in f2p])     # stricter: not also a target test
    g["failed_other"] = len([t for t in failed if t not in f2p and t not in p2p])
    if exit_code not in (0, 1, None):
        g["grade_category"] = "collection-import-syntax error"
    elif g["failed_f2p"] and g["failed_p2p"]:
        g["grade_category"] = "target tests not fixed + passing tests broken"
    elif g["failed_f2p"]:
        g["grade_category"] = "target tests not fixed only"
    elif g["failed_p2p"]:
        g["grade_category"] = "only passing tests broken"
    else:
        g["grade_category"] = "other"
    # the error is read from the log sections of the failing target tests (of the broken passing tests when no target
    # test fails); the whole log is the fallback, for example for collection errors
    secs = failure_sections(log_text)
    scope = "".join(secs.get(section_key(t), "") for t in (g["failed_f2p"] or g["failed_p2p"]))
    g["error_scope"] = "failing tests" if scope else "whole log"
    log_text = scope or log_text
    m = ERRTYPE_RX.search(log_text)
    if m:
        g["first_error_type"] = m.group(1).split(".")[-1]
    elif re.search(r"^E\s+assert\b", log_text, re.M):
        g["first_error_type"] = "AssertionError"
    else:
        m = re.search(r"^(?:FAILED|ERROR) \S+ - (\w+)", log_text, re.M)
        g["first_error_type"] = m.group(1) if m else None
    best = None
    for kind, rx in MISSING_NAME:
        m = rx.search(log_text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), kind, m.group(1))
    if best:
        issue = (task or {}).get("problem_statement") or ""
        name = best[2]
        g["missing_name"] = {"kind": best[1], "name": name,
                             "in_issue": (name in issue or name.split(".")[-1] in issue) if task else None}
        g["fail_kind"] = "missing name"
    elif "DID NOT RAISE" in log_text:
        g["fail_kind"] = "exception not raised"
    elif g["first_error_type"] == "AssertionError":
        g["fail_kind"] = "wrong behaviour or value"
    else:
        g["fail_kind"] = "other error"
    return g


def match_files(mine, gold):
    if not mine:
        return "no edit"
    if gold is None:
        return None
    return "superset" if set(gold) <= set(mine) else "overlap" if set(gold) & set(mine) else "disjoint"


def analyse_files(patch_text, task, trace_files):
    """Edited files against the gold patch; only non-test .py files count (the harness's protected rule decides 'test').
    file_match uses the files in the saved patch; file_match_trace uses the files of successful edit_file / write_file calls."""
    src = lambda ps: sorted(p for p in ps if p.endswith(".py") and not is_protected(p))
    mine_all = patch_files(patch_text)
    new = set(re.findall(r"^diff --git a/(\S+) b/\S+\nnew file mode", patch_text or "", re.M))
    gold = src(patch_files(task.get("patch"))) if task else None
    mine = src(mine_all)
    return {"files_edited": mine, "gold_files": gold or [], "file_match": match_files(mine, gold),
            "file_match_trace": match_files(src(trace_files), gold),
            "patch_protected_files": sorted(p for p in mine_all if is_protected(p)),
            # the patch holds only files the agent created (scratch scripts) and none of them is a gold file
            "scratch_only_patch": bool(mine) and all(p in new and p not in (gold or []) for p in mine)}


# ---------------------------------------------------------------- outcome, failure type, why
def outcome_of(row, rec):
    err = (row["error"] or "").lower()
    if row["resolved"]:
        return "solved"
    if "session timeout" in err:
        return "session timeout"
    if "turns budget" in err or "turn budget" in err:
        return "turn cap"
    if "tool call" in err or "call budget" in err:
        return "call cap"
    if err:
        return "harness error"
    if rec.get("hit_call_cap") and not rec.get("submit_called"):
        return "call cap"
    return "no patch" if not row["patch_chars"] else "wrong patch"


FAILURE_TYPES = [  # (name, fixable by instructions)
    ("garbled edit loop", True), ("no source edit in the patch", True), ("syntax or import error in the patch", True),
    ("missing name that is not in the issue", False), ("missing name that is in the issue", True),
    ("wrong files edited", True), ("some gold files not edited", True), ("passing tests broken", True),
    ("expected exception not raised", True), ("wrong behaviour or value", True), ("other test error", True),
    ("ran out of time before grading", True), ("harness error", False), ("not graded", False),
]
FIXABLE = dict(FAILURE_TYPES)


def failure_type(rec):
    """One type per unsolved task; the first matching rule wins."""
    if rec["resolved"]:
        return None
    if rec["outcome"] == "harness error":
        return "harness error"
    if rec.get("garbled_loop"):
        return "garbled edit loop"
    if not rec["patch_chars"] or rec.get("file_match") == "no edit" or rec.get("scratch_only_patch"):
        return "no source edit in the patch"
    cat = rec["grade_category"]
    if cat == "no test log":
        return "ran out of time before grading" if rec["outcome"] in ("session timeout", "call cap", "turn cap") else "not graded"
    if cat == "collection-import-syntax error":
        return "syntax or import error in the patch"
    mn = rec.get("missing_name")
    if mn and mn.get("in_issue") is False:
        return "missing name that is not in the issue"
    if mn:
        return "missing name that is in the issue"
    if rec.get("file_match") == "disjoint":
        return "wrong files edited"
    if rec.get("file_match") == "overlap":
        return "some gold files not edited"
    if cat == "only passing tests broken":
        return "passing tests broken"
    if rec.get("fail_kind") == "exception not raised":
        return "expected exception not raised"
    if rec.get("fail_kind") == "wrong behaviour or value":
        return "wrong behaviour or value"
    return "other test error"


def why(rec):
    """One deterministic sentence built from the record's fields."""
    n, oc = rec.get("calls"), rec["outcome"]
    h = rec.get("harness_tool_calls")
    # the harness does not count garbled calls; calls refused after the cap are in the trace
    n = f"{n} calls" + (f" (the harness counted {h})" if h is not None and h != n else "")
    fm = rec.get("file_match")
    if oc == "solved":
        s = f"Solved in {n}"
        if rec.get("files_edited"):
            s += f"; edited {', '.join(rec['files_edited'][:2])}"
        s += "; a test or repro ran after the last edit" if rec.get("check_after_last_edit") else "; no test or repro ran after the last edit"
        if rec.get("garbled_edits"):
            s += f"; {rec['garbled_edits']} garbled edit_file call(s) on the way"
        return s + "."
    head = {"session timeout": f"Session timeout after {n}", "call cap": f"Hit the call cap ({n}) without submit_patch",
            "turn cap": f"Hit the turn cap after {n}", "harness error": f"Harness error: {rec.get('harness_error')}",
            "no patch": f"No patch after {n}", "wrong patch": f"Wrong patch after {n}"}[oc]
    parts = [head]
    cat, mn = rec.get("grade_category"), rec.get("missing_name")
    nf, np_ = len(rec.get("failed_f2p") or []), len(rec.get("failed_p2p") or [])
    if not rec["patch_chars"]:
        if not rec.get("edits_ok"):
            parts.append("no edit call succeeded")
        elif rec.get("patch_protected_files") or rec.get("protected_writes"):
            parts.append("the only edits were to scratch or protected files")
        else:
            parts.append("the edits left no patch")
    elif cat == "no test log":
        parts.append("the patch was not graded (no test log)")
    elif cat == "collection-import-syntax error":
        parts.append(f"the tests could not be collected ({rec.get('first_error_type') or 'error'}, pytest exit code {rec.get('test_exit_code')})")
    elif cat in ("target tests not fixed only", "target tests not fixed + passing tests broken", "only passing tests broken", "other"):
        if nf:
            if mn:
                where = {True: "is in the issue text", False: "is not in the issue text", None: "could not be checked against the issue"}[mn.get("in_issue")]
                cause = f"the test log reports the missing {mn['kind']} '{mn['name']}', which {where}"
            elif rec.get("fail_kind") == "exception not raised":
                cause = "an expected exception is not raised"
            elif rec.get("fail_kind") == "wrong behaviour or value":
                cause = "the fix gives a value or behaviour the tests do not accept (AssertionError)"
            else:
                cause = f"first error {rec.get('first_error_type') or 'unknown'}"
            parts.append(f"{nf} target test(s) still fail: {cause}")
        if np_:
            parts.append(f"{np_} test(s) that passed before now fail")
        if not nf and not np_:
            parts.append(f"the tests failed with exit code {rec.get('test_exit_code')} but no failing id matches the task's lists")
    if rec["patch_chars"]:
        if rec.get("scratch_only_patch"):
            parts.append(f"the patch holds only scratch files the agent created ({', '.join(rec['files_edited'][:2])})")
        elif fm == "disjoint":
            parts.append(f"the patch edits none of the gold files (gold: {', '.join(rec['gold_files'][:2])})")
        elif fm == "overlap":
            miss = [p for p in rec["gold_files"] if p not in rec["files_edited"]]
            parts.append(f"the patch misses gold file(s) {', '.join(miss[:2])}")
        elif fm == "no edit":
            parts.append("the patch has no source .py file")
        elif fm == "superset":
            parts.append("the patch edits every gold file")
    if rec.get("garbled_loop"):
        parts.append(f"{rec['garbled_edits']} garbled edit_file calls (loop)")
    elif rec.get("garbled_edits"):
        parts.append(f"{rec['garbled_edits']} garbled edit_file call(s)")
    if rec.get("edits_ok") and not rec.get("check_after_last_edit"):
        parts.append("no test or repro ran after the last edit")
    if rec.get("hit_call_cap") and oc != "call cap":
        parts.append("the call cap was reached")
    if rec.get("end_gap_s") is not None and rec["end_gap_s"] >= HUNG_GAP_S:
        parts.append(f"{rec['end_gap_s']:.0f} s passed between the last trace event and the end")
    return "; ".join(parts) + "."


HUNG_GAP_S = 120.0   # a gap this long between the last trace event and the end of the task is flagged as hung


# ---------------------------------------------------------------- one run
def autopsy_run(run_dir, tasks=None, labels=None):
    """-> list of records (one per finished task), in run order."""
    tasks = tasks if tasks is not None else load_tasks(DEFAULT_TASKS)
    labels = labels if labels is not None else load_labels(DEFAULT_BUILD_LOG)
    ar = os.path.join(run_dir, "agent_run")
    recs = []
    for row in load_results(run_dir):
        iid = row["instance_id"]
        safe = iid.replace("/", "__")
        task, lab = tasks.get(iid), labels.get(iid) or {}
        rec = {"instance_id": iid, "repo": row["repo"], "resolved": row["resolved"], "outcome": None,
               "harness_error": row["error"] or None, "patch_chars": row["patch_chars"], "test_exit_code": row["test_exit_code"],
               "duration_s": round(row["duration_s"], 1), "llm_calls": row["llm_calls"], "harness_tool_calls": row["tool_calls"],
               "task_known": task is not None,
               "difficulty": lab.get("difficulty"), "issue_score": lab.get("issue_score"), "test_score": lab.get("test_score")}
        tp = os.path.join(ar, "traces", f"trace_{safe}.json")
        meta = {}
        calls = []
        if os.path.exists(tp):
            try:
                calls, meta = parse_trace(tp)
            except (ValueError, OSError):
                pass
        rec["trace_found"] = bool(meta)
        rec.update(analyse_calls(calls))
        rec["prompt_tokens"], rec["output_tokens"] = meta.get("prompt_tokens"), meta.get("output_tokens")
        rec["nudges"] = meta.get("nudges")
        rec["end_gap_s"] = round(row["duration_s"] - meta["last_elapsed_s"], 1) if meta else None
        rec["hung"] = rec["end_gap_s"] is not None and rec["end_gap_s"] >= HUNG_GAP_S
        pp = os.path.join(ar, "patches", f"{safe}.patch")
        rec.update(analyse_files(open(pp, errors="replace").read() if os.path.exists(pp) else "", task, rec["trace_edited_files"]))
        lp = os.path.join(ar, "test_outputs", f"{safe}.log")
        rec.update(analyse_grading(open(lp, errors="replace").read() if os.path.exists(lp) else None, task, row["test_exit_code"]))
        rec["outcome"] = outcome_of(row, rec)
        rec["failure_type"] = failure_type(rec)
        rec["why"] = why(rec)
        recs.append(rec)
    return recs


# ---------------------------------------------------------------- aggregates and reports
def pct(a, b):
    return f"{100.0 * a / b:.0f}%" if b else "-"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else 0.0


def rules(recs):
    """(label, tasks that follow it, tasks it applies to, solved among followers, solved among the others that it applies to)."""
    out = []

    def add(label, pred, scope=lambda r: True):
        sc = [r for r in recs if scope(r)]
        yes = [r for r in sc if pred(r)]
        no = [r for r in sc if not pred(r)]
        out.append((label, len(yes), len(sc), sum(r["resolved"] for r in yes), len(no), sum(r["resolved"] for r in no)))
    edited = lambda r: r["edits_ok"] > 0
    add("submit_patch was called", lambda r: r["submit_called"])
    add("at least one edit call succeeded", edited)
    add("first edit by call 12", lambda r: r["first_edit_call"] <= 12, edited)
    add("a test or repro ran after the last edit", lambda r: r["check_after_last_edit"], edited)
    add("a test command (pytest, unittest) ran after the last edit", lambda r: r["test_after_last_edit"], edited)
    add("every read_file had a line range", lambda r: r["rangeless_reads"] == 0, lambda r: r["reads"] > 0)
    add("no garbled edit_file call", lambda r: r["garbled_edits"] == 0)
    add("no identical consecutive calls", lambda r: r["identical_consecutive"] == 0)
    add("no write to a protected file", lambda r: not r["protected_writes"])
    add("no syntax or indentation error seen", lambda r: not r["syntax_error_seen"])
    add("py_compile used", lambda r: r["py_compile_used"])
    for field, label in BEHAVIOURS:
        add(label, lambda r, f=field: r[f])
    return out


def summary(recs):
    n = len(recs)
    s = {"tasks": n, "solved": sum(r["resolved"] for r in recs)}
    s["outcomes"] = collections.Counter(r["outcome"] for r in recs)
    uns = [r for r in recs if not r["resolved"]]
    s["grading"] = collections.Counter(r["grade_category"] for r in uns)
    s["fail_kinds"] = collections.Counter(r["fail_kind"] for r in uns if r["fail_kind"])
    s["failure_types"] = collections.Counter(r["failure_type"] for r in uns)
    kinds = collections.Counter()
    for r in recs:
        kinds.update(r["calls_by_kind"])
    s["kinds"] = kinds
    for k in ("garbled_edits", "edit_errors_other", "reads", "rangeless_reads", "truncated_reads", "searches", "searches_with_head",
              "calls", "identical_consecutive"):
        s[k] = sum(r[k] for r in recs)
    s["garbled_tasks"] = sum(1 for r in recs if r["garbled_edits"])
    s["garbled_max"] = max([r["garbled_edits"] for r in recs] or [0])
    s["loop_tasks"] = sum(1 for r in recs if r["garbled_loop"])
    for k in ("file_match", "file_match_trace"):
        s[k] = collections.Counter(r[k] for r in recs)
        s[k + "_solved"] = collections.Counter(r[k] for r in recs if r["resolved"])
    return s


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


def largest_fixable(recs):
    ft = collections.Counter(r["failure_type"] for r in recs if not r["resolved"])
    fix = [(c, t) for t, c in ft.items() if FIXABLE.get(t)]
    if not fix:
        return None, 0, []
    c, t = max(fix, key=lambda x: (x[0], x[1]))
    return t, c, [r for r in recs if r["failure_type"] == t][:3]


def section_headline(recs, run_dir, s):
    n = s["tasks"]
    return [f"- Run: `{run_dir}`. Finished tasks: **{n}**. Solved: **{s['solved']}** ({pct(s['solved'], n)}).",
            f"- Unsolved: {n - s['solved']}. " + ", ".join(f"{s['outcomes'][o]} {o}" for o in OUTCOMES[1:] if s["outcomes"][o]) + ".",
            f"- edit_file calls: {s['kinds']['edit_file']}, of which {s['garbled_edits']} garbled on {s['garbled_tasks']} tasks "
            f"({s['loop_tasks']} tasks with a loop of 3 or more; at most {s['garbled_max']} in one task).",
            f"- read_file calls: {s['reads']}, of which {s['rangeless_reads']} without a line range ({pct(s['rangeless_reads'], s['reads'])}) "
            f"and {s['truncated_reads']} truncated."]


def section_outcomes(recs, s):
    rows = []
    for o in OUTCOMES:
        rs = [r for r in recs if r["outcome"] == o]
        if rs:
            rows.append((o, len(rs), pct(len(rs), s["tasks"]), f"{mean(r['calls'] for r in rs):.1f}", f"{mean(r['duration_s'] for r in rs):.0f}"))
    return table(["Outcome", "Tasks", "Share", "Calls per task", "Seconds per task"], rows)


def section_rules(recs):
    rows = [(lab, f"{y} of {sc}", pct(y, sc), f"{ys} of {y}", f"{ns} of {no}") for lab, y, sc, ys, no, ns in rules(recs)]
    return table(["Rule or behaviour", "Tasks that show it", "Share", "Solved with it", "Solved without it"], rows)


def section_runtime(recs):
    tot = sum(r["duration_s"] for r in recs)
    rows = [("Duration, seconds", f"{mean(r['duration_s'] for r in recs):.0f}", f"{med(r['duration_s'] for r in recs):.0f}", f"{tot:.0f} ({tot / 3600:.1f} h)"),
            ("Calls (without submit_patch, get_status)", f"{mean(r['calls'] for r in recs):.1f}", f"{med(r['calls'] for r in recs):.0f}", sum(r["calls"] for r in recs)),
            ("Output tokens", f"{mean(r['output_tokens'] for r in recs):.0f}", f"{med(r['output_tokens'] for r in recs):.0f}", sum(r["output_tokens"] or 0 for r in recs)),
            ("Prompt tokens", f"{mean(r['prompt_tokens'] for r in recs):.0f}", f"{med(r['prompt_tokens'] for r in recs):.0f}", sum(r["prompt_tokens"] or 0 for r in recs))]
    out = table(["Per task", "Mean", "Median", "Total"], rows)
    hung = [r for r in recs if r["hung"]]
    out.append("")
    out.append(f"- Tasks that reached the call cap: {sum(1 for r in recs if r['hit_call_cap'])}. Tasks that saw the budget warning: {sum(1 for r in recs if r['budget_warning_seen'])}.")
    out.append(f"- Hung tasks (at least {HUNG_GAP_S:.0f} s between the last trace event and the end): {len(hung)}"
               + (": " + ", ".join(f"{r['instance_id']} ({r['end_gap_s']:.0f} s)" for r in hung[:5]) if hung else "") + ".")
    return out


def section_fixable(recs):
    t, c, ex = largest_fixable(recs)
    if not t:
        return ["- No unsolved task with a fixable failure type."]
    out = [f"- Largest fixable failure type: **{t}**, {c} of {sum(1 for r in recs if not r['resolved'])} unsolved tasks.", "- Examples:"]
    out += [f"  - `{r['instance_id']}`: {r['why']}" for r in ex]
    return out


def write_brief(recs, run_dir, out_dir):
    s = summary(recs)
    L = [f"# Run brief: {os.path.basename(os.path.normpath(run_dir))}", "", "## Headline"] + section_headline(recs, run_dir, s)
    L += ["", "## Outcomes"] + section_outcomes(recs, s)
    L += ["", "## Rule compliance", "Solved counts compare the tasks that show the behaviour with the tasks that do not."] + section_rules(recs)
    L += ["", "## Largest fixable failure type"] + section_fixable(recs)
    ft = [(t, c) for t, c in s["failure_types"].most_common() if t]
    L += ["- All types: " + "; ".join(f"{c} {t}" + ("" if FIXABLE.get(t) else " (not fixable by instructions)") for t, c in ft) + "."]
    L += ["", "## Runtime"] + section_runtime(recs)
    L = L[:120]
    open(os.path.join(out_dir, "brief.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def write_report(recs, run_dir, out_dir):
    s = summary(recs)
    n = s["tasks"]
    uns = [r for r in recs if not r["resolved"]]
    L = [f"# Run log: {os.path.basename(os.path.normpath(run_dir))}", "",
         "Written by `vm/autopsy.py`. Definitions: `research/raw/13_run_log.md`.", "", "## 1. Headline"] + section_headline(recs, run_dir, s)
    L += ["", "## 2. Outcomes", "Each task has one outcome."] + section_outcomes(recs, s)
    L += ["", "## 3. Grading of the unsolved tasks", f"{len(uns)} tasks are unsolved."]
    L += table(["Grading category", "Tasks"], [(c, s["grading"][c]) for c in GRADE_CATS if s["grading"][c]])
    L += ["", "Error kind, read from the log sections of the failing target tests (unsolved tasks with a log):"]
    mn = [r for r in uns if r["missing_name"]]
    L += table(["Kind", "Tasks"], [(k, c) for k, c in s["fail_kinds"].most_common()])
    L += [f"- Missing names: {len(mn)} tasks. In {sum(1 for r in mn if r['missing_name']['in_issue'] is False)} of them the name is not in the issue text."]
    L += ["", "## 4. Failure types", "One type per unsolved task; the first matching rule in this order wins."]
    L += table(["Failure type", "Tasks", "Fixable by instructions"],
               [(t, s["failure_types"][t], "yes" if fx else "no") for t, fx in FAILURE_TYPES if s["failure_types"][t]])
    L += [""] + section_fixable(recs)
    L += ["", "## 5. Rules and behaviours", "Solved counts compare the tasks that show the behaviour with the tasks that do not."] + section_rules(recs)
    aw = collections.Counter(r["call_after_warning"] for r in recs if r["budget_warning_seen"])
    L += ["", f"- Call right after the first budget warning ({sum(aw.values())} tasks): " + ", ".join(f"{c} {k}" for k, c in aw.most_common()) + "."]
    L += [f"- submit_patch was called on {sum(r['submit_called'] for r in recs)} tasks; on {sum(r['submit_empty'] for r in recs)} of them the patch was empty.",
          f"- Tasks with a write to a protected file: {sum(1 for r in recs if r['protected_writes'])}.",
          f"- Tasks with identical consecutive calls: {sum(1 for r in recs if r['identical_consecutive'])} ({s['identical_consecutive']} repeated calls)."]
    L += ["", "## 6. Calls by kind"]
    L += table(["Kind", "Calls", "Per task"], [(k, s["kinds"][k], f"{s['kinds'][k] / n:.1f}") for k in KIND_ORDER if s["kinds"][k]] if n else [])
    L += ["", f"- Garbled edit_file calls: {s['garbled_edits']} on {s['garbled_tasks']} tasks. Other edit_file errors: {s['edit_errors_other']}.",
          f"- read_file without a line range: {s['rangeless_reads']} of {s['reads']}. Truncated reads: {s['truncated_reads']}.",
          f"- Search commands: {s['searches']}, of which {s['searches_with_head']} with `| head`."]
    L += ["", "## 7. Edited files against the gold patch", "Only non-test `.py` files count on both sides.",
          "The patch columns use the files in the saved patch. The call columns use the files of successful `edit_file` and `write_file` calls."]
    L += table(["Edited files", "Tasks (patch)", "Solved (patch)", "Tasks (calls)", "Solved (calls)"],
               [(k, s["file_match"][k], s["file_match_solved"][k], s["file_match_trace"][k], s["file_match_trace_solved"][k])
                for k in ("superset", "overlap", "disjoint", "no edit")])
    L += [f"- Patches that hold only scratch files the agent created: {sum(1 for r in recs if r['scratch_only_patch'])}."]
    if any(r["test_score"] not in (None, "") for r in recs):
        L += ["", "## 8. Solved by task label"]
        rows = []
        for name, key in (("difficulty", "difficulty"), ("test_score", "test_score"), ("issue_score", "issue_score")):
            for v in sorted({r[key] for r in recs if r[key] not in (None, "")}):
                rs = [r for r in recs if r[key] == v]
                rows.append((f"{name} = {v}", len(rs), sum(r["resolved"] for r in rs), pct(sum(r["resolved"] for r in rs), len(rs))))
        L += table(["Label", "Tasks", "Solved", "Share"], rows)
    L += ["", "## 9. Runtime"] + section_runtime(recs)
    L += ["", "## 10. Every task", "Unsolved tasks first, in run order."]
    L += table(["Task", "Outcome", "Failure type", "Calls", "Why"],
               [(r["instance_id"], r["outcome"], r["failure_type"] or "", r["calls"], r["why"].replace("|", "/")) for r in uns + [r for r in recs if r["resolved"]]])
    open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--tasks", default=DEFAULT_TASKS, help="tasks.jsonl with the gold patches (comma-separated list allowed)")
    ap.add_argument("--build-log", default=DEFAULT_BUILD_LOG, help="build_log.csv with the task labels (comma-separated list allowed)")
    ap.add_argument("--out", default=None, help="output directory (default: the run dir)")
    a = ap.parse_args()
    out = a.out or a.run_dir
    os.makedirs(out, exist_ok=True)
    recs = autopsy_run(a.run_dir, load_tasks(a.tasks), load_labels(a.build_log))
    if not recs:
        sys.exit(f"no finished task found in {a.run_dir}")
    with open(os.path.join(out, "autopsy.jsonl"), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    write_report(recs, a.run_dir, out)
    write_brief(recs, a.run_dir, out)
    s = summary(recs)
    unknown = sum(1 for r in recs if not r["task_known"])
    print(f"{a.run_dir}: {s['tasks']} tasks, {s['solved']} solved; garbled edit calls {s['garbled_edits']} on {s['garbled_tasks']} tasks; "
          f"range-less reads {s['rangeless_reads']} of {s['reads']} -> {out}/autopsy.jsonl, report.md, brief.md"
          + (f" ({unknown} tasks not found in --tasks: no gold-file or issue checks for them)" if unknown else ""))


if __name__ == "__main__":
    main()
