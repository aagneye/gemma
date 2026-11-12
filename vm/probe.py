#!/usr/bin/env python3
"""Probe (Loop 1 of the Nov 11 instruction plan): replay one recorded moment of an agent run under a changed system
prompt and score only the model's NEXT action. One probe is one generation (~20 s) instead of a full task (10-20 min).

Standard library only (the VM's python3 has nothing else). Subcommands:

  stats      reference counts of a finished run (garbled edit calls, range-less reads)
  points     pick decision points and store the exact chat request that preceded each one
               --run <results/replica/tag>      rebuilt from the ATIF traces (early steps only, before compaction)
               --from-dumps <results/requests/x> taken from the request log (exact, also after compaction)
  verify     rebuild requests from a run's traces and compare them with that run's dumped requests
  replay     swap the system prompt (--base text -> --variant text) and send each point to the model server
  score      per-variant table: well-formed edit_file, read_file with a range, check command, grep before submit,
             action after a budget warning, completion tokens
  calibrate  unchanged prompt: replayed garbled / range-less shares vs the recorded ones (pass = within 5 points)

Request shape (read from google-adk 1.36.1 LiteLlm + adk_submission 0.2.13 + swegemma 0.2.11, checked against a capture
of LiteLlm's own output): body keys messages, model, max_completion_tokens, temperature, tools, top_p,
chat_template_kwargs{enable_thinking}, thinking_token_budget. messages = system (instruction + "\n\n" + ADK identity
line), user (task prompt), then per model turn one assistant message {content?, tool_calls[1], reasoning_content,
reasoning} followed by a "tool" message whose content is json.dumps(result, ensure_ascii=False); harness nudges are user
messages; a thought-only model turn is dropped by ADK. ADK compacts the history once a prompt reaches 14,336 tokens, so
a trace step is rebuilt only while every earlier prompt stayed below that.

GPU rule: while a tmux session gate1 / instr / rep_* exists or a run_arms.sh / run_replica.sh / run_pair.sh process is
alive, replay sends at most 30 requests per hour at concurrency 1 (shared ledger file); --allow-sessions names tmux
sessions to ignore (the job chain itself runs in `instr`; its screens are still caught by the process check).
"""
from __future__ import annotations
import argparse, collections, concurrent.futures, glob, hashlib, json, math, os, random, re, subprocess, sys, threading, time
import urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("GEMMA_ROOT", "/mnt/biohub/kdata/gemma4"))
IDENTITY = 'You are an agent. Your internal name is "{name}".'
COMPACT_AT = 14336                       # EventsCompactionConfig.token_threshold in local_score.py / the official notebook
GARBLED = "mandatory input parameters are not present"
BUSY_RE = re.compile(r"^(gate1|instr|rep_.*)$")
BUSY_PROC = re.compile(r"\b(run_arms|run_replica|run_pair)\.sh\b")   # a screen or paired run is alive, whatever its tmux name
KINDS = ("edit", "read", "after_edit", "submit", "after_warning")
EDIT_KEYS = ("filepath", "old_string", "new_string")


# ---- bundle (agent.yaml + configs/sampling.yaml, read without PyYAML) -------------------------------------------
class Bundle:
    def __init__(self, d):
        self.dir = Path(d)
        ag = (self.dir / "agent.yaml").read_text(encoding="utf-8")
        self.name = self._scalar(ag, "name") or "swe_agent"
        self.model = self._scalar(ag, "model") or "gemma-4-31b-it-qat-w4a16-ct"
        self.description = self._scalar(ag, "description") or ""
        m = re.search(r"^tools:\s*\n((?:[ \t]+-[^\n]*\n?)+)", ag, re.M)
        self.tools = [x.strip()[1:].strip() for x in m.group(1).splitlines() if x.strip()] if m else []
        inc = re.search(r"^instruction:\s*!include\s+(\S+)", ag, re.M)
        self.prompt_path = self.dir / (inc.group(1) if inc else "prompts/system.md")
        self.instruction = self.prompt_path.read_text(encoding="utf-8")
        gc = re.search(r"^generate_content_config:\s*!include\s+(\S+)", ag, re.M)
        s = (self.dir / gc.group(1)).read_text(encoding="utf-8") if gc else ag
        num = lambda k, cast, dflt=None: (cast(self._scalar(s, k)) if self._scalar(s, k) not in (None, "") else dflt)
        self.temperature = num("temperature", float); self.top_p = num("top_p", float); self.top_k = num("top_k", int)
        self.max_output_tokens = num("max_output_tokens", int); self.thinking_budget = num("thinking_budget", int)

    @staticmethod
    def _scalar(text, key):
        m = re.search(r"^[ \t]*%s:[ \t]*([^\n#]*)" % re.escape(key), text, re.M)
        return m.group(1).strip().strip("'\"") if m else None

    def system_content(self):
        s = IDENTITY.format(name=self.name)
        if self.description: s += f' The description about you is "{self.description}".'
        return self.instruction + "\n\n" + s

    def declarations(self):
        by = {t["function"]["name"]: t for t in json.load(open(HERE / "tool_declarations.json", encoding="utf-8"))}
        return [by[n] for n in self.tools if n in by]

    def envelope(self, messages):
        b = {"messages": messages, "model": self.model}
        if self.max_output_tokens is not None: b["max_completion_tokens"] = self.max_output_tokens
        if self.temperature is not None: b["temperature"] = self.temperature
        b["tools"] = self.declarations()
        if self.top_p is not None: b["top_p"] = self.top_p
        if self.top_k is not None: b["top_k"] = self.top_k
        if self.thinking_budget is not None:
            b["chat_template_kwargs"] = {"enable_thinking": self.thinking_budget > 0}
            if self.thinking_budget > 0: b["thinking_token_budget"] = self.thinking_budget
        return b


