#!/usr/bin/env python3
"""Training examples in the exact form the model sees in a real run (Nov 19-21, round-2 plan).

Round 1 trained on 8-step windows with a hand-written summary of the earlier steps; the model never sees that form on
Kaggle. Here an example is the request the harness really sent (system prompt, task, every step with its thinking, tool
call and tool result, as recorded by the note relay), rendered with the serving model's own chat template, followed by
the model's replies. Nothing is summarised, capped or rewritten.

  check-render   local rendering against the SERVER's tokenizer endpoint, on logged requests (needs the server up):
                   .venv/bin/python exact_data.py check-render --dumps results/requests/confirm2 [--n 50] [--url http://127.0.0.1:8000]
  check-journal  local token count against the prompt_tokens the server reported, on a relay journal (no server needed):
                   .venv/bin/python exact_data.py check-journal --journal results/takeover/<tag> [--n 50]
  build          note runs (relay journals) and own wins -> examples, one JSON line each:
                   .venv/bin/python exact_data.py build --notes r2_tk_train_00 r2_tk_rb2_clean_00 ... --hints datasets/r2/hints_*.jsonl \
                       --own results/replica/bf5_train results/replica/bf5t06_train2 --exclude results/lists/dev48.txt --out datasets/r2/all.jsonl
                   held-out set: --notes r2_tk_dev_00 --only results/lists/dev48.txt --out datasets/r2/heldout.jsonl (no --own)
  tokenize       examples -> train.parquet (input_ids, labels, n, fix_labels, kind, iid) for train_qlora.py:
                   .venv/bin/python exact_data.py tokenize datasets/r2/all.jsonl --max-len 14336 --out datasets/r2/tok_31b
                   held-out rows: ... tokenize datasets/r2/heldout.jsonl --first-step-only --w-first 1 --out datasets/r2/tok_heldout
                   --token-budget N leaves out own-win rows, the longest first, until all rows hold at most N tokens
                   (training time is tokens: about 18 ms each on the four T4s)

What an example is (build):
  * A run is cut into stretches: a new stretch starts when the harness shortened the history (ADK compaction) or added a
    message of its own (the chat template then drops the earlier thinking). One stretch = one example: the last request
    of the stretch plus its reply.
  * Note run (the relay gave the note, the real tests pass): the steps from the note onward are learned; the steps before
    are context. Kept only when the model's text after the note has no leak word, its first thinking is not a bare copy
    (>= 15 own words), a check command follows the last edit, no test or setup file was edited, no call is repeated, and
    every public name the fix adds and the tests use is in the prompt at the note.
  * Own win (solved without a note): the steps from the first source edit onward are learned (round 1 learned every step
    and tied). From a relay journal when there is one (exact); else rebuilt from the trace up to the first shortening.
    Traces store thinking without its trailing newlines (journals: 0-4 of them), so a rebuilt example gets the most
    common ending and is exact in token count, not in every token.
  * A step whose tool call failed (file or parameter errors, the call cap), whose reply the harness dropped, or that
    mixes visible text with a call is never learned (it stays as context).
What is checked (tokenize): for every learned step the prompt the server saw (the request before it, rendered with the
generation prompt) must be a token-for-token prefix of the example; the learned tokens are exactly what the model wrote
from there up to and including its end-of-step token. An example that fails is dropped, never repaired. A too long
example is cut after the last learned step that fits; one whose first learned step does not fit is dropped.
"""
import argparse, collections, csv, glob, json, os, random, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopsy as A
import convert_traces as CT
import probe as P

MODEL_DIR = "models/gemma-4-31b-it-qat-w4a16-ct"       # the SERVING model's tokenizer and chat template
ROOT = os.environ.get("GEMMA_ROOT", "/mnt/biohub/kdata/gemma4")
FREE = ("submit_patch", "get_status")
TRACE_THOUGHT_END = "\n\n"                             # the most common ending of real thinking (51 of 137 pilot steps)
from note_report import LEAK_RX                        # one leak rule for the report and for the builder


