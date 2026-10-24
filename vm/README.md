# vm/ — scripts for the Azure VM (rogii-gpu, 4x Tesla T4, 16 GB each)

State as of 2026-10-17: environment built, 12B weights + two trajectory corpora downloaded, 20,624 training
windows tokenized, and run `12b_r32_v1` (625 steps, 4-GPU DDP, QLoRA r32) launched in tmux.

Paths on the VM (project root `/mnt/biohub/kdata/gemma4`, also reachable as `/data/biohub/kdata/gemma4`):
```
.venv/                      training env: torch 2.8 cu126 (fp16 on T4), transformers 5.17, peft 0.21, bnb 0.50
harness-venv/               swegemma / adk-submission / adk-eval-core (grading + harness), installing
models/gemma-4-12B-it-qat-q4_0-unquantized/   bf16 QAT export used for training (24 GB)
datasets/swe-hero, datasets/nebius-openhands   raw trajectory corpora (CC BY 4.0)
datasets/sft/*.jsonl        converted windows; datasets/sft/tok_12b_8k/train.parquet = merged tokenized set
runs/<run>/ckpt_<step>/     PEFT adapters (adapter_config.json + adapter_model.safetensors)
logs/<run>.log, logs/*.log  everything else
data/wheelhouse/            41 harness wheels from the Kaggle "Gemma 4 Developer Agent Wheelhouse" dataset
```

## Pipeline (what was actually run)
```bash
bash bootstrap.sh                                  # apt, docker, uv venv (then torch upgraded to 2.8 cu126, torchao removed)
hf download google/gemma-4-12B-it-qat-q4_0-unquantized --local-dir models/...   # ungated, no token needed
bash download_trajectories.sh                      # SWE-Hero + nebius OpenHands trajectories
python prepare_data.py --source swe-hero --max-examples 2000 --scan-limit 100000 --out datasets/sft/swe_hero.jsonl
python prepare_data.py --source nebius-openhands --max-examples 2000 --scan-limit 100000 --out datasets/sft/nebius.jsonl
python prepare_data.py --tokenize "datasets/sft/swe_hero.jsonl" --model models/gemma-4-12B-it-qat-q4_0-unquantized --max-len 8192 --out datasets/sft/tok_12b_8k_swehero
python prepare_data.py --tokenize "datasets/sft/nebius.jsonl"   --model models/gemma-4-12B-it-qat-q4_0-unquantized --max-len 8192 --out datasets/sft/tok_12b_8k_nebius
python merge_tokenized.py --out datasets/sft/tok_12b_8k datasets/sft/tok_12b_8k_swehero datasets/sft/tok_12b_8k_nebius
bash launch_train.sh 12b_r32_v1 datasets/sft/tok_12b_8k 1 32 1e-4 4 "--max-steps 625"   # tmux session train_12b_r32_v1
```
Follow training: `tail -f /mnt/biohub/kdata/gemma4/logs/12b_r32_v1.log` (JSON lines every 5 steps; checkpoints every 100).

## Measured facts (T4)
- 12B NF4 + LoRA r32 (131M trainable): 2k tokens 12.5 GB / 179 tok/s; 4k 13.3 GB / 152 tok/s; 8k 14.9 GB / 108 tok/s per GPU.
- Real-data loss starts ~1.0–1.3. fp16 is stable (GradScaler skips the first 1–2 steps while calibrating; harmless).
- 8k windows OOM in the full training loop with chunk 1024 → use `--max-len 7168 --chunk 512` + expandable segments (what launch_train.sh does).
- Unsloth 2026.10.6 refuses fp16 for Gemma4Unified (falls back to fp32) → not used; plain PEFT + chunked CE instead.
- `prepare_model_for_kbit_training` must NOT be used: it upcasts the 262k×3840 embedding to fp32 (~4 GB).
- Whole-epoch cost: 81M tokens ≈ 37 h on 4×T4. 625 steps × 16 windows ≈ 10k windows ≈ 19 h.