# ---- traces -> model turns ----------------------------------------------------------------------------------
def trace_items(trace):
    """ATIF steps -> (system, task, items, clean). items: {"type": "model", thought, text, call{name,args}|None, obs|None,
    prompt_tokens, completion_tokens, step} or {"type": "user", text}. One model item = one model response: the
    recorder splits a response into consecutive agent steps that share extra.elapsed_s. clean=False when the trace
    holds a step this parser does not understand (items stop there)."""
    steps = trace.get("steps") or []
    if len(steps) < 2 or steps[0].get("source") != "system" or steps[1].get("source") != "user": return None, None, [], False
    system, task = steps[0].get("message") or "", steps[1].get("message") or ""
    items = []; cur = None; clean = True
    for i, s in enumerate(steps[2:], start=2):
        ex = s.get("extra") or {}; et = ex.get("event_type")
        if s.get("source") == "agent":
            tcs = s.get("tool_calls") or []
            if len(tcs) > 1: clean = False; break
            key = ex.get("elapsed_s")
            if not (cur is not None and cur["key"] == key and cur["call"] is None):
                cur = {"type": "model", "key": key, "thought": "", "text": "", "call": None, "obs": None,
                       "prompt_tokens": None, "completion_tokens": None, "step": i}
                items.append(cur)
            msg = s.get("message")
            if isinstance(msg, str) and msg:
                if et == "thinking": cur["thought"] = (cur["thought"] + "\n" + msg) if cur["thought"] else msg
                else: cur["text"] = (cur["text"] + msg) if cur["text"] else msg
            if tcs:
                cur["call"] = {"name": tcs[0].get("function_name"), "args": tcs[0].get("arguments") or {}}
                ob = s.get("observation")
                if ob is not None: cur["obs"] = ob.get("content")
            met = s.get("metrics") or {}
            if met.get("prompt_tokens") is not None and cur["prompt_tokens"] is None:
                cur["prompt_tokens"] = met.get("prompt_tokens"); cur["completion_tokens"] = met.get("completion_tokens")
        elif s.get("source") == "system" and et == "continuation_nudge":
            items.append({"type": "user", "text": s.get("message") or ""}); cur = None
        else:
            clean = False; break
    return system, task, items, clean


def obs_content(obs):
    """Trace observation (json.dumps of the result dict, ASCII-escaped) -> the string LiteLlm sends (ensure_ascii=False)."""
    try: return json.dumps(json.loads(obs), ensure_ascii=False)
    except Exception: return obs or ""


def build_messages(system_content, task, items, k):
    """The messages of the request that produced items[k] (everything before it)."""
    msgs = [{"role": "system", "content": system_content}, {"role": "user", "content": task}]
    for n, it in enumerate(items[:k]):
        if it["type"] == "user":
            msgs.append({"role": "user", "content": it["text"]}); continue
        if not it["call"] and not it["text"]: continue            # thought-only event: ADK leaves it out of the context
        m = {"role": "assistant"}; cid = f"call_{n}"
        if it["text"]: m["content"] = it["text"]
        if it["call"]:
            m["tool_calls"] = [{"type": "function", "id": cid, "function": {"name": it["call"]["name"],
                                "arguments": json.dumps(it["call"]["args"], ensure_ascii=False)}}]
        if it["thought"]: m["reasoning_content"] = it["thought"]; m["reasoning"] = it["thought"]
        msgs.append(m)
        if it["call"] and it["obs"] is not None:
            msgs.append({"role": "tool", "tool_call_id": cid, "content": obs_content(it["obs"])})
    return msgs


def exact_until(items):
    """Index of the first model item whose request may already be compacted (an earlier prompt reached the threshold
    or has no token count)."""
    for k, it in enumerate(items):
        if it["type"] == "model" and (it["prompt_tokens"] is None or it["prompt_tokens"] >= COMPACT_AT): return k + 1
    return len(items)


# ---- classification of calls and results (shared by traces, dumps and replies) ------------------------------------
def is_garbled_result(content): return GARBLED in (content or "")
def has_warning(content): return "budget_warning" in (content or "")
def result_ok(content): return (content or "").lstrip().startswith('{"status": "ok"')
def has_range(args): return isinstance(args, dict) and (args.get("start_line") is not None or args.get("end_line") is not None)
def wellformed_edit(args): return isinstance(args, dict) and all(isinstance(args.get(k), str) for k in EDIT_KEYS)


def recorded_info(call, obs, completion_tokens=None):
    if not call: return {"tool": None, "completion_tokens": completion_tokens}
    a = call.get("args") if isinstance(call.get("args"), dict) else {}
    r = {"tool": call.get("name"), "completion_tokens": completion_tokens}
    if r["tool"] == "edit_file": r["garbled"] = is_garbled_result(obs) if obs is not None else not wellformed_edit(a)
    if r["tool"] == "read_file": r["ranged"] = has_range(a)
    if r["tool"] == "run_command": r["command"] = str(a.get("command", ""))[:4000]
    return r


def kinds_of(call, prev_call, prev_obs, warned_before, submitted_before):
    ks = []
    name = call.get("name") if call else None
    if name == "edit_file": ks.append("edit")
    if name == "read_file": ks.append("read")
    if prev_call and prev_call.get("name") == "edit_file" and result_ok(prev_obs): ks.append("after_edit")
    if name == "submit_patch" and not submitted_before: ks.append("submit")
    if has_warning(prev_obs) and not warned_before: ks.append("after_warning")
    return ks


