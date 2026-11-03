#!/usr/bin/env python3
"""QLoRA SFT for Gemma 4 on the 4x T4 VM (fp16, sm75), an H100 (bf16) or Kaggle's 4x L4 (bf16, 31B pipeline).

Recipe validated by scripts/gpu_smoke_chunked.py on a T4 (12B NF4 + LoRA r32: 2k tokens 12.5 GB peak,
4k tokens 13.3 GB, ~150-180 tok/s per GPU):
  * NF4 QLoRA on `gemma-4-*-it-qat-q4_0-unquantized`, all language linear layers, vision/audio excluded.
  * NO prepare_model_for_kbit_training (it upcasts the 262k x H embedding table to fp32 = ~4 GB on 12B).
  * Chunked cross-entropy with final-logit softcapping (Gemma) so full-vocab logits are never materialised.
  * Labels precomputed by prepare_data.py (loss on model-turn spans only, tool responses masked).
E2B/E4B (2026-10-25): loaded through Gemma4ForConditionalGeneration so the PEFT keys carry
  `model.language_model.layers.N` (what the scorer's vLLM expects); the per-layer embedding table (PLE) and its
  projections stay fp16 (bnb skips them), the vision/audio towers are moved to the CPU; the KV-shared layers
  (last `num_kv_shared_layers`) have no k/v projections in transformers>=5.17, so no unused LoRA params exist.
31B on Kaggle 4x L4 (2026-11-03, launched by make_kaggle_train.py): the NF4 31B (~18 GB) does not fit one 24 GB card next
  to 16k activations, so --pipeline 4 cuts the decoder layers into blocks over the cards in ONE process (naive pipeline:
  one card computes at a time; cuda:0 also holds the bf16 embedding = tied lm_head and runs the chunked cross-entropy).
  --attn qchunk replaces SDPA, which has no fused kernel for the 10 head-dim-512 global layers and falls back to the math
  kernel (heads x L x L scores, ~16 GiB per layer at 16k), with query-chunked eager attention recomputed per chunk in
  backward. On bf16 cards (sm>=80) the LoRA master weights stay fp32, the forward runs under bf16 autocast and PEFT's
  fp32 input cast is switched off. --fit-probe measures one max-len forward+backward before training.

Single GPU:
  python train_qlora.py --model models/gemma-4-E4B-it-qat-q4_0-unquantized --data datasets/x/tok_e4b_7k --out runs/smoke --max-steps 20
Data-parallel over the free T4s (each rank holds the 4-bit model; LoRA grads all-reduced by DDP):
  torchrun --nproc_per_node 2 train_qlora.py --model ... --data ... --out runs/e4b_r32_v1 --epochs 1 --grad-accum 8
31B split over 4 GPUs (plain python, no torchrun):
  python train_qlora.py --model <gemma-4-31b-it-qat-q4_0-unquantized> --data <tok_31b_16k> --out runs/31b_r32 \
      --pipeline 4 --attn qchunk --max-len 16384 --optim adamw --epochs 1 --grad-accum 8 --fit-probe --deadline-min 660
"""
from __future__ import annotations
import argparse, gc, json, math, os, re, time
import torch
from torch.utils.data import Dataset, DataLoader
from torch.utils.checkpoint import checkpoint

# modules bitsandbytes must leave in the load dtype (substring match on the dotted module path)
SKIP_QUANT = ["lm_head", "vision_tower", "audio_tower", "embed_vision", "embed_audio",
              "per_layer_model_projection", "per_layer_input_gate", "per_layer_projection"]
LORA_NAMES = "q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj"
QCHUNK = {"chunk": 2048, "max_scores": 2**28, "calls": 0}   # --attn-chunk, --attn-max-scores; calls = attention layer calls


