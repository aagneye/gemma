#!/usr/bin/env python3
"""Does the served adapter change the model's answers, and are they still valid tool calls? (round-2 plan, the check
"15 of 20 answers differ from the untrained model"; gate G1 of research/PLAN_TO_WIN.md on the VM.) Standard library only.

  python3 adapter_effect.py --examples datasets/r2/heldout.jsonl [datasets/r2/all.jsonl] --adapter main_lora [--n 20]
      [--url http://127.0.0.1:8000] [--base gemma-4-31b-it-qat-w4a16-ct] [--out results/r2_effect.json]
For n examples it sends the prompt of the first learned step twice at temperature 0, to the base model and to the
adapter, and compares the tool call (name and arguments). Prints how many differ and how many adapter answers are a
valid tool call. EFFECT PASS = at least 15 of 20 differ (scaled to n) and every adapter answer is a tool call.
"""
import argparse, concurrent.futures, json, random, urllib.request


def ask(url, model, s):
    body = {"model": model, "messages": s["messages"][: s["first_sup"]], "tools": s["tools"], "temperature": 0, "max_completion_tokens": 2048,
            "chat_template_kwargs": {"enable_thinking": True}, "thinking_token_budget": 1024}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    m = json.load(urllib.request.urlopen(req, timeout=3600))["choices"][0]["message"]
    tc = (m.get("tool_calls") or [{}])[0].get("function") or {}
    try: args = json.loads(tc.get("arguments") or "null")
    except Exception: args = None
    return {"name": tc.get("name"), "args": args, "valid": bool(tc.get("name")) and isinstance(args, dict)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", nargs="+", required=True); ap.add_argument("--adapter", default="main_lora")
    ap.add_argument("--base", default="gemma-4-31b-it-qat-w4a16-ct"); ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=20); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    ex = []; seen = set()
    for f in a.examples:
        for line in open(f, encoding="utf-8"):
            s = json.loads(line)
            if s["iid"] not in seen and s.get("seg", 0) == 0: seen.add(s["iid"]); ex.append(s)
    random.Random(a.seed).shuffle(ex); ex = ex[: a.n]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        base = list(pool.map(lambda s: ask(a.url, a.base, s), ex)); adap = list(pool.map(lambda s: ask(a.url, a.adapter, s), ex))
    differ = sum(1 for b, c in zip(base, adap) if (b["name"], b["args"]) != (c["name"], c["args"])); valid = sum(c["valid"] for c in adap)
    need = -(-15 * len(ex) // 20)
    ok = differ >= need and valid == len(ex)
    print(f"answers that differ from the base model: {differ} of {len(ex)} (need {need}); valid tool calls with the adapter: {valid} of {len(ex)}")
    print(f"EFFECT {'PASS' if ok else 'FAIL'}")
    if a.out: json.dump({"n": len(ex), "differ": differ, "valid": valid, "pass": ok, "tasks": [s["iid"] for s in ex]}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