def trace_points(path, bundle, max_prompt_tokens, run_tag):
    trace = json.load(open(path, encoding="utf-8"))
    system, task, items, clean = trace_items(trace)
    if not items: return []
    task_id = re.sub(r"^trace_|\.json$", "", os.path.basename(path))
    lim = exact_until(items); out = []; warned = False; submitted = False; prev = None
    sysc = bundle.system_content()
    for k, it in enumerate(items):
        if it["type"] != "model": prev = None; continue
        pc, po = (prev["call"], prev["obs"]) if prev else (None, None)
        ks = kinds_of(it["call"], pc, po, warned, submitted)
        if po is not None and has_warning(po): warned = True
        if it["call"] and it["call"]["name"] == "submit_patch": submitted = True
        prev = it
        if not ks or k >= lim or it["prompt_tokens"] is None or it["prompt_tokens"] > max_prompt_tokens: continue
        out.append({"id": f"{run_tag}/{task_id}#{k}", "task": task_id, "run": run_tag, "k": k, "kinds": ks, "source": "trace",
                    "prompt_tokens": it["prompt_tokens"], "recorded": recorded_info(it["call"], it["obs"], it["completion_tokens"]),
                    "body": bundle.envelope(build_messages(sysc, task, items, k))})
    return out


# ---- request dumps (netns_bridge.py host ... <dump_dir>) ----------------------------------------------------------
def iter_http_requests(path):
    """Yield (offset, request_line, body_bytes) for every complete HTTP/1.1 request in a dump file."""
    data = open(path, "rb").read(); pos = 0
    while pos < len(data):
        he = data.find(b"\r\n\r\n", pos)
        if he < 0: return
        lines = data[pos:he].decode("latin-1").split("\r\n")
        hdr = {}
        for l in lines[1:]:
            if ":" in l: a, b = l.split(":", 1); hdr[a.strip().lower()] = b.strip()
        start = he + 4
        if "chunked" in hdr.get("transfer-encoding", "").lower():
            body = b""; p = start
            while True:
                le = data.find(b"\r\n", p)
                if le < 0: return
                try: n = int(data[p:le].split(b";")[0].strip() or b"0", 16)
                except ValueError: return
                if le + 2 + n + 2 > len(data): return
                body += data[le + 2:le + 2 + n]; p = le + 2 + n + 2
                if n == 0: break
            end = p
        else:
            n = int(hdr.get("content-length", "0") or 0); end = start + n
            if end > len(data): return                     # the last request is still being written
            body = data[start:end]
        yield pos, lines[0], body
        pos = end