class WindowDS(Dataset):
    def __init__(self, parquet_dir, max_len):
        import pyarrow.parquet as pq
        t = pq.read_table(f"{parquet_dir}/train.parquet", columns=["input_ids", "labels", "n"]).to_pylist()
        self.rows = [r for r in t if r["n"] <= max_len]
        self.dropped = len(t) - len(self.rows)
    def __len__(self): return len(self.rows)
    def __getitem__(self, i):
        r = self.rows[i]
        return {"input_ids": torch.tensor(r["input_ids"]), "labels": torch.tensor(r["labels"])}


def _qchunk_block(q, k, v, allowed, scaling):
    # eager attention for one block of queries (bf16 matmuls, fp32 softmax, as transformers' eager_attention_forward);
    # q [B, Hkv, R*C, D] holds the R query heads of each kv head as rows, k/v [B, Hkv, S, D], allowed [C, S]
    b, hkv, rc, d = q.shape; c, s = allowed.shape
    w = torch.matmul(q, k.transpose(-1, -2))
    if scaling != 1.0: w = w * scaling
    w = w.view(b, hkv, rc // c, c, s).masked_fill(~allowed, float("-inf")).view(b, hkv, rc, s)
    return torch.matmul(torch.softmax(w, dim=-1, dtype=torch.float32).to(q.dtype), v)


def qchunk_attention(module, query, key, value, attention_mask, dropout=0.0, scaling=None, sliding_window=None, softcap=None, **kwargs):
    """Training-only causal attention, registered as attn_implementation "qchunk" (no KV cache, unpadded rows).
    Queries go in blocks whose score matrix stays under QCHUNK["max_scores"] elements; each block is recomputed in
    backward (checkpoint) and a sliding layer's block reads only the keys inside its window. Masks are built from
    positions: transformers passes attention_mask=None to an attention function without a registered mask builder,
    so no L x L mask is materialised or copied between the pipeline cards."""
    assert attention_mask is None and key.shape[2] == query.shape[2] and softcap is None and not dropout, \
        "qchunk is training-only causal attention (no mask, cache, softcap or dropout)"
    b, h, n, d = query.shape; hkv = key.shape[1]; r = h // hkv; win = sliding_window or 0
    scaling = module.head_dim ** -0.5 if scaling is None else scaling
    span = min(n, QCHUNK["chunk"] + win) if win else n                    # keys one block can see
    c = min(QCHUNK["chunk"], max(64, QCHUNK["max_scores"] // (h * span)))
    pos = torch.arange(n, device=query.device); outs = []
    for s in range(0, n, c):
        e = min(n, s + c); k0 = max(0, s - win + 1) if win else 0
        qi, kj = pos[s:e, None], pos[None, k0:e]
        allowed = (kj <= qi) & (kj > qi - win) if win else kj <= qi     # transformers: kv_idx > q_idx - sliding_window
        qb = query[:, :, s:e].reshape(b, hkv, r * (e - s), d)           # head kv*r+i reads kv head kv (repeat_kv layout)
        args = (qb, key[:, :, k0:e], value[:, :, k0:e], allowed, scaling)
        ob = checkpoint(_qchunk_block, *args, use_reentrant=False) if torch.is_grad_enabled() else _qchunk_block(*args)
        outs.append(ob.view(b, h, e - s, d).transpose(1, 2))
    QCHUNK["calls"] += 1
    return torch.cat(outs, dim=1), None                                  # [B, L, H, D] like sdpa_attention_forward


def use_qchunk(model, chunk, max_scores, log=print):
    from transformers import AttentionInterface
    AttentionInterface.register("qchunk", qchunk_attention); QCHUNK.update(chunk=chunk, max_scores=max_scores)
    model.config.get_text_config()._attn_implementation = "qchunk"     # text layers only; the unused vision tower keeps sdpa
    attn = [mod for mod in model.modules() if type(mod).__name__.endswith("TextAttention")]
    assert attn and all(mod.config._attn_implementation == "qchunk" for mod in attn), "qchunk is not active on the text attention layers"
    log(f"attention: qchunk on {len(attn)} layers (blocks of <= {chunk} queries and <= {max_scores / 2**20:.0f}M scores)")


def pipeline_device_map(Cls, cfg, n_gpu, max_len, rank, counts=None, log=print):
    """Naive pipeline in one process: the decoder layers in contiguous blocks over n_gpu cards (one card computes at a
    time); everything else (embedding = tied lm_head, norms, vision tower) on cuda:0, which also runs the chunked
    cross-entropy and so gets fewer layers."""
    from accelerate import init_empty_weights
    with init_empty_weights():
        meta = (Cls.from_config if hasattr(Cls, "from_config") else Cls._from_config)(cfg)
    tc = cfg.get_text_config() if hasattr(cfg, "get_text_config") else cfg; n = tc.num_hidden_layers
    lpath = next(name for name, mod in meta.named_modules() if name.endswith("layers") and isinstance(mod, torch.nn.ModuleList)
                 and len(mod) == n and "vision" not in name and "audio" not in name)
    if not counts:
        # bytes per layer: NF4 weights (~0.53 B/param with double quant) + fp32 LoRA weight, grad and 2 Adam moments
        # + its checkpointed bf16 input at max_len; cuda:0 extra: the bf16 embedding + 3 fp32 [512 x vocab] CE buffers
        layers = meta.get_submodule(lpath)
        lora = sum(rank * (mod.in_features + mod.out_features) for name, mod in layers.named_modules()
                   if isinstance(mod, torch.nn.Linear) and re.search(rf"\.({LORA_NAMES})$", name))
        per_layer = (0.53 * sum(p.numel() for p in layers.parameters()) + 16 * lora) / n + 2 * max_len * tc.hidden_size
        tied = getattr(cfg, "tie_word_embeddings", False) or getattr(tc, "tie_word_embeddings", False)   # the meta model is not tied yet
        extra = 2 * sum(p.numel() for name, p in meta.named_parameters() if not name.startswith(lpath + ".") and "vision" not in name
                        and "audio" not in name and not (tied and name.startswith("lm_head"))) + 12 * 512 * tc.vocab_size
        x = extra / per_layer; first = max(1, round((n + x) / n_gpu - x)); rest = n - first
        counts = [first] + [rest // (n_gpu - 1) + (i < rest % (n_gpu - 1)) for i in range(n_gpu - 1)]
        log(f"pipeline sizing: ~{per_layer / 2**20:.0f} MiB per layer at {max_len} tokens, cuda:0 extra ~{extra / 2**30:.1f} GiB")
    assert len(counts) == n_gpu and sum(counts) == n, f"layers per GPU {counts} must cover {n} layers on {n_gpu} GPUs"
    dm = {f"{lpath}.{i}": g for g, k in enumerate(counts) for i in range(sum(counts[:g]), sum(counts[:g]) + k)}
    def cover(mod, prefix):                                              # every module off the layer path -> cuda:0
        for name, child in mod.named_children():
            path = prefix + name
            if path == lpath: continue
            if lpath.startswith(path + "."): cover(child, path + ".")
            else: dm[path] = 0
        for pn, _ in list(mod.named_parameters(recurse=False)) + list(mod.named_buffers(recurse=False)): dm[prefix + pn] = 0
    cover(meta, "")
    log(f"pipeline over {n_gpu} GPUs: decoder layers per GPU {counts} ({lpath}); embedding, lm_head and loss on cuda:0")
    return dm


def build_model(path, rank, alpha, local_rank, four_bit=True, resume=None, offload_towers=True, log=print,
                pipeline=0, layers_per_gpu=None, max_len=8192, attn="sdpa", attn_chunk=2048, attn_max_scores=2**28):
    from transformers import AutoConfig, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, PeftModel
    # T4 (sm75) reports *emulated* bf16 support; only use bf16 on Ampere+ (H100/A100/L4)
    bf16 = torch.cuda.get_device_capability(local_rank)[0] >= 8; dt = torch.bfloat16 if bf16 else torch.float16
    cfg = AutoConfig.from_pretrained(path)
    archs = list(getattr(cfg, "architectures", None) or [])
    tc = cfg.get_text_config() if hasattr(cfg, "get_text_config") else cfg
    is_e_model = bool(getattr(tc, "hidden_size_per_layer_input", 0))          # E2B/E4B: per-layer embeddings
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dt,
                               bnb_4bit_use_double_quant=True, llm_int8_skip_modules=SKIP_QUANT) if four_bit else None
    if "Gemma4ForConditionalGeneration" in archs:
        from transformers import Gemma4ForConditionalGeneration as Cls          # keeps `model.language_model.` in the keys
    else:
        Cls = AutoModelForCausalLM
    dm = pipeline_device_map(Cls, cfg, pipeline, max_len, rank, layers_per_gpu, log) if pipeline > 1 else {"": local_rank}
    devs = sorted(set(dm.values()))
    t0 = time.time()
    m = Cls.from_pretrained(path, quantization_config=quant, dtype=dt, device_map=dm, attn_implementation="sdpa")
    m.config.use_cache = False
    if offload_towers and hasattr(m, "model"):
        for name, child in list(m.model.named_children()):
            if any(k in name for k in ("vision", "audio")):
                child.to("cpu"); log(f"moved {name} to cpu")
    torch.cuda.empty_cache()
    log(f"loaded {Cls.__name__} from {path} in {(time.time() - t0) / 60:.1f} min | e_model={is_e_model} | dtype {dt} | gpu mem "
        + " ".join(f"{torch.cuda.memory_allocated(d)/2**30:.2f}" for d in devs) + " GB")
    if attn == "qchunk": use_qchunk(m, attn_chunk, attn_max_scores, log)
    m.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False}); m.enable_input_require_grads()
    names = [n for n, _ in m.named_modules()]
    if any(".language_model.layers." in n for n in names):
        targets = rf".*language_model\.layers\.\d+\.(self_attn|mlp)\.({LORA_NAMES})$"
    else:
        targets = rf".*(language_model|model\.layers).*\.({LORA_NAMES})$"
    n_t = sum(1 for n in names if re.fullmatch(targets, n))
    log(f"lora targets: {n_t} modules match {targets}")
    assert n_t > 0, "no LoRA target modules matched"
    if resume:
        m = PeftModel.from_pretrained(m, resume, is_trainable=True)
    else:
        m = get_peft_model(m, LoraConfig(r=rank, lora_alpha=alpha or rank, lora_dropout=0.0, bias="none", task_type="CAUSAL_LM", target_modules=targets))
    if bf16:   # bf16 autocast path: fp32 LoRA master weights, activations stay bf16 (no PEFT cast of inputs to fp32)
        lora_layers = [mod for mod in m.modules() if hasattr(mod, "cast_input_dtype_enabled")]
        for mod in lora_layers: mod.cast_input_dtype_enabled = False
        log(f"bf16 autocast: PEFT input cast off on {len(lora_layers)} LoRA layers | trainable dtypes {sorted({str(p.dtype) for p in m.parameters() if p.requires_grad})}")
    return m, dt, devs


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
        dev = self.lm_head.weight.device                          # pipeline: the tied lm_head (and the loss) live on cuda:0
        hs, tgt = h[:-1].to(dev), labels[0, 1:].to(dev)
        n = (tgt != -100).sum().clamp(min=1)
        tot = torch.zeros((), device=dev, dtype=torch.float32)
        for s in range(0, hs.shape[0], self.chunk):
            tot = tot + checkpoint(self._chunk_loss, hs[s:s + self.chunk], tgt[s:s + self.chunk], use_reentrant=False)
        return tot / n, n.detach()


def fit_probe(lm, ds, max_len, in_dev, dt, devs):
    """One forward+backward on a max_len sequence cut from the longest windows: peak memory per GPU and ms/token at the
    full context, before any optimizer step. On OOM it retries at 3/4 and 1/2 of the length. Returns (records, longest
    length that fit, 0 if none)."""
    src = sorted(ds.rows, key=lambda r: -r["n"]); assert src, "no windows to probe with"
    ids, lab = [], []
    while len(ids) < max_len:
        for r in src:
            ids += r["input_ids"]; lab += r["labels"]
            if len(ids) >= max_len: break
    recs = []
    for n in (max_len, max_len * 3 // 4, max_len // 2):
        x, y = torch.tensor([ids[:n]], device=in_dev), torch.tensor([lab[:n]], device=in_dev)
        for d in devs: torch.cuda.reset_peak_memory_stats(d); torch.cuda.synchronize(d)
        t = time.time(); oom = False; loss = None
        try:
            with torch.autocast("cuda", dtype=dt):
                loss, _ = lm(x, y)
            loss.backward()
            for d in devs: torch.cuda.synchronize(d)
        except torch.OutOfMemoryError:
            oom = True
        sec = time.time() - t
        recs.append({"fit_probe": {"tokens": n, "oom": oom, "sec": round(sec, 1), "ms_per_token": None if oom else round(1000 * sec / n, 2),
                                   "loss": None if oom else round(float(loss.detach()), 4), "qchunk_calls": QCHUNK["calls"],
                                   "peak_gb": [round(torch.cuda.max_memory_allocated(d) / 2**30, 2) for d in devs],
                                   "reserved_gb": [round(torch.cuda.max_memory_reserved(d) / 2**30, 2) for d in devs]}})
        loss = x = y = None; lm.zero_grad(set_to_none=True); gc.collect(); torch.cuda.empty_cache()
        if not oom: return recs, n
    return recs, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--max-len", type=int, default=8192); ap.add_argument("--rank", type=int, default=32); ap.add_argument("--alpha", type=int, default=None)
    ap.add_argument("--lr", type=float, default=1e-4); ap.add_argument("--epochs", type=float, default=2); ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--warmup", type=float, default=0.03); ap.add_argument("--save-every", type=int, default=100); ap.add_argument("--log-every", type=int, default=5)
    ap.add_argument("--no-4bit", action="store_true"); ap.add_argument("--resume", default=None); ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=512, help="tokens per cross-entropy chunk (512 -> ~0.5 GB fp32 logits on a 262k vocab)")
    ap.add_argument("--keep-towers", action="store_true", help="keep the vision/audio towers on the GPU (default: moved to cpu)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pipeline", type=int, default=0, help="split the model over this many GPUs in one process (naive pipeline; the 31B on 4x L4)")
    ap.add_argument("--layers-per-gpu", default=None, help="decoder layers per GPU for --pipeline, e.g. 8,18,17,17 (default: sized from the config)")
    ap.add_argument("--attn", choices=["sdpa", "qchunk"], default="sdpa", help="qchunk = query-chunked eager attention (head-dim-512 global layers at 16k)")
    ap.add_argument("--attn-chunk", type=int, default=2048, help="max queries per qchunk block")
    ap.add_argument("--attn-max-scores", type=int, default=2**28, help="max score elements per qchunk block (2^28 = 1 GiB in fp32)")
    ap.add_argument("--optim", choices=["adamw8bit", "adamw"], default="adamw8bit", help="adamw = torch AdamW with fp32 moments (~8 B/param)")
    ap.add_argument("--fit-probe", action="store_true", help="before training, one forward+backward at --max-len (peak memory per GPU, ms/token); "
                                                             "on OOM retry shorter and train only on the windows that fit")
    ap.add_argument("--deadline-min", type=float, default=0, help="stop and save the adapter after this many minutes since start (0 = none)")
    a = ap.parse_args()
    t_start = time.time()
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.makedirs(a.out, exist_ok=True)
    local_rank = int(os.environ.get("LOCAL_RANK", 0)); world = int(os.environ.get("WORLD_SIZE", 1)); rank = int(os.environ.get("RANK", 0))
    assert a.pipeline <= 1 or world == 1, "--pipeline runs as one process (plain python, not torchrun)"
    torch.cuda.set_device(local_rank); torch.manual_seed(a.seed)
    if world > 1: torch.distributed.init_process_group("nccl")
    is_main = rank == 0
    log = open(f"{a.out}/train_log.jsonl", "a") if is_main else None
    say = (lambda *x: print(*x, flush=True)) if is_main else (lambda *x: None)
    from transformers import AutoTokenizer, get_cosine_schedule_with_warmup
    tok = AutoTokenizer.from_pretrained(a.model)
    model, dt, devs = build_model(a.model, a.rank, a.alpha, local_rank, four_bit=not a.no_4bit, resume=a.resume, offload_towers=not a.keep_towers, log=say,
                                  pipeline=a.pipeline, layers_per_gpu=[int(x) for x in a.layers_per_gpu.split(",")] if a.layers_per_gpu else None,
                                  max_len=a.max_len, attn=a.attn, attn_chunk=a.attn_chunk, attn_max_scores=a.attn_max_scores)
    if is_main: model.print_trainable_parameters()
    in_dev = model.get_input_embeddings().weight.device                  # cuda:local_rank, or cuda:0 for --pipeline
    peak = lambda stat=torch.cuda.max_memory_allocated: (lambda v: v if len(v) > 1 else v[0])([round(stat(d) / 2**30, 2) for d in devs])
    lm = ChunkedLM(model, chunk=a.chunk)
    params = [p for p in model.parameters() if p.requires_grad]
    # Wrap the LOSS module (whose forward is what we call) so DDP actually synchronises gradients.
    ddp = torch.nn.parallel.DistributedDataParallel(lm, device_ids=[local_rank], find_unused_parameters=False,
                                                    gradient_as_bucket_view=True, broadcast_buffers=False) if world > 1 else None
    fwd = ddp if ddp is not None else lm

    ds = WindowDS(a.data, a.max_len)
    if a.fit_probe:
        model.train()                                      # gradient checkpointing is only active in train mode
        recs, fit = fit_probe(lm, ds, a.max_len, in_dev, dt, devs)
        for rec in recs:
            say(json.dumps(rec))
            if is_main: log.write(json.dumps(rec) + "\n"); log.flush()
        assert fit, "fit probe: even max-len/2 runs out of memory"
        if fit < a.max_len:
            ds.rows = [r for r in ds.rows if r["n"] <= fit]; say(f"fit probe: training only on windows <= {fit} tokens ({len(ds)} left)")
    sampler = torch.utils.data.distributed.DistributedSampler(ds, shuffle=True, seed=a.seed) if world > 1 else None
    g = torch.Generator(); g.manual_seed(a.seed)
    dl = DataLoader(ds, batch_size=1, shuffle=sampler is None, sampler=sampler, num_workers=2, pin_memory=True, generator=g)
    steps_per_epoch = math.ceil(len(dl) / a.grad_accum); total = a.max_steps or int(steps_per_epoch * a.epochs)
    if a.optim == "adamw":     # fp32 moments; no 8-bit optimizer kernels on parameters spread over several cards
        opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    else:
        try:
            import bitsandbytes as bnb; opt = bnb.optim.AdamW8bit(params, lr=a.lr, weight_decay=0.0)
        except Exception:
            opt = torch.optim.AdamW(params, lr=a.lr)
    sched = get_cosine_schedule_with_warmup(opt, max(1, int(a.warmup * total)), total)
    use_scaler = dt == torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=use_scaler, init_scale=2.0**14)
    if is_main:
        say(f"windows {len(ds)} (dropped over max-len {ds.dropped}) | per-rank micro-batches/epoch {len(dl)} | optimizer steps total {total} | dtype {dt} | world {world} | grad_accum {a.grad_accum} | {type(opt).__name__}")
        json.dump(vars(a), open(f"{a.out}/args.json", "w"), indent=1)

    model.train(); step = 0; micro = 0; t0 = time.time(); tokens = 0; sup = 0; run_loss = 0.0; run_n = 0; skipped = 0
    ep = 0
    if a.pipeline > 1 or a.fit_probe:                     # mem_gb = training peak (not the load or the probe)
        for d in devs: torch.cuda.reset_peak_memory_stats(d)
    state_path = os.path.join(a.resume, "trainer_state.pt") if a.resume else None
    if state_path and os.path.exists(state_path):          # full resume: optimizer, scheduler, scaler, step
        st = torch.load(state_path, map_location="cpu" if a.pipeline > 1 else f"cuda:{local_rank}", weights_only=False)
        opt.load_state_dict(st["opt"]); sched.load_state_dict(st["sched"]); scaler.load_state_dict(st["scaler"])
        step = st["step"]; ep = st["epoch"]
        say(f"resumed trainer state at step {step}, epoch {ep}")
    while step < total:
        if sampler: sampler.set_epoch(ep)
        for batch in dl:
            ids = batch["input_ids"].to(in_dev, non_blocking=True); lab = batch["labels"].to(in_dev, non_blocking=True)
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
            if is_main and micro == 1:
                assert a.attn != "qchunk" or QCHUNK["calls"] > 0, "qchunk attention was never called"
                say(json.dumps({"first_micro_loss": round(float(loss.detach()), 4), "sup_tokens": int(n_sup), "seq_len": int(ids.shape[1]),
                                "mem_gb": peak(), "sec": round(time.time() - t0, 1)}))
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
                        say(msg); log.write(json.dumps({"sync_check": msg}) + "\n"); log.flush()
                if is_main and step % a.log_every == 0:
                    el = time.time() - t0
                    rec = {"step": step, "epoch": round(step / steps_per_epoch, 3), "loss": round(run_loss / max(1, run_n), 4), "grad_norm": round(float(gn), 3),
                           "lr": sched.get_last_lr()[0], "tok_s_per_rank": round(tokens / el), "tok_s_total": round(tokens * world / el),
                           "sup_tokens": sup * world, "skipped_nonfinite": skipped, "elapsed_min": round(el / 60, 1),
                           "eta_min": round((el / step) * (total - step) / 60, 1), "mem_gb": peak()}
                    if a.pipeline > 1: rec["mem_reserved_gb"] = peak(torch.cuda.max_memory_reserved)
                    say(json.dumps(rec)); log.write(json.dumps(rec) + "\n"); log.flush(); run_loss = 0.0; run_n = 0
                if is_main and step % a.save_every == 0:
                    d = f"{a.out}/ckpt_{step}"
                    model.save_pretrained(d); tok.save_pretrained(d)
                    torch.save({"opt": opt.state_dict(), "sched": sched.state_dict(), "scaler": scaler.state_dict(),
                                "step": step, "epoch": ep}, os.path.join(d, "trainer_state.pt"))
                if a.deadline_min:                         # all ranks stop at the same step (MAX over ranks)
                    late = torch.tensor([float(time.time() - t_start > 60 * a.deadline_min)], device=in_dev)
                    if world > 1: torch.distributed.all_reduce(late, op=torch.distributed.ReduceOp.MAX)
                    if late.item(): say(f"deadline of {a.deadline_min} min reached after step {step}: stopping"); total = step
                if step >= total: break
        ep += 1
    if world > 1: torch.distributed.barrier()
    if is_main:
        el = time.time() - t0
        rec = {"summary": {"steps": step, "micro_batches": micro, "tokens": tokens * world, "sup_tokens": sup * world, "train_min": round(el / 60, 1),
                           "tok_s_total": round(tokens * world / el), "ms_per_token": round(1000 * el / max(1, tokens * world), 2), "mem_gb": peak(),
                           "mem_reserved_gb": peak(torch.cuda.max_memory_reserved), "skipped_nonfinite": skipped, "total_min": round((time.time() - t_start) / 60, 1)}}
        say(json.dumps(rec)); log.write(json.dumps(rec) + "\n"); log.flush()
        model.save_pretrained(f"{a.out}/final"); tok.save_pretrained(f"{a.out}/final")
        say(f"saved -> {a.out}/final (PEFT dir; package with make_submission.py --bundle ... --adapter {a.out}/final). skipped_nonfinite={skipped}")
    if world > 1: torch.distributed.destroy_process_group()


if __name__ == "__main__":
    main()
