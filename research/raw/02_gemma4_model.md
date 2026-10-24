# Gemma 4 model-family dossier (for an offline SWE coding agent on Kaggle)

Compiled 2026-10-16. Every number carries a source URL. Items marked **UNVERIFIED** are single-source, community-measured, inferred by me, or contradicted elsewhere. Items marked **COMPUTED** are derived by me from published config values (formula shown).

Primary sources used: Gemma 4 Technical Report arXiv 2607.02770 (HTML v1: https://arxiv.org/html/2607.02770v1 ; abs page shows v2 dated 2026-07-24, PDF header says 2026-06-19 — https://arxiv.org/abs/2607.02770), the model card https://ai.google.dev/gemma/docs/core/model_card_4 (note: page is marked *deprecated*, pointing to gemma.ai), the docs overview https://ai.google.dev/gemma/docs/core, HF `config.json` files for each `-it` checkpoint, the vLLM recipe https://github.com/vllm-project/recipes/blob/main/Google/Gemma4.md, Unsloth docs https://unsloth.ai/docs/models/gemma-4 and https://unsloth.ai/docs/models/gemma-4/train, HF transformers docs https://huggingface.co/docs/transformers/main/model_doc/gemma4, and GitHub issues/community benchmarks cited inline.

---

## 1. Sizes and architecture

### 1.1 Family table

| | E2B | E4B | 12B ("Unified") | 26B-A4B (MoE) | 31B |
|---|---|---|---|---|---|
| Effective / total params (model card) | 2.3B eff. (5.1B incl. embeddings) | 4.5B eff. (8B incl. embeddings) | 11.95B | 25.2B total / 3.8B active | 30.7B |
| Report Table 1 (M): embedder / einsums / drafter | 400+2,340 PLE / 1,870 / 76 | 670+2,820 PLE / 3,940 / 77 | 1,000 / 10,890 / 400 | 740 / 24,500 (2,800 active) / 430 | 1,410 / 29,290 / 500 |
| Vision encoder | 150M (ViT, d=768, 16 layers) | 150M | none (encoder-free: 48x48x3 patches through one 35M matmul) | 550M (d=1152, 27 layers) | 550M |
| Audio encoder | 305M USM/Conformer | 305M | none (raw 16 kHz, 40 ms chunks -> 640-d vectors projected in) | none | none |
| Layers | 35 | 42 | 48 | 30 | 60 |
| hidden_size | 1536 | 2560 | 3840 | 2816 | 5376 |
| intermediate_size | 6144 | 10240 | 15360 | 2112 dense + MoE `moe_intermediate_size` 704 | 21504 |
| Attention heads / KV heads (sliding) | 8 / 1 | 8 / 2 | 16 / 8 | 16 / 8 | 32 / 16 |
| Global-layer KV heads / head_dim | 1 (null -> same) / 512 | 2 (assumed same) / 512 | 1 / 512 | 2 / 512 | 4 / 512 |
| head_dim (sliding) | 256 | 256 | 256 | 256 | 256 |
| Sliding window | 512 | 512 | 1024 | 1024 | 1024 |
| Local:global ratio | 4:1 (7 global layers) | 5:1 (7 global) | 5:1 (8 global) | 5:1 (5 global) | 5:1 (10 global) |
| KV-shared layers (`num_kv_shared_layers`) | 20 of 35 | 18 of 42 | 0 | 0 | 0 |
| Keys reused as values on global layers (`attention_k_eq_v`) | no | no | yes | yes | yes |
| Context (`max_position_embeddings`) | 131,072 | 131,072 | 262,144 | 262,144 | 262,144 |
| Vocab | 262,144 | 262,144 | 262,144 | 262,144 | 262,144 |
| MoE | - | - | - | 128 experts, top-8 (`top_k_experts: 8`) + 1 shared expert | - |
| Modalities in | text, image, video, audio | text, image, video, audio | text, image, video, audio | text, image, video | text, image, video |

Sources: model card spec table (https://ai.google.dev/gemma/docs/core/model_card_4); report Table 1 and Section 2 (https://arxiv.org/html/2607.02770v1); configs: https://huggingface.co/google/gemma-4-E2B-it/raw/main/config.json , https://huggingface.co/google/gemma-4-E4B-it/raw/main/config.json , https://huggingface.co/google/gemma-4-12B-it/raw/main/config.json , https://huggingface.co/google/gemma-4-26B-A4B-it/raw/main/config.json , https://huggingface.co/google/gemma-4-31B-it/raw/main/config.json . Expert count "8 active / 128 total + 1 shared" is from the model card; the report itself does not state expert counts. **Discrepancy flag:** the report body says "3.8B activated parameters for 26B total" while its Table 1 says 2,800M active einsum params of 24,500M — the difference is embeddings/attention vs einsum-only accounting; treat 3.8B as the working number.

### 1.2 Architectural details relevant to serving/training

- Positional encoding: "pp-RoPE" with p=0.25 (`partial_rotary_factor: 0.25`, `rope_type: proportional`) on global layers, theta 1e6; standard RoPE theta 1e4 on sliding layers (report Sec. 2; all configs).
- Norms: pre- and post-RMSNorm plus QK-norm; `final_logit_softcapping: 30.0` (report; configs).
- Global KV reduction "up to 37.5%" from k=v reuse plus KV-cache sharing (report Introduction).
- E2B/E4B: Per-Layer Embeddings (PLE) table of shape `[262144, num_layers * 256]` (`hidden_size_per_layer_input: 256`) — this is why E2B's checkpoint is ~10 GB bf16 despite 2.3B "effective" params, and a 4-bit E2B checkpoint still carries a ~4.4 GB PLE table (https://github.com/unslothai/unsloth/issues/7055). E2B/E4B also share KV across their last 20/18 layers (YOCO-style self-decoder / cross-decoder in vLLM: https://docs.vllm.ai/en/latest/api/vllm/model_executor/models/gemma4/).
- Tokenizer: SentencePiece, split digits, preserved whitespace, byte fallback, 262k vocab, "matches the Gemini tokenizer" (report Sec. 2.4). The 262k vocab matters for training memory (see 2.4).
- MTP drafter: every size ships a 4-layer drafter for speculative decoding (report Sec. 2.6; docs overview). vLLM recommends `num_speculative_tokens` 2 (E2B), 4 (E4B), 4-8 (12B), 4 (26B), 4-8 (31B) (vLLM recipe).
- `tie_word_embeddings: true` on 26B/E4B configs (and presumably all) — relevant for LoRA on lm_head.

### 1.3 Can the multimodal parts be dropped for text-only?

- Yes in practice. transformers exposes `Gemma4ForCausalLM`/`Gemma4TextModel` built from `Gemma4TextConfig`, and the docs show `Gemma4ForCausalLM.from_pretrained("google/gemma-4-E2B-it")` loading directly from the multimodal checkpoint (https://huggingface.co/docs/transformers/main/model_doc/gemma4).
- vLLM has `--language-model-only` (used in the JarvisLabs benchmark and the takimov competition entry: https://jarvislabs.ai/blog/gemma-4-mtp-vs-dflash-benchmark , https://github.com/takimov/gemma-coding-agent) and `--limit-mm-per-prompt '{"image":0,"audio":0}'` (vLLM recipe).
- Unsloth's text notebooks set `finetune_vision_layers=False`; all community LoRA entries exclude `vision_tower` (https://huggingface.co/karthik-a/sparkflashxgemma4).
- Savings are small for the big models (550M vision encoder on 26B/31B; the 12B has no encoder at all), large relatively for E2B/E4B (455M of enc. plus PLE).

---

## 2. Memory footprints

### 2.1 Weights

| Size | bf16 (report Table 3) | bf16 real on-disk / Unsloth | Google docs "BF16 incl. ~20% overhead" / Q4_0 | QAT W4A16 (vLLM recipe savings) | Other quantized |
|---|---|---|---|---|---|
| E2B | 4.6 GB (excludes PLE — see flag) | ~10 GB | 11.4 / 2.9 GB | ~26% smaller than bf16 | mobile int2/4/8: 3.6x smaller; 4-bit 4 GB |
| E4B | 9.0 GB | ~16 GB | 17.9 / 4.5 GB | (between) | mobile QAT 4.1x smaller; 4-bit 5.5-6 GB |
| 12B | 24.0 GB | ~25 GB | 26.7 / 6.7 GB | ~7-8 GB 4-bit | FP8 ~12 GB (**COMPUTED**) |
| 26B-A4B | 52.0 GB (7.6 GB active) | 52 GB | 57.7 / 14.4 GB | **no W4A16 released** ("excluded because of quality loss") — int8 per-channel ~47% saving (~27.5 GB) | FP8-Dynamic ~27 GB (RedHatAI); NVFP4 ~16.5 GB |
| 31B | 64.0 GB | 62 GB | 69.9 / 17.5 GB | ~66% smaller (~18-22 GB) | FP8 ~32 GB (**COMPUTED**) |

Sources: report Table 3 (https://arxiv.org/html/2607.02770v1); Unsloth table (https://unsloth.ai/docs/models/gemma-4); docs overview memory table (https://ai.google.dev/gemma/docs/core); vLLM recipe QAT section (https://github.com/vllm-project/recipes/blob/main/Google/Gemma4.md); 26B FP8 27 GB and NVFP4 16.5 GB (https://ai-muninn.com/en/blog/swe-bench-lite-gemma4-26b-38-percent , https://ai-muninn.com/en/blog/dgx-spark-gemma4-26b-nvfp4-52-toks). **Flag:** the report's 4.6/9.0 GB for E2B/E4B are "effective-param" numbers; the real checkpoints are ~2x that because of the PLE table.

QAT checkpoint catalogue (docs overview): `-qat-q4_0-gguf` (all 5), `-qat-w4a16-ct` compressed-tensors for vLLM/SGLang (E2B, E4B, 12B, 31B only), `-qat-mobile-ct` (E2B/E4B), `-qat-q4_0-unquantized` bf16 weights trained with QAT (all 5), `-assistant` MTP drafters. The Kaggle competition model is `gemma-4-31b-it-qat-w4a16-ct` (https://github.com/happyc0der/gemma-swe-agent). The W4A16 HF page lists "34B params", tensor types I64/I32/BF16, no file size, no LoRA note; it warns that an MTP draft model must be a QAT checkpoint of the same precision (https://huggingface.co/google/gemma-4-31B-it-qat-w4a16-ct).

### 2.2 KV cache per token (COMPUTED from configs; bf16 KV, 2 bytes/element)

Formula per layer: `2 (K,V) x n_kv_heads x head_dim x 2 B`; for global layers with `attention_k_eq_v` only K needs storing if the engine exploits it (`n_kv x 512 x 2 B`); sliding layers only ever hold `window` tokens if the engine's allocator is window-aware (vLLM V1 hybrid KV manager — **UNVERIFIED for Gemma 4 specifically**); E2B/E4B shared layers hold no KV.

| Size | Sliding layers owning KV x per-token bytes | Global layers x per-token bytes (K only / K+V) | Per-token that scales with context | 128k-token sequence (global part) | Fixed sliding-window part per sequence |
|---|---|---|---|---|---|
| E2B | 12 x 1 KiB | 3 x 2 KiB (no k=v) | 6 KiB | 0.75 GiB | 12 KiB x 512 = 6 MiB |
| E4B | 20 x 2 KiB | 4 x 4 KiB (no k=v) | 16 KiB | 2.0 GiB | 40 KiB x 512 = 20 MiB |
| 12B | 40 x 8 KiB | 8 x (1 / 2 KiB) | 8 / 16 KiB | 1.0 / 2.0 GiB | 320 KiB x 1024 = 320 MiB |
| 26B-A4B | 25 x 8 KiB | 5 x (2 / 4 KiB) | 10 / 20 KiB | 1.25 / 2.5 GiB | 200 KiB x 1024 = 200 MiB |
| 31B | 50 x 16 KiB | 10 x (4 / 8 KiB) | 40 / 80 KiB | 5.0 / 10.0 GiB | 800 KiB x 1024 = 800 MiB |

If an engine does **not** exploit the sliding window (treats every layer as full-context), the per-token cost is 840 KiB for 31B (105 GiB at 128k) — i.e., window-aware caching is mandatory. `--kv-cache-dtype fp8` halves all of the above (vLLM recipe). Sanity check vs. vendor: on DGX Spark with 26B-A4B NVFP4, vLLM reported 81.8 GiB free -> 714,768 KV tokens = ~120 KB/token (https://ai-muninn.com/en/blog/dgx-spark-gemma4-26b-nvfp4-52-toks) — that is ~6x my 20 KiB figure, implying vLLM 0.19 was *not* (fully) exploiting the sliding window and/or k=v for Gemma 4 at the time. **Treat vLLM's effective KV cost as 100-120 KB/token for 26B-A4B unless you verify the hybrid allocator is active**; for 31B, scale by 2x heads -> expect ~200-250 KB/token in practice (**UNVERIFIED**).

### 2.3 What fits where (inference)

Hardware notes: T4 = 16 GB, sm75, no bf16, no FlashAttention-2, no Marlin/INT4 vLLM kernels ("vLLM's INT4 kernels need Ampere" — https://github.com/happyc0der/gemma-swe-agent). L4 = 24 GB, sm89, bf16 + FP8, 300 GB/s, PCIe only. vLLM minimums from the recipe: E2B/E4B 1x24 GB, 12B 1x40 GB, 31B 1x80 GB, 26B-A4B 1x80 GB — all bf16.

| Target | Inference verdict |
|---|---|
| T4 16 GB | E2B/E4B fp16 or Q4/8-bit (llama.cpp or transformers); 12B W4 (~7-8 GB) via llama.cpp/transformers; **not** 31B. 2xT4 (Kaggle free tier): 31B Q4_0 GGUF via llama.cpp works (used by a competition entrant: https://github.com/happyc0der/gemma-swe-agent). Audio tower overflows fp16 on T4 (Unsloth known issue). |
| L4 24 GB | E4B bf16 (vLLM says 24 GB+); 12B W4A16 (~8 GB weights, lots of KV); 26B-A4B only via community NVFP4/AWQ (~16-18 GB) with little KV; 31B W4A16 (~18-22 GB) does not leave usable KV — effectively no. |
| 4x L4 (96 GB; Kaggle competition box) | 31B W4A16 with TP=4 (32 Q-heads/16 KV-heads/4 global KV-heads all divide by 4) ~5 GB weights per GPU + ~18 GB KV each; 31B bf16 TP=4 = 16 GB/GPU + ~6 GB KV each (tight, 8-32k ctx); 26B-A4B bf16 TP=4 = 13 GB/GPU. Competition entries confirm TP=4 rollouts on vLLM 0.19.1 (https://github.com/takimov/gemma-coding-agent). L4 has no NVLink; TP over PCIe caps decode speed (see Sec. 6). |
| H100 80 GB | 31B bf16 (62-64 GB + ~16-18 GB KV; InferenceBench ran 8k ctx; vLLM recipe ran 32k with `--gpu-memory-utilization 0.90` on 2xH100 for 31B and 1xH100 for 26B — https://inferencebench.io/blog/gemma-4-31b-h100-complete-inference-benchmark/ , vLLM recipe); 26B-A4B bf16 (52 GB) with ~25 GB KV; 31B FP8/W4A16 with 128k+ KV. |

### 2.4 What fits where (LoRA / QLoRA training, long context)

Vendor/community numbers: E2B QLoRA 8-10 GB; E4B QLoRA ~10 GB, E4B 16-bit LoRA 17 GB; E2B GRPO 9 GB; 31B QLoRA 22 GB; 26B-A4B 16-bit LoRA ">40 GB" and QLoRA "not recommended" for the MoE (https://unsloth.ai/docs/models/gemma-4/train). TRL article: E4B NF4 QLoRA r=16, seq 4096, ~14 GB estimated (https://dev.to/pulkitgovrani/fine-tuning-gemma-4-for-function-calling-with-trls-new-multimodal-tool-support-4ghf). 31B QLoRA r=16 on 2xT4 fit only 3,072 tokens (https://github.com/happyc0der/gemma-swe-agent); another entrant trained 31B QLoRA (r=16 and r=8, rsLoRA alpha=2r, all 7 projections across 60 layers, vision excluded) on 2xT4 using chunked cross-entropy under a 14.5 GB ceiling at seq ~1024, 120 s/step (https://huggingface.co/karthik-a/sparkflashxgemma4). FSDP-QLoRA of 31B across 4xL4 with `bnb_4bit_quant_storage=bfloat16` is the pattern used in a GRPO entry (https://github.com/takimov/gemma-coding-agent).

Long-context training arithmetic (**COMPUTED**): the 262,144 vocab makes the logits tensor 512 KB/token in bf16 (1 MB fp32) — 16-32 GB for a single 32k sequence — so chunked/fused cross-entropy (Unsloth, Liger, or `logits_to_keep`/custom chunked CE) is mandatory. Checkpointed hidden states for 31B are `5376 x 60 x 2 B` = 645 KB/token -> ~21 GB at 32k, ~84 GB at 128k, before the recomputed layer's activations. Practical conclusions:

- T4 16 GB: E2B/E4B QLoRA to ~4-8k tokens; 31B QLoRA only at ~1-3k tokens (two entrants above). No bf16 -> fp16 training with its overflow risks.
- L4 24 GB: E4B LoRA/QLoRA to ~8-16k; 12B QLoRA ~8k (**UNVERIFIED** - no published number); 31B QLoRA (22 GB base) only with ~2-4k sequences.
- 4x L4: 31B QLoRA with FSDP at 8k is demonstrated (takimov); 32k is listed as an unverified target there; realistically the per-GPU 24 GB and PCIe make 32k-128k training impractical on this box. Use sequence packing + short trajectories, or train elsewhere and only *serve* on 4xL4.
- H100 80 GB: 31B QLoRA at 16-32k with gradient checkpointing and chunked CE is feasible (**UNVERIFIED** but consistent with the arithmetic); 31B bf16 LoRA (64 GB weights) leaves ~15 GB — only short sequences, better on 2xH100 (the TPU paper's baseline was 2xH100 for 31B LoRA: https://arxiv.org/abs/2605.25645); 26B-A4B bf16 LoRA (>40 GB) fits with 8-16k; 12B bf16 LoRA fits with 32k. 128k training needs multi-GPU with sequence/context parallelism on any size above E4B.

---

## 3. Agentic / coding capabilities

### 3.1 Official benchmarks (instruction-tuned; the report labels Table 5 "thinking mode unless noted")

| Benchmark | 31B | 26B-A4B | 12B | E4B | E2B | Gemma 3 27B (no think) |
|---|---|---|---|---|---|---|
| LiveCodeBench v6 | 80.0 | 77.1 | 72.0 | 52.0 | 44.0 | 29.1 |
| Codeforces Elo | 2150 | 1718 | 1659 | 940 | 633 | 110 |
| Tau2-bench avg of 3 | 76.9 | 68.2 | 69.0 | 42.2 | 24.5 | 16.2 |
| Tau2 airline / retail / telecom | 75.0 / 86.4 / 69.3 | 76.0 / 85.5 / 43.0 | 75.0 / 77.6 / 54.4 | 52.0 / 67.1 / 18.4 | 31.0 / 34.6 / 19.7 | 39.0 / 6.6 / 3.1 |
| AIME 2026 (no tools) | 89.2 | 88.3 | 77.5 | 42.5 | 37.5 | 20.8 |
| GPQA Diamond | 84.3 | 82.3 | 78.8 | 58.6 | 43.4 | 42.4 |
| MMLU-Pro | 85.2 | 82.6 | 77.2 | 69.4 | 60.0 | 67.6 |
| BBEH | 74.4 | 64.8 | 53.0 | 33.1 | 21.9 | 19.3 |
| HLE (no tools / with search) | 19.5 / 26.5 | 8.7 / 17.2 | 5.2 / - | - | - | - |
| MRCR v2 8-needle 128k | 66.4 | 44.1 | 43.4 | 25.4 | 19.1 | 13.5 |
| RULER 32k / 128k (no thinking) | 96.8 / 96.4 | 97.3 / 89.8 | 96.4 / 91.2 | 95.2 / 86.6 | 83.0 / 70.4 | 91.1 / 66.0 |
| LOFT 128k recall@k | 79.5 | 66.3 | 66.4 | 58.5 | 50.5 | 8.6 |
| GraphWalks <128k F1 | 82.3 | 72.6 | 71.0 | 50.9 | 4.1 | 32.8 |

Sources: report Tables 5 and 9 (https://arxiv.org/html/2607.02770v1); model card (https://ai.google.dev/gemma/docs/core/model_card_4). Arena (text) Elo as of 2026-06-19: 31B 1451 (rank 43, "leading dense open model"), 26B-A4B 1438 (rank 61), Gemma 3 27B 1366 (report Table 4).

**Not reported by Google anywhere I could find: SWE-bench Verified, Terminal-Bench, BFCL, Aider Polyglot, HumanEval/MBPP.** The absence of SWE-bench is itself noted by community reviewers (https://gist.github.com/hungson175/61a805368649c225026a69adf2ad87e0).

### 3.2 Community coding-agent results (all UNVERIFIED single-source)

- SWE-bench Verified: 26B-A4B 17.4% vs Qwen3.6-35B-A3B 73.4%, attributed to grigio.org's table (sources "@namcios, @AIHeadlineJP"; methodology not described) — https://grigio.org/can-i-really-code-on-my-pc-gemma4-26b-a4b-vs-qwen3-6-35b-a3b-coding-benchmark/ ; repeated in https://gist.github.com/hungson175/61a805368649c225026a69adf2ad87e0 which also lists Terminal-Bench 2.0 42.9% and "MCP Tool Use" 18.1% for 26B-A4B (origin unstated). Hacker News quotes in that gist: "Refuses to use MCP tools even when asked", "Gets stuck in loops requiring human intervention".
- SWE-bench Lite: 26B-A4B FP8-Dynamic + mini-swe-agent v2.2.8 (bash-in-markdown actions, custom edit tool, `step_limit 100`, temperature 0.3, no reasoning parser, no custom chat template, `--max-model-len 96000`) = **116/300 = 38.67%**, #16 on the 2026-04-16 Lite snapshot, vs SWE-agent+Claude 3.7 Sonnet 48.0 and OpenHands+Claude 3.5 Sonnet 41.67 (https://ai-muninn.com/en/blog/swe-bench-lite-gemma4-26b-38-percent). Failure modes: intermittently empty `tool_calls` with 10+ tools (so native tool calling was abandoned), whole-file rewrites deleting methods, endless exploration without submitting.
- Same author: OpenHands (11 native-JSON tools) -> 40+ errors, never finished a trivial task because Gemma 4 omitted required parameters (`command`, `path`); SWE-agent (plain-text actions) -> fixed a bug in 9 steps. "Gemma 4 can code. It just can't fill out JSON forms reliably." (https://ai-muninn.com/en/blog/swe-bench-local-models-framework-matters)
- 12B QAT Q4_0 on a 75-problem LiveCodeBench subset, thinking off, 4096-token cap: 86.7% vs Qwen3.6-27B Q4_K_M 53.3%; Tau2-airline 15 tasks: 0.467 vs 0.400; 56.3 tok/s decode on a V100 (https://gist.github.com/magnus919/178c2f4fb6513ec74d977fe7213f33da).
- Kaggle Gemma 4 Developer Agent competition public leaderboard (31B W4A16, 4xL4, ~60 hidden tasks per one entrant, "about 120" per another): top public score ~0.15-0.18; typical prompt-only configs ~0.06-0.12; one entrant's best 0.12 = 7/58 at rank 418/1559 on 2026-10-03 (https://github.com/happyc0der/gemma-swe-agent ; search summary of Kaggle notebooks). The official Kaggle pages did not render for me — **task count, deadline (Nov 2 vs Nov 25 vs Dec 2, 2026) and prize pool ($100k vs $110k+) are conflicting across sources; verify on https://www.kaggle.com/competitions/gemma-4-developer-agent**.

### 3.3 Thinking mode

- Enabled by placing `<|think|>` at the start of the system turn; removing it disables thinking. Output: `<|channel>thought\n...<channel|>` then the answer. **12B, 26B-A4B and 31B emit an empty thought block `<|channel>thought\n<channel|>` even with thinking off; E2B/E4B emit none.** Google recommends including the empty block in training prompts when fine-tuning the large models on non-thinking data (https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4 ; https://huggingface.co/google/gemma-4-12B-it).
- Multi-turn: strip prior thoughts from history, **except within a model turn that makes tool calls** (template flag `preserve_thinking`). To turn thinking off mid-conversation also remove `<|think|>` (prompt-formatting page; chat_template.jinja).
- transformers: `apply_chat_template(..., enable_thinking=True)`, `processor.parse_response()` splits thinking/content/tool calls. vLLM: `chat_template_kwargs: {"enable_thinking": true}` per request or `--default-chat-template-kwargs`, plus `--reasoning-parser gemma4` (vLLM recipe).
- Post-training says thinking "improves reasoning-heavy domains such as mathematics and coding" (report Introduction). The SWE-bench Lite author found the reasoning parser *hurt* patch quality (ai-muninn) — **UNVERIFIED**, possibly a parser bug rather than thinking itself.

### 3.4 Native function-calling format (exact syntax)

From the chat template (https://huggingface.co/google/gemma-4-31B-it/raw/main/chat_template.jinja), the prompt-format page, and the function-calling guide (https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4):

```
<bos><|turn>system
<|think|>                                   # only if enable_thinking
{system text}
<|tool>declaration:get_weather{description:<|"|>...<|"|>,parameters:{properties:{location:{description:<|"|>...<|"|>,type:<|"|>STRING<|"|>}},required:[<|"|>location<|"|>],type:<|"|>OBJECT<|"|>}}<tool|><turn|>
<|turn>user
What's the weather in London?<turn|>
<|turn>model
<|channel>thought
...reasoning...
<channel|><|tool_call>call:get_weather{location:<|"|>London<|"|>}<tool_call|><|tool_response>response:get_weather{temperature:15,weather:<|"|>sunny<|"|>}<tool_response|>It is 15 C and sunny.<turn|>
```

Rules: not JSON — bare keys, `<|"|>` as string delimiter, numbers/`true`/`false`/`null` bare, nested `{}`/`[]`, keys sorted, types upper-cased; `assistant` renders as `model`; the model stops after emitting `<|tool_response>` (so `<|tool_response>` must be an extra stop sequence); tool results are matched by `tool_call_id` from `role: tool` messages or a `tool_responses` list on the assistant message; media in tool results become `<|image|>`/`<|audio|>`; a string `arguments` field raises in the template (must be a mapping). EOS ids: 1 (`<eos>`) and 106 (`<turn|>`) (12B config). A reference parser regex from Google: `<\|tool_call>call:(\w+)\{(.*?)\}<tool_call\|>` (function-calling page). vLLM: `--enable-auto-tool-choice --tool-call-parser gemma4 --chat-template examples/tool_chat_template_gemma4.jinja`.

### 3.5 Known tool-calling issues

- Chat template mis-renders an assistant message that has both `content` and `tool_calls` (ends with `<turn|>` without reopening `<|turn>model`), which makes the 26B emit `thought<channel|>` garbage; Google's fix PR #20 (RyanMullins, 2026-04-09) is still unmerged with conflicts as of July (https://huggingface.co/google/gemma-4-26B-A4B-it/discussions/20). Multi-round tool calling: the model "often stops after one successful tool call", claims to have run operations it did not; Google staff escalated 2026-06-12 and promised a PR 2026-07-24; still open at 2026-07-20 per the reporter (https://huggingface.co/google/gemma-4-31B-it/discussions/115). Workaround reported: force an open thought channel after tool responses (the stock template does this when thinking is enabled).
- Servers returning raw `<|tool_call>` text in `content` instead of `tool_calls`: mlx-lm #1096, llama-cpp-python #2227, Ollama "empty tool calls" (ai-muninn framework post).
- Small sizes: E2B/E4B have Tau2 scores of 24-42 vs 69-77 for 12B+; the only size-specific report is that "earlier string-argument failures were attributed to the 12B proxy" when a tool expected integers (https://github.com/happyc0der/gemma-swe-agent). Omitted required parameters on 26B with 11 tools (ai-muninn). No official per-size BFCL numbers exist.
- `tool_chat_template_gemma4.jinja` from vLLM "helped in OpenCode but not in Copilot or Codex" (HF discussion 115).

---

## 4. Google's post-training recipe and fine-tuning guidance

- The technical report's Section 3 is **short**: instruction tuning "follows a similar post-training approach as in Gemma 3", with the main addition being thinking mode; data filtered for PII, unsafe/toxic outputs, mistaken self-identification, duplicates; PT models end with `<eos>`, IT with `<turn|>` (https://arxiv.org/html/2607.02770v1). **No RL algorithm, reward model, distillation teacher, token counts, or agentic/tool-use data mixture is disclosed** — claims elsewhere (e.g., DEV Community articles on logit distillation) are not backed by the report (**UNVERIFIED**). Pre-training cutoff January 2025; TPU v5p/v6e with 4,096-12,288 chips per size (report Table 2).
- Blog-level claims only: "trained on Android development and designed with Agent Mode in mind" (https://android-developers.googleblog.com/2026/04/gemma-4-new-standard-for-local-agentic-intelligence.html); "native function-calling support", "configurable thinking modes" (model card).
- Official fine-tuning guidance: Google docs link QLoRA text/vision guides and a Colab LoRA notebook (docs overview). Prompt-format page: when fine-tuning 12B/26B/31B on non-thinking data, include the empty `<|channel>thought\n<channel|>` block in the model turn; strip thoughts from history except in tool-call turns; "Add BOS explicitly after tokenization; do not tokenize the literal text '[BOS]'" (report Appendix Table 11).
- Unsloth recipe (https://unsloth.ai/docs/models/gemma-4/train): LR 2e-4 (2e-5 for long runs), `adamw_8bit`, r=8-32 with alpha >= r, dropout 0, target all attention + MLP linears, `train_on_responses_only(instruction_part="<|turn>user\n", response_part="<|turn>model\n")`, templates `gemma-4` vs `gemma-4-thinking` (use thinking template for 26B/31B, non-thinking for small), keep >=75% reasoning examples if you want to preserve thinking, strip the duplicate `<bos>` the processor adds; expected SFT loss ~1-3 for 26B/31B; for the MoE prefer bf16 LoRA over QLoRA, start with small rank/short context.
- TRL/PEFT example (E4B, NF4, r=16, alpha=32, dropout 0.05, all 7 projections, LR 2e-4 cosine, seq 4096, ~20M trainable params) (https://dev.to/pulkitgovrani/fine-tuning-gemma-4-for-function-calling-with-trls-new-multimodal-tool-support-4ghf). Community 31B adapters: r=8/16 rsLoRA alpha=2r, LR 1e-4, 2 epochs (karthik-a).
- "it" vs base: all community and competition work fine-tunes the `-it` checkpoints (the competition mandates the IT QAT checkpoint). PT checkpoints exist (report) but there is no published guidance favouring them for agents.
- **For QAT W4A16 serving, train on `-qat-q4_0-unquantized` (the bf16 QAT weights)** — the compressed-tensors artifact "has no quantized forward path" (https://huggingface.co/karthik-a/sparkflashxgemma4); one entrant instead unpacked W4 -> NF4 on CPU for FSDP-QLoRA (takimov).

---

## 5. Ecosystem support status (through Oct 2026)

### 5.1 vLLM

- Architecture `gemma4` landed in **vLLM 0.19.0**; transformers >= 5.5.0 required (`transformers_version 5.5.0.dev0` in the configs; the 12B config says 5.10.0.dev0). Early PyPI builds had a vLLM/transformers-5.5/huggingface_hub dependency conflict (https://github.com/Manzela/gemma4-vllm-deployment ; https://huggingface.co/google/gemma-4-26B-A4B-it/discussions/19). Competition entrants use 0.19.1; a bug reporter used 0.22; the recipe says install nightly.
- LoRA: issue #39246 closed 2026-04-17 by PR #39291, which added `SupportsLoRA` to `Gemma4ForConditionalGeneration` **for the language model only** (maintainer jeejeelee: tower/connector LoRA out of scope; no Gemma 4-specific LoRA test was added; reviewer could not confirm testing on 31B-it) (https://github.com/vllm-project/vllm/issues/39246 , https://github.com/vllm-project/vllm/pull/39291). Current API docs list `Gemma4ForConditionalGeneration` as `SupportsLoRA`, and the 12B `Gemma4UnifiedForConditionalGeneration` inherits it (https://docs.vllm.ai/en/latest/api/vllm/model_executor/models/gemma4_mm/ , .../gemma4_unified/).
- LoRA correctness bug: with a q/v-only adapter on E4B, vLLM 0.22.0 produced output "identical to base-only" (adapter silently not applied, linked to #39815/#39816); a nightly with #39816 raised agreement with HF+PEFT to 99.93% (https://github.com/vllm-project/vllm/issues/47026). **Verify your adapter actually changes outputs in the exact vLLM build you serve with.**
- Multi-LoRA constraints: `--enable-lora --max-lora-rank N --max-loras K --lora-modules name=path`; `--lora-target-modules` to restrict; runtime load via `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True` + `/v1/load_lora_adapter`. A community adapter is served as `vllm serve google/gemma-4-31b-it-qat-w4a16-ct --enable-lora --max-lora-rank 128 --max-loras 8` (karthik-a) — LoRA over a compressed-tensors W4A16 base is therefore at least launchable (**UNVERIFIED** that it was run end-to-end). MoE expert LoRA: vLLM >= 0.15 has fused-MoE LoRA kernels (https://vllm.ai/blog/2026-02-26-multi-lora); 3D PEFT `target_parameters` adapters need `--enable-mixed-moe-lora-format` and `is_3d_lora_weight` (https://docs.vllm.ai/en/latest/features/lora/); a layout fix for PEFT 0.18+ 3D expert LoRAs is PR #52198; fused-MoE LoRA requires the Triton experts backend. **Nothing confirms expert-LoRA on Gemma 4's 26B-A4B specifically; the Manzela write-up (vLLM 0.17-0.19) reported the MoE class lacked `get_expert_mapping()`, blocking bitsandbytes/NF4 loading.** Keep MoE adapters to attention + dense MLP (+ shared expert) unless you test it.
- Attention backend gotcha: global layers use head_dim 512, above FlashAttention-2's 256 limit (https://github.com/Dao-AILab/flash-attention/issues/2427 ; transformers #45201), so vLLM falls back to `TRITON_ATTN` — blamed for E4B running ~9 tok/s on an RTX 4090 (https://allenkuo.medium.com/gemma-4-on-vllm-vs-ollama-benchmarks-on-a-96-gb-blackwell-gpu-804ca4845a21). Expect similar on L4.
- Quantization in vLLM: W4A16 QAT checkpoints auto-detected (no flag); 26B-A4B: `--quantization int8_per_channel_weight_only`, FP8-Dynamic (RedHatAI) works, NVFP4 via `nvidia/Gemma-4-26B-A4B-NVFP4` with `--quantization modelopt`; NVFP4 "broke tool-calling tokens" in one report (ai-muninn SWE-bench Lite post) (**UNVERIFIED**).
- Other recipe flags: `--reasoning-parser gemma4`, `--tool-call-parser gemma4`, `--chat-template examples/tool_chat_template_gemma4.jinja`, `--limit-mm-per-prompt`, `--kv-cache-dtype fp8`, `--language-model-only`, `--async-scheduling`; structured-output schema descriptions are not visible to the model; missing stop token id 106 causes turn-boundary looping if a custom template drops it (Manzela).

### 5.2 Transformers / PEFT / TRL

- transformers >= 5.5 (12B: 5.10); classes `Gemma4ForConditionalGeneration`, `Gemma4ForCausalLM`, `Gemma4Unified*` (12B); `AutoModelForMultimodalLM`/`AutoModelForImageTextToText`; `padding_side="left"` for batched generation; `attn_implementation="sdpa"` in examples (https://huggingface.co/docs/transformers/main/model_doc/gemma4).
- Issues: chat_template missing from `tokenizer_config.json` -> load the separate jinja (https://github.com/huggingface/transformers/issues/45205 — also hits mlx-community conversions); per-layer FA2/SDPA dispatch request for head_dim 512 (#45201); audio-tower eager mask inverted (#48818); vision sliding-mask layer_idx fix (#48482). **E2B/E4B produce gibberish if `use_cache=False`** (which gradient checkpointing / QLoRA tutorials often force) because of KV sharing — Unsloth patched it; 31B/26B hit an `IndexError` from `num_kv_shared_layers=0` -> `[:-0]` in early code (https://unsloth.ai/docs/models/gemma-4/train).
- PEFT: dense linears target normally; on transformers 5 the MoE experts are fused 3D parameters (`mlp.experts.gate_up_proj` / `down_proj`) that need `target_parameters`; PEFT 0.21's conversion step can silently remap dense `gate_proj/up_proj/down_proj` onto the fused experts and drop LoRA from shared-expert linears (https://github.com/unslothai/unsloth/pull/12281); a fused-expert LoRA merged to the wrong weights in one Unsloth report (https://github.com/unslothai/unsloth-zoo/pull/1232); DPOTrainer ref-adapter crash with `target_parameters` (https://github.com/huggingface/trl/issues/5222). Expert names/shapes for Gemma 4 specifically were not confirmed in any source (**UNVERIFIED**).
- TRL: SFTTrainer works with Gemma 4's native system/user/assistant/tool roles and tool-call datasets; GRPO supported via Unsloth (`fast_inference=False`, Unsloth inference instead of vLLM).

### 5.3 Unsloth

- Notebooks: E4B text/vision/audio, E2B vision/audio, E2B GRPO (Sudoku), "31B on Kaggle", 26B-A4B and 31B vision (A100). Claims 1.5x faster, 50-60% less VRAM vs FA2 setups. GGUF export `q4_k_m/q8_0/f16`. Known fixes listed in 5.2. Note the E2B 4-bit checkpoint OOMed on an 8 GB card until layer offload (PLE table) (https://github.com/unslothai/unsloth/issues/7055).

---

## 6. Size trade-offs for a coding agent under fixed compute

### 6.1 Measured throughput (vLLM unless noted)

| Setup | 31B | 26B-A4B | 12B | E4B | Source |
|---|---|---|---|---|---|
| 1x H100, bf16, c=1 / c=16, 32k ctx | 40.3 / 375 tok/s; with MTP 125.3 / 953 | 177.1 / 975; MTP 264 / 1808; DFlash 306 / 1957 | - | - | https://jarvislabs.ai/blog/gemma-4-mtp-vs-dflash-benchmark |
| 1x H100 bf16, 8k ctx, batch | peak 855 tok/s; 1,260 sustained at c=128; TTFT 279 ms | - | - | - | https://inferencebench.io/blog/gemma-4-31b-h100-complete-inference-benchmark/ |
| 96 GB Blackwell workstation, single stream | 22 tok/s | 131 tok/s | - | 124 tok/s (RTX 4090: ~9 tok/s due to TRITON_ATTN) | https://allenkuo.medium.com/gemma-4-on-vllm-vs-ollama-benchmarks-on-a-96-gb-blackwell-gpu-804ca4845a21 |
| DGX Spark GB10 (273 GB/s), NVFP4, vLLM 0.19 | ~7 tok/s | ~52 tok/s | - | - | https://ai-muninn.com/en/blog/dgx-spark-gemma4-26b-nvfp4-52-toks |
| RTX 4090 Q4 llama.cpp / M4 Pro 48 GB | - | 5-10 / 73 tok/s | - | - | grigio.org |
| V100 QAT Q4_0 | - | - | 56.3 tok/s | - | magnus919 gist |

**No published L4 numbers exist.** Estimate (**UNVERIFIED**): the L4's 300 GB/s is close to the GB10's 273 GB/s, so expect single-stream 26B-A4B at FP8/NVFP4 ~40-60 tok/s on one L4 and 31B W4A16 with TP=4 over PCIe roughly 10-25 tok/s; MTP (`-assistant` drafter at matching QAT precision) gave 3.1x on 31B for coding prompts on H100 (3.82x coding-category) and is the single biggest lever for a dense model.

### 6.2 Comparison

| | E4B | 12B | 26B-A4B | 31B |
|---|---|---|---|---|
| LiveCodeBench / Tau2 avg / Codeforces | 52.0 / 42.2 / 940 | 72.0 / 69.0 / 1659 | 77.1 / 68.2 / 1718 | 80.0 / 76.9 / 2150 |
| 128k long-context (RULER 128k / MRCR) | 86.6 / 25.4 | 91.2 / 43.4 | 89.8 / 44.1 | 96.4 / 66.4 |
| Weights bf16 / 4-bit | 16 / 5.5 GB | 25 / 7-8 GB | 52 / 16-18 GB (no official W4) | 64 / 18-22 GB (official W4A16) |
| Decode speed class | fastest (but TRITON_ATTN penalty) | fast | ~4B-class per token; 4-7x faster than 31B | slowest; MTP recovers ~3x |
| Per-token KV (computed, global part) | 16 KiB | 8-16 KiB | 10-20 KiB | 40-80 KiB |
| LoRA training cost | QLoRA 10 GB; LoRA 17 GB | QLoRA ~10-12 GB (est.) | bf16 LoRA >40 GB; QLoRA discouraged; expert-LoRA risky in vLLM | QLoRA 22 GB; bf16 LoRA 2xH100 |
| Tool-calling evidence | weakest (Tau2 42) | decent in a 15-task check | 38.67% SWE-bench Lite with text actions; fails JSON tool schemas | best Tau2; template multi-round bug most benign ("more resilient") |
| Fits 4xL4 for serving | trivially | trivially | yes (bf16 TP4 or FP8 1 GPU) | yes at W4A16 TP4; bf16 TP4 tight |
| Kaggle competition | not allowed | not allowed | not allowed | mandated (`gemma-4-31b-it-qat-w4a16-ct`) |

---

## 7. Implications for our agent

1. **Model choice is fixed for the competition (31B-it QAT W4A16 on 4xL4), so optimise around dense-31B latency.** Budget ~10-25 tok/s per stream (unverified) and use the official `-assistant` MTP drafter at QAT precision with `num_speculative_tokens 4-8`; coding prompts get the largest speculative gains (3.8x on H100). Serve with `--language-model-only`, `--limit-mm-per-prompt '{"image":0,"audio":0}'`, `--kv-cache-dtype fp8`, and the largest `--max-model-len` the KV budget allows after measuring vLLM's *actual* KV bytes/token (community data suggests the hybrid sliding-window allocator may not be fully exploited; 128k x 50-250 KB = 6-30 GB per sequence). For local development, 26B-A4B FP8 on a single 24 GB+ GPU or 12B W4A16 is the fast proxy; note the 12B is the closest in benchmarks per GB.
2. **Do not rely on native `tool_calls` JSON with many tools.** The strongest community SWE result (38.67% SWE-bench Lite) came from a mini-swe-agent-style loop with *one* bash action in a fenced block and a dedicated edit tool; OpenHands-style 11-tool JSON schemas produced 40+ errors per task. If we keep native calls, keep the tool count small (<=5), integer/enum-typed arguments, and parse `<|tool_call>call:name{...}<tool_call|>` ourselves with `<|tool_response>` as a stop sequence; validate every call before executing.
3. **Chat-template hygiene is a correctness issue, not polish.** Known template bugs: assistant turns with content+tool_calls, multiple tool rounds stopping after one call, missing `<|turn>model` reopen. Pin one template (vLLM's `tool_chat_template_gemma4.jinja` or a patched copy), render training data with the *same* template, keep the empty `<|channel>thought\n<channel|>` block when thinking is off, keep thoughts inside tool-call turns and strip them elsewhere, stop on ids 1 and 106, and confirm `<bos>` is not duplicated.
4. **Thinking: test both.** Google says thinking helps coding; one SWE run found the reasoning parser degraded patches. Run an A/B on a 30-task local split; if thinking is kept, fine-tune with >=75% reasoning trajectories (Unsloth guidance) or the model's thinking behaviour degrades.
5. **LoRA plan.** Train on `gemma-4-31b-it-qat-q4_0-unquantized` (bf16 QAT weights) with NF4 QLoRA, r=16-32, alpha = r to 2r, LR 1e-4 to 2e-4, targets q/k/v/o + gate/up/down, vision excluded, loss only on `<|turn>model` spans, chunked cross-entropy (262k vocab), sequences packed to the longest context the GPU allows (4xL4: ~8k; H100: 16-32k). Serve with `--enable-lora --max-lora-rank <= 128` over the W4A16 base, and **run a base-vs-adapter diff test in the exact vLLM build** (issue #47026 showed silent no-op adapters in 0.22.0). Avoid lm_head/embedding adapters (tied embeddings, no documented vLLM support) and avoid the MoE path entirely for the competition.
6. **Long context is a strength we can use but must pay for.** 31B is the only size that stays >95% RULER at 128k, and 256k is supported; but KV at 128k is 5-10 GB per sequence even in the ideal computed case and possibly 3x more in current vLLM. Prefer 32k-64k with aggressive context compaction (the official harness exposes `ContextCacheConfig`/`EventsCompactionConfig` per a competition entry) over raw 128k.
7. **Known speed/stability gotchas to pre-empt:** TRITON_ATTN fallback from head_dim 512 (no FA2) — benchmark attention backends on L4; QAT NVFP4 reportedly broke tool tokens (use W4A16/FP8); `use_cache=False` gibberish on E2B/E4B if we ever use them as sub-agents; transformers chat_template loading from the separate jinja; T4s cannot run vLLM INT4 kernels (use llama.cpp Q4_0 GGUF there).
8. **Expectation setting.** Public Kaggle scores sit at 0.06-0.18 with prompt-only agents; community SWE-bench Verified for the family is ~17% (single source) versus ~38% on Lite with a well-matched scaffold. Scaffold/action-format choices have moved results more than anything else reported so far; LoRA should target format adherence (tool syntax, edit discipline, submit behaviour, no whole-file rewrites) before attempting to teach new coding skill.

### Open items to verify before committing
- Official Kaggle rules page (hidden task count, deadline, adapter size/rank limits, vLLM version in the harness) — pages did not render here.
- Whether vLLM's hybrid KV allocator applies the 1024-token window and k=v reuse for Gemma 4 (measure `KV cache tokens` at startup for 31B).
- LoRA on top of compressed-tensors W4A16 end-to-end (load + output changes + speed hit).
- Actual L4 tokens/s for 31B W4A16 TP=4 with and without MTP.
