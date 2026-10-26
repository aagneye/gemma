#!/usr/bin/env python3
"""Merge several tokenized parquet dirs (from prepare_data.py --tokenize) into one training dir.
  python merge_tokenized.py --out datasets/sft/tok_12b_8k datasets/sft/tok_12b_8k_swehero datasets/sft/tok_12b_8k_nebius
A dir may carry a repeat factor (`dir=2` duplicates its windows twice; shuffled with everything else), which is how
a small, valuable set (own 31B traces) is up-weighted against a large external one. Prints the token share per dir
and writes <out>/stats.json (the ">= 50 % external tokens" rule is checked from that).
"""
import argparse, json, os, random
import pyarrow as pa, pyarrow.parquet as pq

ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("dirs", nargs="+", help="tokenized dir or dir=repeat")
ap.add_argument("--seed", type=int, default=0); ap.add_argument("--max-len", type=int, default=0, help="drop windows longer than this (0 = keep all)")
a = ap.parse_args()
rows = []; shares = {}
for spec in a.dirs:
    d, _, rep = spec.partition("="); rep = int(rep or 1)
    t = pq.read_table(f"{d}/train.parquet").to_pylist()
    if a.max_len: t = [r for r in t if r["n"] <= a.max_len]
    for r in t: r.setdefault("repo", ""); r.setdefault("src", ""); r.setdefault("iid", "")
    tokens = sum(r["n"] for r in t) * rep; sup = sum(sum(1 for x in r["labels"] if x != -100) for r in t) * rep
    shares[d] = {"windows": len(t), "repeat": rep, "tokens": tokens, "supervised": sup}
    print(f"{d}: {len(t)} windows x{rep}, {tokens:,} tokens, {sup:,} supervised")
    rows += t * rep
random.Random(a.seed).shuffle(rows)
os.makedirs(a.out, exist_ok=True); pq.write_table(pa.Table.from_pylist(rows), f"{a.out}/train.parquet")
ns = sorted(r["n"] for r in rows); sup = sum(sum(1 for x in r["labels"] if x != -100) for r in rows); total = sum(ns)
for d, s in shares.items(): s["token_share"] = round(s["tokens"] / max(1, total), 3)
st = {"windows": len(rows), "tokens": total, "supervised": sup, "median": ns[len(ns)//2] if ns else 0, "p90": ns[int(len(ns)*.9)] if ns else 0,
      "max": ns[-1] if ns else 0, "sources": shares, "seed": a.seed, "max_len": a.max_len}
json.dump(st, open(f"{a.out}/stats.json", "w"), indent=1)
print(f"merged {len(rows)} windows -> {a.out}; tokens total {total:,} median {st['median']} p90 {st['p90']}; supervised {sup:,}; shares "
      + ", ".join(f"{os.path.basename(d.rstrip('/'))}={s['token_share']:.0%}" for d, s in shares.items()))
