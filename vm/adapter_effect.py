#!/usr/bin/env python3
"""Does the served adapter change the model's answers, and are they still valid tool calls? (round-2 plan, the check
"15 of 20 answers differ from the untrained model"; gate G1 of research/PLAN_TO_WIN.md on the VM.) Standard library only.

  python3 adapter_effect.py --examples datasets/r2/heldout.jsonl [datasets/r2/all.jsonl] --adapter main_lora [--n 20]
      [--url http://127.0.0.1:8000] [--base gemma-4-31b-it-qat-w4a16-ct] [--out results/r2_effect.json]
For n prompts it sends the prompt of the first learned step twice at temperature 0, to the base model and to the
adapter, and compares the whole answer: the thinking and the tool call (name and arguments). Note examples come first
(the adapter was taught to act differently there); own wins only fill the sample, because on those prompts the adapter
was taught the base model's own answer and an equal tool call is the wanted result.
It also asks the base model a second time on 5 prompts: how often two answers of the SAME model differ (batching makes
temperature 0 not fully repeatable). That number is printed for reading the result; it is not part of the rule.
EFFECT PASS = at least 15 of 20 answers differ (scaled to n), and the adapter's answers are tool calls as often as the
base model's, give or take one, and in at least 9 of 10 cases. The check catches an adapter the server does not apply
and one that breaks the tool-call format. It says nothing about a gain: only the test on the EVAL tasks does.
"""
import argparse, concurrent.futures, json, random, urllib.request


def ask(url, model, s):
    body = {"model": model, "messages": s["messages"][: s["first_sup"]], "tools": s["tools"], "temperature": 0, "max_completion_tokens": 2048,
            "chat_template_kwargs": {"enable_thinking": True}, "thinking_token_budget": 1024}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        m = json.load(urllib.request.urlopen(req, timeout=3600))["choices"][0]["message"]
    except Exception as e:                                   # a refused or failed request is an answer that is no tool call
        return {"name": None, "args": None, "think": "", "text": f"request failed: {str(e)[:120]}", "valid": False, "failed": True}
    tc = (m.get("tool_calls") or [{}])[0].get("function") or {}
    try: args = json.loads(tc.get("arguments") or "null")
    except Exception: args = None
    return {"name": tc.get("name"), "args": args, "think": (m.get("reasoning_content") or m.get("reasoning") or "").strip(),
            "text": (m.get("content") or "").strip(), "valid": bool(tc.get("name")) and isinstance(args, dict)}


call = lambda r: (r["name"], json.dumps(r["args"], sort_keys=True))
whole = lambda r: (r["think"], r["text"]) + call(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", nargs="+", required=True); ap.add_argument("--adapter", default="main_lora")
    ap.add_argument("--base", default="gemma-4-31b-it-qat-w4a16-ct"); ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=20); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--out", default=None)
    ap.add_argument("--repeat", type=int, default=5, help="prompts on which the base model is asked twice (how repeatable is temperature 0?)")
    a = ap.parse_args()
    ex = []; seen = set()
    for f in a.examples:
        for line in open(f, encoding="utf-8"):
            s = json.loads(line)
            if s["iid"] not in seen: seen.add(s["iid"]); ex.append(s)          # the first stretch of each task
    is_note = lambda s: str(s.get("kind", "")).startswith("note")
    rnd = random.Random(a.seed); notes = [s for s in ex if is_note(s)]; own = [s for s in ex if not is_note(s)]
    rnd.shuffle(notes); rnd.shuffle(own); ex = (notes + own)[: a.n]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        base = list(pool.map(lambda s: ask(a.url, a.base, s), ex)); adap = list(pool.map(lambda s: ask(a.url, a.adapter, s), ex))
        again = list(pool.map(lambda s: ask(a.url, a.base, s), ex[: a.repeat]))
    n = len(ex); differ = sum(whole(b) != whole(c) for b, c in zip(base, adap)); differ_call = sum(call(b) != call(c) for b, c in zip(base, adap))
    noise = sum(whole(b) != whole(c) for b, c in zip(base, again)); vb = sum(b["valid"] for b in base); va = sum(c["valid"] for c in adap)
    failed = sum(1 for r in base + adap if r.get("failed"))
    need = -(-15 * n // 20); ok = n > 0 and differ >= need and va >= vb - 1 and va * 10 >= 9 * n and not failed
    print(f"prompts: {n} ({sum(1 for s in ex if is_note(s))} note examples, the rest own wins)")
    print(f"answers that differ from the base model: {differ} of {n} (need {need}); tool calls that differ: {differ_call}")
    print(f"the base model asked twice: {noise} of {len(again)} answers differ")
    print(f"valid tool calls: adapter {va} of {n}, base {vb} of {n}; failed requests: {failed}")
    print(f"EFFECT {'PASS' if ok else 'FAIL'}")
    if a.out:
        json.dump({"n": n, "differ": differ, "differ_call": differ_call, "base_twice_differ": noise, "base_twice_n": len(again), "valid": va, "valid_base": vb,
                   "failed": failed, "pass": ok, "tasks": [s["iid"] for s in ex]}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