# ---- rendering ----------------------------------------------------------------------------------------------------
def template_messages(messages):
    """The request's messages as the server hands them to the chat template:
    - text content as a list of parts [{"type": "text", "text": ...}] (vLLM's "openai" content format; the Gemma
      template treats a list differently from a string, e.g. it adds a space after each part of the system message);
    - tool-call arguments as objects (JSON strings on the wire; the template raises on a string)."""
    out = []
    for m in messages:
        if isinstance(m.get("content"), str):
            m = dict(m, content=[{"type": "text", "text": m["content"]}])
        if m.get("role") == "assistant" and m.get("tool_calls"):
            tcs = []
            for tc in m["tool_calls"]:
                fn = dict(tc.get("function") or {}); a = fn.get("arguments")
                if isinstance(a, str):
                    try: fn["arguments"] = json.loads(a)
                    except Exception: pass
                tcs.append(dict(tc, function=fn))
            m = dict(m, tool_calls=tcs)
        out.append(m)
    return out


def render(tok, body, add_generation_prompt=True):
    kw = dict(body.get("chat_template_kwargs") or {}); kw.setdefault("enable_thinking", True)
    return tok.apply_chat_template(template_messages(body["messages"]), tools=body.get("tools"), tokenize=False,
                                   add_generation_prompt=add_generation_prompt, **kw)


def ids_of(tok, text): return tok(text, add_special_tokens=False)["input_ids"]


def load_tok(model_dir):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(model_dir)


def server_tokens(url, body):
    req = {"model": body["model"], "messages": body["messages"], "tools": body.get("tools"), "add_generation_prompt": True,
           "chat_template_kwargs": body.get("chat_template_kwargs") or {"enable_thinking": True}}
    r = urllib.request.Request(url + "/tokenize", data=json.dumps(req).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=600))


def show_diff(tok, mine, theirs):
    k = next((i for i, (x, y) in enumerate(zip(mine, theirs)) if x != y), min(len(mine), len(theirs)))
    print(f"      first difference at token {k}: local {tok.decode(mine[max(0, k - 12):k + 12])!r}")
    print(f"      {'':27}server {tok.decode(theirs[max(0, k - 12):k + 12])!r}")


def cmd_check_render(a):
    tok = load_tok(a.model); recs, info = P.load_dumps(a.dumps); print(f"request log {a.dumps}: {info}")
    random.Random(a.seed).shuffle(recs)                 # a mix of early and late steps of many runs
    same = 0; n = 0; sizes = []
    for r in recs[: a.n]:
        body = P.dump_body(r); mine = ids_of(tok, render(tok, body))
        try: srv = server_tokens(a.url, body)
        except Exception as e: print(f"   server tokenize failed: {type(e).__name__}: {e}"); return False
        theirs = srv.get("tokens") or []; n += 1; sizes.append(len(mine))
        if mine == theirs or (not theirs and srv.get("count") == len(mine)): same += 1
        else:
            print(f"   MISMATCH request with {r['n']} messages: local {len(mine)} tokens, server {srv.get('count')}")
            if theirs: show_diff(tok, mine, theirs)
    print(f"== check-render: {same} of {n} requests tokenise exactly like the server (prompt tokens {min(sizes)}..{max(sizes)})")
    return same == n and n > 0


def cmd_check_journal(a):
    tok = load_tok(a.model); ex = []
    for jd in a.journal:
        for f in sorted(glob.glob(os.path.join(jd, "*.jsonl"))):
            if os.path.basename(f) == "events.jsonl": continue
            for line in open(f, encoding="utf-8"):
                r = json.loads(line)
                if ((r.get("reply") or {}).get("usage") or {}).get("prompt_tokens"): ex.append(r)
    random.Random(a.seed).shuffle(ex)
    out = collections.Counter(); bad = 0
    for kind in ("plain", "noted"):
        pick = [r for r in ex if bool(r.get("noted")) == (kind == "noted")][: a.n]
        for r in pick:
            mine = len(ids_of(tok, render(tok, r["request"]))); srv = r["reply"]["usage"]["prompt_tokens"]
            d = mine - srv; out[(kind, "equal" if d == 0 else f"off by {d:+d}")] += 1
            if d and bad < 5:
                bad += 1; print(f"   {kind} {r['iid']} seq {r['seq']}: local {mine}, server {srv} ({r['n_messages']} messages)")
    for (kind, what), v in sorted(out.items()): print(f"   {kind:6s} {what:14s} {v}")
    plain_ok = all(what == "equal" for (kind, what) in out if kind == "plain") and any(kind == "plain" for kind, _ in out)
    print(f"== check-journal: plain requests {'ALL EQUAL' if plain_ok else 'NOT all equal'}; "
          f"noted requests show the server count lowered by the note's size (equal = the lowering is exact)")
    return plain_ok


