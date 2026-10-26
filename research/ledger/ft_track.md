# Fine-tuning track ledger (Workstream 4: E4B distillation LoRA)

Session log of the fine-tuning pipeline work. Dates are UTC. VM root `/mnt/biohub/kdata/gemma4` (R). Scripts: `vm/`
(copied to `~/gemma4_vm/`). Everything below was measured, not planned, unless marked "plan".

## 2026-10-25 — pipeline build (steps 1-5 of the workstream brief)

### Base model (step 1)
- `google/gemma-4-E4B-it-qat-q4_0-unquantized` exists on Hugging Face (ungated, 9 files, `model.safetensors` 15.9 GB,
  `Gemma4ForConditionalGeneration`, bf16, text config: hidden 2560, 42 layers, PLE 256/layer, `num_kv_shared_layers` 18,
  tied embeddings, softcap 30). Downloaded with `vm/download_model.sh` in 4 min to `R/models/gemma-4-E4B-it-qat-q4_0-unquantized`.
- Its `tokenizer.json` is byte-identical (md5 72b1044…) to the 12B/31B one; its `chat_template.jinja` differs from the
  12B/31B template only in the `add_generation_prompt` branch (no empty-thought stub when thinking is off), so training
  renderings are identical across the three models (verified: same text for a tool-calling sample).
- The harness really enables thinking per request: `adk_submission.resolvers.generation.apply_thinking_config_to_model`
  bridges the bundle's `thinking_config` into `extra_body.chat_template_kwargs.enable_thinking=True` (+ budget), so
  training with `enable_thinking=True` (the `<|think|>` token in the system turn) matches inference.

### Data pipeline (steps 2-3)
- `vm/convert_traces.py` (new): ATIF-v1.7 trace parser + episode filters (resolved, cut after the first successful
  `submit_patch` that follows the last edit, no protected-file edits, <= 24 calls, no identical consecutive calls, no
  continuation nudges, <= 3 per task, masking of rejected turns: FileEditError / FileWriteError / FileReadError /
  ValueError / BudgetExceeded / ADK parameter rejection / hallucinated tool).
- `vm/prepare_data.py` v3: header derived from a bundle (`--bundle submissions/v5_single`: `prompts/system.md`, tool list,
  `eval_config.yaml` budgets incl. the 90 s command timeout; graph block only when graph tools are declared); real tool
  declarations as ADK sends them (`vm/tool_declarations.json`, dumped through `FunctionTool._get_declaration` +
  `lite_llm._function_declaration_to_tool_param`); `--source harness-trace` (+ `--split-by-repo`); `--rerender` of earlier
  windows with trajectory filters and truncation at the call cap; per-assistant-message label masking (`train: false`);
  `--thought-cap N` tokens (tail kept, sentence boundary); `stats.json` per output.
- Trace statistics (all `scratch/kev_*_out/eval` runs = pub022, v3t2k, v4single, v4phased, v5single; 31B only):
  109 resolved 31B episodes -> kept 46 (23 tasks: fastapi 28 episodes / 14 tasks, rich 18 / 9). Dropped: over 24 calls 34,
  protected-file edit 8 (all `tests/test_*.py` edits), identical consecutive calls 6, no edit 4, no submit after last
  edit 3, nudges 3, per-task cap 5. Masked turns 30 (FileWriteError 24 = `/tmp` scratch files rejected by `write_file`).
  Calls per kept episode: 8-24, median 20. 3 closing texts synthesised.
- `datasets/traces_31b_v1/{all,fastapi,rich}.jsonl`: 126 / 73 / 53 windows (8-step windows, last 5 observations verbatim).
  Token lengths (E4B tokenizer, thought cap 600): median 6,697, p90 8,569, max 10,413 -> at max-len 7,168 only 79/126
  windows fit, at 8,192 104/126. Decision: train the E4B at max-len 8,192 (12.6 GB peak at 7k; see trainer).
  Task ids per split: fastapi = 11194, 13537, 14301, 14372, 14419, 14458, 14463, 14492, 14786, 14794, 14873, 15589, 5077,
  5624; rich = 2943, 3006, 3043, 3067, 3278, 3480, 3518, 3521, 3718. Cross-fit rule: an adapter trained on split
  `fastapi` is evaluated on rich tasks only (and vice versa).