## Data facts
- SWE-Hero: 34,269 trajectories, OpenHands, Qwen3-Coder-480B teacher, median 115 messages (~57 tool calls); no resolved flag (all kept).
- nebius: 67,074 trajectories, `resolved` 0/1 (32k resolved), `exit_status` "submit"; same message schema plus tool_call_id.
- Conversion keeps trajectories with 4–60 tool steps, no identical consecutive calls, no edits to existing test/config files, ≤2 per instance, ≤80 per repo, shortest first; adds `rm -f <scratch files>` + `submit_patch` + a closing text turn; windows of 8 tool steps with a structured summary of earlier steps and only the last 5 observations verbatim (mirrors ADK compaction).
- Qwen teachers emit no reasoning; each tool-calling turn's plan text is moved into the Gemma `thought` channel at tokenization so thinking stays alive.

## What the T4 box cannot do
Train the 31B at useful context; serve the QAT w4a16 checkpoints with vLLM (needs Ampere+). Those belong on the H100 or Kaggle L4x4.

## Known pitfalls hit today
- `pkill -f <pattern>` inside an ssh one-liner kills the one-liner itself if the pattern text appears anywhere in it — use `[p]attern` tricks AND keep launch text out of kill commands.
- `nohup ... &` inside ssh: add `< /dev/null` and `disown`, or ssh hangs for 60 s.
- `/data/biohub` is a symlink to the 1 TB disk at `/mnt/biohub`; the 2.8 TB `/mnt` is ephemeral.

## Update 2026-10-17 (evening): grader state, submission builder
- **Local grader (public repos)**: `vm/gold_check.py` + repaired wheels/image variants give **21/129 sound tasks** (gold passes, empty fails): fastapi 15/67, requests 5/13, httpx 1/1.
  Fixed so far: missing wheels (httpx2, typing-inspection, inline-snapshot, dirty-equals, ...), dropped shadowing release wheels, per-repo images (`swebench-sandbox-{fa,rich,req}`).
  Not fixed: all 48 rich tasks pass with an EMPTY patch (some package outside /workspace provides a newer rich; sandbox has no network, so not a PyPI fetch) and 48 fastapi tasks still fail with
  `Router.__init__() got an unexpected keyword argument 'on_startup'` (a too-new starlette is still selected). Treat the public-repo grader as a smoke test only; local CV on these repos anti-correlates with the leaderboard anyway.
- **Submission builder**: `vm/make_submission.py` writes agent.yaml / prompts / configs / eval_config (+ adapters/main_lora) and submission.zip, and validates with `adk_submission.validate_directory`.
  Shipped agent = single root LlmAgent, 6 core tools (no graph tools, no sub-agent), the *trained* system prompt, budgets 5.0 min / 50 calls / 80 turns / 150 s (identical to the numbers in the training prompts), T=1.0, top_p 0.95, thinking budget 4096, max_output_tokens 8192.
  Baseline (no adapter) package validated at `/mnt/biohub/kdata/gemma4/submissions/base_12b.zip`.
- **Adapter loading (mostly retired)**: vLLM 0.19.1 `Gemma4ForCausalLM` (the class the scorer uses for the 12B via --hf-overrides) has `hf_to_vllm_mapper = {"model.language_model.": "model."}` and `SupportsLoRA`, so adapters trained on the multimodal wrapper load. Still verify the saved keys in `runs/12b_r32_v3/ckpt_100` look like `base_model.model.model.language_model.layers.N...` and do a base-vs-adapter diff test.
- **Shell pitfall**: `pkill -f "pattern"` inside an `ssh '...'` command whose own text contains the pattern kills the ssh shell (exit 255). Use `[x]pattern` AND keep kill commands in a separate call from launch text.