# ---- runs -> steps ------------------------------------------------------------------------------------------------
def jload(s):
    try:
        o = json.loads(s) if isinstance(s, str) else s
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def ids(path): return [l.strip() for l in open(path) if l.strip() and not l.startswith("#")]


def reply_message(reply):
    """The assistant message the harness puts into its next request for this reply: LiteLlm copies the server's
    `reasoning` into `reasoning_content` and `reasoning` and keeps the tool calls as they are (170 of 170 pilot steps)."""
    m = ((reply or {}).get("choices") or [{}])[0].get("message") or {}
    out = {"role": "assistant"}
    if m.get("content"): out["content"] = m["content"]
    if m.get("tool_calls"): out["tool_calls"] = m["tool_calls"]
    r = m.get("reasoning") or m.get("reasoning_content")
    if r: out["reasoning_content"] = r; out["reasoning"] = r
    return out


def same_reply(a, b):
    return ((a.get("tool_calls") or []) == (b.get("tool_calls") or []) and (a.get("content") or None) == (b.get("content") or None)
            and (a.get("reasoning_content") or a.get("reasoning") or "") == (b.get("reasoning_content") or b.get("reasoning") or ""))


def call_id(msg): return ((msg.get("tool_calls") or [{}])[0]).get("id")


def journal_steps(path):
    """One dict per model reply of a relay journal, in order. M = the messages of its request (note-free), msg = the
    reply as an assistant message, seg = the stretch it belongs to, kept = the harness put the reply into its history,
    result = the content of its tool result."""
    recs = sorted((json.loads(l) for l in open(path, encoding="utf-8")), key=lambda r: r["seq"])
    recs = [r for r in recs if ((r.get("reply") or {}).get("choices"))]
    out = []; seg = 0
    for i, r in enumerate(recs):
        M = r["request"]["messages"]
        if i:
            prev = recs[i - 1]["request"]["messages"]; grown = M[len(prev):] if M[:len(prev)] == prev else None
            if grown is None or any(m.get("role") == "user" for m in grown): seg += 1
        out.append({"M": M, "msg": reply_message(r["reply"]), "seg": seg, "event": r.get("event") or "pass", "noted": bool(r.get("noted")),
                    "tools": r["request"].get("tools"), "usage": (r["reply"].get("usage") or {}).get("prompt_tokens"), "kept": True, "result": None})
    for i, e in enumerate(out):
        nxt = out[i + 1] if i + 1 < len(out) else None
        if nxt is None: continue
        if nxt["M"][:len(e["M"])] == e["M"]:                        # the next request extends this one
            new = nxt["M"][len(e["M"]):]
            e["kept"] = bool(new) and new[0].get("role") == "assistant" and same_reply(new[0], e["msg"])
            if e["kept"]: e["result"] = next((m.get("content") for m in new[1:] if m.get("role") == "tool" and m.get("tool_call_id") == call_id(e["msg"])), None)
        else:                                                      # the history was shortened after this reply
            e["result"] = next((m.get("content") for m in nxt["M"] if m.get("role") == "tool" and m.get("tool_call_id") == call_id(e["msg"])), None)
    return out


def trace_steps(path, bundle):
    """The same step list rebuilt from a trace (runs made without the relay), up to the first history shortening.
    None when the trace has a harness nudge or a step the parser does not understand."""
    system, task, items, clean = P.trace_items(json.load(open(path, errors="replace")))
    if not clean or not items or any(it["type"] == "user" for it in items): return None
    items = [dict(it, thought=(it["thought"] + TRACE_THOUGHT_END) if it["thought"] else it["thought"]) for it in items]
    sysc = bundle.system_content(); tools = bundle.declarations(); eu = P.exact_until(items); out = []
    for k, it in enumerate(items[:eu]):
        full = P.build_messages(sysc, task, items, k + 1); M = P.build_messages(sysc, task, items, k)
        kept = bool(it["call"] or it["text"])
        msg = full[len(M)] if kept and len(full) > len(M) else {"role": "assistant"}
        out.append({"M": M, "msg": msg, "seg": 0, "event": "pass", "noted": False, "tools": tools, "usage": it["prompt_tokens"],
                    "kept": kept, "result": P.obs_content(it["obs"]) if it["call"] and it["obs"] is not None else None})
    return out


