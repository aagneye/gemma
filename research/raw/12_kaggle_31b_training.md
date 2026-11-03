# 12 — 31B LoRA training on Kaggle 4×L4 (trainer, smoke run Nov 3, full-run commands)

Scope: Phase 3 step 2 of the Nov 3 plan. `vm/train_qlora.py` gains a 31B path (model split over 4 GPUs, query-chunked
attention, bf16 autocast path); `vm/make_kaggle_train.py` builds the Kaggle notebook; one 20-step smoke run on Kaggle
4×L4 measures memory and speed. Kaggle GPUs are for **training only**.

## 1. Result
**The 31B trains on Kaggle 4×L4 at 16k context, and its adapter packages, validates and hot-swaps on the w4a16 base.**

| Measure (smoke, Nov 3, private kernel `aagneye/gemma4-31b-lora-smoke` v1) | Value |
|---|---|
| Stack on Kaggle | torch 2.10.0+cu128, transformers 5.13.1, peft 0.19.1, accelerate 1.13.0, bitsandbytes 0.46.1; 4× NVIDIA L4 (23,034 MiB each) |
| Load of the 62 GB bf16 base into NF4 over 4 GPUs | 8.5 min; weights after load 4.49 / 4.22 / 3.99 / 3.99 GiB (split [8, 18, 17, 17]) |
| **Fit probe, one 16,384-token sequence, forward + backward** | **no OOM; peak allocated 14.3 / 15.6 / 15.4 / 16.8 GiB, reserved 15.3 / 16.7 / 16.2 / 18.6 GiB; 202 s = 12.3 ms/token** |
| **Training, 20 steps × 1 window** (lengths 3.8k–11k, 144,845 tokens, 25,355 supervised) | **26.2 min = 92 tok/s = 10.9 ms/token**; peak allocated 12.2 / 13.4 / 13.1 / 14.1 GiB, reserved ≤ 15.0 GiB |
| Loss | finite on every step, 0 skipped; first window 0.339; mean 0.64 over steps 1–10 and 0.40 over steps 11–20 (different windows, one per step: no trend claim); grad norm ≤ 10.2 before clipping |
| Trainable parameters | 244,858,880 (r32 on 410 modules), fp32 |
| Adapter | `run/final` fp32 980 MB; packaged fp16 **467 MiB, 820 tensors, layers 0–59, prefix `base_model.model.model.language_model.layers.`, `target_modules` plain list: G0 OK** (in the notebook and again on the VM) |
| Bundle check | `make_submission.py --bundle submissions/v7 --adapter …/run/final` → `harness-venv … --validate`: **VALID**, adapters `{'main_lora': 32}`, 467.2 MiB (zip 423 MiB) |
| VM hot-swap (vLLM 0.19.1, `-w4a16-ct`, TP 4 on T4, fp16, `--max-lora-rank 32`) | `/v1/load_lora_adapter` 200 in 1.2 s; one chat request with `k31b_smoke`: `finish_reason stop`, coherent answer (23 + 37 tokens); `/v1/unload_lora_adapter` 200; server log clean; the 4 running requests continued |
| Session time, quota | kernel 39.6 min (push → complete 43 min) ≈ **1.4 h of the 30-h weekly quota** (L4 billed 2×) |

Faster and lighter than the public reference (scottweeden: 16.7 ms/token, 20.4 GiB peak on the last card at 16k),
probably because a sliding layer's query blocks read only their 1024-token window and no L × L mask is built or copied
(their code is not public). Not shown by the smoke: that the adapter changes the agent's behaviour (20 steps, one
request). The Phase 3 gate measures that.

## 2. What the trainer does now (`vm/train_qlora.py`)
The E4B/12B DDP paths are unchanged by default (`--pipeline 0 --attn sdpa --optim adamw8bit`). New options:

