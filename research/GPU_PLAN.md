# GPU & Timeline Plan — one T4 (16 GB, local) + one H100 (80 GB, cloud) + Kaggle L4×4 quota

Dates: today 2026-10-16 · Paper Track Nov 12 · entry/merge Nov 25 · **final Dec 2**. Seven working weeks. One Kaggle submission per day, 11–46 h scoring latency ⇒ at most ~40 more leaderboard probes; local evaluation decides everything.

## 1. What each device is for

### T4 (sm75, 16 GB, fp16 only, no bf16, no FlashAttention-2, no vLLM INT4 kernels)
Use it as the **data, harness and test bench**, never as a training box for 12B/31B.
1. Download the 21 GB dataset + wheelhouse; rebuild the repaired grader (missing `typing_inspection`, `inline_snapshot`, `dirty_equals`, `pytest-httpbin`; remove shadowing release wheels); run the gold-patch soundness check on all 129 tasks; mark empty-patch-passing tasks. CPU/disk-bound.
2. Run the sandbox farm (Docker, 4 GiB / 2 vCPU per task as on the scorer) for teacher and self rollouts against a *remote* vLLM endpoint (H100 or teacher API). The T4 hosts containers, not the model.
3. Data pipeline: convert external trajectories to the 9 ADK tools + harness JSON observations; render with the Gemma 4 V2 chat template; assert loss masks; build compaction-shaped contexts; dedupe; length histograms. CPU-bound.
4. Template and parser unit tests: round-trip rendered samples through vLLM 0.19.1's `gemma4` tool/reasoning parsers. For live serving on the T4 use E2B/E4B via transformers/bitsandbytes or llama.cpp GGUF (vLLM W4A16 kernels need Ampere+).
5. QLoRA smoke tests only on E2B/E4B at ≤4k context (10 GB class) to debug the training script before paying for H100 time.
6. Localisation benchmark: map gold hunks → graph nodes; evaluate grep / BM25 / raw-embedding / centred-embedding / PPR variants (pure NumPy + NetworkX). Feeds both the agent and the paper.

### H100 (80 GB)
Use it in **alternating phases**: generation (vLLM) and training (Unsloth/PEFT). Do not co-locate.
- **Serving for rollouts and CV:** `gemma-4-31b-it-qat-w4a16-ct` (~18–22 GB) or the 12B W4A16 with `--kv-cache-dtype fp8`, `--async-scheduling`, `--enable-lora --max-lora-rank <= 64`, gemma4 parsers, `max_model_len 32768`, concurrency 16–32 with the T4-hosted sandbox farm. Expect ~400 tok/s aggregate for the 31B (bf16 reference 375 @c=16) ⇒ one 129-task pass ≈ 45M tokens ≈ 30 h if sequential, ~3–4 h at concurrency 16. Use the `-assistant` MTP drafter if the W4A16 pairing works (3× on coding prompts, UNVERIFIED on L4/W4A16).
- **Training 31B:** NF4 QLoRA on `google/gemma-4-31B-it-qat-q4_0-unquantized` (22 GB resident), r 32–64, all language linear layers, vision excluded, LR 1e-4 cosine, warmup 3%, bs 1 × grad-accum 16, `max_seq_length` 24k, Unsloth gradient checkpointing, chunked cross-entropy (262k vocab makes it mandatory), response-only loss with error-turn masking, PEFT ≥ 0.19.1 export. Estimate 7–11 h per epoch for 3k × 16k tokens (UNVERIFIED; measure tok/s in the first hour and re-plan).
- **Training 12B:** bf16 LoRA at 32k context, same recipe, ≈3.5–4.5 h/epoch.
- **Checkpoint gate (every 200 steps):** temperature-0 base-vs-adapter diff in vLLM 0.19.1 → 30-task smoke run counting parser rejections, test-file edits, loops → only then resolution rate.