# A file the model creates for itself in the workspace root (a reproduction or check script). Many are named test_*.py,
# which the harness's rule calls protected; they are scratch files, not the project's tests.
SCRATCH_RX = re.compile(r"^(test_|tests_|reproduce|repro|check_|debug|verify|demo|tmp_|scratch|final_test|comprehensive|edge_case|minimal)[^/]*\.(py|sh|txt|json)$", re.I)


def describe(steps, declared):
    """Adds per step: name, args, ok, path, masked (never learned), and marks source edits and edits of the project's
    own test or setup files (a scratch script the model wrote itself is neither)."""
    seen = set(); scratch = set()
    for e in steps:
        fn = ((e["msg"].get("tool_calls") or [{}])[0]).get("function") or {}
        e["name"] = fn.get("name"); e["args"] = jload(fn.get("arguments")); o = jload(e["result"])
        e["ok"] = o.get("status") == "ok"
        p = A.clean_path(e["args"].get("filepath")) if isinstance(e["args"].get("filepath"), str) else ""
        e["path"] = p
        masked, why = CT.classify_observation(e["name"] or "", e["result"] if isinstance(e["result"], str) else "", declared) if e["name"] else (False, None)
        if e["name"] and e["msg"].get("content"): masked, why = True, "text with a call"     # the template moves the text behind the call
        if not e["kept"]: masked, why = True, "reply dropped by the harness"
        e["masked"] = masked; e["mask_reason"] = why
        if e["name"] == "write_file" and e["ok"] and p and p not in seen and SCRATCH_RX.match(p): scratch.add(p)
        e["source_edit"] = bool(e["ok"] and p and not A.is_protected(p) and p not in scratch and (e["name"] == "edit_file" or (e["name"] == "write_file" and p in seen)))
        e["protected_edit"] = bool(e["ok"] and p and A.is_protected(p) and p not in scratch and e["name"] in ("edit_file", "write_file") and not p.startswith("/tmp/"))
        if e["name"] in ("read_file", "edit_file") and e["ok"] and p: seen.add(p)
    return steps


def supervised_checks(steps, start):
    """Reasons to drop a run, read from its learned part only."""
    part = steps[start:]; sig = [(e["name"], json.dumps(e["args"], sort_keys=True)) for e in part if e["name"]]
    edits = [i for i, e in enumerate(part) if e["name"] in ("edit_file", "write_file") and e["ok"]]
    why = []
    if any(e["protected_edit"] for e in part): why.append("a test or setup file was edited")
    if any(sig[i] == sig[i + 1] for i in range(len(sig) - 1)): why.append("a call is repeated")
    if not any(e["source_edit"] for e in part): why.append("no source edit in the learned part")
    return why, edits


def examples_of(steps, start, base):
    """One example per stretch that holds learned steps (index >= start)."""
    out = []
    for seg in sorted({e["seg"] for e in steps[start:]}):
        idx = [i for i, e in enumerate(steps) if e["seg"] == seg and (e["kept"] or i == len(steps) - 1)]
        idx = [i for i in idx if steps[i]["msg"].get("tool_calls") or steps[i]["msg"].get("content")]
        sup = [i for i in idx if i >= start and not steps[i]["masked"]]
        if not sup: continue
        last = steps[idx[-1]]
        out.append(dict(base, seg=seg, messages=last["M"] + [last["msg"]], tools=last["tools"], sup=[len(steps[i]["M"]) for i in sup],
                        first_sup=len(steps[sup[0]]["M"]), n_steps=len(sup)))
    return out