| Option | What it does | Why |
|---|---|---|
| `--pipeline 4` | One process; the 60 decoder layers are cut into contiguous blocks over the 4 cards (`device_map`, accelerate hooks move activations between cards). cuda:0 also holds the bf16 embedding (= tied `lm_head`), the norms and the chunked cross-entropy, so it gets fewer layers. Default split is sized from the config: **[8, 18, 17, 17]** at 16k. `--layers-per-gpu a,b,c,d` overrides it. | The NF4 31B is ~18 GB and does not fit one 24 GB card next to 16k activations. Naive pipeline: one card computes at a time. |
| `--attn qchunk` | Registers a custom attention function (`AttentionInterface.register("qchunk", ...)`) for the text layers only. Queries go in blocks whose score matrix stays under `--attn-max-scores` (2^28 elements, 1 GiB in fp32; at 16k the global layers get 512-query blocks), each block recomputed in backward (`checkpoint`, nested inside HF's per-layer checkpoint). A sliding layer's block reads only the keys inside its 1024-token window. Math = transformers' eager attention (bf16 matmuls, fp32 softmax). | SDPA has no fused kernel for the head-dim-512 global layers and falls back to the math kernel: heads × L × L scores, ~16 GiB per layer at 16k (scottweeden write-up). |
| bf16 path (sm ≥ 80) | LoRA master weights fp32 (PEFT default), forward under bf16 autocast, `cast_input_dtype_enabled = False` on every LoRA layer. | PEFT casts LoRA inputs to the fp32 weight dtype when autocast is off, which doubles activation memory. In PEFT 0.19.1's 4-bit path the cast only runs without autocast (`requires_conversion = not torch.is_autocast_enabled()`), so with autocast on, the switch is a safeguard. |
| `--fit-probe` | Before training: one forward + backward on a `--max-len` sequence cut from the longest windows; logs peak memory per GPU and ms/token. On OOM it retries at 3/4 and 1/2 and trains only on windows that fit. | The real windows top out at 11.3k tokens, so only the probe tests 16k. |
| `--deadline-min M` | Stops after the current optimizer step once M minutes have passed since start, then saves `final`. | Kaggle's session cap (`kernels push -t`, 12 h max): the adapter must be written before the kill. |
| `--optim adamw` | torch AdamW with fp32 moments (245M LoRA params → ~2 GB over 4 cards). | Avoids bitsandbytes' 8-bit optimizer kernels on parameters spread over several cards. |

Logging: `mem_gb` (and `mem_reserved_gb` with `--pipeline`) become per-GPU lists; a closing `{"summary": ...}` record
gives steps, tokens, tok/s, ms/token, peak memory and minutes. The first micro-batch asserts that qchunk was called.

## 3. Verified facts the design rests on
- **Kaggle image (pinned `python@sha256:37c64f…`, `scratch/kfreeze/before.txt` on the VM):** torch 2.10.0+cu128,
  peft 0.19.1, accelerate 1.13.0, pyarrow 24.0.0, safetensors 0.7.0, tokenizers 0.22.2, **transformers 5.0.0** (too
  old for Gemma 4) and **no bitsandbytes**. The competition wheelhouse supplies transformers 5.13.1, bitsandbytes
  0.46.1, safetensors 0.8.0 and tokenizers 0.22.2; the notebook installs only these four, `--no-deps`.
- **Base model:** Kaggle Model `google/gemma-4/transformers/gemma-4-31b-it-qat-q4_0-unquantized`, version **2**:
  2 safetensors shards (49.8 GB + 12.8 GB). Its `chat_template.jinja` is **16,934 bytes**; the serving model
  `gemma-4-31b-it-qat-w4a16-ct` (VM copy, same as 12B) has **18,683 bytes**. `tokenizer.json` is identical across all
  Gemma 4 sizes. **Tokenize training windows with `--model models/gemma-4-31b-it-qat-w4a16-ct`** (what the scorer
  renders), never with the unquantized model's template; the notebook only consumes pre-tokenized windows.
- **31B shapes (config):** 60 layers = 50 sliding (window 1024, head dim 256, 16 KV heads) + 10 global (head dim 512,
  4 KV heads, `attention_k_eq_v`: no `v_proj`); hidden 5376, MLP 21504, 32 query heads, vocab 262,144, tied
  embeddings, final-logit softcap 30. LoRA r32 on q/k/v/o/gate/up/down → **410 modules** (50 `v_proj`), 244.9M
  parameters, 467 MiB in fp16.
- **Masks:** in transformers 5.13.1, an attention implementation without a registered mask builder makes
  `create_causal_mask`/`create_sliding_window_causal_mask` return the input mask (None) (`masking_utils.py:853`).
  qchunk builds the causal and sliding masks from positions per block, so no 16k × 16k mask is built or copied to each card.
- **CPU equivalence test** (VM, CPU only, the Kaggle versions torch 2.10.0 / transformers 5.13.1 / peft 0.19.1 /
  accelerate 1.13.0; script `scratch/k31b/test_qchunk_cpu.py` on the VM): tiny Gemma 4 with sliding and k=v global
  layers, LoRA on all targets, gradient checkpointing on, 43 tokens, blocks of 5/8/64 queries: qchunk vs eager loss
  identical (6.265785), largest relative LoRA-gradient difference 8e-5, hidden states 7e-6; under bf16 autocast the
  losses are identical. The device map covers every parameter and buffer of the meta 31B (66 entries).

## 4. Smoke run (Nov 3): how it was run
Data: the 42 own resolved 31B episodes of `datasets/traces_31b_v2/all.jsonl` (fastapi + rich, 116 windows), re-tokenized
for the 31B at 16k: 822,392 tokens, median 7,007, p90 9,534, max 11,276, 184,362 supervised. Everything lives on the VM
under `/mnt/biohub/kdata/gemma4/scratch/k31b/` (`K=.venv/bin/kaggle`):

```bash
.venv/bin/python ~/gemma4_vm/prepare_data.py --tokenize datasets/traces_31b_v2/all.jsonl --model models/gemma-4-31b-it-qat-w4a16-ct \
    --max-len 16384 --thought-cap 1000 --out scratch/k31b/tok_31b_16k_smoke
cd scratch/k31b      # holds the new train_qlora.py, make_kaggle_train.py and make_submission.py
python3 make_kaggle_train.py dataset ds_smoke aagneye/gemma4-31b-train-smoke --data tok_31b_16k_smoke && $K datasets create -p ds_smoke
python3 make_kaggle_train.py notebook nb_smoke aagneye/gemma4-31b-lora-smoke --dataset aagneye/gemma4-31b-train-smoke --minutes 95
$K kernels push -p nb_smoke --accelerator NvidiaL4 -t 7200
$K kernels output aagneye/gemma4-31b-lora-smoke -p out_smoke
```
The notebook ran `train_qlora.py --pipeline 4 --attn qchunk --deadline-min 95 --max-len 16384 --rank 32 --lr 1e-4
--optim adamw --max-steps 20 --grad-accum 1 --log-every 1 --fit-probe` (alpha = r = 32), then the G0 packaging.
Session timeline (s): GPU check 8, wheels 24, versions 52, model load 66 → 578, LoRA 581, fit probe → 785, first
window → 862, step 20 → 2360, adapter saved 2362, G0 2367.

Outputs on the VM: `out_smoke/report.json` (GPUs, versions, fit probe, step records, summary, G0), `out_smoke/train.log`,
`out_smoke/run/final` (fp32 PEFT adapter), `out_smoke/packaged/adapters/main_lora` (fp16), plus the validated test bundle
`bundle_v7_smoke/` (v7 + adapter; a test artifact, not for submission). CPU test: `test_qchunk_cpu.py` with `cpu-venv/`.

Hot-swap commands used (one request, then unload; the server is shared with the running tests):
```bash
A=/mnt/biohub/kdata/gemma4/scratch/k31b/bundle_v7_smoke/adapters/main_lora
curl -X POST localhost:8000/v1/load_lora_adapter -H 'Content-Type: application/json' -d "{\"lora_name\": \"k31b_smoke\", \"lora_path\": \"$A\"}"
curl localhost:8000/v1/chat/completions -H 'Content-Type: application/json' \
     -d '{"model": "k31b_smoke", "messages": [{"role": "user", "content": "In one sentence: what does git diff show?"}], "max_tokens": 64, "temperature": 0}'
curl -X POST localhost:8000/v1/unload_lora_adapter -H 'Content-Type: application/json' -d '{"lora_name": "k31b_smoke"}'
```

## 5. Full run on the real data (expected Nov 9–10)
Deploy first: `vm/train_qlora.py` and `vm/make_kaggle_train.py` to `~/gemma4_vm/` (the dataset step copies
`train_qlora.py` and `make_submission.py` from the script's own directory). Run on the VM from `/mnt/biohub/kdata/gemma4`
with `K=.venv/bin/kaggle`. `<own>` = the filtered own-31B episodes (`FT_DATA_SPEC.md` filters, TRAIN repos only).

```bash
# 1. windows: 16k, rendered with the SERVING model's chat template, 31B thought cap
.venv/bin/python ~/gemma4_vm/prepare_data.py --tokenize datasets/<own>/all.jsonl --model models/gemma-4-31b-it-qat-w4a16-ct \
    --max-len 16384 --thought-cap 1000 --out datasets/<own>/tok_31b_16k
# 2. private dataset (flat: scripts + train.parquet + stats.json)
python3 ~/gemma4_vm/make_kaggle_train.py dataset scratch/k31b/ds_v1 aagneye/gemma4-31b-train-v1 --data datasets/<own>/tok_31b_16k
$K datasets create -p scratch/k31b/ds_v1            # wait for: $K datasets status aagneye/gemma4-31b-train-v1 -> ready
# 3. notebook: 1 epoch, LR 1e-4, r32 (alpha = r unless decided otherwise), stop and save at 660 min
python3 ~/gemma4_vm/make_kaggle_train.py notebook scratch/k31b/nb_v1 aagneye/gemma4-31b-lora-v1 --dataset aagneye/gemma4-31b-train-v1 \
    --minutes 660 --train-args "--max-len 16384 --rank 32 --lr 1e-4 --optim adamw --epochs 1 --grad-accum 8 --log-every 1 --save-every 1000 --fit-probe"
$K kernels push -p scratch/k31b/nb_v1 --accelerator NvidiaL4 -t 41400
# 4. after "complete": download (report.json, train.log, run/, packaged/)
$K kernels output aagneye/gemma4-31b-lora-v1 -p scratch/k31b/out_v1
# 5. adapter bundle on the winning prompt, validated (then the strict gate on the VM)
.venv/bin/python ~/gemma4_vm/make_submission.py --bundle submissions/<winner> --adapter scratch/k31b/out_v1/run/final --out submissions/<winner>_lora1
harness-venv/bin/python ~/gemma4_vm/make_submission.py --validate submissions/<winner>_lora1
```

**Budget (from the smoke):** about 13 min before the first step (wheels 1 min, load 8.5 min, LoRA setup, 16k
probe 3.4 min), then 10.9 ms/token at the smoke's window lengths (12.3 at 16k), so one window of ~7k tokens takes
~79 s. Own episodes average ~19.6k tokens after windowing (822k tokens / 42 episodes). Hence:

| Data | Tokens | Wall time | Quota (2×) |
|---|---|---|---|
| floor: 100 episodes | ~2.0M | ~6.1 h | ~12.3 h |
| target: 150 episodes | ~2.9M | ~9.1 h | ~18.2 h |
| most one session can take (`--minutes 660`) | ~3.5M | 11 h | 22 h |

- Keep the data under ~3.5M tokens (about 180 episodes). Past that, `--deadline-min` stops mid-epoch with the
  cosine LR not yet decayed; cap episodes instead.
- The quota week resets Saturday 00:00 UTC (STATE.md: reset at 2026-10-24 00:05 UTC). A full run on Nov 9–10 falls in
  the Nov 7–13 week, which has the whole 30 h. The smoke used ~1.4 h of the Oct 31–Nov 6 week.
- Settings still open for the main session:
  - **alpha:** the smoke used the trainer default alpha = r (scale 1.0); the E4B runs used 64 (scale 2).
  - **grad-accum:** 8 gives ~50 steps for ~400 windows; the E4B/12B recipe used ~16 windows per step.
- Memory headroom at 16k: the tightest card (GPU 3) reserved 18.6 of 22.5 GiB, so about 3.5 GiB is left after the CUDA
  context. If a later run OOMs, the probe retries at 12k and 8k and trains on what fits. The other fallback is
  `--layers-per-gpu` (e.g. 8,18,18,16 to unload GPU 3).

## 6. Pitfalls
- `kaggle datasets create` skips sub-directories: the dataset is flat (scripts + `train.parquet` + `stats.json`).
- An unknown `machine_shape` silently gives T4 ×2; the notebook asserts 4 L4s before installing anything.
- `kaggle kernels logs` is empty while a kernel runs; the notebook's own `report.json` and `train.log` are the record.
- `--fit-probe` must run in train mode (HF gradient checkpointing is off in eval mode, which would fake an OOM).
- Do not run `train_qlora.py --pipeline` under torchrun (asserted).
