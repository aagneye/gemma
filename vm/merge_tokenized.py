#!/usr/bin/env python3
"""Merge several tokenized parquet dirs (from prepare_data.py --tokenize) into one training dir.
  python merge_tokenized.py --out datasets/sft/tok_12b_8k datasets/sft/tok_12b_8k_swehero datasets/sft/tok_12b_8k_nebius
"""
import argparse, os, random
import pyarrow as pa, pyarrow.parquet as pq

ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("dirs", nargs="+"); ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
rows = []
for d in a.dirs:
    t = pq.read_table(f"{d}/train.parquet").to_pylist(); print(d, len(t)); rows += t
random.Random(a.seed).shuffle(rows)
os.makedirs(a.out, exist_ok=True); pq.write_table(pa.Table.from_pylist(rows), f"{a.out}/train.parquet")
ns = sorted(r["n"] for r in rows); sup = sum(sum(1 for x in r["labels"] if x != -100) for r in rows)
print(f"merged {len(rows)} windows -> {a.out}; tokens total {sum(ns):,} median {ns[len(ns)//2]} p90 {ns[int(len(ns)*.9)]}; supervised {sup:,}")