- External re-render (`sft_v4_wide`, 3,138 trajectories, under the v5 header; fastapi/rich repos excluded, none present):
  | variant | filters | trajectories | windows (<= 7,168 tok) | tokens | supervised |
  |---|---|---|---|---|---|
  | ext28 | <= 28 steps, first edit <= 10, >= 1 test cmd, repo cap 20 | 19 | 63 | 339k | 61k |
  | ext32 | <= 32 steps, same | 47 | 147 | 815k | 153k |
  | ext36 | <= 36 steps, first edit <= 14, windows cut at call 28 | 548 (260 repos) | 2,264 before tokenisation | see stats.json | |
  The brief's "<= 24 steps" keeps 4 trajectories (OpenHands teachers explore ~30 steps); "first edit <= 10" is the
  next binding filter (658 rejections at <= 36 steps). v1 therefore trains on ext36 (+ traces); ext28/ext32 are kept
  for a strict ablation (`datasets/e4b_v1/tok_strictA`).

### Trainer (step 4)
- `vm/train_qlora.py`: E-model path = `Gemma4ForConditionalGeneration` (keys `base_model.model.model.language_model.layers.N…`),
  bnb skips `lm_head`, PLE projections and the vision/audio towers (towers moved to CPU), LoRA regex
  `language_model.layers.N.(self_attn|mlp).(q,k,v,o,gate,up,down)`; the 18 KV-shared layers have no k/v projections in
  transformers 5.17, so 258 target modules (24x7 + 18x5), 69.8M trainable params (0.87 %).
- Load smoke on one T4 (GPU 3, `datasets/sft_v4_mid/tok_12b_7k`, 3 optimizer steps x 2 micro-batches, r32 a64, fp16):
  weights 8.5 GB after load, peak 12.6 GB at 5.6k-7k tokens, 295-318 tok/s per T4, loss 1.63 -> 1.32 -> 1.19
  (first micro-batch 0.78), no non-finite steps, adapter saved with the expected key prefix (516 tensors).
- `vm/launch_train.sh` / `vm/start_train_free.sh` take `--model <path>` and `--max-len N` (`start_train_free.sh` also
  `--data --run --epochs --rank --lr --alpha --max-gpus`); `vm/merge_tokenized.py` takes `dir=k` repeat factors and
  writes token shares (the ">= 50 % external tokens" check).

### Packaging (step 5, G0)
- `vm/make_submission.py --bundle submissions/v5_single --model gemma-4-e4b-it-qat-w4a16-ct --adapter <peft dir> --out …`
  copies the bundle, sets `model:` + `adapter: main_lora`, writes the adapter with `target_modules` as a list,
  `base_model_name_or_path = google/<model>`, fp16 weights, and enforces G0: key prefix
  `base_model.model.model.language_model.layers.`, module names within the 7 projections, finite fp16, <= 3,072 MiB.
  Load-smoke adapter packaged as `submissions/e4b_v5_smoke0` (133 MiB, 42 layers) and VALID in harness-venv
  (`discover_adapters` sees `main_lora` rank 32).
- `vm/make_g1_notebook.py` (new): Kaggle notebook = scorer stack (pinned image, wheelhouse, `VllmServer` +
  `discover_adapters`, LoRA mounted as `main_lora`), 20 prompts at T=0 to the base served name and to `main_lora`
  (differ count, tool-call parse rate, tok/s, reasoning rate), then 3 full tasks through the Evaluator; adapter weights
  travel as a private Kaggle dataset (`--prepare-adapter-dataset`).

### Open / next (filled in below as they complete)
- 20-step smoke adapter (r32 a64 lr 1e-4) on `datasets/e4b_v1/tok_fitA`: running on GPU 3 (tmux `ft_mix`).
- E4B LoRA v1 (1 epoch, ext36 + traces fastapi x3): waits for the smoke; only GPU 3 is free (GPUs 1-2 serve the E4B
  track's vLLM, GPU 0 belongs to another project), so v1 runs on one T4 unless a second frees up.