## Kaggle submission flow (used 2026-10-18 for the baseline; repeat for adapter runs)
1. `python make_submission.py --out submissions/<name> [--adapter runs/.../ckpt_N]` then `--validate submissions/<name>` in harness-venv.
2. `python make_notebook.py submissions/<name> submissions/nb_<name> aagneye/<slug> "<Title>"` writes a notebook that embeds the bundle files, rewrites them and zips `/kaggle/working/submission.zip`,
   plus `kernel-metadata.json` (private, no GPU, no internet, competition attached only). NOTE: an adapter bundle is ~250 MiB and cannot be embedded as text; for adapter runs attach the adapter as a private Kaggle
   dataset (`kaggle datasets create`) and copy it into `adapters/main_lora/` inside the notebook (metadata `dataset_sources`).
3. `kaggle kernels push -p submissions/nb_<name>` (runs in ~30 s on CPU), check `kaggle kernels output` equals the validated bundle.
4. `kaggle competitions submit gemma-4-developer-agent -k aagneye/<slug> -f submission.zip -v <version> -m "<msg>"`; status via `kaggle competitions submissions gemma-4-developer-agent`.
- Scoring happens afterwards on Kaggle's 4xL4 machine (hours); the notebook's own accelerator is irrelevant (a public CPU-only notebook scored 0.08). One submission per day; the slot is consumed at submit time.
- Baseline submitted: ref 57334428, notebook aagneye/gemma4-12b-baseline-v1 version 2 (version 1 failed on a newline bug in my generator, fixed). Package = 12B w4a16, no adapter, thinking on, 5.0 min / 50 calls / 80 turns / 150 s, T=1.0.

## Local copy of the Kaggle scorer (2026-10-18)
- Kaggle's public score = resolution rate on 58 HIDDEN private-repo tasks; it cannot be computed outside Kaggle. What we copy is the method:
  the same swegemma two-phase harness (Phase 1 agent in Docker sandbox, Phase 2 pytest verification) with the scorer's EvalConfig
  (events compaction 15/2/14336/5, context cache 2048/1800/10, submission limits, adapter routing) on our 21 sound public tasks.
- Serving: `vm/serve_vllm.sh` (vLLM 0.19.1 from the wheelhouse in `vllm-venv`, scorer flags incl. `--reasoning-config` for the thinking budget,
  `--hf-overrides` Gemma4ForCausalLM, LoRA main_lora). T4-specific: fp16, gpu-mem 0.84, max 8 seqs, CUDA graphs for batch 1-8, and a LOCAL patch to
  `vllm/v1/attention/ops/triton_unified_attention.py::_get_tile_size` (tile 16 for 512-wide heads; T4 has 64 KB shared memory; original saved as .orig).
  `vm/wait_vllm.sh` starts it in tmux `vllm`. Single-stream decode: base 13.8 tok/s, adapter 15.5 tok/s; prompt processing only ~100-480 tok/s.
- Scoring: `vm/run_local_score.sh <submission_dir> <tag> <time_min> <concurrency>` -> results/local/<tag>/{fa,req,hx}/task_results.jsonl + summary JSON.
  Because the T4s are ~25x slower per task than the scorer's 4xL4 under concurrency, the local time cap is raised (150 min) so the 50-call / 80-turn
  budgets bind instead, as they do on the scorer. Local numbers measure quality under the call budget, not time pressure.
- Training bug found 2026-10-18: run 12b_r32_v3 computed the loss outside the DDP wrapper, so the 4 ranks never synchronised gradients
  (each trained its own adapter on 1/4 of the data); rank 1 finished first and the final barrier timed out (NCCL abort at step ~583).
  ckpt_500 = rank-0 adapter trained on ~2,000 windows. Fixed in train_qlora.py (DDP wraps the loss module, no per-rank skip, trainer_state.pt for resume).

