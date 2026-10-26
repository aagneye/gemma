#!/usr/bin/env python3
"""Build SFT data for the Gemma 4 Developer Agent harness: converts trajectories into the harness's ADK tool
schema, renders windowed, compaction-shaped samples under the header of a SHIPPED bundle (its system prompt,
tool list and eval_config budgets), and tokenizes them with the target model's own chat template using exact
span masking (loss on model turns only; tool responses and rejected turns are never trained on).

v3 (2026-10-25): header derived from a bundle directory (--bundle), harness-trace source (own resolved 31B runs,
parsed by convert_traces.py), re-rendering of already converted windows, error masking, thought caps, stats.json.

  # own resolved harness traces, split by repo for the cross-fit evaluation
  python prepare_data.py --source harness-trace --traces "scratch/kev_*_out/eval" --bundle submissions/v5_single \
      --split-by-repo --out datasets/traces_31b_v1
  # re-render previously converted OpenHands windows under the v5 header with the v5 filters
  python prepare_data.py --rerender datasets/sft_v4_mid/all.jsonl --bundle submissions/v5_single \
      --max-steps 24 --first-edit-by 10 --min-tests 1 --repo-cap 20 --out datasets/sft_v5_ext/mid.jsonl
  # raw corpora (unchanged path, now with the bundle header)
  python prepare_data.py --source nebius-openhands --bundle submissions/v5_single --max-examples 1500 --out datasets/x/nebius.jsonl
  # tokenize for a target model (E4B: thought cap 600 tokens; 31B: 1000)
  python prepare_data.py --tokenize datasets/traces_31b_v1/fastapi.jsonl --model models/gemma-4-E4B-it-qat-q4_0-unquantized \
      --max-len 7168 --thought-cap 600 --out datasets/traces_31b_v1/tok_e4b_7k_fastapi
"""
from __future__ import annotations
import argparse, collections, glob, json, os, random, re
from pathlib import Path

SCHEMA_VERSION = "adk-v3"
RNG = random.Random(0)
HERE = Path(__file__).resolve().parent

