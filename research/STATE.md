# Factory state ledger (update after every build / eval / submission)

## Current best (2026-10-25)
- **Paired-eval best: v5_single** (31B, `vm/prompts/system_v5.md`, T 0.2, thinking 4096, 28 calls / 8 min, 90 s cmd timeout): **26/53** Kaggle-sound tasks, 276 s/task (120-task projection 9.1 h). Paired: vs pub022 **+3** (4W/1L) on 50 common; vs v3t2k +1 (4W/3L) on 52; vs v4_single +3 (5W/2L) on 49. Shipped daily from Oct 25 (`results/ship.txt`, fallback v3t2k).
- **E4B baseline** (`submissions/e4b_v3t2k`, same bundle with model e4b): **8/75**, 97 s/task, 12.5 calls mean, 2 no-patch; all 6 of its resolved tasks that pub022 attempted were also solved by pub022. Small-model LB top = 0.06 -> this already leads it. First E4B LB slot: Oct 27, then weekly.
- **Goal:** #1 main track (needs ~16/62 private, see `C:\Users\aagne\.claude\plans\sleepy-hatching-squid.md`) and the $10k small-model bonus. LB best so far 0.17.

## Ledger
| Date | Artifact | Change | Paired eval (Kaggle-sound, same order) | LB |
|---|---|---|---|---|
| 10-18 | base_12b | 12B, own prompt | - | 0.08 |
| 10-19 | pub022 | exact public 0.22 bundle (31B, T 0.2, 8 min/28 calls, thinking 4096) | 22/50 (Kaggle L4) | 0.15 |
| 10-20 | v3_31b | + edit-by-call-10, output caps, hygiene | - | 0.17 |
| 10-21 | v3t2k_31b | v3 + thinking 2048 | 23/52 (25/52 incl. 2 extra); paired 23 vs 22, 3 wins / 2 losses | pending (57491112) |
| 10-21 | v4_single, v4_phased (31B + _12b variants) | loop-breaking tool rules, edit protocol, timeout 90; phased = scout/fixer/finisher | built, validated, compiled; 12B phased smoke: hand-over works, scout ignores its 8-call stop (24-28 calls) | - |
| 10-21 | 12b_r32_v4mid adapter | QLoRA r32 on 1,263 curated trajectories, 394 steps, loss 1.08 -> 0.30 | not evaluated | - |

## What we learned (keep)
- Same bundle, two runs: 5/50 tasks flip; union of two runs 25/50. LB differences < 3 tasks are noise.
- Failure buckets (pub022, 50 runs): no edit 10, unverified wrong patch 14, lost edit 9 (0 resolved), 8-min timeouts 7.
- Prompt-only stop rules are not obeyed by the 12B (scout 24-28 calls); untested on the 31B.
- Skills: 0/4 locally, forum 0.15 -> 0.00. Multi-agent analyzers / voting: worse in other teams' paired evals.