## 2026-10-18 evening: skills, v2 prompt, curated data, plan
- Plan: `research/PLAN_TOP10.md` (31B + disciplined harness as main line; 12B LoRA as upside; daily-slot schedule; decision gates).
- **Skills** (`vm/skills/`): `locate` (issue -> ranked files/symbols via weighted grep + definition bonus; git-free fallback) and `finalize`
  (revert protected files, delete scratch, py_compile, diff summary). Validated in the sandbox image on real snapshots: gold file ranked #1 for
  rich_3454 and requests_7205. ADK tool: `run_skill_script(skill_name, file_path, args={...})`; scripts run in a temp dir, so they `chdir('/workspace')`.
- **Prompt v2** `vm/prompts/system_v2.md`: locate -> read -> edit -> ONE targeted test -> finalize -> submit -> text reply; loop/hygiene rules.
- `make_submission.py` now takes `--model --time --calls --turns --prompt --skills --thinking`. Packages on the VM: `base_12b`, `base_31b`
  (5.5 min / 40 calls / 60 turns), `v2_12b` (skills + prompt v2, 45 calls / 70 turns), `lora_v3_ckpt500`.
- Notebook `aagneye/gemma4-31b-baseline-v1` v1 pushed (output verified = base_31b); NOT submitted yet (slot). Adapter dataset `aagneye/gemma4-lora-v3-ckpt500` created.
- Local scoring (tmux `score_base`, `score_v2`; 21 sound tasks; vLLM on the T4s is ~40-80 min/task): first traces showed the ckpt_500 adapter
  grep-thrashing (67 run_command / 52 errors on one task) -> its run was stopped; base vs v2 continue overnight.
- Curated SFT subsets from the v3 windows (`build_v4_short.py`): short (<=30 steps, <=2 errors): 169 traj / 666 windows; **mid (<=36, <=3): 1,263 traj / 6,113 windows / 458 repos (chosen)**; wide (<=42, <=4): 3,138 traj.
- `scripts/after_scoring.sh` (running): when both scoring runs finish -> stop vLLM -> `launch_train.sh 12b_r32_v4mid datasets/sft_v4_mid/tok_12b_7k 1 32 1e-4 4` (~15 h).
- Shell rule (hit it three more times today): never put `pkill -f <pattern>` in the same ssh command as text containing the pattern; kill in one call, launch in another.

## 2026-10-18 night: forum/notebook round 2 -> plan revision 2
- 12B baseline scored 0.08. The public 0.22 cluster = flexonafft "Budget-Aware Coding Agent v2" (31B, T 0.2, thinking 4096, 8 min / 28 calls / 80 turns / 240 s, CALL PLAN prompt). Full intel: research/raw/07_forum_round2.md + 07b_top_notebooks_large.md; plan: research/PLAN_TOP10.md (rev 2).
- Packages on the VM: `pub022` (exact 0.22 reproduction; notebook aagneye/gemma4-31b-pub022-repro v1 queued for the next slot via scripts/submit_when_open.sh), `v3_31b` (0.22 profile + prompts/system_v3.md; notebook aagneye/gemma4-31b-v3-prompt v2), `v2_12b` (skills smoke), `base_31b` (our old prompt; shelved).
- Skills smoke (12B): invoked, but the model misuses the schema (`task_text`, missing skill_name, extra list/load calls). Scripts now accept any option name / positional / stdin text. Skills stay a gated Day-6 experiment.
- Local A/B protocol: 21 sound tasks, 12B served by vLLM on the T4s (~40-80 min/task) -> at most two configs per night; paired comparison; adopt only if >=2 tasks better.
- Skills smoke, first 2 of 4 tasks (12B, v2 prompt, 50-call budget): fastapi_15588 unresolved, 44 calls, 10 run_skill_script calls (locate x3, finalize x5); fastapi_15661 unresolved, 45 calls, 23 skill calls (locate x11). The 12B burns its budget re-running skills instead of editing. This matches the forum's 0.15->0.00 reports; skills are off the main line unless a 31B smoke looks different.
- Day-2 submit loop: Kaggle returns 400 on CreateCodeSubmission until the daily quota resets at 00:00 UTC; the loop retries every 5-10 min (pid in logs/kaggle_submit.log).
- Skills smoke final (18:19 UTC): 4/4 tasks done, **0 resolved**; traces hold 61 run_skill_script calls (locate 34, finalize 16). Decision: skills are dropped from the submission line; `vm/skills/` stays as paper-track material (localization benchmark). after_smoke.sh then took over the GPUs for the DDP check + retrain.