# ---- competition tool declarations ------------------------------------------------------------------
# vm/tool_declarations.json holds the declarations exactly as ADK's LiteLlm wrapper sends them to vLLM
# (dumped on the VM through FunctionTool._get_declaration + lite_llm._function_declaration_to_tool_param with the
# adk_submission reasoning patch applied). The inline list is the fallback when that file is missing.
TOOLS_FALLBACK = [
    {"type": "function", "function": {"name": "run_command", "description": "Execute a shell command inside the repository sandbox.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read the contents of a file from the repository workspace.",
     "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "start_line": {"nullable": True, "type": "integer"},
                                                      "end_line": {"nullable": True, "type": "integer"}}, "required": ["filepath"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace a contiguous block of text in an existing file.",
     "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "old_string": {"type": "string"},
                                                      "new_string": {"type": "string"}, "allow_multiple": {"default": False, "type": "boolean"}},
                    "required": ["filepath", "old_string", "new_string"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create or overwrite a file in the workspace.",
     "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["filepath", "content"]}}},
    {"type": "function", "function": {"name": "get_status", "description": "Check active budget details (time, tool calls) and active patch details.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "submit_patch", "description": "Capture the current working tree modifications as the agent's submission.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_code_neighbors", "description": "Discover structural code graph neighbors (callers and callees) for a given code node.",
     "parameters": {"type": "object", "properties": {"node": {"type": "string"}, "edge_type": {"nullable": True, "type": "string"},
                                                      "max_neighbors": {"default": 50, "type": "integer"}}, "required": ["node"]}}},
    {"type": "function", "function": {"name": "search_similar_code", "description": "Find semantically similar code functions and classes using precomputed graph embeddings.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"default": 10, "type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_code_subgraph", "description": "Extract the relationship graph (nodes and connecting edges) for a focal set of code elements.",
     "parameters": {"type": "object", "properties": {"nodes": {"items": {"type": "string"}, "type": "array"}}, "required": ["nodes"]}}},
]
GRAPH_TOOLS = ("get_code_neighbors", "search_similar_code", "get_code_subgraph")


def all_tool_declarations():
    p = HERE / "tool_declarations.json"
    if p.is_file():
        try: return json.load(open(p, encoding="utf-8"))
        except Exception: pass
    return TOOLS_FALLBACK


def tool_declarations(names):
    by = {t["function"]["name"]: t for t in all_tool_declarations()}
    return [by[n] for n in names if n in by]


# ---- shipped bundle = single source of truth for the training header ----------------------------------
class Bundle:
    """Reads agent.yaml (+ !include prompts), eval_config.yaml and configs/sampling.yaml of a submission directory."""
    HARNESS = {"max_stdout_chars": 5000, "max_file_lines": 150, "max_file_chars": 10000}   # swegemma defaults (seen in every trace)

    def __init__(self, d):
        import yaml
        self.dir = Path(d)
        class L(yaml.SafeLoader): pass
        base = self.dir
        def inc(loader, node):
            rel = loader.construct_scalar(node); return (base / rel).read_text(encoding="utf-8")
        L.add_constructor("!include", inc)
        ag = yaml.load((self.dir / "agent.yaml").read_text(encoding="utf-8"), Loader=L) or {}
        if "instruction" not in ag and ag.get("sub_agents"):          # workflow agent: take the first sub-agent's header
            sub = ag["sub_agents"][0]["config_path"]; base = (self.dir / sub).parent
            ag = yaml.load((self.dir / sub).read_text(encoding="utf-8"), Loader=L) or {}
        self.name = ag.get("name", "swe_agent"); self.model = ag.get("model", "")
        self.system_prompt = str(ag.get("instruction", "")).strip()
        self.tools = list(ag.get("tools") or ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch"])
        ev = {}
        for n in ("eval_config.yaml", "eval_config.yml"):
            p = self.dir / n
            if p.is_file(): raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}; ev = raw.get("evaluation", raw); break
        self.budget = {"time_minutes": float(ev.get("max_time_minutes", 8.0)), "tool_calls": int(ev.get("max_tool_calls", 28)),
                       "turns": int(ev.get("max_turns", ev.get("max_llm_calls", 80)))}
        self.timeout_seconds = int(ev.get("timeout_seconds", 300))
        gc = ag.get("generate_content_config") or {}
        if isinstance(gc, str): gc = yaml.safe_load(gc) or {}
        self.thinking_budget = int(((gc.get("thinking_config") or {}).get("thinking_budget")) or 0)
        self.temperature = gc.get("temperature")

    def describe(self):
        return {"dir": str(self.dir), "model": self.model, "tools": self.tools, "budget": self.budget, "timeout_seconds": self.timeout_seconds,
                "thinking_budget": self.thinking_budget, "temperature": self.temperature, "system_prompt_chars": len(self.system_prompt)}

    def has_graph_tools(self): return any(t in self.tools for t in GRAPH_TOOLS)


# Existing test / config files: editing these conflicts with the hidden test_patch or gets reset by the grader.
PROTECTED_RE = re.compile(r"(^|/)(tests?|testing)/.*\.py$|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|(^|/)pytest\.ini$|(^|/)pyproject\.toml$|(^|/)setup\.cfg$|(^|/)tox\.ini$|(^|/)setup\.py$")
# Scratch files agents typically create at the repo root; we teach the model to delete them before submit.
SCRATCH_RE = re.compile(r"^(?:[^/]+/)?(test_|tests_|reproduce|repro|check_|debug|verify|demo|tmp_|scratch|final_test|comprehensive|edge_case|minimal)[^/]*\.(py|sh|txt|json)$", re.I)
MAX_OBS_CHARS = 2000           # harness caps at 5000; 2000 keeps 7k-token windows feasible on T4
MAX_READ_LINES = 150
WINDOW_STEPS = 8               # tool steps per training window
KEEP_LAST_OBS = 5              # ADK compaction keeps last 5 events; everything earlier is summarised
MASK_ERROR_TYPES = {"FileEditError", "FileWriteError", "FileReadError", "ValueError", "BudgetExceeded"}
BUDGET_FREE = {"submit_patch", "get_status"}   # the harness does not count these against max_tool_calls (tools/execution.py)


def ok(**kw):  return json.dumps({"status": "ok", **kw}, ensure_ascii=False)
def err(t, m, details=None):
    d = {"status": "error", "error_type": t, "error_message": m}
    if details is not None: d["details"] = details
    return json.dumps(d, ensure_ascii=False)
def clip(s, n=MAX_OBS_CHARS):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n...[truncated {len(s)-n} chars]"


# ---- harness-exact initial prompt (swegemma 0.2.11 harness/agent_runner.py build_agent_prompt) ---------
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
GRAPH_LINES = {"search_similar_code": "- `search_similar_code(query)`: Find functions/classes with similar precomputed embeddings given a symbol name (e.g. `pkg.module.Class.method`, `Class.method`, or `func_name`).",
               "get_code_neighbors": "- `get_code_neighbors(node)`: Find callers and callees of a symbol node (e.g. `pkg.module.Class.method` or `Class.method`).",
               "get_code_subgraph": "- `get_code_subgraph(nodes)`: Get the induced call subgraph connecting a list of symbol nodes."}
GRAPH_HEAD = ("## Code Intelligence Tools\n"
              "This repository has pre-built code graph and embedding data indexed by dotted symbol path (e.g. `pkg.module.Class.method`). Use these tools for fast, targeted navigation:\n")


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


def budget_block(b: Bundle):
    bb = b.budget; h = b.HARNESS
    return ("## Task Budget (Session terminates when any budget is exhausted)\n"
            f"- Time allowance: {bb['time_minutes']} minutes\n- Tool calls allowance: {bb['tool_calls']} calls\n- Max loop iterations: {bb['turns']} turns\n",
            "## Execution Environment Rules\n"
            f"- Single command timeout: {b.timeout_seconds} seconds (commands exceeding this fail without ending the session)\n"
            f"- Command output limit: {h['max_stdout_chars']} characters\n- File view limit: {h['max_file_lines']} lines per read_file call\n"
            f"- File character limit: {h['max_file_chars']} characters per read_file call\n"
            "- Environment is offline (no network/PyPI access). All repository and test dependencies are ALREADY pre-installed. Do NOT attempt to run pip install or download packages.\n")


def build_user_prompt(b: Bundle, repo, problem, touched_paths):
    tb, eb = budget_block(b)
    parts = [f"You are evaluating a software engineering task for repository {repo}.\n\nProblem Statement:\n{problem}\n", tb, eb, INSTRUCTIONS]
    lines = [GRAPH_LINES[t] for t in GRAPH_LINES if t in b.tools]
    if lines: parts.append(GRAPH_HEAD + "\n".join(lines) + "\n")
    tree = workspace_tree_from_paths(touched_paths)
    if tree:
        parts.append("## Workspace Layout\nThe repository is located at `/workspace`. Here is the directory tree (up to 3 levels):\n```\n" + tree + "\n```\n")
    return "\n".join(parts)


_BUDGET_LINES = [(re.compile(r"^- Time allowance: .*$", re.M), lambda b: f"- Time allowance: {b.budget['time_minutes']} minutes"),
                 (re.compile(r"^- Tool calls allowance: .*$", re.M), lambda b: f"- Tool calls allowance: {b.budget['tool_calls']} calls"),
                 (re.compile(r"^- Max loop iterations: .*$", re.M), lambda b: f"- Max loop iterations: {b.budget['turns']} turns"),
                 (re.compile(r"^- Single command timeout: .*$", re.M), lambda b: f"- Single command timeout: {b.timeout_seconds} seconds (commands exceeding this fail without ending the session)")]
_GRAPH_BLOCK_RE = re.compile(r"## Code Intelligence Tools\n.*?(?=\n## |\Z)", re.S)


def rerender_task_prompt(b: Bundle, text: str) -> str:
    """Re-render a harness task prompt (from a trace or an earlier conversion) under the bundle's budgets/tools."""
    for rx, fn in _BUDGET_LINES: text = rx.sub(fn(b), text, count=1)
    if not b.has_graph_tools(): text = _GRAPH_BLOCK_RE.sub("", text).replace("\n\n\n## Workspace", "\n\n## Workspace")
    return text


def budget_warn(b: Bundle, obs_json: str, used: int) -> str:
    """Mirror swegemma.tools.base._attach_low_budget_warning for the bundle's call cap (strips any older warning)."""
    mx = b.budget["tool_calls"]; rem = max(0, mx - used)
    try: d = json.loads(obs_json)
    except Exception: return obs_json
    if not isinstance(d, dict): return obs_json
    d.pop("budget_warning", None)
    if mx >= 20 and rem <= 10:
        d["budget_warning"] = f"Only {rem} tool call(s) remaining ({used}/{mx} used). Finalize your edits and call submit_patch soon."
    return json.dumps(d, ensure_ascii=False)


def masked_observation(tool, content, declared):
    """True when the model turn that produced `content` must not be trained on (tool rejection)."""
    if declared and tool not in declared: return True
    if not content or not content.startswith("{"): return False
    try: o = json.loads(content)
    except Exception: return False
    if o.get("status") == "error": return o.get("error_type") in MASK_ERROR_TYPES
    return "status" not in o and "error" in o


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
    """OpenHands / SWE-agent function call -> (adk_tool, adk_args, kind) or None to drop the turn."""
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


# ---- trajectory extraction (external corpora) ----------------------------------------------------------
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
            pending = {"thought": thought, "text": (text or "")[:600], "tool": tool, "args": args, "observation": None, "kind": kind}
            steps.append(pending)
        elif role == "tool" and pending is not None:
            raw = m.get("content") if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
            pending["observation"] = to_adk_observation(pending["tool"], pending["args"], raw, pending.get("kind", "call")); pending = None
    if not problem or not steps: return
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


# ---- own harness traces -> canonical trajectories ----------------------------------------------------------
def iter_harness_traces(pattern, b: Bundle, max_calls, per_task, teacher):
    import convert_traces as CT
    episodes, stats = CT.collect(pattern, max_calls=max_calls, per_task=per_task, teacher=teacher, declared=set(b.tools))
    for e in episodes:
        steps = []
        for t in e["turns"]:
            thought = t["thought"]
            if t["text"]:            # visible text before a call: the canonical template would render it after the tool
                thought = (thought + "\n\n" + t["text"]).strip() if thought else t["text"]   # response, so fold it into the thought
            steps.append({"thought": thought, "text": "", "tool": t["tool"], "args": t["args"], "observation": t["obs"],
                          "masked": bool(t["masked"]), "kind": "call"})
        steps.append({"thought": e["final_thought"], "text": e["final_text"], "tool": None, "args": None, "observation": None})
        yield {"instance_id": e["instance_id"], "repo": e["repo"], "task_prompt": rerender_task_prompt(b, e["task_prompt"]),
               "steps": steps, "resolved": True, "n_dropped_calls": 0, "source_schema": SCHEMA_VERSION, "run": e["run"],
               "n_calls": e["n_calls"], "n_masked": e["n_masked"]}
    iter_harness_traces.stats = dict(stats)


# ---- quality filters (external corpora) -------------------------------------------------------------------
def quality_ok(t, max_steps=48):
    steps = [s for s in t["steps"] if s["tool"]]
    if not (4 <= len(steps) <= max_steps): return False
    if t["n_dropped_calls"] > 0.25 * max(1, len(steps)): return False
    sig = [(s["tool"], json.dumps(s["args"], sort_keys=True)) for s in steps]
    for i in range(len(sig) - 1):
        if sig[i] == sig[i + 1]: return False            # identical consecutive calls = loop
    if not any(s["tool"] in ("edit_file", "write_file") for s in steps): return False
    errs = sum(1 for s in steps[-6:] if s["observation"] and '"status": "error"' in s["observation"])
    return errs < 4


# ---- rendering: windowed, compaction-shaped samples ----------------------------------------------------
def summarize_prefix(steps):
    """Deterministic stand-in for ADK's LLM compaction summary: what happened before the visible window."""
    cmds = [str(s["args"].get("command", "")) for s in steps if s["tool"] == "run_command" and isinstance(s["args"], dict)]
    reads = []; edits = []; writes = []
    for s in steps:
        fp = s["args"].get("filepath") if isinstance(s["args"], dict) else None     # rejected calls may lack it
        if not fp: continue
        if s["tool"] == "read_file" and fp not in reads: reads.append(fp)
        if s["tool"] == "edit_file" and fp not in edits: edits.append(fp)
        if s["tool"] == "write_file" and fp not in writes: writes.append(fp)
    parts = [f"[Context summary of {len(steps)} earlier steps]"]
    if cmds: parts.append("Commands run (most recent last): " + "; ".join(c[:80] for c in cmds[-6:]))
    if reads: parts.append("Files read: " + ", ".join(reads[-10:]))
    if edits: parts.append("Files edited: " + ", ".join(edits))
    if writes: parts.append("Files created: " + ", ".join(writes))
    last_thought = next((s["thought"] for s in reversed(steps) if s.get("thought")), "")
    if last_thought: parts.append("Last reasoning: " + last_thought.strip().replace("\n", " ")[:400])
    return "\n".join(parts)


def window_samples(t, b: Bundle):
    """Yield message lists. Window w covers tool steps [a, b); steps before a are summarised; the final
    trailing text turn is attached to the last window. Assistant messages carry train=False when masked."""
    tool_steps = [s for s in t["steps"] if s["tool"]]
    tail = next((s for s in reversed(t["steps"]) if s["tool"] is None and s["text"]), None)
    if "task_prompt" in t: user = t["task_prompt"]
    else:
        touched = [s["args"]["filepath"] for s in tool_steps if s["tool"] in ("read_file", "edit_file", "write_file") and s["args"].get("filepath")]
        user = build_user_prompt(b, t["repo"], t["problem_statement"], touched)
    header = [{"role": "system", "content": b.system_prompt}, {"role": "user", "content": user}]
    n = len(tool_steps)
    for a in range(0, n, WINDOW_STEPS):
        bb = min(n, a + WINDOW_STEPS)
        msgs = list(header)
        if a > 0:
            msgs.append({"role": "user", "content": summarize_prefix(tool_steps[:a]) + "\n\nContinue from here using the tools."})
        for i in range(a, bb):
            s = tool_steps[i]
            am = {"role": "assistant", "content": s["text"] or "",
                  "tool_calls": [{"type": "function", "id": f"c{i}", "function": {"name": s["tool"], "arguments": s["args"]}}]}
            if s["thought"]: am["reasoning_content"] = s["thought"]
            obs = s["observation"] if s["observation"] is not None else ok()
            # mask rejected turns from the full observation here, before compaction hides it (all sources, not only traces)
            if s.get("masked") or masked_observation(s["tool"], obs, set(b.tools)): am["train"] = False
            msgs.append(am)
            if s["tool"] not in BUDGET_FREE: obs = budget_warn(b, obs, used=sum(1 for k in range(i + 1) if tool_steps[k]["tool"] not in BUDGET_FREE))
            if i < bb - KEEP_LAST_OBS:      # inside the window but older than the last 5 events -> compacted
                obs = json.dumps({"status": "ok", "note": "[earlier output compacted]"})
            msgs.append({"role": "tool", "name": s["tool"], "tool_call_id": f"c{i}", "content": obs})
        if bb == n and tail is not None:
            fm = {"role": "assistant", "content": tail["text"]}
            if tail.get("thought"): fm["reasoning_content"] = tail["thought"]
            msgs.append(fm)
        yield {"window": f"{a}-{bb}", "messages": msgs}


def write_rows(f, t, source, b: Bundle, counters):
    nw = 0
    for w in window_samples(t, b):
        f.write(json.dumps({"source": source, "instance_id": t["instance_id"], "repo": t["repo"], "n_steps": t.get("n_calls", sum(1 for s in t["steps"] if s["tool"])),
                            "window": w["window"], "tools": b.tools, "run": t.get("run", ""), "messages": w["messages"]}, ensure_ascii=False) + "\n")
        nw += 1
        counters["masked_turns"] += sum(1 for m in w["messages"] if m.get("role") == "assistant" and m.get("train") is False)
    return nw


def write_stats(path, stats):
    json.dump(stats, open(path, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print(f"stats -> {path}")


# ---- re-render previously converted windows under a new header ----------------------------------------------
def rerender(paths, b: Bundle, out, max_steps, first_edit_by, min_tests, repo_cap, exclude_repos, per_instance, cap_steps=0):
    """Group windows by trajectory, apply the trajectory filters, rewrite system/user headers, budget warnings and
    masking, and write the surviving windows. Windows are truncated at the bundle's call cap (cap_steps, default =
    max_tool_calls): nothing after call #cap is shown, so no window ever runs past the budget the model will have."""
    cap_steps = cap_steps or b.budget["tool_calls"]
    traj = collections.OrderedDict(); stats = collections.Counter()
    for p in paths:
        for line in open(p, encoding="utf-8"):
            r = json.loads(line); key = (r.get("source"), r["instance_id"], r["n_steps"])
            traj.setdefault(key, []).append(r)
    test_re = re.compile(r"pytest|unittest|python3? (-c|-m|\S+\.py)")
    kept = []; repos = collections.Counter(); inst = collections.Counter()
    for key, rows in traj.items():
        rows.sort(key=lambda r: int(r["window"].split("-")[0]))
        repo = rows[0]["repo"]
        if any(x.lower() in repo.lower() for x in exclude_repos): stats["excluded_repo"] += 1; continue
        n_steps = rows[0]["n_steps"]
        if n_steps > max_steps: stats["too_long"] += 1; continue
        calls = []
        for r in rows:
            a0 = int(r["window"].split("-")[0]); k = 0
            for m in r["messages"]:
                if m.get("role") == "assistant" and m.get("tool_calls"):
                    fn = m["tool_calls"][0]["function"]; calls.append((a0 + k, fn["name"], fn["arguments"])); k += 1
        first_edit = next((i for i, nm, _ in calls if nm in ("edit_file", "write_file")), None)
        if first_edit is None: stats["no_edit"] += 1; continue
        if first_edit + 1 > first_edit_by: stats["late_first_edit"] += 1; continue
        tests = sum(1 for _, nm, ar in calls if nm == "run_command" and test_re.search(str(ar.get("command", ""))))
        if tests < min_tests: stats["no_test_command"] += 1; continue
        if repos[repo] >= repo_cap: stats["repo_cap"] += 1; continue
        if inst[key[1]] >= per_instance: stats["instance_cap"] += 1; continue
        repos[repo] += 1; inst[key[1]] += 1; kept.append((key, rows))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    nw = 0; masked = 0; per_repo = collections.Counter()
    with open(out, "w", encoding="utf-8") as f:
        for key, rows in kept:
            # A trajectory that would run past the call cap never submits within it; from call cap-10 its turns would be
            # shown with budget warnings while the teacher keeps exploring, which teaches ignoring the warning. Cut such
            # trajectories at cap-10 (before the first warning) and keep only the prefix; trajectories that fit within
            # the cap keep everything, including their warned-but-finishing turns.
            n_total = rows[0]["n_steps"]
            cut_at = cap_steps if n_total <= cap_steps else cap_steps - 10
            if n_total > cap_steps: stats["trajectories_cut_before_warning"] += 1
            for r in rows:
                a0 = int(r["window"].split("-")[0]); used = a0; msgs = []; prev_asst = None; truncated = False
                if a0 >= cut_at: stats["windows_past_cap"] += 1; continue
                for m in r["messages"]:
                    m = dict(m)
                    if m["role"] == "system": m["content"] = b.system_prompt
                    elif m["role"] == "user" and not msgs[1:]:
                        m["content"] = rerender_task_prompt(b, m["content"])
                    elif m["role"] == "assistant" and m.get("tool_calls"):
                        if used >= cut_at and m["tool_calls"][0]["function"]["name"] not in BUDGET_FREE:
                            truncated = True; break                       # the budget (or the pre-warning cut) ends the session here
                        prev_asst = m
                        if m["tool_calls"][0]["function"]["name"] not in BUDGET_FREE: used += 1
                    elif m["role"] == "assistant" and truncated: break
                    elif m["role"] == "tool":
                        c = m["content"]
                        if prev_asst is not None:
                            if prev_asst.get("train") is False: masked += 1          # masked at conversion time (kept)
                            elif masked_observation(prev_asst["tool_calls"][0]["function"]["name"], c, set(b.tools)): prev_asst["train"] = False; masked += 1
                            if prev_asst["tool_calls"][0]["function"]["name"] not in BUDGET_FREE and not c.startswith('{"status": "ok", "note"'):
                                m["content"] = budget_warn(b, c, used)
                    msgs.append(m)
                if truncated:
                    stats["windows_truncated_at_cap"] += 1
                    while msgs and msgs[-1]["role"] != "tool": msgs.pop()      # end on a tool response, like a live session
                if not any(m["role"] == "assistant" for m in msgs): continue
                r["messages"] = msgs; r["tools"] = b.tools; r["rerendered_from"] = os.path.basename(out)
                f.write(json.dumps(r, ensure_ascii=False) + "\n"); nw += 1; per_repo[r["repo"]] += 1
    stats.update({"trajectories_in": len(traj), "kept_trajectories": len(kept), "windows": nw, "masked_turns": masked, "repos": len(repos), "cap_steps": cap_steps})
    print(f"rerender: {dict(stats)} -> {out}")
    write_stats(os.path.join(os.path.dirname(out) or ".", os.path.basename(out).rsplit(".", 1)[0] + ".stats.json"),
                {"filter_stats": dict(stats), "per_repo_windows": dict(per_repo), "bundle": b.describe(), "inputs": paths,
                 "filters": {"max_steps": max_steps, "first_edit_by": first_edit_by, "min_tests": min_tests, "repo_cap": repo_cap, "exclude_repos": exclude_repos}})


# ---- tokenisation with exact span masking --------------------------------------------------------------
MODEL_OPEN, TURN_CLOSE = "<|turn>model\n", "<turn|>"
TR_OPEN, TR_CLOSE = "<|tool_response>", "<tool_response|>"


def model_pieces(text):
    """Character pieces of the model turns, one per assistant message: a tool-calling message ends where its
    tool response starts; the closing text piece ends after <turn|>. Tool responses are never included."""
    pieces = []; pos = 0
    while True:
        i = text.find(MODEL_OPEN, pos)
        if i < 0: break
        j = text.find(TURN_CLOSE, i)
        j = len(text) if j < 0 else j + len(TURN_CLOSE)
        cur = i + len(MODEL_OPEN)
        while cur < j:
            k = text.find(TR_OPEN, cur, j)
            if k < 0: pieces.append((cur, j)); break
            # include the <|tool_response> token: it is the EOS the model must GENERATE to end a tool-call turn
            # (generation_config eos_token_id includes it), so it needs a supervised target like <turn|> does
            pieces.append((cur, k + len(TR_OPEN)))
            kk = text.find(TR_CLOSE, k, j)
            cur = (kk + len(TR_CLOSE)) if kk >= 0 else j
        pos = j
    return pieces


def fix_thoughts(msgs):
    """Teacher trajectories from non-thinking models have no reasoning; Gemma 4 runs with thinking ON in the
    harness, so keep the thought channel alive: move a tool-calling turn's plan text into reasoning_content
    when no reasoning exists (the canonical template would otherwise render that text after the tool response)."""
    out = []
    for m in msgs:
        if m.get("role") == "assistant" and m.get("tool_calls") and (m.get("content") or "").strip():
            m = dict(m)
            m["reasoning_content"] = ((m.get("reasoning_content") or "").strip() + "\n\n" + m["content"].strip()).strip()[:6000] if m.get("reasoning_content") else m["content"].strip()[:1200]
            m["content"] = ""
        out.append(m)
    return out


_SENT_END = re.compile(r"(?<=[.!?:])\s+|\n+")


def cap_thought(text, cap, tok):
    """Keep the tail of an over-long thought (the conclusion and the plan), cut at a sentence boundary."""
    if not text or cap <= 0: return text, False
    n = len(tok(text, add_special_tokens=False)["input_ids"])
    if n <= cap: return text, False
    parts = [p for p in _SENT_END.split(text) if p and p.strip()]
    keep = []; total = 0
    for p in reversed(parts):
        k = len(tok(p, add_special_tokens=False)["input_ids"]) + 1
        if total + k > cap: break
        keep.append(p); total += k
    if not keep:                       # a single huge sentence: hard cut on tokens
        ids = tok(text, add_special_tokens=False)["input_ids"][-cap:]
        return tok.decode(ids), True
    return "\n".join(reversed(keep)), True


def tokenize_file(paths, model_dir, max_len, out_dir, thought_cap=0, tools_default=None):
    from transformers import AutoTokenizer
    import pyarrow as pa, pyarrow.parquet as pq
    tok = AutoTokenizer.from_pretrained(model_dir)
    rows = []; skipped = collections.Counter(); masked_pieces = 0; piece_mismatch = 0; capped = 0; thought_tokens = []
    per_repo = collections.defaultdict(lambda: collections.Counter())
    for p in paths:
        for line in open(p, encoding="utf-8"):
            t = json.loads(line); msgs = fix_thoughts(t["messages"])
            if thought_cap:
                for m in msgs:
                    if m.get("role") == "assistant" and m.get("reasoning_content"):
                        m["reasoning_content"], c = cap_thought(m["reasoning_content"], thought_cap, tok); capped += c
                        thought_tokens.append(len(tok(m["reasoning_content"], add_special_tokens=False)["input_ids"]))
            tools = tool_declarations(t.get("tools") or tools_default or [x["function"]["name"] for x in TOOLS_FALLBACK])
            try:
                text = tok.apply_chat_template(msgs, tools=tools, tokenize=False, enable_thinking=True)
            except Exception:
                skipped["template"] += 1; continue
            enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
            ids = enc["input_ids"]; offs = enc["offset_mapping"]
            if len(ids) > max_len: skipped["too_long"] += 1; continue
            pieces = model_pieces(text)
            flags = [m.get("train", True) for m in msgs if m.get("role") == "assistant"]
            if len(pieces) == len(flags):
                spans = [pc for pc, fl in zip(pieces, flags) if fl]; masked_pieces += len(pieces) - len(spans)
            else:
                piece_mismatch += 1; spans = pieces
            labels = [-100] * len(ids); si = 0
            for ti, (cs, ce) in enumerate(offs):
                if ce <= cs: continue
                while si < len(spans) and spans[si][1] <= cs: si += 1
                if si < len(spans) and spans[si][0] <= cs and ce <= spans[si][1]: labels[ti] = ids[ti]
            nsup = sum(1 for x in labels if x != -100)
            if nsup < 8: skipped["no_labels"] += 1; continue
            repo = t.get("repo", "")
            rows.append({"input_ids": ids, "labels": labels, "n": len(ids), "src": t.get("source", ""), "iid": t.get("instance_id", ""), "repo": repo})
            pr = per_repo[repo]; pr["windows"] += 1; pr["tokens"] += len(ids); pr["supervised"] += nsup
    os.makedirs(out_dir, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), f"{out_dir}/train.parquet")
    ns = sorted(r["n"] for r in rows); lab = sum(sum(1 for x in r["labels"] if x != -100) for r in rows)
    st = {"windows": len(rows), "skipped": dict(skipped), "tokens": sum(ns), "supervised_tokens": lab, "tokens_median": ns[len(ns)//2] if ns else 0,
          "tokens_p90": ns[int(len(ns)*.9)] if ns else 0, "tokens_max": ns[-1] if ns else 0, "masked_pieces": masked_pieces, "piece_mismatch": piece_mismatch,
          "thoughts_capped": capped, "thought_tokens_median": sorted(thought_tokens)[len(thought_tokens)//2] if thought_tokens else None,
          "thought_cap": thought_cap, "max_len": max_len, "model": str(model_dir), "inputs": paths,
          "per_repo": {k: dict(v) for k, v in per_repo.items()}, "tasks": sorted({r["iid"] for r in rows})}
    print(f"wrote {len(rows)} windows (skipped {dict(skipped)}); tokens median {st['tokens_median']}, p90 {st['tokens_p90']}, max {st['tokens_max']}, "
          f"total {st['tokens']:,}, supervised {lab:,}; masked pieces {masked_pieces}, piece mismatches {piece_mismatch}, thoughts capped {capped}")
    write_stats(f"{out_dir}/stats.json", st)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", help="submission directory whose prompt/tools/budgets define the training header (required for conversion)")
    ap.add_argument("--source", choices=list(SOURCES) + ["harness-trace"]); ap.add_argument("--max-examples", type=int, default=1500)
    ap.add_argument("--out"); ap.add_argument("--tokenize", nargs="*"); ap.add_argument("--model"); ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--thought-cap", type=int, default=0, help="max thought tokens at tokenisation (E4B 600, 31B 1000; 0 = unlimited)")
    ap.add_argument("--scan-limit", type=int, default=0, help="stop after this many usable trajectories are found (0 = max_examples*3)")
    # harness-trace source
    ap.add_argument("--traces", default="scratch/kev_*_out/eval"); ap.add_argument("--max-calls", type=int, default=24)
    ap.add_argument("--per-task", type=int, default=3); ap.add_argument("--teacher", default="31b")
    ap.add_argument("--split-by-repo", action="store_true", help="write <out>/all.jsonl plus one jsonl per repo (cross-fit splits)")
    # rerender
    ap.add_argument("--rerender", nargs="*", help="jsonl window files to re-render under --bundle")
    ap.add_argument("--max-steps", type=int, default=24); ap.add_argument("--first-edit-by", type=int, default=10); ap.add_argument("--min-tests", type=int, default=1)
    ap.add_argument("--repo-cap", type=int, default=20); ap.add_argument("--per-instance", type=int, default=2)
    ap.add_argument("--cap-steps", type=int, default=0, help="truncate re-rendered windows at this call number (0 = the bundle's max_tool_calls)")
    ap.add_argument("--exclude-repos", default="fastapi/fastapi,Textualize/rich", help="comma-separated repo names never used for training (public task repos)")
    a = ap.parse_args()
    if a.tokenize:
        paths = [p for g in a.tokenize for p in glob.glob(g)]
        return tokenize_file(paths, a.model, a.max_len, a.out, a.thought_cap)
    b = Bundle(a.bundle); print("bundle:", json.dumps(b.describe()))
    if a.rerender:
        paths = [p for g in a.rerender for p in glob.glob(g)]
        return rerender(paths, b, a.out, a.max_steps, a.first_edit_by, a.min_tests, a.repo_cap, [x for x in a.exclude_repos.split(",") if x], a.per_instance, a.cap_steps)
    counters = collections.Counter()
    if a.source == "harness-trace":
        os.makedirs(a.out, exist_ok=True)
        eps = list(iter_harness_traces(a.traces, b, a.max_calls, a.per_task, a.teacher)); fstats = iter_harness_traces.stats
        groups = {"all": eps}
        if a.split_by_repo:
            for e in eps: groups.setdefault(e["instance_id"].split("_")[0], []).append(e)
        stats = {"filter_stats": fstats, "bundle": b.describe(), "traces": a.traces, "splits": {}}
        for name, group in groups.items():
            nw = 0; per_repo = collections.Counter(); per_repo_w = collections.Counter()
            with open(os.path.join(a.out, f"{name}.jsonl"), "w", encoding="utf-8") as f:
                for t in group:
                    w = write_rows(f, t, "harness-trace", b, counters); nw += w
                    per_repo[t["repo"]] += 1; per_repo_w[t["repo"]] += w
            stats["splits"][name] = {"episodes": len(group), "windows": nw, "per_repo_episodes": dict(per_repo), "per_repo_windows": dict(per_repo_w),
                                     "task_ids": sorted({t["instance_id"] for t in group}), "runs": dict(collections.Counter(t["run"] for t in group)),
                                     "calls": sorted(t["n_calls"] for t in group)}
            print(f"split {name}: {len(group)} episodes -> {nw} windows; repos {dict(per_repo)}")
        stats["masked_turns"] = counters["masked_turns"]
        return write_stats(os.path.join(a.out, "stats.json"), stats)
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
            nw += write_rows(f, t, a.source, b, counters); n += 1
            if n >= a.max_examples: break
    print(f"{a.source}: scanned {scanned} usable-or-not, rejected {rejected}, kept {n} trajectories -> {nw} windows "
          f"from {len(seen)} instances / {len(repos)} repos -> {a.out}")
    write_stats(a.out.rsplit(".", 1)[0] + ".stats.json", {"source": a.source, "scanned": scanned, "rejected": rejected, "trajectories": n, "windows": nw,
                                                          "instances": len(seen), "repos": len(repos), "masked_turns": counters["masked_turns"], "bundle": b.describe()})


if __name__ == "__main__":
    main()