def cmd_build(a):
    hints = {}
    for f in a.hints or []:
        for line in open(f, encoding="utf-8"):
            r = json.loads(line); hints[r["instance_id"]] = r
    only = set(ids(a.only)) if a.only else None; excl = set()
    for f in a.exclude or []: excl |= set(ids(f))
    use = lambda iid: (only is None or iid in only) and iid not in excl
    bundle = P.Bundle(a.bundle); declared = set(bundle.tools)
    stats = collections.Counter(); drops = collections.Counter(); out = []; have_own = {}
    tok = load_tok(a.model) if a.own else None

    # 1. runs made through the relay: note runs, and wins without a note
    for tag in a.notes or []:
        run = os.path.join(ROOT, "results/replica", tag); jd = os.path.join(ROOT, "results/takeover", tag)
        if not os.path.exists(os.path.join(run, "results.csv")): print(f"   {tag}: no results.csv, skipped"); continue
        for r in csv.DictReader(open(os.path.join(run, "results.csv"))):
            iid = r["instance_id"]; jf = os.path.join(jd, iid + ".jsonl")
            if not use(iid): continue
            stats["runs"] += 1
            if not os.path.exists(jf): drops["no journal"] += 1; continue
            steps = describe(journal_steps(jf), declared); h = hints.get(iid) or {}
            t = next((i for i, e in enumerate(steps) if e["event"].startswith("takeover")), None)
            solved = r.get("resolved") == "True"
            if t is None:                                   # no note: an own win when solved
                stats["runs without a note"] += 1
                if not solved: continue
                s = next((i for i, e in enumerate(steps) if e["source_edit"]), None)
                if s is None: drops["own win: no source edit"] += 1; continue
                why, _ = supervised_checks(steps, s)
                if why: drops["own win: " + why[0]] += 1; continue
                ex = examples_of(steps, s, {"iid": iid, "repo": r.get("repo") or h.get("repo"), "kind": "own", "source": tag, "exact": True, "fix_lines": []})
                if ex: have_own[iid] = (sum(1 for e in steps if e["name"] and e["name"] not in FREE), ex); stats["own wins from journals"] += 1
                continue
            stats["note given"] += 1
            kind = "note_first" if steps[t]["event"].endswith("first_change") else "note_deadline"
            if not solved: drops["note run: tests fail"] += 1; continue
            stats["note runs that pass the tests"] += 1
            why, edits = supervised_checks(steps, t); part = steps[t:]
            text = "\n".join((e["msg"].get("reasoning_content") or "") + "\n" + (e["msg"].get("content") or "") for e in part)
            note_lines = {l.strip() for b in h.get("blocks") or [] for l in (b["old"] + "\n" + b["new"]).split("\n") if l.strip()}
            own_words = sum(len(l.split()) for l in (part[0]["msg"].get("reasoning_content") or "").split("\n") if l.strip() and l.strip() not in note_lines)
            if LEAK_RX.search(text): why.append("leak word")
            if own_words < 15: why.append("first thinking is a bare copy")
            if not (edits and any(e["name"] == "run_command" for e in part[edits[-1] + 1:])): why.append("no check after the last edit")
            if not part[0]["kept"] or part[0]["masked"]: why.append("the step at the note failed")
            ctx = json.dumps(steps[t]["M"], ensure_ascii=False)
            if any(n not in ctx for n in h.get("new_public_names") or []): why.append("a name of the fix is not in the prompt")
            if why:
                for w in why: drops["note run: " + w] += 1
                stats["note runs dropped"] += 1; continue
            fix_lines = sorted({l.strip() for b in h.get("blocks") or [] for l in b["new"].split("\n") if l.strip() and l not in b["old"].split("\n")})
            ex = examples_of(steps, t, {"iid": iid, "repo": r.get("repo") or h.get("repo"), "kind": kind, "source": tag, "exact": True, "fix_lines": fix_lines})
            if not ex: drops["note run: no learned step left"] += 1; continue
            out += ex; stats["clean note runs"] += 1; stats[f"clean {kind}"] += 1

    # 2. own wins of earlier runs (no relay): the run with the fewest calls per task, rebuilt from its trace
    cand = {}
    for run in a.own or []:
        run = run if os.path.isabs(run) else os.path.join(ROOT, run)
        for r in csv.DictReader(open(os.path.join(run, "results.csv"))):
            iid = r["instance_id"]
            if r.get("resolved") != "True" or not use(iid) or iid in have_own: continue
            calls = int(r.get("tool_calls") or 99)
            if iid not in cand or calls < cand[iid][0]: cand[iid] = (calls, run, r.get("repo"))
    for iid, (calls, run, repo) in sorted(cand.items()):
        stats["own wins considered (traces)"] += 1
        steps = trace_steps(os.path.join(run, "agent_run", "traces", f"trace_{iid}.json"), bundle)
        if steps is None: drops["own win: nudge or unreadable trace"] += 1; continue
        steps = describe(steps, declared)
        s = next((i for i, e in enumerate(steps) if e["source_edit"]), None)
        if s is None: drops["own win: no source edit before the history was shortened"] += 1; continue
        why, _ = supervised_checks(steps, s)
        if why: drops["own win: " + why[0]] += 1; continue
        body = {"messages": steps[s]["M"], "tools": steps[s]["tools"]}
        if steps[s]["usage"] and len(ids_of(tok, render(tok, body))) != steps[s]["usage"]: drops["own win: token count differs from the server's"] += 1; continue
        ex = examples_of(steps, s, {"iid": iid, "repo": repo, "kind": "own", "source": os.path.basename(run), "exact": False, "fix_lines": []})
        if ex: have_own[iid] = (calls, ex); stats["own wins from traces"] += 1
    for iid, (calls, ex) in sorted(have_own.items()): out += ex

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for e in out: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    kinds = collections.Counter(e["kind"] for e in out); tasks = collections.defaultdict(set)
    for e in out: tasks[e["kind"]].add(e["iid"])
    st = {"stats": dict(stats), "drops": dict(drops), "examples": dict(kinds), "tasks": {k: len(v) for k, v in tasks.items()},
          "note_tasks": sorted(tasks["note_first"] | tasks["note_deadline"]), "out": a.out}
    json.dump(st, open(os.path.splitext(a.out)[0] + ".stats.json", "w"), indent=1)
    print(f"== build -> {a.out}: {len(out)} examples | " + ", ".join(f"{k} {v} (from {len(tasks[k])} tasks)" for k, v in sorted(kinds.items())))
    for k, v in sorted(stats.items()): print(f"   {v:5d}  {k}")
    for k, v in sorted(drops.items(), key=lambda x: -x[1]): print(f"   {v:5d}  dropped: {k}")
    return True


