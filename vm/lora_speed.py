#!/usr/bin/env python3
"""Generation speed of a served model with and without a LoRA adapter (Nov 19, round-2 plan step 1).

The same requests as the Kaggle speed notebook (make_kaggle_speed.py): every request forces its number of output
tokens (ignore_eos) and starts with a unique tag (no prefix-cache hits). Cases: decode at 1 request x 500 tokens,
decode at 4 requests x 400 tokens, a ~6k-token prompt + 64 tokens. Standard library only.

  python3 lora_speed.py --arms base=gemma-4-31b-it-qat-w4a16-ct adapter=main_lora --out results/speed/t4_r16.json
      [--url http://127.0.0.1:8000] [--rounds 2] [--note "T4 x4, max_lora_rank 16"]
With arms named `base` and `adapter` it adds slowdown_<case>_c<requests> = adapter seconds / base seconds.
On a LoRA-enabled server `base` is the base model served beside the adapter; on Kaggle's L4s that costs x1.00-1.02
against a plain server (results/replica/lora1_l4_speed.txt).
"""
import argparse, concurrent.futures, json, os, time, urllib.request

LONG = " ".join(["The quick brown fox jumps over the lazy dog while the compiler reports a type error in module seven."] * 300)
CASES = (("decode", 1, 500, False), ("decode", 4, 400, False), ("long_prompt", 1, 64, True))


def one(url, mid, tag, n, long=False):
    text = (f"[{tag}] " + LONG + " Summarise the text above in one line.") if long else (
        f"[{tag}] Explain in detail how the Python import system finds and loads a module: sys.path, finders, loaders and caching. Write at least 400 words.")
    body = {"model": mid, "messages": [{"role": "user", "content": text}], "max_tokens": n, "temperature": 0, "ignore_eos": True,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    u = json.load(urllib.request.urlopen(req, timeout=3600))["usage"]
    return u["completion_tokens"], u["prompt_tokens"]


def bench(url, arm, mid, rounds, stamp):
    one(url, mid, f"{stamp}-warm-{arm}", 16); one(url, mid, f"{stamp}-warm-{arm}-long", 8, True)
    recs = []
    for case, conc, n, long in CASES:
        for r in range(rounds):
            t = time.time()
            with concurrent.futures.ThreadPoolExecutor(conc) as ex:
                res = list(ex.map(lambda i: one(url, mid, f"{stamp}-{arm}-{case}-{conc}-{r}-{i}", n, long), range(conc)))
            el = time.time() - t; out = sum(x[0] for x in res); inp = sum(x[1] for x in res)
            rec = {"arm": arm, "case": case, "concurrency": conc, "round": r, "out_tokens": out, "prompt_tokens": inp,
                   "sec": round(el, 2), "out_tok_s": round(out / el, 2)}
            recs.append(rec); print(rec, flush=True)
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", required=True, help="name=served-model-id, e.g. base=gemma-4-31b-it-qat-w4a16-ct adapter=main_lora")
    ap.add_argument("--out", required=True); ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--rounds", type=int, default=2); ap.add_argument("--note", default="")
    a = ap.parse_args()
    arms = [x.split("=", 1) for x in a.arms]
    stamp = f"{int(time.time())}"                      # unique per run: no prefix-cache hit from an earlier run either
    report = {"note": a.note, "url": a.url, "arms": dict(arms), "runs": []}
    for arm, mid in arms:
        report["runs"] += bench(a.url, arm, mid, a.rounds, stamp)
    secs = lambda arm, case, conc: sum(x["sec"] for x in report["runs"] if x["arm"] == arm and x["case"] == case and x["concurrency"] == conc)
    toks = lambda arm, case, conc: sum(x["out_tokens"] for x in report["runs"] if x["arm"] == arm and x["case"] == case and x["concurrency"] == conc)
    for arm, _ in arms:
        for case, conc, n, long in CASES:
            report[f"{arm}_tok_s_{case}_c{conc}"] = round(toks(arm, case, conc) / secs(arm, case, conc), 2)
    if {"base", "adapter"} <= {x[0] for x in arms}:
        for case, conc, n, long in CASES:
            report[f"slowdown_{case}_c{conc}"] = round(secs("adapter", case, conc) / secs("base", case, conc), 3)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(report, open(a.out, "w"), indent=1)
    print({k: v for k, v in report.items() if k not in ("runs", "arms", "url")}, flush=True)


if __name__ == "__main__":
    main()