## Open hypotheses (next builds, ordered by expected value)
1. VM replica scorer with subprocess sandbox (validating vs Kaggle's 71 sound tasks) -> unlimited paired evals.
2. v4_single vs v3t2k (tool rules + timeout 90) on the replica.
3. Structural stop for the scout that does not rely on obedience (e.g. scout with include_contents/turn limits, LoopAgent).
4. 12B + adapter at 2x speed with more calls.
5. Variance exploitation: the union of 2 runs solves +2-3 tasks -> any in-run mechanism that retries a failed attempt.

## Queue / running
- VM: subprocess-sandbox controls (gold/empty, 129 tasks) - running 10-22.
- Kaggle quota: 2.8 h left until 10-24 00:00 UTC.

## 2026-10-22 update
- **VM replica scorer validated**: `scorer-host-venv` (Kaggle host `pip freeze`, py 3.12.13) + subprocess sandbox -> gold/empty controls give 70 sound tasks; **69/71 agree with Kaggle** (VM-only rich_4070; Kaggle-only rich_3782, rich_4075). 31B serves on 4xT4 (decode 8.9 tok/s, prefill 57 tok/s). Tools: `vm/run_replica.sh`, `vm/compare_runs.py`, `vm/sub_status.py`.
- Calibration run started 13:02 UTC: pub022 on the replica, 50 tasks, time 36 min, concurrency 3 (Kaggle-env pub022 = 22/50).
- Day-4 (v3t2k) **failed on the scorer**: "Notebook hit an unhandled error while rerunning". Discussion 751339: since ~04:00 UTC Oct 21 many teams' byte-identical bundles fail ("Notebook Threw Exception"); no host fix yet. Not caused by thinking 2048.
- Day-5 submitted: v4_single (ref 57525114), may hit the same scorer issue.
- Research round 3 (`research/raw/08_notebooks_round3.md`): identical bundles vary with SD 1.56 tasks/58; the public "0.22" configs average 9.25-10.0/58 (~0.17) over 8-10 draws; a 2-task gain needs ~11 draws per arm to see on the LB. Forcing earlier edits traded timeouts for wrong patches (scottweeden, 48 paired tasks). Concurrency inflates timeouts (8 -> 2 concurrent: 33 -> 19 timeouts of 48) -> calibrate the replica's time scaling against Kaggle's sequential run. Tasks are mostly always/never solved (rho 0.59).
- Implication for the goal (> 0.22 = >= 13/58 on a draw): raise the true mean from ~10/58 to >= 12/58 (paired-eval +3-4 tasks on 50), then spend daily slots on that config (the LB keeps the best draw; P(draw >= 13) ~ 26 % per draw at mean 12).

## 2026-10-22 16:25 UTC
- Replica calibration attempt 1 invalid: at concurrency 3 with a 36-min wall cap the T4s ran 6-16x slower than Kaggle L4s -> 11/16 runs timed out (VM 5/16 vs Kaggle 10/16 on the same tasks). Fix: `vm/patch_replica_clock.py` (replica-only harness clock scaling, REPLICA_TIME_SCALE) + concurrency 1 (as the scorer).
- VM GPUs are now partly used by other projects (7.6/7.6/3.8/4.0 GB) -> the 31B (TP=4) cannot start. `vm/opportunistic_replica.sh` waits for free memory, then runs the queue `results/replica_queue.txt`: pub022_cal (16) -> v4_single (16) -> v4_phased (16), scale 10.
- Kaggle L4 evals of v4_single and v4_phased (50 tasks each) are scheduled for 2026-10-24 00:05 UTC (`vm/push_at.sh`, quota reset).
- Watching: v4_single LB submission 57525114 (`logs/subwatch.log`); scorer outage (discussion 751339) may fail it.

## 2026-10-24 results (Kaggle L4, paired, same task order)
| Bundle | Resolved | vs pub022 | Mean s/task (120-task proj.) | Verdict |
|---|---|---|---|---|
| v4_single | 22/49 | +0 (3 wins / 3 losses) | 297 (9.9 h) | REJECT (tie) |
| v4_phased | 14/37 | -4 (0 wins / 4 losses) | 396 (13.2 h, would break the 12 h cap) | REJECT |
- LB: v4_single 0.13 (one draw; consistent with a ~0.17 mean). Best LB still 0.17.
- Conclusion: prompt rules and the scout/fixer/finisher split do not raise the mean; the phased design costs time. Prompt-level changes on top of the 0.22 profile have now tied 3 times (v3t2k, v4_single) -> the next lever must change capability or compute per task, not wording.

## 2026-10-24 ECC adoption (user request: copy what fits from Affaan Mustafa's setup)
- Source: affaan-m/everything-claude-code @ 90606c83 (MIT). Vendored 4 markdown skills into `.claude/skills/`
  (loop-design-check, benchmark-optimization-loop, eval-harness, agent-introspection-debugging) and wired them into
  the factory loop (CLAUDE.md). Skipped all Node.js hook features and skills duplicating superpowers/claude-skills.
- New candidate `v5_single` = v4_single + reproduce-first, callers lookup, explicit minimal-diff list, restate-objective
  recovery (ideas from ECC gateguard / orch-fix-defect / build-error-resolver / agent-introspection-debugging).
  Kaggle L4 eval pushed 2026-10-24 ~18:20 UTC (50 tasks, same order); also queued on the VM replica.
- Expectation (honest): three wording-only changes have tied; v5 is measured, not assumed. Adopt only on >= +3 paired.
- Project is now a git repo (atomic commits on `main`); no remote configured yet.

## 2026-10-24 18:15 UTC — submission + plan to win
- Submitted v3t2k again (ref 57603042; its Oct 21 attempt was lost to the scorer outage, host confirmed and promised reruns).
  Oct 23 slot was lost (the old one-shot queue had ended) -> `vm/daily_ship.sh` now ships `results/ship.txt` every UTC day.
- Found the **$10k Small Model bonus** (E2B/E4B base, LoRA allowed, one of the 2 final picks; top public 0.06).
  Plan: `research/PLAN_TO_WIN.md` (Track A 31B daily draws + mean raising; Track B E4B baseline -> E4B bundle -> 31B->E4B
  distillation LoRA). E4B (11 GB) downloaded to the VM.

## 2026-10-25 09:50 UTC — WS0 done; three parallel sessions running
- Shipper: Kaggle refuses a new submission while one is PENDING (400 body captured). `vm/daily_ship.py` deployed (tmux + cron watchdog); `results/ship.txt` = v5_single (fallback v3t2k); `results/ship_schedule.txt` = E4B slot on 2026-10-27 (`aagneye/gemma4-e4b-v3t2k` v1, byte-checked). v5 goes out as soon as 57603042 finishes scoring.
- Sessions started by the user: research sprint (`research/raw/09*,10*,11*`, FT_DATA_SPEC, INSTRUCTION_DESIGN, e1/e2/e4b prompt drafts), E4B track (serving, replica calibration, phase builder, E5/E6), fine-tuning pipeline (trace converter, E4B trainer path, smoke adapter). They log to `research/ledger/*.md`; the main session commits.
- **New measured bug -> v5.1**: the "/tmp scratch" rule (since v3) makes the model call `write_file` on /tmp paths, rejected by the harness as path traversal: v3t2k 16 tasks/16 calls, v4_single 31/35, v5 27 of 53 tasks / 29 wasted calls (11 recovered via run_command); pub022 0. `vm/prompts/system_v5_1.md` = v5 + one line (scratch files only via run_command heredoc or `python -c`). All Oct-31 bundles (v5.1 control, E1, E2) build on v5.1.
- Bucket shift pub022 -> v5 (50 common): 2 NO_PATCH_TIMEOUT -> RESOLVED, 2 WRONG_PATCH -> RESOLVED, 1 RESOLVED -> WRONG_PATCH; 12 WRONG_PATCH stayed (E1 target), 4 NO_PATCH_CALLS stayed (E2 target). v5 stop reasons: 40 submitted, 7 submitted empty, 5 text stop, 1 calls exhausted.
- Oct 31 Kaggle plan (30 GPU-h): G1 smoke-adapter load test (~1 h) + paired evals v5.1 / E1 / E2 (~9 h each).
- 09:58 UTC: `submissions/v5_1` built (make_submission.py path; only the one prompt line differs from v5_single), validated; its Kaggle eval notebook `kev_v5_1` is scheduled for push at 2026-10-31 00:05 UTC (tmux `pushat_v51`). E1/E2/G1 notebooks follow when the sessions deliver the phase builder, prompts and smoke adapter. The E4B session is serving E4B on GPU 1 (port 8001) and running the replica calibration (`results/replica/e4b_v3t2k_cal`).
- 10:45 UTC: E1/E2 bundles built from the new spec builder (`vm/specs/e1_31b.json` = SequentialAgent phase_solver (thinking 4096) -> phase_verifier (thinking 2048); `e2_31b.json` = single agent with `e2_demo.md`; `e1s_31b.json` = stacked research-sprint drafts for week 2). All compile. Oct 31 schedule (tmux pushat_*): 00:05 kev_v5_1, 00:06 kev_e1_31b, 04:45 kev_e2_31b; G1 smoke-adapter notebook follows when the FT session delivers it (~28 of 30 GPU-h). Notebooks are regenerated before the push if prompts change.
- Research sprint delivered (uncommitted until its turn ends): raw/09a (bucket ceilings: union of all 31B runs 28/49, v5 25, 21 tasks never solved by anyone -> procedure changes cap at ~+3; beyond that is capability), raw/09, 10, 11, FT_DATA_SPEC.md, INSTRUCTION_DESIGN.md (ranked cards + experiment queue), prompt drafts e1_solver/e1_verifier/e2_demo/e4b_short.

## 2026-10-26 02:30 UTC — session results merged (E4B track, FT pipeline, research sprint)
- **E4B replica validated**: `e4b_v3t2k_cal` on the VM (TP=1 T4, clock scale 3) agrees with the Kaggle E4B run on **69/71 tasks (97%)**, same 8 resolved. The VM replica is now the E4B decision tool (unlimited runs).
- E4B experiments (71 Kaggle-sound tasks, replica): baseline e4b_v3t2k 8/71 (338 s/task on T4); **e4b_v5 (v5.1 prompt) 10/71** (+2, same time); **e4b_e5 (LoopAgent x3 solver->verifier, 20 min/60 calls) 10/71** (+2, 427 s/task = 26% slower); e4b_e6_t2048 (short prompt) 0/10 so far. Neither meets the +3 gate yet; the E4B's dominant bucket is "wrong patch, never verified" (59/71), not budget.
- FT pipeline delivered: E4B bf16 base downloaded; `convert_traces.py` (109 resolved 31B episodes -> 46 kept, 23 tasks; 30 masked turns, 24 of them the /tmp write_file refusals); `prepare_data.py` v3 (bundle-derived header, harness-trace source, error masking, thought cap); datasets `traces_31b_v1`, `sft_v5_ext` (ext28/32/36), `e4b_v1/tok_fitA` (2,018 windows, 11.2M tokens, 91% external) + `tok_fitB`, `tok_strictA`; trainer E4B path (Gemma4ForConditionalGeneration, 258 LoRA targets, 69.8M params, ~250-320 tok/s per T4, 12.6-13.4 GB); **smoke adapter e4b_smoke20** (20 steps, loss 0.64 -> 0.61) packaged as `submissions/e4b_v5_smoke20` (G0 passed); G1 notebook `submissions/nb_g1_e4b_smoke` + adapter dataset dir prepared.
- Research sprint delivered raw/09, 09a, 10, 11, FT_DATA_SPEC.md, INSTRUCTION_DESIGN.md and the e1/e2/e4b prompt drafts (see 10:45 entry).
- Drift fixed: newer `convert_traces.py` deployed to the VM; stray `prompts/build_v4.py` and old `daily_ship.sh` removed from the VM; `e4b_short.md` deployed. All scripts pass syntax/JSON/CRLF checks; builder selftest OK. Two independent code reviews running.

## 2026-10-26 03:30 UTC — debug pass (user request): two independent reviews + fixes
Confirmed bugs and fixes (all deployed; details in vm/README.md):
- **Training launcher gate** (`start_train_free.sh`): required `SYNC_OK` even for single-GPU runs, but the trainer prints it only for world > 1 -> every 1-GPU launch reported "DDP SMOKE FAILED" (this is why E4B LoRA v1 never started on Oct 25). Fixed; GPU 0 is now excluded by default in `start_train_free.sh`, `launch_train.sh` (default GPUS 1,2,3) and `opportunistic_replica.sh` (refuses TP > allowed GPUs).
- **Data pipeline**: (1) the `<|tool_response>` token that ends a tool-call turn (an EOS the model must generate) was never supervised -> now included in each call turn's label span; (2) rejected turns were masked only for harness traces -> now masked from the full observation at conversion time for every source; (3) trajectories longer than the call cap were cut at the cap, showing budget warnings while the teacher kept exploring -> now cut at cap-10 (before the first warning); (4) `get_status` is budget-free in the harness -> excluded from call counts and warnings; (5) `convert_traces.py` protected-file set now matches `prepare_data.py` (test_*.py, *_test.py, setup.py). Datasets rebuilt as `traces_31b_v2`, `sft_v5_ext/ext36b`, `e4b_v2/tok_fitA|fitB` under the shipped v5.1 header; E4B LoRA v1 launches from `build_e4b_v2_data.sh`.
- **Shipper** (`daily_ship.py`): the per-kernel failure counter never reset (two transient errors would silently switch to the fallback bundle for the life of the process) -> reset daily; ledger rows now keyed by new ref (a submission stamped after midnight is still recorded); watchdog uses exact tmux name match.
- **Analysis**: timeout buckets came from a 470 s wall-clock rule, wrong on the replica (clock scale) and over-counting on Kaggle (verification time) -> now from the harness error column; nudges were counted from the wrong event source (always 0) -> from `continuation_nudge` events; "ambiguous" edit errors keyed on the wrong word; `compare_runs.py` no longer counts crashed rows as 0 s.
- **LB stats** (`sub_status.py --stats`): the API returns one page of 20 submissions; from ~Nov 8 the per-config means and the "earliest valid ref" (final-pick rule) would have silently dropped older draws -> paged. Ship messages now start with "<bundle>:" so grouping is correct.
- **Oct 31 Kaggle schedule**: four 4-h notebooks would have cost ~36 GPU-h (> 30) and the tmux timers did not survive a reboot -> cron entries: 00:05 G1 + E1, 05:00 E2 + v5.1 (v5.1 cut to 3 h); ~28 GPU-h.
- Left as known limitations: rejected turns older than the last 5 observations in the OLD external windows stay trainable (fix = re-convert from the raw corpora; planned for data v3); the G1 probe measures tok/s with a cold/warm order bias (the 3 full Evaluator tasks in the same notebook are the real test); `run_replica.sh` multiplies an explicit time with REPLICA_TIME_SCALE (use `auto`).
- 02:45 UTC: corrected data rebuilt (`e4b_v2/tok_fitA`: 1,676 windows, 8.8M tokens, 1.5M supervised; sanity: 1,774/1,783 `<|tool_response>` tokens now supervised) and **E4B LoRA v1 (`e4b_r32_v1`) training started on GPU 3** (r32 a64, lr 1e-4, 1 epoch, max-len 8192, eff. batch 16; ~12 h). The fixed launcher passed its single-GPU gate.