# ---- examples -> tokens ---------------------------------------------------------------------------------------------
def cmd_tokenize(a):
    import pyarrow as pa, pyarrow.parquet as pq
    tok = load_tok(a.model); weights = {"note_first": a.w_first, "note_deadline": a.w_deadline, "own": a.w_own}
    end_ids = {tok.convert_tokens_to_ids("<|tool_response>"), tok.convert_tokens_to_ids("<turn|>")}
    rows = []; stats = collections.Counter(); per_kind = collections.defaultdict(lambda: collections.Counter()); lost = []
    for line in open(a.data, encoding="utf-8"):
        s = json.loads(line); body = {"messages": s["messages"], "tools": s["tools"], "chat_template_kwargs": {"enable_thinking": True}}
        text = render(tok, body, add_generation_prompt=False)
        enc = tok(text, add_special_tokens=False, return_offsets_mapping=True); full = enc["input_ids"]; offs = enc["offset_mapping"]
        spans = []; ok = True
        for n_ctx in s["sup"]:
            p = ids_of(tok, render(tok, dict(body, messages=s["messages"][:n_ctx]), add_generation_prompt=True))
            if full[:len(p)] != p: ok = False; break
            e = next((i for i in range(len(p), len(full)) if full[i] in end_ids), None)
            if e is None: ok = False; break
            spans.append((len(p), e + 1))
        stats["examples"] += 1
        if not ok or not spans: stats["dropped: the prompt is not a prefix of the example"] += 1; lost.append((s["iid"], s["kind"], "prefix")); continue
        fit = [(b, e) for b, e in spans if e <= a.max_len]
        if not fit or fit[0] != spans[0]:
            stats["dropped: the first learned step does not fit"] += 1; per_kind[s["kind"]]["too long"] += 1; lost.append((s["iid"], s["kind"], f"too long ({spans[0][1]} tokens to the first learned step)")); continue
        if a.first_step_only: fit = fit[:1]                    # held-out rows: the prompt at the note and the first step after it
        elif len(fit) < len(spans): stats["cut after the last learned step that fits"] += 1
        end = fit[-1][1]; ids_ = full[:end]; labels = [-100] * end; fix = [-100] * end
        for b, e in fit: labels[b:e] = ids_[b:e]
        b0, e0 = fit[0]; c0, c1 = offs[b0][0], offs[e0 - 1][1]; step_text = text[c0:c1]
        for fl in s.get("fix_lines") or []:                    # tokens of the fix's new lines inside the first learned step
            pos = step_text.find(fl)
            while pos >= 0:
                lo, hi = c0 + pos, c0 + pos + len(fl)
                for i in range(b0, e0):
                    if offs[i][0] < hi and offs[i][1] > lo: fix[i] = ids_[i]
                pos = step_text.find(fl, pos + len(fl))
        nsup = sum(1 for x in labels if x != -100); w = weights.get(s["kind"], 1)
        for rep in range(w):
            rows.append({"input_ids": ids_, "labels": labels, "fix_labels": fix, "n": end, "kind": s["kind"], "iid": s["iid"], "repo": s.get("repo") or "",
                         "source": s.get("source") or "", "copy": rep})
        k = per_kind[s["kind"]]; k["examples"] += 1; k["rows"] += w; k["tokens"] += end * w; k["learned tokens"] += nsup * w
        k["fix tokens"] += sum(1 for x in fix if x != -100)
    if a.token_budget:                                         # training time is tokens: own wins give way, the longest first
        total = sum(r["n"] for r in rows); drop = set(); k = per_kind["own"]
        for r in sorted((r for r in rows if r["kind"] == "own"), key=lambda r: -r["n"]):
            if total <= a.token_budget: break
            drop.add(id(r)); total -= r["n"]; stats["own rows left out for the token budget"] += 1
            k["rows"] -= 1; k["tokens"] -= r["n"]; k["learned tokens"] -= sum(1 for x in r["labels"] if x != -100); k["left out for the budget"] += 1
        rows = [r for r in rows if id(r) not in drop]
        if total > a.token_budget: stats["tokens over the budget after all own rows were left out"] = total - a.token_budget
    os.makedirs(a.out, exist_ok=True)
    random.Random(a.seed).shuffle(rows)
    pq.write_table(pa.Table.from_pylist(rows), f"{a.out}/train.parquet")
    ns = sorted(r["n"] for r in rows) or [0]
    st = {"rows": len(rows), "tokens": sum(ns), "learned_tokens": sum(sum(1 for x in r["labels"] if x != -100) for r in rows), "max_len": a.max_len,
          "tokens_median": ns[len(ns) // 2], "tokens_max": ns[-1], "stats": dict(stats), "per_kind": {k: dict(v) for k, v in per_kind.items()},
          "weights": weights, "lost": lost, "tasks": sorted({r["iid"] for r in rows}), "model": a.model}
    json.dump(st, open(f"{a.out}/stats.json", "w"), indent=1)
    print(f"== tokenize -> {a.out}/train.parquet: {len(rows)} rows, {st['tokens']:,} tokens ({st['learned_tokens']:,} learned), "
          f"median {st['tokens_median']}, max {st['tokens_max']} (limit {a.max_len})")
    for k, v in sorted(per_kind.items()): print(f"   {k:14s} {dict(v)}")
    for k, v in sorted(stats.items()): print(f"   {v:5d}  {k}")
    return True


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check-render"); p.add_argument("--dumps", required=True); p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--n", type=int, default=50); p.add_argument("--seed", type=int, default=0); p.add_argument("--model", default=MODEL_DIR)
    p = sub.add_parser("check-journal"); p.add_argument("--journal", nargs="+", required=True)
    p.add_argument("--n", type=int, default=50); p.add_argument("--seed", type=int, default=0); p.add_argument("--model", default=MODEL_DIR)
    p = sub.add_parser("build"); p.add_argument("--notes", nargs="*"); p.add_argument("--hints", nargs="*"); p.add_argument("--own", nargs="*")
    p.add_argument("--bundle", default="submissions/budgetfit_v5"); p.add_argument("--only"); p.add_argument("--exclude", nargs="*")
    p.add_argument("--out", required=True); p.add_argument("--model", default=MODEL_DIR)
    p = sub.add_parser("tokenize"); p.add_argument("data"); p.add_argument("--out", required=True); p.add_argument("--max-len", type=int, default=14336)
    p.add_argument("--w-first", type=int, default=2); p.add_argument("--w-deadline", type=int, default=1); p.add_argument("--w-own", type=int, default=1)
    p.add_argument("--seed", type=int, default=0); p.add_argument("--model", default=MODEL_DIR)
    p.add_argument("--first-step-only", action="store_true", help="keep each example up to its first learned step (held-out rows for heldout_loss.py)")
    p.add_argument("--token-budget", type=int, default=0, help="at most this many tokens in all rows: own-win rows are left out, the longest "
                                                               "first, until the set fits (0 = no budget; note rows are never left out)")
    a = ap.parse_args()
    ok = {"check-render": cmd_check_render, "check-journal": cmd_check_journal, "build": cmd_build, "tokenize": cmd_tokenize}[a.cmd](a)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
