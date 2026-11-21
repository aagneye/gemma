#!/usr/bin/env python3
"""Small token sets for the GPU test of the round-2 training steps (r2_gpu_smoke.sh). CPU only.

  .venv/bin/python smoke_rows.py --rows datasets/r2/tok_len_16384 --heldout datasets/r2/tok_heldout_pc --out datasets/r2
Writes, for each length limit N in --lengths:
  <out>/tok_smoke_<N>/train.parquet   3 short rows, one row as long as the limit allows (does a full row train once the
                                      optimizer holds its state?), and one row that cannot fit (two long rows joined,
                                      about 30k tokens: does the trainer leave it out and go on?)
  <out>/tok_smoke_<N>/seed.txt        a trainer seed whose shuffle puts the full row after the first update, the row that
                                      cannot fit after the full row, and a short row last (found by running the
                                      trainer's own data loader): the full row is judged before anything failed
and <out>/tok_heldout_smoke/train.parquet: the 3 shortest held-out rows.
"""
import argparse, os, sys

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_qlora as TQ


def order(d, seed):
    """Row lengths in the order the trainer would see them (same data set class, loader and generator)."""
    ds = TQ.WindowDS(d, 10**6); g = torch.Generator(); g.manual_seed(seed)
    return [int(b["input_ids"].shape[1]) for b in DataLoader(ds, batch_size=1, shuffle=True, num_workers=2, generator=g)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True); ap.add_argument("--heldout", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--lengths", default="15360,14336,13312,12288")
    a = ap.parse_args()
    import pyarrow as pa, pyarrow.parquet as pq
    rows = sorted((r for r in pq.read_table(f"{a.rows}/train.parquet").to_pylist() if r.get("copy", 0) == 0), key=lambda r: r["n"])
    short = rows[:3]; big = rows[-2:]
    cant = dict(big[0], input_ids=big[0]["input_ids"] + big[1]["input_ids"], labels=big[0]["labels"] + big[1]["labels"],
                fix_labels=big[0]["fix_labels"] + big[1]["fix_labels"], n=big[0]["n"] + big[1]["n"], iid="cannot_fit")
    for n in [int(x) for x in a.lengths.split(",")]:
        full = max((r for r in rows if r["n"] <= n), key=lambda r: r["n"])
        d = f"{a.out}/tok_smoke_{n}"; os.makedirs(d, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(short + [full, cant]), f"{d}/train.parquet")
        seed = next((s for s in range(64) if (lambda o: 1 <= o.index(full["n"]) < o.index(cant["n"]) <= 3)(order(d, s))), None)
        assert seed is not None, "no seed gives the wanted order"
        open(f"{d}/seed.txt", "w").write(str(seed))
        print(f"{d}: short {[r['n'] for r in short]}, full {full['n']}, cannot fit {cant['n']}; seed {seed} -> order {order(d, seed)}")
    held = sorted(pq.read_table(f"{a.heldout}/train.parquet").to_pylist(), key=lambda r: r["n"])[:3]
    os.makedirs(f"{a.out}/tok_heldout_smoke", exist_ok=True)
    pq.write_table(pa.Table.from_pylist(held), f"{a.out}/tok_heldout_smoke/train.parquet")
    print(f"{a.out}/tok_heldout_smoke: rows {[r['n'] for r in held]}")


if __name__ == "__main__":
    main()
