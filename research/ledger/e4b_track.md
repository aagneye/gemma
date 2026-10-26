# E4B track ledger (Workstream 3: replica calibration + E5/E6 experiments)

Owner: E4B-track session (started 2026-10-25 by the main session). Scope: `vm/serve_vllm.sh`, `vm/wait_vllm.sh`,
`vm/run_replica.sh`, `vm/opportunistic_replica.sh`, `vm/build_v4.py`, `vm/prompts/{phase_solver,phase_verifier,e4b_demo}.md`.
Nothing here is committed by this session; the main session merges decisions into `research/STATE.md`.

## Baseline facts (Kaggle L4x4, kernel `gemma4-kaggle-eval-e4b-v3t2k`, downloaded to `scratch/kev_e4b_out/`)
- Bundle `submissions/e4b_v3t2k` = v3 prompt, T 0.2, thinking 2048, 28 calls / 8 min / 80 turns, command timeout 240 s,
  model `gemma-4-e4b-it-qat-w4a16-ct`. Kaggle served it with TP=4 on 4xL4 (no hf-overrides), vLLM up in 5.9 min.
- 75 tasks ran (71 Kaggle-sound first, then 4 unsound): **8/71 sound resolved** (8/75 overall).
  Resolved: rich_3006, fastapi_14301, fastapi_14463, rich_3454, fastapi_14786, fastapi_14873, fastapi_9753, rich_3905.
- Duration (sound tasks): mean 95.3 s, median 61.4 s, p90 190 s, max 404 s -> 0 timeouts (cap 480 s). Calls: mean 12.2,
  median 11, max 28. No-patch runs: 2.
- Outcome taxonomy from the traces (71 sound): 59 submitted a wrong patch (edit + submit, unresolved), 7 resolved with
  submit, 1 resolved via the fallback working-tree diff (no submit), 2 ended without submit (edit, then 3 run_commands),
  2 submitted with patch_size 0. => **the dominant bucket is "wrong patch, never verified", not budget** (budget use 12/28
  calls, 95/480 s). E5 (verifier loop, more budget) targets exactly this bucket; E6 targets instruction following.
- `analyze_traces.py` on the 75 Kaggle runs: modes WRONG_PATCH 65, RESOLVED 8, NO_PATCH_CALLS 2; 64/75 runs ran at least
  one test (resolved 6/44 with one test run, 1/16 with two); edit errors not_found 19, ambiguous 6 (3+ edit errors -> 0/15
  resolved; 3+ repeated identical calls -> 0/13); stop reasons submitted 70, text_stop 3, submitted_empty 2, no nudges;
  median per-call latency 33 s on L4x4. The E4B tests but does not act on the result: it submits anyway.