### Kaggle L4×4 (≈15 h/week at 2× quota burn)
Reserve for **scorer-equivalent full runs** only: one 120-task run ≈ 11 h. Use it to (a) calibrate the per-task cap with the adapter attached, (b) run the final candidate end-to-end before each real submission. Never use it for training.

## 2. Compute budget (my estimate)
| Item | H100-hours |
|---|---|
| 3–4 full 31B QLoRA runs (2 epochs) | ~70–90 |
| 6–8 12B/E4B runs + ablations | ~40–50 |
| Rollouts: 2 teacher-format passes + 2–4 self-RFT passes over 129 + ~500 external tasks | ~120–150 |
| Held-out CV runs (≥100 tasks × 2 seeds × ~8 candidates) | ~60–80 |
| **Total** | **~300–370 H100-h ≈ $600–1,100 at $2–3/h** |
Teacher API spend (open-weight via OpenRouter, ~1–2M output tokens per 129-task pass) is small; keep a provenance manifest per example for the Apache-2.0 release.

## 3. Week-by-week
**Week 1 (Oct 16–22) — ground truth.** Dataset + wheelhouse down; repaired grader; gold-patch soundness table; reproduce the official notebook on the H100 with 31B and 12B at the 5.5-min cap on 30 tasks (2 seeds) to get our own baseline and tok/s; settle open questions 1–3 and 6 (adapter applied? `search_similar_code` semantics? compaction? speed with adapter). Build the held-out CV set (≥100 SWE-rebench/SWE-Gym tasks with images) through `swegemma`. First Kaggle submission: a robust prompt-only package (hygiene finaliser, caps, thinking on) to establish our LB noise floor and prove the pipeline.
**Week 2 (Oct 23–29) — data.** Localisation benchmark + labels from gold patches; trajectory conversion pipeline for Open-SWE-Traces / SWE-Hero / Nemotron-SFT-SWE-v2 / Nebius / Kwai-Klear; teacher rollouts (DeepSeek-V4 or Qwen3.6 via the harness) on 129 + 500 tasks; procedure supervision set; paper skeleton started. Localisation skill script v1 (grep-first + PPR) shipped and A/B'd on CV.
**Week 3 (Oct 30–Nov 5) — SFT round 1.** 12B bf16 LoRA and 31B QLoRA on ~4k examples; checkpoint gates; CV under cap for both sizes; pick the size by **Nov 5**. Submit best adapter package (first LoRA on the LB; keep the prompt-only package as fallback final #2).
**Week 4 (Nov 6–12) — RFT + paper.** Self-rollouts with the round-1 adapter on external tasks, filter, RFT epoch; ablation tables (thinking budget, caps, localiser on/off, adapter rank) for the paper; **paper submitted Nov 12**.
**Week 5 (Nov 13–19) — round 2 training + robustness.** Preference pairs (optional), error-masking refinements, hygiene/loop negatives; long-run stability (no 12-h overrun) checked on Kaggle L4×4 with the adapter attached.
**Week 6 (Nov 20–26) — freeze candidates.** Two final packages chosen by paired CV (≥2 seeds, McNemar); team merger deadline Nov 25 if merging.
**Week 7 (Nov 27–Dec 2) — submit, verify, reproduce.** Final submissions by Nov 30 to leave two scoring days of slack; write the reproducibility README and training code for the winner obligations.

## 4. Kill criteria and fallbacks
- If the adapter is not applied by vLLM 0.19.1 or costs >25% decode speed at r≥32 (week 1): drop to r16 attention+MLP, or ship prompt+skills only and put the LoRA effort into the 12B where the time budget is looser.
- If 31B at the 5.5-min cap loses more tasks to timeouts than the 12B gains from speed (week 3 CV): switch to 12B for the main track.
- If held-out CV does not move with the adapter but public-repo CV does: we are overfitting the four repos — rebalance data toward external corpora and retrain.
- Always keep a validated no-adapter package as one of the two finals.
