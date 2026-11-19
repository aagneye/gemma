#!/usr/bin/env python3
"""Rank-sliced copy of a PEFT LoRA adapter, for SPEED tests only (Nov 19, round-2 plan step 1).

vLLM's decode cost with an adapter follows the server's max LoRA rank (see serve_vllm.sh), and the scorer sets that to
the largest rank in the bundle. So the cost of a rank-16 or rank-8 adapter can be measured before one is trained: keep
the first RANK rows of every lora_A and the first RANK columns of every lora_B of an existing adapter. The result is
not a useful model, only a file with the right shapes.

  .venv/bin/python slice_adapter.py runs/31b_bf5_v2_r32/final runs/31b_bf5_v2_r32/sliced_r16 --rank 16
Then package it like any adapter:
  make_submission.py --bundle submissions/budgetfit_v5 --adapter <out> --out submissions/<name>
"""
import argparse, json, shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out"); ap.add_argument("--rank", type=int, required=True)
    a = ap.parse_args()
    from safetensors.torch import load_file, save_file
    src, out = Path(a.src), Path(a.out)
    cfg = json.loads((src / "adapter_config.json").read_text())
    r0 = int(cfg["r"])
    assert 0 < a.rank <= r0, f"rank {a.rank} must be in 1..{r0}"
    w = load_file(str(src / "adapter_model.safetensors")); cut = {}; na = nb = 0
    for k, v in w.items():
        if ".lora_A." in k:
            assert v.shape[0] == r0, (k, tuple(v.shape))
            cut[k] = v[: a.rank, :].contiguous(); na += 1
        elif ".lora_B." in k:
            assert v.shape[1] == r0, (k, tuple(v.shape))
            cut[k] = v[:, : a.rank].contiguous(); nb += 1
        else:
            raise SystemExit(f"unexpected tensor {k}")
    assert na == nb and na > 0, (na, nb)
    alpha = a.rank * cfg.get("lora_alpha", r0) / r0          # same alpha/r scale as the source
    cfg["lora_alpha"] = int(alpha) if float(alpha).is_integer() else alpha
    cfg["r"] = a.rank
    out.mkdir(parents=True, exist_ok=True)
    (out / "adapter_config.json").write_text(json.dumps(cfg, indent=2))
    save_file(cut, str(out / "adapter_model.safetensors"))
    for f in src.iterdir():                                  # tokenizer and template files travel with the adapter
        if f.is_file() and f.name not in ("adapter_config.json", "adapter_model.safetensors"):
            shutil.copyfile(f, out / f.name)
    mib = (out / "adapter_model.safetensors").stat().st_size / 2**20
    print(f"sliced {src} r{r0} -> {out} r{a.rank}: {na} module pairs, {mib:.0f} MiB (speed tests only)")


if __name__ == "__main__":
    main()