def _task_hash(c):
    """Hash of the first user message. After compaction it is a list of text parts (the summary), not the task prompt."""
    if not isinstance(c, str): c = json.dumps(c, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1((c or "").encode("utf-8", "surrogatepass")).hexdigest()


def _h(prev, obj): return hashlib.sha1(prev + json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8", "surrogatepass")).digest()[:10]


def _msum(m):
    """Small summary of one message, enough to classify a point without keeping the body."""
    r = m.get("role")
    if r == "assistant":
        tcs = m.get("tool_calls") or []
        if not tcs: return {"role": r, "call": None}
        fn = tcs[0].get("function") or {}
        try: args = json.loads(fn.get("arguments") or "{}")
        except Exception: args = {}
        if not isinstance(args, dict): args = {}
        slim = {k: (v if k in ("command", "start_line", "end_line", "filepath") else "") for k, v in args.items()}   # keys, small values
        return {"role": r, "call": {"name": fn.get("name"), "args": slim}}
    if r == "tool":
        c = m.get("content") if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
        return {"role": r, "garbled": is_garbled_result(c), "warn": has_warning(c), "ok": result_ok(c)}
    return {"role": r}


def load_dumps(pattern):
    """Index every agent request (has tools, starts with a system message) found under a dump dir / glob."""
    files = sorted(glob.glob(os.path.join(pattern, "*.http")) if os.path.isdir(pattern) else glob.glob(pattern))
    recs = []; seen = set(); n_all = 0
    for f in files:
        for off, line, body in iter_http_requests(f):
            if not line.startswith("POST") or "chat/completions" not in line: continue
            n_all += 1
            try: b = json.loads(body)
            except Exception: continue
            msgs = b.get("messages") or []
            if not b.get("tools") or len(msgs) < 2 or msgs[0].get("role") != "system": continue
            chain = []; h = b""
            for m in msgs: h = _h(h, m); chain.append(h)
            if chain[-1] in seen: continue                     # litellm retry of the same request
            seen.add(chain[-1])
            recs.append({"file": f, "off": off, "n": len(msgs), "chain": chain, "sum": [_msum(m) for m in msgs],
                         "system": msgs[0].get("content") or "", "task_h": _task_hash(msgs[1].get("content"))})
    return recs, {"files": len(files), "chat_requests": n_all, "agent_requests": len(recs)}


def dump_body(rec):
    for off, line, body in iter_http_requests(rec["file"]):
        if off == rec["off"]: return json.loads(body)
    raise KeyError(rec["off"])


def link_successors(recs):
    """rec -> the shortest later request of the same conversation (its messages start with rec's messages)."""
    by = collections.defaultdict(list)
    for i, r in enumerate(recs):
        for j in range(r["n"] - 1): by[r["chain"][j]].append(i)
    for r in recs:
        c = [recs[i] for i in by.get(r["chain"][-1], ()) if recs[i]["n"] > r["n"]]
        r["succ"] = min(c, key=lambda x: x["n"]) if c else None


def dump_points(recs, base_text, tag):
    link_successors(recs); out = []
    for r in recs:
        if base_text and base_text.strip() not in r["system"]: continue
        s = r["sum"]; n = r["n"]
        prev_call = prev_obs = None; warned = False; submitted = False
        for j, m in enumerate(s):
            if m["role"] == "assistant" and m.get("call") and m["call"]["name"] == "submit_patch": submitted = True
            if m["role"] == "tool" and m.get("warn") and j < n - 1: warned = True
        if s[-1]["role"] == "tool" and n >= 2 and s[-2]["role"] == "assistant":
            prev_call = s[-2].get("call")
            prev_obs = ('{"status": "ok"' if s[-1]["ok"] else "") + (" budget_warning" if s[-1]["warn"] else "")
        call = None; obs = None; known = False
        su = r["succ"]
        if su is not None and su["sum"][n]["role"] == "assistant":
            known = True; call = su["sum"][n].get("call")
            if call and su["n"] > n + 1 and su["sum"][n + 1]["role"] == "tool": obs = GARBLED if su["sum"][n + 1]["garbled"] else ""
        ks = kinds_of(call, prev_call, prev_obs, warned, submitted)
        if not ks: continue
        rec_info = recorded_info(call, obs) if known else {"tool": "?"}
        out.append({"id": f"{tag}/{r['task_h'][:10]}#{n}.{r['chain'][-1].hex()[:6]}", "task": r["task_h"][:10], "run": tag, "k": n,
                    "kinds": ks, "source": "dump", "prompt_tokens": None, "recorded": rec_info, "_rec": r})
    return out


# ---- sampling ---------------------------------------------------------------------------------------------------
def sample(points, want, per_task, seed, garbled_share=0.32):
    """Up to want[kind] points per kind, round-robin over tasks (at most per_task per task, kind and stratum).
    Edit points are drawn in two strata so that garbled_share of them are recorded-garbled calls (the whole-run rate of
    bf5_train is 32%; garbled calls sit in few tasks, so a plain task round-robin would return under 10%)."""
    rng = random.Random(seed); chosen = {}

    def take(cands, n, kind):
        by = collections.defaultdict(list)
        for p in cands: by[p["task"]].append(p)
        tasks = sorted(by); rng.shuffle(tasks)
        for t in tasks: rng.shuffle(by[t])
        got = 0; rnd = 0
        while got < n and rnd < per_task:
            progressed = False
            for t in tasks:
                if rnd < len(by[t]) and got < n:
                    p = by[t][rnd]; progressed = True
                    if p["id"] not in chosen: chosen[p["id"]] = dict(p, sampled_for=[kind]); got += 1
                    elif kind not in chosen[p["id"]]["sampled_for"]: chosen[p["id"]]["sampled_for"].append(kind); got += 1
            if not progressed: break
            rnd += 1
        return got

    for kind, n in want.items():
        cands = [p for p in points if kind in p["kinds"]]
        if kind == "edit":
            g = take([p for p in cands if p["recorded"].get("garbled")], int(round(n * garbled_share)), kind)
            g += take([p for p in cands if p["recorded"].get("garbled") is False], n - g, kind)
            if g < n: take([p for p in cands if p["recorded"].get("garbled")], n - g, kind)      # fill up; ids already taken are skipped
        else:
            take(cands, n, kind)
    return list(chosen.values())


def parse_want(a):
    kinds = [k for k in a.kinds.split(",") if k]
    for k in kinds:
        if k not in KINDS: sys.exit(f"unknown kind {k}; choose from {KINDS}")
    return {k: a.n for k in kinds}


# ---- commands: stats / points / verify ---------------------------------------------------------------------------
def trace_files(run):
    d = Path(run)
    for sub in ("agent_run/traces", "traces", "."):
        fs = sorted(glob.glob(str(d / sub / "trace_*.json")))
        if fs: return fs
    return []


def cmd_stats(a):
    e = g = r = nr = 0
    for f in trace_files(a.run):
        for s in json.load(open(f, encoding="utf-8")).get("steps", []):
            for tc in s.get("tool_calls") or []:
                o = (s.get("observation") or {}).get("content") or ""
                if tc.get("function_name") == "edit_file": e += 1; g += is_garbled_result(o)
                if tc.get("function_name") == "read_file": r += 1; nr += not has_range(tc.get("arguments"))
    print(f"{a.run}: edit_file calls {e}, garbled {g} ({pct(g, e)}); read_file calls {r}, range-less {nr} ({pct(nr, r)})")


def cmd_points(a):
    want = parse_want(a)
    if a.from_dumps:
        recs, st = load_dumps(a.from_dumps)
        base = Path(a.base).read_text(encoding="utf-8") if a.base else ""
        pts = dump_points(recs, base, a.tag or os.path.basename(os.path.normpath(a.from_dumps)))
        print(f"dumps: {st}; candidate points {len(pts)}", file=sys.stderr)
    else:
        b = Bundle(a.bundle); pts = []; tag = a.tag or os.path.basename(os.path.normpath(a.run)); bad = 0
        for f in trace_files(a.run):
            tr = json.load(open(f, encoding="utf-8"))
            if not tr.get("steps") or (tr["steps"][0].get("message") or "").strip() != b.instruction.strip(): bad += 1; continue
            pts += trace_points(f, b, a.max_prompt_tokens, tag)
        if bad: print(f"warning: {bad} traces skipped (their system prompt is not {b.prompt_path})", file=sys.stderr)
    avail = collections.Counter(k for p in pts for k in p["kinds"])
    sel = sample(pts, want, a.per_task, a.seed, a.garbled_share)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for p in sel:
            if "_rec" in p: p["body"] = dump_body(p.pop("_rec"))
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    got = collections.Counter(k for p in sel for k in p["sampled_for"])
    print(f"points -> {a.out}: {len(sel)} points from {len({p['task'] for p in sel})} tasks; "
          + ", ".join(f"{k} {got[k]}/{want[k]} (available {avail[k]})" for k in want))
    for k in want:
        ps = [p for p in sel if k in p["sampled_for"]]
        if k == "edit": print(f"  recorded garbled at the edit points: {sum(1 for p in ps if p['recorded'].get('garbled'))}/{len(ps)}")
        if k == "read": print(f"  recorded range-less at the read points: {sum(1 for p in ps if p['recorded'].get('ranged') is False)}/{len(ps)}")


def strip_ids(body):
    b = json.loads(json.dumps(body))
    for m in b.get("messages", []):
        m.pop("tool_call_id", None)
        for tc in m.get("tool_calls") or []: tc.pop("id", None)
    return b


def strip_ws(body):
    b = strip_ids(body)
    for m in b["messages"]:
        for k in ("content", "reasoning", "reasoning_content"):
            if isinstance(m.get(k), str): m[k] = m[k].strip()
    return b


def first_diff(x, y, path=""):
    if type(x) != type(y): return f"{path}: type {type(x).__name__} vs {type(y).__name__}: {str(x)[:120]!r} | {str(y)[:120]!r}"
    if isinstance(x, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x: return f"{path}.{k}: only in dump: {str(y[k])[:160]!r}"
            if k not in y: return f"{path}.{k}: only in rebuilt: {str(x[k])[:160]!r}"
            d = first_diff(x[k], y[k], f"{path}.{k}")
            if d: return d
        return None
    if isinstance(x, list):
        if len(x) != len(y): return f"{path}: length {len(x)} vs {len(y)}"
        for i, (p, q) in enumerate(zip(x, y)):
            d = first_diff(p, q, f"{path}[{i}]")
            if d: return d
        return None
    if x != y:
        if isinstance(x, str):
            i = next((i for i, (c, d) in enumerate(zip(x, y)) if c != d), min(len(x), len(y)))
            return f"{path}: differs at char {i} (len {len(x)} vs {len(y)}): rebuilt {x[max(0, i - 40):i + 60]!r} | dump {y[max(0, i - 40):i + 60]!r}"
        return f"{path}: {x!r} vs {y!r}"
    return None


def cmd_verify(a):
    b = Bundle(a.bundle); recs, st = load_dumps(a.dumps)
    by = collections.defaultdict(list)
    for r in recs: by[(r["task_h"], r["n"])].append(r)
    c = collections.Counter(); diffs = []
    for f in trace_files(a.run):
        system, task, items, clean = trace_items(json.load(open(f, encoding="utf-8")))
        if not items or system.strip() != b.instruction.strip(): c["traces_skipped"] += 1; continue
        th = hashlib.sha1(task.encode("utf-8", "surrogatepass")).hexdigest(); lim = exact_until(items)
        for k, it in enumerate(items):
            if it["type"] != "model" or k >= lim: continue
            mine = b.envelope(build_messages(b.system_content(), task, items, k))
            cands = [r for r in by.get((th, len(mine["messages"])), ()) if b.instruction.strip() in r["system"]]
            if not cands: c["no_dump_for_step"] += 1; continue
            c["steps_compared"] += 1; bodies = [dump_body(r) for r in cands]
            if any(strip_ids(mine) == strip_ids(d) for d in bodies): c["equal"] += 1
            elif any(strip_ws(mine) == strip_ws(d) for d in bodies):
                c["equal_but_whitespace"] += 1
                if len(diffs) < a.show: diffs.append(f"{os.path.basename(f)} item {k} [whitespace]: " + str(first_diff(strip_ids(mine), strip_ids(bodies[0]))))
            else:
                c["different"] += 1
                if len(diffs) < a.show: diffs.append(f"{os.path.basename(f)} item {k}: " + str(first_diff(strip_ws(mine), strip_ws(bodies[0]))))
    print(f"dumps: {st}"); print("verify:", dict(c))
    for d in diffs: print("  " + d)
    ok = c["equal"] >= a.need and c["different"] == 0
    print(f"RESULT: {'PASS' if ok else 'FAIL'} (equal apart from ids on {c['equal']} steps, need {a.need}; {c['equal_but_whitespace']} more differ only in leading/trailing "
          f"whitespace of earlier thoughts or text, which the trace does not keep; different: {c['different']})")
    sys.exit(0 if ok else 3)


# ---- replay -----------------------------------------------------------------------------------------------------
def busy_sessions(allow):
    """Test runs alive now: tmux sessions gate1 / instr / rep_* not named in `allow`, plus any running test-run script.
    A screen runs inside `instr`, which the job chain allows for itself, so the session name alone would miss it."""
    busy = []
    try:
        out = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, timeout=10).stdout
        busy = [s for s in out.split() if BUSY_RE.match(s) and s not in allow]
    except Exception:
        pass
    try:
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=10).stdout
        if any(BUSY_PROC.search(l) for l in ps.splitlines()): busy.append("a test-run script")
    except Exception:
        pass
    return busy


class Ledger:
    """Timestamps of every probe request sent from this machine (shared by all probe.py runs)."""
    def __init__(self, path): self.path = path; os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    def last_hour(self):
        now = time.time()
        try: return sum(1 for l in open(self.path) if l.strip() and now - float(l.split()[0]) < 3600)
        except FileNotFoundError: return 0
    def add(self):
        with open(self.path, "a") as f: f.write(f"{time.time():.0f}\n")


def swap_system(body, base_text, variant_text):
    b = json.loads(json.dumps(body)); s = b["messages"][0]["content"]
    if base_text.strip() not in s: raise ValueError("the base prompt text is not in this request's system message")
    b["messages"][0]["content"] = s.replace(base_text.strip(), variant_text.strip(), 1)
    return b


def call_server(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"})
    t0 = time.time()
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}", "latency": round(time.time() - t0, 1)}
        except Exception as e:
            if attempt: return {"error": f"{type(e).__name__}: {e}", "latency": round(time.time() - t0, 1)}
            time.sleep(5)
    ch = (d.get("choices") or [{}])[0]; msg = ch.get("message") or {}; tcs = msg.get("tool_calls") or []
    out = {"latency": round(time.time() - t0, 1), "finish": ch.get("finish_reason"), "n_tool_calls": len(tcs), "tool_calls": tcs,
           "content": (msg.get("content") or "")[:3000],
           "reasoning_chars": len(msg.get("reasoning") or msg.get("reasoning_content") or ""),
           "completion_tokens": (d.get("usage") or {}).get("completion_tokens"), "prompt_tokens": (d.get("usage") or {}).get("prompt_tokens")}
    if tcs:
        fn = tcs[0].get("function") or {}; raw = fn.get("arguments")
        try: args = json.loads(raw) if isinstance(raw, str) else raw
        except Exception: args = None
        out["action"] = {"name": fn.get("name"), "args": args if isinstance(args, dict) else {"_unparsed": raw}}
    else:
        out["action"] = None
    return out


def read_results(out_dir):
    p = os.path.join(out_dir, "results.jsonl"); rows = {}
    if os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            try: r = json.loads(l)
            except Exception: continue
            if "error" not in r: rows[(r["point"], r["variant"])] = r
    return rows


def cmd_replay(a):
    base = Path(a.base).read_text(encoding="utf-8")
    variants = []
    for v in a.variant:
        name, path = v.split("=", 1); variants.append((name, Path(path).read_text(encoding="utf-8")))
    pts = [json.loads(l) for l in open(a.points, encoding="utf-8") if l.strip()]
    if a.limit: pts = pts[:a.limit]
    os.makedirs(a.out, exist_ok=True); done = read_results(a.out)
    jobs = [(p, n, t) for p in pts for n, t in variants if (p["id"], n) not in done]
    allow = set(x for x in a.allow_sessions.split(",") if x); ledger = Ledger(a.ledger)
    deadline = a.deadline_epoch or (time.time() + a.deadline_min * 60 if a.deadline_min else None)
    print(f"replay: {len(pts)} points x {len(variants)} variants; {len(done)} results exist, {len(jobs)} to send; "
          f"busy sessions now: {busy_sessions(allow) or 'none'}; requests in the last hour: {ledger.last_hour()}", flush=True)
    lock = threading.Lock(); fout = open(os.path.join(a.out, "results.jsonl"), "a", encoding="utf-8"); sent = errs = 0

    def run(p, name, text):
        try: res = call_server(a.url, swap_system(p["body"], base, text), a.timeout)
        except ValueError as e: res = {"error": str(e)}
        row = {"point": p["id"], "variant": name, "task": p["task"], "kinds": p.get("sampled_for") or p["kinds"],
               "recorded": p["recorded"], "recorded_prompt_tokens": p.get("prompt_tokens"), "ts": round(time.time()), **res}
        with lock: fout.write(json.dumps(row, ensure_ascii=False) + "\n"); fout.flush()
        return "error" in res

    stop = ""; inflight = set(); busy_at = 0; busy = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
        while jobs or inflight:
            if jobs and not stop:
                if deadline and time.time() > deadline: stop = "deadline reached"
                if time.time() - busy_at > 30: busy = busy_sessions(allow); busy_at = time.time()
                cap = 1 if busy else max(1, a.concurrency)
                if not stop and len(inflight) < cap:
                    if busy and ledger.last_hour() >= a.busy_rate:
                        if a.wait: time.sleep(60); continue
                        stop = f"30/hour cap reached while {','.join(busy)} is running"
                    else:
                        p, n, t = jobs.pop(0); ledger.add(); sent += 1
                        inflight.add(ex.submit(run, p, n, t)); continue
            if not inflight: break
            fin, inflight = concurrent.futures.wait(inflight, return_when=concurrent.futures.FIRST_COMPLETED)
            errs += sum(1 for f in fin if f.result())
            if sent % 20 == 0: print(f"  sent {sent}, errors {errs}, left {len(jobs)}", flush=True)
    fout.close()
    print(f"replay done: sent {sent}, errors {errs}, not sent {len(jobs)}" + (f" ({stop})" if stop else ""), flush=True)


# ---- scoring ----------------------------------------------------------------------------------------------------
PYTEST_PATH = re.compile(r"pytest\b[^|;&\n]*?(\S+\.py\b|\btests?/\S*|\btesting/\S*)")
GREP = re.compile(r"(^|[\s;&|(])(git\s+grep|grep|rg|ag|ack)\s")


def count_cases(cmd):
    """How many cases a check command exercises (heuristic): print()/assert statements, or the arguments of one print()."""
    n = max(len(re.findall(r"\bprint\s*\(", cmd)), len(re.findall(r"\bassert\s", cmd)))
    best = 0
    for m in re.finditer(r"\bprint\s*\(", cmd):
        depth = 1; commas = 0; i = m.end(); q = None
        while i < len(cmd) and depth:
            ch = cmd[i]
            if q:
                if ch == "\\": i += 1
                elif ch == q: q = None
            elif ch in "'\"": q = ch
            elif ch in "([{": depth += 1
            elif ch in ")]}": depth -= 1
            elif ch == "," and depth == 1: commas += 1
            i += 1
        best = max(best, commas + 1)
    return max(n, best)


def act(row):
    a = row.get("action"); return (a.get("name"), a.get("args") or {}) if a else (None, {})


def pct(x, n): return f"{100.0 * x / n:.0f}%" if n else "-"
def cell(x, n): return f"{x}/{n} ({pct(x, n)})" if n else "0/0"


def metrics_for(rows):
    """rows: results of one variant. -> ordered list of (label, x, n) and mean tokens."""
    out = []; by = collections.defaultdict(list)
    for r in rows:
        for k in r["kinds"]: by[k].append(r)
    e = by["edit"]
    if e:
        ed = [r for r in e if act(r)[0] == "edit_file"]; wf = [r for r in ed if wellformed_edit(act(r)[1])]
        out += [("edit points: next action is edit_file", len(ed), len(e)),
                ("edit points: edit_file well formed (of edit_file calls)", len(wf), len(ed)),
                ("edit points: edit_file garbled (of edit_file calls)", len(ed) - len(wf), len(ed))]
        for lab, flag in (("recorded garbled", True), ("recorded well formed", False)):
            sub = [r for r in ed if bool(r["recorded"].get("garbled")) == flag]
            out.append((f"  - at points with a {lab} call: well formed", sum(1 for r in sub if wellformed_edit(act(r)[1])), len(sub)))
        out.append(("edit points: no tool call at all", sum(1 for r in e if act(r)[0] is None), len(e)))
    rd = by["read"]
    if rd:
        rr = [r for r in rd if act(r)[0] == "read_file"]; rg = [r for r in rr if has_range(act(r)[1])]
        out += [("read points: next action is read_file", len(rr), len(rd)),
                ("read points: read_file with a range (of read_file calls)", len(rg), len(rr)),
                ("read points: read_file without a range (of read_file calls)", len(rr) - len(rg), len(rr)),
                ("read points: run_command instead (grep/sed/cat)", sum(1 for r in rd if act(r)[0] == "run_command"), len(rd))]
    ae = by["after_edit"]
    if ae:
        cm = [str(act(r)[1].get("command", "")) for r in ae if act(r)[0] == "run_command"]
        pc = sum("py_compile" in c for c in cm); pt = sum(bool(PYTEST_PATH.search(c)) for c in cm); c3 = sum(count_cases(c) >= 3 for c in cm)
        out += [("after an edit: next action is run_command", len(cm), len(ae)),
                ("after an edit: command has py_compile", pc, len(ae)),
                ("after an edit: command starts with py_compile", sum(bool(re.match(r"\s*(cd \S+ && )?python3? -m py_compile", c)) for c in cm), len(ae)),
                ("after an edit: command runs pytest on a path", pt, len(ae)),
                ("after an edit: command has 3 or more cases", c3, len(ae)),
                ("after an edit: next action is another edit", sum(1 for r in ae if act(r)[0] in ("edit_file", "write_file")), len(ae)),
                ("after an edit: next action is submit_patch", sum(1 for r in ae if act(r)[0] == "submit_patch"), len(ae))]
    sb = by["submit"]
    if sb:
        out += [("submit points: next action is submit_patch", sum(1 for r in sb if act(r)[0] == "submit_patch"), len(sb)),
                ("submit points: a grep first (sibling search)", sum(1 for r in sb if act(r)[0] == "run_command" and GREP.search(str(act(r)[1].get("command", "")))), len(sb)),
                ("submit points: another edit first", sum(1 for r in sb if act(r)[0] in ("edit_file", "write_file")), len(sb))]
    w = by["after_warning"]
    if w:
        ed = sum(1 for r in w if act(r)[0] in ("edit_file", "write_file")); su = sum(1 for r in w if act(r)[0] == "submit_patch")
        out += [("after the budget warning: edit or submit", ed + su, len(w)), ("  - edit", ed, len(w)), ("  - submit", su, len(w)),
                ("after the budget warning: explore (read / command)", sum(1 for r in w if act(r)[0] in ("read_file", "run_command", "get_status")), len(w))]
    toks = {k: [r["completion_tokens"] for r in v if r.get("completion_tokens") is not None] for k, v in by.items()}
    return out, toks


def sign_test(b01, b10):
    n = b01 + b10
    if n == 0: return 1.0
    k = min(b01, b10)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def paired(rows_by_variant, base, var, kind, tool, good):
    """Points where both variants called `tool`: base bad -> variant good, and the reverse."""
    b = {r["point"]: r for r in rows_by_variant[base] if kind in r["kinds"] and act(r)[0] == tool}
    v = {r["point"]: r for r in rows_by_variant[var] if kind in r["kinds"] and act(r)[0] == tool}
    both = sorted(set(b) & set(v)); up = sum(1 for p in both if not good(act(b[p])[1]) and good(act(v[p])[1]))
    down = sum(1 for p in both if good(act(b[p])[1]) and not good(act(v[p])[1]))
    return len(both), up, down, sign_test(up, down)


def load_scored(a):
    rows = list(read_results(a.out).values())
    names = [v for v in (a.variants.split(",") if a.variants else []) if v] or sorted({r["variant"] for r in rows})
    byv = {n: [r for r in rows if r["variant"] == n] for n in names}
    common = set.intersection(*[{r["point"] for r in byv[n]} for n in names]) if names else set()
    return names, {n: [r for r in byv[n] if r["point"] in common] for n in names}, len(common), {n: len(byv[n]) for n in names}


def score_md(a):
    names, byv, ncommon, nall = load_scored(a)
    if not names or not ncommon: return "No results yet.\n"
    base = a.base_name if a.base_name in names else names[0]
    L = [f"## Probe comparison ({a.out})", "",
         f"Points answered under every variant: {ncommon} (answered per variant: " + ", ".join(f"{n} {nall[n]}" for n in names) + f"). Base: `{base}`.", ""]
    mets = {n: metrics_for(byv[n]) for n in names}
    L += ["| Measure | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for i, (lab, _, _) in enumerate(mets[names[0]][0]):
        L.append(f"| {lab} | " + " | ".join(cell(mets[n][0][i][1], mets[n][0][i][2]) for n in names) + " |")
    for k in KINDS:
        if any(mets[n][1].get(k) for n in names):
            L.append(f"| mean completion tokens at {k.replace('_', ' ')} points | "
                     + " | ".join((f"{sum(mets[n][1][k]) / len(mets[n][1][k]):.0f}" if mets[n][1].get(k) else "-") for n in names) + " |")
    allt = {n: [r["completion_tokens"] for r in byv[n] if r.get("completion_tokens") is not None] for n in names}
    L.append("| mean completion tokens, all points | " + " | ".join((f"{sum(allt[n]) / len(allt[n]):.0f}" if allt[n] else "-") for n in names) + " |")
    L.append("| mean seconds per request | " + " | ".join(f"{sum(r.get('latency') or 0 for r in byv[n]) / max(1, len(byv[n])):.0f}" for n in names) + " |")
    others = [n for n in names if n != base]
    if others:
        L += ["", f"Paired against `{base}` (points where both called the tool; sign test, two-sided):", "",
              "| Variant | Measure | Points | Fixed | Broken | p |", "|---|---|---|---|---|---|"]
        for n in others:
            for lab, kind, tool, good in (("edit_file well formed", "edit", "edit_file", wellformed_edit), ("read_file with a range", "read", "read_file", has_range)):
                if any(kind in r["kinds"] for r in byv[n]):
                    nb, up, down, p = paired(byv, base, n, kind, tool, good)
                    L.append(f"| {n} | {lab} | {nb} | {up} | {down} | {p:.3f} |")
    return "\n".join(L) + "\n"


def cmd_score(a):
    md = score_md(a); print(md)
    if a.md:
        os.makedirs(os.path.dirname(os.path.abspath(a.md)), exist_ok=True)
        with open(a.md, "a" if a.append else "w", encoding="utf-8") as f: f.write(md + "\n")


def cmd_calibrate(a):
    rows = [r for r in read_results(a.out).values() if r["variant"] == a.variant]
    L = [f"## Calibration: unchanged prompt `{a.variant}` ({a.out})", ""]
    ok = True
    L += ["| Rate | Recorded at these points | Replayed | Difference | Points | Verdict |", "|---|---|---|---|---|---|"]
    for lab, kind, tool, bad_rec, bad_new in (
            ("garbled edit_file", "edit", "edit_file", lambda r: bool(r["recorded"].get("garbled")), lambda r: not wellformed_edit(act(r)[1])),
            ("range-less read_file", "read", "read_file", lambda r: r["recorded"].get("ranged") is False, lambda r: not has_range(act(r)[1]))):
        pts = [r for r in rows if kind in r["kinds"] and r["recorded"].get("tool") == tool]
        same = [r for r in pts if act(r)[0] == tool]
        if not pts: L.append(f"| {lab} | - | - | - | 0 | no points |"); ok = False; continue
        rec = 100.0 * sum(bad_rec(r) for r in pts) / len(pts); new = 100.0 * sum(bad_new(r) for r in same) / max(1, len(same))
        good = abs(rec - new) <= a.tolerance and len(pts) >= a.min_points and len(same) > 0
        ok &= good
        L.append(f"| {lab} | {sum(bad_rec(r) for r in pts)}/{len(pts)} ({rec:.0f}%) | {sum(bad_new(r) for r in same)}/{len(same)} ({new:.0f}%) | "
                 f"{new - rec:+.0f} points | {len(pts)} (need {a.min_points}) | {'pass' if good else 'FAIL'} |")
        L.append(f"| - same tool chosen as recorded | | {len(same)}/{len(pts)} ({pct(len(same), len(pts))}) | | | |")
    tok = [(r["prompt_tokens"], r["recorded_prompt_tokens"]) for r in rows if r.get("prompt_tokens") and r.get("recorded_prompt_tokens")]
    L += ["", f"Calibration {'PASSED' if ok else 'FAILED'} (tolerance {a.tolerance} points; the replayed share is taken over the replies that "
          "called the same tool as the recording).", ""]
    if tok:      # the server tokenises the rebuilt request: the same count as in the trace means the same prompt
        eq = sum(1 for x, y in tok if x == y)
        L += [f"Rebuilt requests whose prompt-token count equals the recorded one: {eq}/{len(tok)} ({pct(eq, len(tok))}); "
              f"largest difference {max(abs(x - y) for x, y in tok)} tokens.", ""]
    md = "\n".join(L); print(md)
    if a.md:
        os.makedirs(os.path.dirname(os.path.abspath(a.md)), exist_ok=True)
        with open(a.md, "a" if a.append else "w", encoding="utf-8") as f: f.write(md + "\n")
    sys.exit(0 if ok else 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("stats"); p.add_argument("--run", required=True); p.set_defaults(fn=cmd_stats)
    p = sp.add_parser("points")
    p.add_argument("--run"); p.add_argument("--from-dumps"); p.add_argument("--bundle", default=str(ROOT / "submissions/budgetfit_v5"))
    p.add_argument("--base", help="with --from-dumps: keep only requests whose system message holds this prompt file's text")
    p.add_argument("--kinds", default="edit,read"); p.add_argument("--n", type=int, default=150, help="points per kind")
    p.add_argument("--per-task", type=int, default=6); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--garbled-share", type=float, default=0.32, help="share of the edit points whose recorded call was garbled")
    p.add_argument("--max-prompt-tokens", type=int, default=14000); p.add_argument("--tag"); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_points)
    p = sp.add_parser("verify")
    p.add_argument("--run", required=True); p.add_argument("--dumps", required=True); p.add_argument("--bundle", required=True)
    p.add_argument("--need", type=int, default=20); p.add_argument("--show", type=int, default=8); p.set_defaults(fn=cmd_verify)
    p = sp.add_parser("replay")
    p.add_argument("--points", required=True); p.add_argument("--base", required=True, help="prompt file the points were recorded under")
    p.add_argument("--variant", action="append", required=True, help="name=prompt_file (repeatable); name=<base file> replays unchanged")
    p.add_argument("--out", required=True); p.add_argument("--url", default="http://127.0.0.1:8000/v1/chat/completions")
    p.add_argument("--concurrency", type=int, default=1); p.add_argument("--limit", type=int, default=0); p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--deadline-min", type=float, default=0); p.add_argument("--deadline-epoch", type=float, default=0)
    p.add_argument("--allow-sessions", default="", help="comma-separated tmux session names that do not count as test runs")
    p.add_argument("--busy-rate", type=int, default=30); p.add_argument("--wait", action="store_true", help="wait for the hourly cap instead of stopping")
    p.add_argument("--ledger", default=str(ROOT / "results/probes/rate_ledger.txt")); p.set_defaults(fn=cmd_replay)
    p = sp.add_parser("score")
    p.add_argument("--out", required=True); p.add_argument("--variants", default=""); p.add_argument("--base-name", default="")
    p.add_argument("--md"); p.add_argument("--append", action="store_true"); p.set_defaults(fn=cmd_score)
    p = sp.add_parser("calibrate")
    p.add_argument("--out", required=True); p.add_argument("--variant", required=True); p.add_argument("--tolerance", type=float, default=5.0)
    p.add_argument("--min-points", type=int, default=150); p.add_argument("--md"); p.add_argument("--append", action="store_true"); p.set_defaults(fn=cmd_calibrate)
    a = ap.parse_args()
    if a.cmd == "points" and not (a.run or a.from_dumps): ap.error("points needs --run or --from-dumps")
    a.fn(a)


if __name__ == "__main__":
    main()
