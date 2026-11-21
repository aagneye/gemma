#!/usr/bin/env python3
"""Sanity check of a trained adapter on held-out note examples (round-2 plan step 6). The GPUs must be free.

  .venv/bin/python heldout_loss.py --adapter runs/31b_r2_r16/final [--more runs/31b_r2_r16/ckpt_10 runs/31b_r2_r16/ckpt_20] \
      --data datasets/r2/tok_heldout --max-len 14336 [--out results/r2_heldout.json]
The rows come from `exact_data.py tokenize --first-step-only` on the dev tasks' note runs (never trained on): the prompt
at the note and the model's first step after it (its thinking and the first edit of the real fix).
For the base model (adapter off) and for each adapter it prints the mean loss per token over
  step   the whole first step after the note, and
  fix    only the tokens of the lines the real fix adds (the content of the change, not its shape),
and the ratio to the base. Rule fixed in the plan: the round stops when the adapter's `step` loss is not at least 10 %
below the base's. This catches a training that did not take; it is no proof of a gain (a public adapter in this
competition lowered its loss by 27 % and solved fewer tasks).
"""
import argparse, json, os, sys, time

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_qlora as TQ


def row_losses(lm, ids, label_sets, in_dev, dt):
    """[(sum of token losses, tokens)] for each label set, from one forward pass."""
    with torch.no_grad(), torch.autocast("cuda", dtype=dt):
        h = lm.base.model(input_ids=torch.tensor([ids], device=in_dev), use_cache=False).last_hidden_state[0]
        dev = lm.lm_head.weight.device; hs = h[:-1].to(dev)
        tg = [torch.tensor(l[1:], device=dev) for l in label_sets]; sums = [0.0] * len(tg)
        for s in range(0, hs.shape[0], lm.chunk):
            if not any(bool((t[s:s + lm.chunk] != -100).any()) for t in tg): continue
            lg = lm.lm_head(hs[s:s + lm.chunk]).float()
            if lm.softcap: lg = torch.tanh(lg / lm.softcap) * lm.softcap
            for i, t in enumerate(tg):
                sums[i] += float(torch.nn.functional.cross_entropy(lg, t[s:s + lm.chunk], ignore_index=-100, reduction="sum"))
    return [(sums[i], int((tg[i] != -100).sum())) for i in range(len(tg))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True); ap.add_argument("--more", nargs="*", default=[]); ap.add_argument("--data", required=True)
    ap.add_argument("--model", default="models/gemma-4-31B-it-qat-q4_0-unquantized"); ap.add_argument("--max-len", type=int, default=14336)
    ap.add_argument("--rank", type=int, default=16); ap.add_argument("--pipeline", type=int, default=4); ap.add_argument("--out", default=None)
    ap.add_argument("--need", type=float, default=0.90, help="the adapter's step loss must be at most this share of the base's")
    a = ap.parse_args()
    import pyarrow.parquet as pq
    rows = [r for r in pq.read_table(f"{a.data}/train.parquet").to_pylist() if r.get("copy", 0) == 0 and r["n"] <= a.max_len]
    assert rows, "no held-out rows"
    model, dt, devs = TQ.build_model(a.model, a.rank, None, 0, four_bit=True, resume=a.adapter, pipeline=a.pipeline, max_len=a.max_len, attn="qchunk")
    model.eval(); lm = TQ.ChunkedLM(model, chunk=512); in_dev = model.get_input_embeddings().weight.device
    arms = [("base", None), (os.path.basename(os.path.dirname(a.adapter.rstrip("/")) or a.adapter) + "/" + os.path.basename(a.adapter.rstrip("/")), "default")]
    for i, d in enumerate(a.more):
        model.load_adapter(d, adapter_name=f"more{i}"); arms.append((os.path.basename(d.rstrip("/")), f"more{i}"))
    res = {}; t0 = time.time()
    for name, adapter in arms:
        tot = [[0.0, 0], [0.0, 0]]
        for r in rows:
            if adapter is None:
                with model.disable_adapter(): out = row_losses(lm, r["input_ids"], [r["labels"], r["fix_labels"]], in_dev, dt)
            else:
                model.set_adapter(adapter); out = row_losses(lm, r["input_ids"], [r["labels"], r["fix_labels"]], in_dev, dt)
            for k in (0, 1): tot[k][0] += out[k][0]; tot[k][1] += out[k][1]
        res[name] = {"step_loss": tot[0][0] / max(1, tot[0][1]), "step_tokens": tot[0][1], "fix_loss": tot[1][0] / max(1, tot[1][1]), "fix_tokens": tot[1][1]}
        print(f"{name:28s} step loss {res[name]['step_loss']:.4f} over {tot[0][1]} tokens | fix loss {res[name]['fix_loss']:.4f} over {tot[1][1]} tokens "
              f"| {len(rows)} rows, {(time.time() - t0) / 60:.1f} min", flush=True)
    base = res["base"]; main_name = arms[1][0]
    for name, _ in arms[1:]:
        res[name]["step_ratio"] = res[name]["step_loss"] / max(1e-9, base["step_loss"]); res[name]["fix_ratio"] = res[name]["fix_loss"] / max(1e-9, base["fix_loss"])
        print(f"{name:28s} step loss x{res[name]['step_ratio']:.3f} of the base, fix loss x{res[name]['fix_ratio']:.3f}")
    ok = res[main_name]["step_ratio"] <= a.need
    print(f"SANITY {'PASS' if ok else 'FAIL'}: step loss x{res[main_name]['step_ratio']:.3f} of the base (need <= x{a.need}); rows {len(rows)}")
    if a.out: json.dump({"rows": len(rows), "need": a.need, "pass": ok, "arms": res}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
