#!/usr/bin/env python3
"""Convert open SWE-agent trajectories (OpenHands-style function calling) into the competition's ADK
tool schema, emit windowed, compaction-shaped SFT samples, and tokenize them with the Gemma 4 chat
template using exact span masking (loss on model turns only, never on tool responses).

v2 (2026-10-17) — validated against nvidia/SWE-Hero-openhands-trajectories and
nebius/SWE-rebench-openhands-trajectories schemas and the Gemma 4 V2 chat template rendering.

Usage (on the VM):
  python prepare_data.py --source swe-hero --max-examples 1500 --out datasets/sft/swe_hero.jsonl
  python prepare_data.py --source nebius-openhands --max-examples 1500 --out datasets/sft/nebius.jsonl
  python prepare_data.py --tokenize "datasets/sft/*.jsonl" --model models/gemma-4-12B-it-qat-q4_0-unquantized \
      --max-len 8192 --out datasets/sft/tok_12b_8k
"""
from __future__ import annotations
import argparse, glob, json, os, random, re
from pathlib import Path

SCHEMA_VERSION = "adk-v2"
RNG = random.Random(0)

# ---- competition tool declarations (names + arg names must match the harness exactly) ----------
TOOLS = [
    {"type": "function", "function": {"name": "run_command", "description": "Executes a shell command in /bin/bash -c inside /workspace.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Reads a file from /workspace with 1-indexed inclusive line slicing.",
     "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "start_line": {"type": "integer"},
                                                      "end_line": {"type": "integer"}}, "required": ["filepath"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replaces old_string with new_string in an existing non-empty file inside /workspace.",
     "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "old_string": {"type": "string"},
                                                      "new_string": {"type": "string"}, "allow_multiple": {"type": "boolean"}},
                    "required": ["filepath", "old_string", "new_string"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Creates or overwrites a file at /workspace/<filepath>, creating parent directories.",
     "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["filepath", "content"]}}},
    {"type": "function", "function": {"name": "submit_patch", "description": "Stages untracked file intents and captures git diff HEAD from /workspace.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_status", "description": "Returns live budget consumption and patch status.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_code_neighbors", "description": "Finds incoming and outgoing neighbors of a symbol in the repository call/dependency graph.",
     "parameters": {"type": "object", "properties": {"node": {"type": "string"}, "edge_type": {"type": "string"},
                                                      "max_neighbors": {"type": "integer"}}, "required": ["node"]}}},
    {"type": "function", "function": {"name": "search_similar_code", "description": "Finds top-k graph nodes with highest cosine similarity to query in the pre-computed embeddings.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_code_subgraph", "description": "Extracts the induced subgraph for a list of symbols.",
     "parameters": {"type": "object", "properties": {"nodes": {"type": "array", "items": {"type": "string"}}}, "required": ["nodes"]}}},
]

SYSTEM_PROMPT = ("You are an expert autonomous software engineer assigned to resolve an issue in a repository "
                 "efficiently and decisively. Work inside /workspace with the provided tools. Reproduce the problem "
                 "when practical, make a minimal fix in source files only (never edit existing tests or packaging/config "
                 "files), run the nearest existing tests, remove any scratch files you created, call submit_patch after "
                 "meaningful edits, and finish with a short text summary after submit_patch.")

# Existing test / config files: editing these conflicts with the hidden test_patch or gets reset by the grader.
PROTECTED_RE = re.compile(r"(^|/)(tests?|testing)/.*\.py$|(^|/)conftest\.py$|(^|/)pytest\.ini$|(^|/)pyproject\.toml$|(^|/)setup\.cfg$|(^|/)tox\.ini$|(^|/)setup\.py$")
# Scratch files agents typically create at the repo root; we teach the model to delete them before submit.
SCRATCH_RE = re.compile(r"^(?:[^/]+/)?(test_|tests_|reproduce|repro|check_|debug|verify|demo|tmp_|scratch|final_test|comprehensive|edge_case|minimal)[^/]*\.(py|sh|txt|json)$", re.I)
MAX_OBS_CHARS = 2000           # harness caps at 5000; 2000 keeps 8k-token windows feasible on T4
MAX_READ_LINES = 150
WINDOW_STEPS = 8               # tool steps per training window
KEEP_LAST_OBS = 5              # ADK compaction keeps last 5 events; everything earlier is summarised


def ok(**kw):  return json.dumps({"status": "ok", **kw}, ensure_ascii=False)
def err(t, m, details=None):
    d = {"status": "error", "error_type": t, "error_message": m}
    if details is not None: d["details"] = details
    return json.dumps(d, ensure_ascii=False)
def clip(s, n=MAX_OBS_CHARS):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n...[truncated {len(s)-n} chars]"


# ---- harness-exact initial prompt (swegemma 0.2.11 harness/agent_runner.py build_agent_prompt) ---------
BUDGET = {"time_minutes": 5.0, "tool_calls": 50, "turns": 80}     # what eval_config.yaml will declare
PRUNED_TOP_DIRS = ("docs", "docs_src", "tests", "test_data", "examples", "benchmarks", "assets", "imgs", "questions", "site", "g3doc", "google3")
INSTRUCTIONS = "\n".join([
    "## Instructions:",
    "0. All source code is under `/workspace`. Do NOT search outside `/workspace` (e.g. `/usr/`, `/wheels/`, system site-packages). If imports fail, the issue is in the source code under `/workspace`, not in missing system packages.",
    "1. Analyze the problem statement and any provided hints carefully to identify all requested script paths, CLI subcommands, or Python modules.",
    "2. Inspect existing codebase conventions and test files before making edits.",
    "3. Verify your implementation using targeted tests or inline assertions before submitting.",
    "4. Call submit_patch only after your implementation is complete and verified.",
    "5. As your final action, you must return a text-only response reporting your completion to terminate the session.",
])
GRAPH_BLOCK = ("## Code Intelligence Tools\n"
               "This repository has pre-built code graph and embedding data indexed by dotted symbol path (e.g. `pkg.module.Class.method`). Use these tools for fast, targeted navigation:\n"
               "- `search_similar_code(query)`: Find functions/classes with similar precomputed embeddings given a symbol name (e.g. `pkg.module.Class.method`, `Class.method`, or `func_name`).\n"
               "- `get_code_neighbors(node)`: Find callers and callees of a symbol node (e.g. `pkg.module.Class.method` or `Class.method`).\n"
               "- `get_code_subgraph(nodes)`: Get the induced call subgraph connecting a list of symbol nodes.\n")


def workspace_tree_from_paths(paths, max_lines=200):
    """Approximate the harness's `find . -maxdepth 3` listing from the files a trajectory touched
    (we do not have the real tree for external repos). Pruned dirs follow the harness."""
    entries = set()
    for p in paths:
        parts = [x for x in p.split("/") if x]
        if not parts or parts[0] in PRUNED_TOP_DIRS or any(x.startswith(".") or x == "__pycache__" for x in parts): continue
        for d in range(1, min(3, len(parts)) + 1):
            entries.add("./" + "/".join(parts[:d]))
    return "\n".join(sorted(entries)[:max_lines])


def build_user_prompt(repo, problem, touched_paths, with_graph):
    b = BUDGET
    parts = [f"You are evaluating a software engineering task for repository {repo}.\n\nProblem Statement:\n{problem}\n",
             "## Task Budget (Session terminates when any budget is exhausted)\n"
             f"- Time allowance: {b['time_minutes']} minutes\n- Tool calls allowance: {b['tool_calls']} calls\n- Max loop iterations: {b['turns']} turns\n",
             "## Execution Environment Rules\n"
             "- Single command timeout: 150 seconds (commands exceeding this fail without ending the session)\n"
             "- Command output limit: 5000 characters\n- File view limit: 150 lines per read_file call\n"
             "- File character limit: 10000 characters per read_file call\n"
             "- Environment is offline (no network/PyPI access). All repository and test dependencies are ALREADY pre-installed. Do NOT attempt to run pip install or download packages.\n",
             INSTRUCTIONS]
    if with_graph: parts.append(GRAPH_BLOCK)
    tree = workspace_tree_from_paths(touched_paths)
    if tree:
        parts.append("## Workspace Layout\nThe repository is located at `/workspace`. Here is the directory tree (up to 3 levels):\n```\n" + tree + "\n```\n")
    return "\n".join(parts)


def budget_warn(obs_json: str, used: int) -> str:
    """Mirror swegemma.tools.base._attach_low_budget_warning."""
    mx = BUDGET["tool_calls"]; rem = max(0, mx - used)
    if mx < 20 or rem > 10: return obs_json
    try:
        d = json.loads(obs_json)
        if isinstance(d, dict) and "budget_warning" not in d:
            d["budget_warning"] = f"Only {rem} tool call(s) remaining ({used}/{mx} used). Finalize your edits and call submit_patch soon."
            return json.dumps(d, ensure_ascii=False)
    except Exception:
        pass
    return obs_json


# ---- path / command normalisation ------------------------------------------------------------------
_REPO_DIR = {"name": None}   # per-trajectory workspace subdir (OpenHands uses /workspace/<owner>__<repo>__<ver>)


def norm_path(p: str) -> str:
    p = str(p or "")
    for pre in ("/workspace/", "/testbed/", "/repo/", "/app/"):
        if p.startswith(pre): p = p[len(pre):]
    p = p.lstrip("/")
    rd = _REPO_DIR["name"]
    if rd and (p == rd or p.startswith(rd + "/")):
        p = p[len(rd):].lstrip("/")
    if p in ("workspace", "testbed"): p = ""
    return p


def norm_command(cmd: str) -> str:
    rd = _REPO_DIR["name"]
    if rd:
        cmd = cmd.replace(f"/workspace/{rd}/", "/workspace/").replace(f"/workspace/{rd}", "/workspace")
    return cmd.replace("/testbed/", "/workspace/").replace("/testbed", "/workspace")


ISSUE_RE = re.compile(r"<issue_description>\s*(.*?)\s*</issue_description>", re.S)
UPLOAD_RE = re.compile(r"<uploaded_files>\s*/workspace/([^\s<]+)\s*</uploaded_files>")


def extract_problem(first_user: str) -> str:
    m = UPLOAD_RE.search(first_user or "")
    _REPO_DIR["name"] = m.group(1).strip("/") if m else None
    m = ISSUE_RE.search(first_user or "")
    text = m.group(1) if m else (first_user or "")
    text = re.sub(r"^\[ISSUE\]\s*", "", text.strip())
    text = re.sub(r"\s*\[/ISSUE\]\s*$", "", text)
    return text[:12000]


# ---- scaffold -> ADK mapping ---------------------------------------------------------------------
def map_call(name: str, args: dict):
    """OpenHands / SWE-agent function call -> (adk_tool, adk_args, kind) or None to drop the turn.
    kind in {"call", "dirview"}; dirview = directory listing expressed as run_command."""
    if name in ("execute_bash", "bash", "run_command", "execute_command"):
        cmd = args.get("command") or args.get("cmd") or ""
        if not isinstance(cmd, str) or not cmd.strip() or str(args.get("is_input", "false")).lower() == "true":
            return None
        return "run_command", {"command": norm_command(cmd)}, "call"
    if name in ("str_replace_editor", "str_replace_based_edit_tool", "file_editor"):
        cmd = args.get("command"); path = norm_path(args.get("path", ""))
        if cmd == "view":
            base = path.rsplit("/", 1)[-1]
            if path == "" or "." not in base:          # directory view -> ls
                return "run_command", {"command": f"ls -la {path or '.'}"}, "dirview"
            a = {"filepath": path}
            vr = args.get("view_range")
            if vr and isinstance(vr, list) and len(vr) == 2:
                s = int(vr[0]); e = int(vr[1])
                a.update(start_line=max(1, s), end_line=(e if e > 0 else s + MAX_READ_LINES - 1))
            return "read_file", a, "call"
        if cmd == "str_replace":
            return "edit_file", {"filepath": path, "old_string": args.get("old_str", ""), "new_string": args.get("new_str", "")}, "call"
        if cmd == "create":
            return "write_file", {"filepath": path, "content": args.get("file_text", "")}, "call"
        return None   # insert / undo_edit have no equivalent
    if name in ("finish", "submit", "submit_patch"):
        return "submit_patch", {}, "call"
    return None   # think, task_tracker, browser, ipython ...


_NUMBERED = re.compile(r"^\s*(\d+)\t(.*)$")


def _edit_diff(path, old, new):
    import difflib
    d = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{path}", f"b/{path}", n=2))
    return clip(d, 1500)


def to_adk_observation(tool: str, args: dict, raw: str, kind: str) -> str:
    """Tool results in the exact JSON shapes of swegemma 0.2.11 (README section 6)."""
    raw = raw or ""
    if tool == "read_file":
        lines = raw.splitlines(); nums = []; body = []
        for l in lines:
            m = _NUMBERED.match(l)           # OpenHands `cat -n` output -> raw lines (the harness returns raw content)
            if m: nums.append(int(m.group(1))); body.append(m.group(2))
            elif not l.startswith("Here's the result of running"): body.append(l)
        start = nums[0] if nums else int(args.get("start_line", 1)); end = start + len(body) - 1
        trunc = len(body) > MAX_READ_LINES
        if trunc: body = body[:MAX_READ_LINES]; end = start + MAX_READ_LINES - 1
        return ok(filepath=args["filepath"], content=clip("\n".join(body), 3000), start_line=start, end_line=end,
                  total_lines=max(end, args.get("end_line", end)), is_truncated=trunc)
    if tool == "run_command":
        m = re.search(r"\[Command finished with exit code (-?\d+)\]", raw)
        code = int(m.group(1)) if m else 0
        out = re.sub(r"\[Command finished with exit code -?\d+\]|\[The command completed.*?\]|\[Current working directory:.*?\]|\[Python interpreter:.*?\]|\[Command execution timed out.*?\]", "", raw, flags=re.S).strip()
        if code == 0: return ok(stdout=clip(out), stderr="", exit_code=0)
        return err("CommandError", clip(f"Command exited with code {code}", 200), {"stdout": clip(out), "stderr": "", "exit_code": code})
    if tool == "edit_file":
        if re.search(r"No replacement was performed|did not appear verbatim|Multiple occurrences|multiple", raw, re.I):
            return err("FileEditError", clip(raw, 500), {})
        return ok(filepath=args["filepath"], occurrences=1, strategy="exact",
                  diff=_edit_diff(args["filepath"], args.get("old_string", ""), args.get("new_string", "")), is_truncated=False)
    if tool == "write_file":
        return ok(filepath=args["filepath"], size=len(args.get("content", "").encode("utf-8")))
    if tool == "submit_patch":
        return ok(patch_size=1200, files_changed=1)
    return ok(result=clip(raw))


# ---- trajectory extraction -------------------------------------------------------------------------
def _from_openai_style(row, msgs):
    if not msgs: return
    if isinstance(msgs, str):
        try: msgs = json.loads(msgs)
        except Exception: return
    problem = None; steps = []; pending = None; dropped = 0; created = []
    _REPO_DIR["name"] = None
    for m in msgs:
        role = m.get("role")
        if role == "user" and problem is None:
            raw_user = m.get("content") if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
            problem = extract_problem(raw_user)
        elif role == "assistant":
            calls = m.get("tool_calls") or []
            thought = m.get("reasoning_content") or m.get("thinking") or ""
            text = m.get("content") if isinstance(m.get("content"), str) else ""
            if not calls:
                steps.append({"thought": thought, "text": text or "", "tool": None, "args": None, "observation": None}); pending = None; continue
            c = calls[0]; fn = c.get("function", c)
            a = fn.get("arguments") or {}
            if isinstance(a, str):
                try: a = json.loads(a)
                except Exception: a = {}
            mapped = map_call(fn.get("name", ""), a)
            if mapped is None: dropped += 1; pending = None; continue
            tool, args, kind = mapped
            fp = args.get("filepath", "")
            if tool == "edit_file" and PROTECTED_RE.search(fp): return          # edits an existing test/config file
            if tool == "write_file" and re.search(r"(^|/)(tests?|testing)/", fp): return   # adds files into the test tree
            if tool == "write_file": created.append(fp)
            # model text that duplicates the thought is common in OpenHands; keep it short
            pending = {"thought": thought, "text": (text or "")[:600], "tool": tool, "args": args, "observation": None, "kind": kind}
            steps.append(pending)
        elif role == "tool" and pending is not None:
            raw = m.get("content") if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
            pending["observation"] = to_adk_observation(pending["tool"], pending["args"], raw, pending.get("kind", "call")); pending = None
    if not problem or not steps: return
    # teach hygiene: delete scratch files before submitting, and always submit
    scratch = sorted({p for p in created if SCRATCH_RE.search(p) and not PROTECTED_RE.search(p)})
    steps = [s for s in steps if s["tool"] != "submit_patch"]
    if scratch:
        steps.append({"thought": "Clean up the scratch files I created so they do not end up in the patch.", "text": "",
                      "tool": "run_command", "args": {"command": "rm -f " + " ".join(scratch)}, "observation": ok(stdout="", stderr="", exit_code=0), "kind": "call"})
    steps.append({"thought": "", "text": "", "tool": "submit_patch", "args": {}, "observation": ok(patch_size=1200, files_changed=1), "kind": "call"})
    steps.append({"thought": "", "text": "Submitted the fix for the reported issue.", "tool": None, "args": None, "observation": None})
    yield {"instance_id": row.get("instance_id") or row.get("id") or "", "repo": row.get("repo", ""),
           "problem_statement": problem, "steps": steps, "resolved": bool(row.get("resolved", True)),
           "n_dropped_calls": dropped, "source_schema": SCHEMA_VERSION}


def iter_swe_hero(root):
    import pyarrow.parquet as pq
    for f in sorted(glob.glob(f"{root}/**/*.parquet", recursive=True)):
        pf = pq.ParquetFile(f)
        for rb in pf.iter_batches(batch_size=64):
            for row in rb.to_pylist():
                yield from _from_openai_style(row, row.get("trajectory") or row.get("messages"))


def iter_nebius(root):
    import pyarrow.parquet as pq
    for f in sorted(glob.glob(f"{root}/**/*.parquet", recursive=True)):
        pf = pq.ParquetFile(f)
        cols = [c for c in pf.schema_arrow.names if c != "tools"]
        for rb in pf.iter_batches(batch_size=64, columns=cols):
            for row in rb.to_pylist():
                if not row.get("resolved"): continue
                if row.get("exit_status") not in (None, "submit", "submitted"): continue
                yield from _from_openai_style(row, row.get("trajectory") or row.get("messages"))


SOURCES = {"swe-hero": ("datasets/swe-hero", iter_swe_hero), "nebius-openhands": ("datasets/nebius-openhands", iter_nebius)}


# ---- quality filters -------------------------------------------------------------------------------
def quality_ok(t, max_steps=48):
    # Declared budget is 50 tool calls (BUDGET); submit_patch is free and a cleanup `rm` may be appended,
    # so cap the teacher's own steps at 48. Shorter trajectories are preferred in main().
    steps = [s for s in t["steps"] if s["tool"]]
    if not (4 <= len(steps) <= max_steps): return False
    if t["n_dropped_calls"] > 0.25 * max(1, len(steps)): return False
    sig = [(s["tool"], json.dumps(s["args"], sort_keys=True)) for s in steps]
    for i in range(len(sig) - 1):
        if sig[i] == sig[i + 1]: return False            # identical consecutive calls = loop
    if not any(s["tool"] in ("edit_file", "write_file") for s in steps): return False
    # trajectories that end in a long error streak are unhelpful
    errs = sum(1 for s in steps[-6:] if s["observation"] and '"status": "error"' in s["observation"])
    return errs < 4


# ---- rendering: windowed, compaction-shaped samples ----------------------------------------------------
def summarize_prefix(steps):
    """Deterministic stand-in for ADK's LLM compaction summary: what happened before the visible window."""
    cmds = [s["args"]["command"] for s in steps if s["tool"] == "run_command"]
    reads = []; edits = []; writes = []
    for s in steps:
        if s["tool"] == "read_file" and s["args"]["filepath"] not in reads: reads.append(s["args"]["filepath"])
        if s["tool"] == "edit_file" and s["args"]["filepath"] not in edits: edits.append(s["args"]["filepath"])
        if s["tool"] == "write_file" and s["args"]["filepath"] not in writes: writes.append(s["args"]["filepath"])
    parts = [f"[Context summary of {len(steps)} earlier steps]"]
    if cmds: parts.append("Commands run (most recent last): " + "; ".join(c[:80] for c in cmds[-6:]))
    if reads: parts.append("Files read: " + ", ".join(reads[-10:]))
    if edits: parts.append("Files edited: " + ", ".join(edits))
    if writes: parts.append("Files created: " + ", ".join(writes))
    last_thought = next((s["thought"] for s in reversed(steps) if s.get("thought")), "")
    if last_thought: parts.append("Last reasoning: " + last_thought.strip().replace("\n", " ")[:400])
    return "\n".join(parts)


def window_samples(t):
    """Yield message lists. Window w covers tool steps [a, b); steps before a are summarised; the final
    trailing text turn is attached to the last window."""
    tool_steps = [s for s in t["steps"] if s["tool"]]
    tail_text = next((s for s in reversed(t["steps"]) if s["tool"] is None and s["text"]), None)
    touched = [s["args"]["filepath"] for s in tool_steps if s["tool"] in ("read_file", "edit_file", "write_file") and s["args"].get("filepath")]
    with_graph = (hash(t["instance_id"]) % 2 == 0)      # half the samples show the graph-tool paragraph (our agent may or may not declare them)
    header = [{"role": "system", "content": SYSTEM_PROMPT},
              {"role": "user", "content": build_user_prompt(t["repo"], t["problem_statement"], touched, with_graph)}]
    n = len(tool_steps)
    starts = list(range(0, n, WINDOW_STEPS))
    for a in starts:
        b = min(n, a + WINDOW_STEPS)
        msgs = list(header)
        if a > 0:
            msgs.append({"role": "user", "content": summarize_prefix(tool_steps[:a]) + "\n\nContinue from here using the tools."})
        for i in range(a, b):
            s = tool_steps[i]
            am = {"role": "assistant", "content": s["text"] or "",
                  "tool_calls": [{"type": "function", "id": f"c{i}", "function": {"name": s["tool"], "arguments": s["args"]}}]}
            if s["thought"]: am["reasoning_content"] = s["thought"][:1500]
            msgs.append(am)
            obs = s["observation"] or ok()
            if s["tool"] != "submit_patch": obs = budget_warn(obs, used=i + 1)      # submit_patch is free; others count
            if i < b - KEEP_LAST_OBS:      # inside the window but older than the last 5 events -> compacted
                obs = json.dumps({"status": "ok", "note": "[earlier output compacted]"})
            msgs.append({"role": "tool", "name": s["tool"], "tool_call_id": f"c{i}", "content": obs})
        if b == n and tail_text is not None:
            msgs.append({"role": "assistant", "content": tail_text["text"]})
        yield {"window": f"{a}-{b}", "messages": msgs}


# ---- tokenisation with exact span masking --------------------------------------------------------------
MODEL_OPEN, TURN_CLOSE = "<|turn>model\n", "<turn|>"
TR_OPEN, TR_CLOSE = "<|tool_response>", "<tool_response|>"


def label_spans(text):
    """Character spans to train on: inside <|turn>model ... <turn|> (inclusive of the closing token),
    minus tool-response spans. Returns list of (start, end)."""
    spans = []
    pos = 0
    while True:
        i = text.find(MODEL_OPEN, pos)
        if i < 0: break
        j = text.find(TURN_CLOSE, i)
        j = len(text) if j < 0 else j + len(TURN_CLOSE)
        seg_start = i + len(MODEL_OPEN); cur = seg_start
        while True:
            k = text.find(TR_OPEN, cur, j)
            if k < 0: spans.append((cur, j)); break
            spans.append((cur, k))
            kk = text.find(TR_CLOSE, k, j)
            cur = (kk + len(TR_CLOSE)) if kk >= 0 else j
            if cur >= j: break
        pos = j
    return [(a, b) for a, b in spans if b > a]


def fix_thoughts(msgs):
    """Teacher trajectories from non-thinking models have no reasoning; Gemma 4 runs with thinking ON in the
    harness (+20 points), so keep the thought channel alive: move a tool-calling turn's short plan text into
    reasoning_content when no reasoning exists. Turns with neither stay thought-free (the model learns thoughts
    are optional, not forbidden)."""
    out = []
    for m in msgs:
        if m.get("role") == "assistant" and m.get("tool_calls") and not m.get("reasoning_content") and (m.get("content") or "").strip():
            m = dict(m); m["reasoning_content"] = m["content"].strip()[:1200]; m["content"] = ""
        out.append(m)
    return out


def tokenize_file(paths, model_dir, max_len, out_dir):
    from transformers import AutoTokenizer
    import pyarrow as pa, pyarrow.parquet as pq
    tok = AutoTokenizer.from_pretrained(model_dir)
    rows = []; skipped = {"template": 0, "too_long": 0, "no_labels": 0}
    for p in paths:
        for line in open(p, encoding="utf-8"):
            t = json.loads(line); msgs = fix_thoughts(t["messages"])
            try:
                text = tok.apply_chat_template(msgs, tools=TOOLS, tokenize=False, enable_thinking=True)
            except Exception:
                skipped["template"] += 1; continue
            enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
            ids = enc["input_ids"]; offs = enc["offset_mapping"]
            if len(ids) > max_len: skipped["too_long"] += 1; continue
            spans = label_spans(text); labels = [-100] * len(ids)
            si = 0
            for ti, (cs, ce) in enumerate(offs):
                if ce <= cs: continue
                while si < len(spans) and spans[si][1] <= cs: si += 1
                if si < len(spans) and spans[si][0] <= cs and ce <= spans[si][1]: labels[ti] = ids[ti]
            if sum(1 for x in labels if x != -100) < 8: skipped["no_labels"] += 1; continue
            rows.append({"input_ids": ids, "labels": labels, "n": len(ids), "src": t.get("source", ""), "iid": t.get("instance_id", "")})
    os.makedirs(out_dir, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), f"{out_dir}/train.parquet")
    ns = sorted(r["n"] for r in rows); lab = sum(sum(1 for x in r["labels"] if x != -100) for r in rows)
    print(f"wrote {len(rows)} windows (skipped {skipped}); tokens median {ns[len(ns)//2] if ns else 0}, "
          f"p90 {ns[int(len(ns)*.9)] if ns else 0}, max {ns[-1] if ns else 0}, total {sum(ns):,}, supervised {lab:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=SOURCES.keys()); ap.add_argument("--max-examples", type=int, default=1500)
    ap.add_argument("--out"); ap.add_argument("--tokenize", nargs="*"); ap.add_argument("--model"); ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--scan-limit", type=int, default=0, help="stop after this many usable trajectories are found (0 = max_examples*3)")
    a = ap.parse_args()
    if a.tokenize:
        paths = [p for g in a.tokenize for p in glob.glob(g)]
        return tokenize_file(paths, a.model, a.max_len, a.out)
    root, it = SOURCES[a.source]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    limit = a.scan_limit or a.max_examples * 3
    cands = []; scanned = 0; rejected = 0
    for t in it(root):
        scanned += 1
        if not quality_ok(t): rejected += 1; continue
        t["_n"] = sum(1 for s in t["steps"] if s["tool"])
        cands.append(t)
        if len(cands) >= limit: break
    cands.sort(key=lambda t: (t["_n"], RNG.random()))
    n = 0; nw = 0; seen = {}; repos = {}
    with open(a.out, "w", encoding="utf-8") as f:
        for t in cands:
            if seen.get(t["instance_id"], 0) >= 2: continue
            if repos.get(t["repo"], 0) >= max(20, a.max_examples // 25): continue
            seen[t["instance_id"]] = seen.get(t["instance_id"], 0) + 1
            repos[t["repo"]] = repos.get(t["repo"], 0) + 1
            for w in window_samples(t):
                f.write(json.dumps({"source": a.source, "instance_id": t["instance_id"], "repo": t["repo"], "n_steps": t["_n"],
                                    "window": w["window"], "messages": w["messages"]}, ensure_ascii=False) + "\n"); nw += 1
            n += 1
            if n >= a.max_examples: break
    print(f"{a.source}: scanned {scanned} usable-or-not, rejected {rejected}, kept {n} trajectories -> {nw} windows "
          f"from {len(seen)} instances / {len(repos)} repos -> {a.out}")


if __name__ == "__main__":
    main()
