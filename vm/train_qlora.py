#!/usr/bin/env python3
"""QLoRA SFT for Gemma 4 on the 4x T4 VM (fp16, sm75) or an H100 (bf16).

Recipe validated by scripts/gpu_smoke_chunked.py on a T4 (12B NF4 + LoRA r32: 2k tokens 12.5 GB peak,
4k tokens 13.3 GB, ~150-180 tok/s per GPU):
  * NF4 QLoRA on `gemma-4-*-it-qat-q4_0-unquantized`, all language linear layers, vision excluded.
  * NO prepare_model_for_kbit_training (it upcasts the 262k x H embedding table to fp32 = ~4 GB on 12B).
  * Chunked cross-entropy with final-logit softcapping (Gemma) so full-vocab logits are never materialised.
  * Labels precomputed by prepare_data.py (loss on model-turn spans only, tool responses masked).

Single GPU:
  python train_qlora.py --model models/gemma-4-12B-it-qat-q4_0-unquantized --data datasets/sft/tok_12b_8k --out runs/smoke --epochs 0.02
4x T4 data-parallel (each rank holds the 4-bit model; LoRA grads all-reduced by DDP):
  torchrun --nproc_per_node 4 train_qlora.py --model ... --data ... --out runs/12b_r32_v1 --epochs 2 --grad-accum 4
"""
from __future__ import annotations
import argparse, json, math, os, time
import torch
from torch.utils.data import Dataset, DataLoader
from torch.utils.checkpoint import checkpoint


class WindowDS(Dataset):
    def __init__(self, parquet_dir, max_len):
        import pyarrow.parquet as pq
        t = pq.read_table(f"{parquet_dir}/train.parquet").to_pylist()
        self.rows = [r for r in t if r["n"] <= max_len]
    def __len__(self): return len(self.rows)
    def __getitem__(self, i):
        r = self.rows[i]
        return {"input_ids": torch.tensor(r["input_ids"]), "labels": torch.tensor(r["labels"])}


def build_model(path, rank, alpha, local_rank, four_bit=True, resume=None):
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, PeftModel
    # T4 (sm75) reports *emulated* bf16 support; only use bf16 on Ampere+ (H100/A100/L4)
    bf16 = torch.cuda.get_device_capability(local_rank)[0] >= 8; dt = torch.bfloat16 if bf16 else torch.float16
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dt,
                               bnb_4bit_use_double_quant=True) if four_bit else None
    m = AutoModelForCausalLM.from_pretrained(path, quantization_config=quant, dtype=dt, device_map={"": local_rank}, attn_implementation="sdpa")
    m.config.use_cache = False
    m.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False}); m.enable_input_require_grads()
    targets = r".*(language_model|model\.layers).*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)$"
    if resume:
        m = PeftModel.from_pretrained(m, resume, is_trainable=True)
    else:
        m = get_peft_model(m, LoraConfig(r=rank, lora_alpha=alpha or rank, lora_dropout=0.0, bias="none", task_type="CAUSAL_LM", target_modules=targets))
    return m, dt