## 2026-10-19 morning: hand-off stall, shared GPUs, submit-loop fix
- **The VM is shared with other projects.** At ~18:25 UTC Oct 18, minutes after our vLLM released the GPUs, another project's job (`scripts/train.py --config configs/dual_v3_s2.yaml`) took GPU 2, and later a whisper LoRA job (`/mnt/voice`) joined it there. `after_smoke.sh` waited for *all four* GPUs to be free and stalled for 13 h. Never kill those jobs.
- New `start_train_free.sh [min_gpus=3]`: waits for >= min free GPUs (<500 MiB used), runs the DDP smoke on them with `CUDA_VISIBLE_DEVICES`, and launches with `GPUS=... NPROC=...` (now supported by `launch_train.sh`) and grad_accum = round(16 / n) to keep the effective batch ~16.
- 07:55 UTC: DDP smoke on GPUs 0,1,3 -> SYNC_OK x3, adapter saved; `12b_r32_v4mid` running (world 3, grad_accum 5, 394 optimizer steps, ~3.2 min/step -> ~21 h, ETA ~Oct 20 05:00 UTC).
- **Kaggle CLI success message changed**: a successful `competitions submit` now prints "0 submissions remaining today." (not "Successfully submitted"), so the old loop kept retrying (harmless 400s). Day-2 `pub022` was actually submitted 00:09:32 UTC Oct 19, ref **57373958**. `scripts/submit_when_open.sh` now confirms success from the submission list and takes an optional not-before time; Day-3 (`gemma4-31b-v3-prompt` v2) is queued for 00:02 UTC Oct 20.

## 2026-10-19: scoring on Kaggle's own environment (vm/make_kaggle_eval.py, vm/kev_status.py)
- Why: the T4s cannot serve the 31B at useful speed, and our Docker grader turned out to disagree with Kaggle's sandbox.
- `make_kaggle_eval.py controls ...` -> CPU notebook (no GPU quota): gold and empty patch through the harness Evaluator with `sandbox='subprocess'` on all 129 public tasks (~25 min). `make_kaggle_eval.py agent ... --bundle <dir> --order-csv results/kaggle_soundness.csv --hours H` -> L4 notebook: vLLM started like the official notebook / scorer, bundle run task by task until H hours, `eval/results.csv` + `patches.json` in the kernel output.
- Gotchas found: (1) the default Kaggle image is Python 3.13 and the wheelhouse is cp312 -> pin `docker_image` to the official notebook's image (`gcr.io/kaggle-private-byod/python@sha256:37c64f...`); (2) unknown `machine_shape` ids silently fall back to "T4 x2" (31B then dies on bf16) -> the official notebook uses `NvidiaL4`; (3) thousands of sandbox `WARNING` log lines overflow the IOPub channel (CellTimeoutError) -> root/library logging set to ERROR, progress via print; (4) `kaggle kernels logs` returns nothing while a kernel is running.
- **Kaggle-environment soundness (results/kaggle_soundness.csv): 71/129 sound** = fastapi 29 + rich 42; requests 0/13 and httpx 0/1 (gold fails). Only 8 of our 21 Docker-sound tasks are Kaggle-sound -> local T4/Docker A/Bs measured mostly the wrong tasks; they are retired. All A/Bs now run on Kaggle-sound tasks.
- GPU quota: 30 h/week (refresh Saturdays 00:00 UTC); L4 notebooks bill at 2x.