## Serving the E4B on one T4 (2026-10-25 09:46 UTC)
- `serve_vllm.sh`/`wait_vllm.sh` now take `TP` (default 4), `GPUS` (CUDA_VISIBLE_DEVICES), `PORT`, `MAXSEQ`; ports other
  than 8000 get tmux session `vllm_<port>` and log `logs/vllm_serve_<port>.log`, so one single-GPU server per free T4 can
  run beside the others. `run_replica.sh` takes `PORT` and a time argument `auto` (= the bundle's own max_time_minutes).
  `opportunistic_replica.sh` is now a per-server queue runner (MODEL/TP/GPUS/PORT/NEED_MIB/CONC; old 31B defaults kept).
- E4B on GPU 1, TP=1, fp16, MEM 0.92, CUDA graphs 1-8, scorer flags (gemma4 tool/reasoning parsers, 32k context,
  auto tool choice, no hf-overrides): **loads and serves without errors** (vLLM 0.19.1 supports the E4B's KV sharing
  (18 shared layers) and per-layer embeddings; weights 11.5 GB, KV cache 45,360 tokens = 6.9 concurrent 32k requests).
  No fallback to MODE=eager or FLEX_ATTENTION was needed.
- Speed (chat completions, T=0, 200 output tokens):

| Setting | Prompt tokens | TTFT | Prefill | Decode per stream |
|---|---|---|---|---|
| single stream, short prompt | 22 | 0.05 s | - | 57 tok/s |
| single stream, long prompt | 4,494 | 8.4 s | ~540 tok/s | 32.5 tok/s |
| 2 concurrent, long prompts | 4,491 each | 4.5 s (prefix-cache hit) | - | 24.2 tok/s each (48 aggregate) |
| 3 concurrent, long prompts | 4,491 each | 0.1-0.3 s (cache) | - | 17.5 tok/s each (52 aggregate) |

  Command used (inline python, urllib streaming against `/v1/chat/completions` on port 8001) is in the session log; the
  replica runs use concurrency 1 like the scorer, so the single-stream numbers are the relevant ones.
- The old `opprep` tmux session (31B opportunistic queue, port 8000, waiting since Oct 22) could not be stopped from this
  session (permission classifier). It only starts when all four GPUs have >= 12.2 GB free, which is never the case while
  an E4B server holds a GPU; it never saw port 8001/8002. Residual risk: if every E4B server is down and GPU 0's foreign
  job shrinks, it would grab all four GPUs for the 31B.

## Calibration run (gate for everything after it)
- Started 09:52 UTC: `REPLICA_TIME_SCALE=3 PORT=8001 bash run_replica.sh submissions/e4b_v3t2k e4b_v3t2k_cal 71 8 1`
  (tmux `rep_8001`; 71 Kaggle-sound tasks; concurrency 1; provisional clock scale 3 from the expected L4x4-TP4 vs T4-TP1
  speed ratio; the Kaggle run never came within 76 s of the cap, so the scale only matters for the budget display).
- Note: the harness Evaluator takes `task_ids` as a set, so the replica's execution order is the tasks.jsonl order, not the
  Kaggle round-robin order; with all 71 tasks run this does not affect the pairing.
- Result: pending.

## Experiments (replica, 71 Kaggle-sound tasks, concurrency 1, one config per free T4)
Bundles built with the new spec builder (`build_v4.py --only ...`; every bundle passed validate_directory + compile):

| Bundle | Change vs baseline e4b_v3t2k | Budgets | Thinking |
|---|---|---|---|
| e4b_v5 (control) | system_v5_1 prompt (v5 + the /workspace-only write rule), command timeout 90 | 28 calls / 8 min / 80 turns | 2048 |
| e4b_e5 | LoopAgent(max_iterations=3) over [solver, verifier]; solver = v5 minus submit, hands over CHANGED/REPRO/TEST; verifier reruns repro + one `timeout 60 pytest -x -q -k`, fixes once, diff checklist, submit_patch, FAILED report hands back | 60 calls / 20 min / 120 turns, timeout 90 | 2048 |
| e4b_e6_t1024 / t2048 / t4096 | short prompt `e4b_demo.md` (~400 tokens, one worked example, "one sentence then one call") | 28 / 8 / 80, timeout 90 | 1024 / 2048 / 4096 |
| e4b_e6r_t2048 | research session's `e4b_short.md` (built only if the file appears) | 28 / 8 / 80, timeout 90 | 2048 |

Queue on GPU 2 (port 8002, `results/e4b_queue_8002.txt`): e4b_e5 -> e4b_v5 -> e4b_e6_t2048 -> e4b_e6_t1024 -> e4b_e6_t4096.
10:04 UTC: on the main session's request all three new prompts carry the v5.1 rule (write_file/edit_file accept /workspace
paths only; scratch files via run_command heredocs or `python -c`; measured: 27 of 53 v5 tasks on the 31B wasted 29 calls on
/tmp write_file), and the control `e4b_v5` is built from `system_v5_1.md`. The E5 run (started 10:00 with the old prompts, 0
tasks finished) was stopped and restarted at 10:04 with the rebuilt bundles.
GPU 3 is left free for the fine-tuning session unless it stays idle overnight.

### Run ledger
| Date (UTC) | Bundle | Port/GPU | Scale | n | Resolved | vs baseline (W/L) | Mean / p90 s | 120-task proj. at Kaggle speed | Buckets | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-25 09:52 | e4b_v3t2k_cal | 8001 / GPU1 | 3 | 71 | - | calibration | - | - | - | running |
