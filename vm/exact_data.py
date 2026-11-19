#!/usr/bin/env python3
"""Training examples in the exact form the model sees in a real run (Nov 19, round-2 plan).

Round 1 trained on 8-step windows with a hand-written summary of the earlier steps; the model never sees that form on
Kaggle. Here an example is the request the harness really sent (system prompt, task, every step with its thinking, tool
call and tool result, as recorded by the note relay or the request log), rendered with the serving model's own chat
template, followed by the model's replies. Nothing is summarised, capped or rewritten.

  check-render   local rendering against the SERVER's tokenizer endpoint, on logged requests (needs the server up):
                   .venv/bin/python exact_data.py check-render --dumps results/requests/confirm2 [--n 50] [--url http://127.0.0.1:8000]
  check-journal  local token count against the prompt_tokens the server reported, on a relay journal (no server needed):
                   .venv/bin/python exact_data.py check-journal --journal results/takeover/<tag> [--n 50]
Both must agree on every request before a dataset is built from the same code path (the review's rule: train only at
50 of 50). A public notebook's local rendering agreed with the server in 0 of 803 requests until it mirrored the
message fields (research/raw/07b_top_notebooks_large.md).
"""
import argparse, collections, glob, json, os, random, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe as P

MODEL_DIR = "models/gemma-4-31b-it-qat-w4a16-ct"       # the SERVING model's tokenizer and chat template


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


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check-render"); p.add_argument("--dumps", required=True); p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--n", type=int, default=50); p.add_argument("--seed", type=int, default=0); p.add_argument("--model", default=MODEL_DIR)
    p = sub.add_parser("check-journal"); p.add_argument("--journal", nargs="+", required=True)
    p.add_argument("--n", type=int, default=50); p.add_argument("--seed", type=int, default=0); p.add_argument("--model", default=MODEL_DIR)
    a = ap.parse_args()
    ok = cmd_check_render(a) if a.cmd == "check-render" else cmd_check_journal(a)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