class ChunkedLM(torch.nn.Module):
    """Computes mean CE over labelled positions without materialising [L, 262144] logits.
    It is an nn.Module whose forward() is the whole loss computation, so it can be wrapped in DDP:
    DDP only all-reduces gradients when the forward runs THROUGH the DDP wrapper (reducer.prepare_for_backward).
    (Run 12b_r32_v3 called the base model directly, so the 4 ranks never synchronised gradients.)"""
    def __init__(self, peft_model, chunk=1024):
        super().__init__()
        self.peft = peft_model                                       # registers the LoRA params as submodule params
        self.base = peft_model.base_model.model                     # Gemma4*ForConditionalGeneration
        self.lm_head = self.base.lm_head
        tc = self.base.config.get_text_config() if hasattr(self.base.config, "get_text_config") else self.base.config
        self.softcap = getattr(tc, "final_logit_softcapping", None); self.chunk = chunk
    def _chunk_loss(self, h, tgt):
        lg = self.lm_head(h).float()
        if self.softcap: lg = torch.tanh(lg / self.softcap) * self.softcap
        return torch.nn.functional.cross_entropy(lg, tgt, ignore_index=-100, reduction="sum")
    def forward(self, input_ids, labels):
        h = self.base.model(input_ids=input_ids, use_cache=False).last_hidden_state[0]   # [L, H]
        hs, tgt = h[:-1], labels[0, 1:]
        n = (tgt != -100).sum().clamp(min=1)
        tot = torch.zeros((), device=h.device, dtype=torch.float32)
        for s in range(0, hs.shape[0], self.chunk):
            tot = tot + checkpoint(self._chunk_loss, hs[s:s + self.chunk], tgt[s:s + self.chunk], use_reentrant=False)
        return tot / n, n.detach()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--max-len", type=int, default=8192); ap.add_argument("--rank", type=int, default=32); ap.add_argument("--alpha", type=int, default=None)
    ap.add_argument("--lr", type=float, default=1e-4); ap.add_argument("--epochs", type=float, default=2); ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--warmup", type=float, default=0.03); ap.add_argument("--save-every", type=int, default=100); ap.add_argument("--log-every", type=int, default=5)
    ap.add_argument("--no-4bit", action="store_true"); ap.add_argument("--resume", default=None); ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=512, help="tokens per cross-entropy chunk (512 -> ~0.5 GB fp32 logits on a 262k vocab)")
    a = ap.parse_args()
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.makedirs(a.out, exist_ok=True)
    local_rank = int(os.environ.get("LOCAL_RANK", 0)); world = int(os.environ.get("WORLD_SIZE", 1)); rank = int(os.environ.get("RANK", 0))
    torch.cuda.set_device(local_rank)
    if world > 1: torch.distributed.init_process_group("nccl")
    is_main = rank == 0
    log = open(f"{a.out}/train_log.jsonl", "a") if is_main else None
    from transformers import AutoTokenizer, get_cosine_schedule_with_warmup
    tok = AutoTokenizer.from_pretrained(a.model)
    model, dt = build_model(a.model, a.rank, a.alpha, local_rank, four_bit=not a.no_4bit, resume=a.resume)
    if is_main: model.print_trainable_parameters()
    lm = ChunkedLM(model, chunk=a.chunk)
    params = [p for p in model.parameters() if p.requires_grad]
    # Wrap the LOSS module (whose forward is what we call) so DDP actually synchronises gradients.
    ddp = torch.nn.parallel.DistributedDataParallel(lm, device_ids=[local_rank], find_unused_parameters=False,
                                                    gradient_as_bucket_view=True, broadcast_buffers=False) if world > 1 else None
    fwd = ddp if ddp is not None else lm

    ds = WindowDS(a.data, a.max_len)
    sampler = torch.utils.data.distributed.DistributedSampler(ds, shuffle=True, seed=0) if world > 1 else None
    dl = DataLoader(ds, batch_size=1, shuffle=sampler is None, sampler=sampler, num_workers=2, pin_memory=True)
    steps_per_epoch = math.ceil(len(dl) / a.grad_accum); total = a.max_steps or int(steps_per_epoch * a.epochs)
    try:
        import bitsandbytes as bnb; opt = bnb.optim.AdamW8bit(params, lr=a.lr, weight_decay=0.0)
    except Exception:
        opt = torch.optim.AdamW(params, lr=a.lr)
    sched = get_cosine_schedule_with_warmup(opt, max(1, int(a.warmup * total)), total)
    use_scaler = dt == torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=use_scaler, init_scale=2.0**14)
    if is_main:
        print(f"windows {len(ds)} | per-rank micro-batches/epoch {len(dl)} | optimizer steps total {total} | dtype {dt} | world {world}", flush=True)

    model.train(); step = 0; micro = 0; t0 = time.time(); tokens = 0; sup = 0; run_loss = 0.0; run_n = 0; skipped = 0
    ep = 0
    state_path = os.path.join(a.resume, "trainer_state.pt") if a.resume else None
    if state_path and os.path.exists(state_path):          # full resume: optimizer, scheduler, scaler, step
        st = torch.load(state_path, map_location=f"cuda:{local_rank}", weights_only=False)
        opt.load_state_dict(st["opt"]); sched.load_state_dict(st["sched"]); scaler.load_state_dict(st["scaler"])
        step = st["step"]; ep = st["epoch"]
        if is_main: print(f"resumed trainer state at step {step}, epoch {ep}", flush=True)
    while step < total:
        if sampler: sampler.set_epoch(ep)
        for batch in dl:
            ids = batch["input_ids"].cuda(local_rank, non_blocking=True); lab = batch["labels"].cuda(local_rank, non_blocking=True)
            sync_ctx = ddp.no_sync() if (ddp is not None and (micro + 1) % a.grad_accum != 0) else torch.autocast("cpu", enabled=False)
            with sync_ctx:
                with torch.autocast("cuda", dtype=dt):
                    loss, n_sup = fwd(ids, lab)
                # Never skip backward on one rank alone (that desynchronises DDP collectives). A non-finite loss is
                # back-propagated as-is: DDP averages it into every rank's grads, GradScaler (fp16) sees inf/nan on all
                # ranks and skips that optimizer step everywhere; for bf16 we zero the step below.
                if not torch.isfinite(loss): skipped += 1
                scaler.scale(loss / a.grad_accum).backward()
            micro += 1; tokens += ids.shape[1]; sup += int(n_sup); run_loss += float(loss.detach()) if torch.isfinite(loss) else 0.0; run_n += 1
            if micro % a.grad_accum == 0:
                scaler.unscale_(opt); gn = torch.nn.utils.clip_grad_norm_(params, 1.0)
                if not use_scaler and not torch.isfinite(gn):      # bf16 path: identical grads on all ranks -> consistent skip
                    opt.zero_grad(set_to_none=True)
                else:
                    scaler.step(opt)
                scaler.update(); opt.zero_grad(set_to_none=True); sched.step(); step += 1
                if world > 1 and (step <= 3 or step % a.save_every == 0):
                    # all ranks must hold identical LoRA weights if DDP really synchronises gradients
                    with torch.no_grad():
                        cs = torch.stack([sum(p.detach().double().sum() for p in params), sum(p.detach().double().abs().sum() for p in params)])
                    gathered = [torch.zeros_like(cs) for _ in range(world)]
                    torch.distributed.all_gather(gathered, cs)
                    if is_main:
                        ref = gathered[0]; ok = all(torch.allclose(g, ref, rtol=1e-9, atol=1e-6) for g in gathered)
                        msg = f"SYNC_{'OK' if ok else 'MISMATCH'} step {step} checksums " + " ".join(f"{float(g[1]):.6f}" for g in gathered)
                        print(msg, flush=True); log.write(json.dumps({"sync_check": msg}) + "\n"); log.flush()
                if is_main and step % a.log_every == 0:
                    el = time.time() - t0
                    rec = {"step": step, "epoch": round(step / steps_per_epoch, 3), "loss": round(run_loss / max(1, run_n), 4), "grad_norm": round(float(gn), 3),
                           "lr": sched.get_last_lr()[0], "tok_s_per_rank": round(tokens / el), "tok_s_total": round(tokens * world / el),
                           "sup_tokens": sup * world, "skipped_nonfinite": skipped, "elapsed_min": round(el / 60, 1),
                           "eta_min": round((el / step) * (total - step) / 60, 1), "mem_gb": round(torch.cuda.max_memory_allocated() / 2**30, 1)}
                    print(json.dumps(rec), flush=True); log.write(json.dumps(rec) + "\n"); log.flush(); run_loss = 0.0; run_n = 0
                if is_main and step % a.save_every == 0:
                    d = f"{a.out}/ckpt_{step}"
                    model.save_pretrained(d); tok.save_pretrained(d)
                    torch.save({"opt": opt.state_dict(), "sched": sched.state_dict(), "scaler": scaler.state_dict(),
                                "step": step, "epoch": ep}, os.path.join(d, "trainer_state.pt"))
                if step >= total: break
        ep += 1
    if world > 1: torch.distributed.barrier()
    if is_main:
        model.save_pretrained(f"{a.out}/final"); tok.save_pretrained(f"{a.out}/final")
        print(f"saved -> {a.out}/final (PEFT dir; copy to submission/adapters/main_lora/). skipped_nonfinite={skipped}", flush=True)
    if world > 1: torch.distributed.destroy_process_group()


if __name__ == "__main__":
    main()
