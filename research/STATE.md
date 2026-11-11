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
- 09:00 UTC: E4B replica queue: `e4b_e6_t2048` (short prompt, 2048 thinking) **7/71** (baseline 8, v5.1 10) -> the short prompt does not help; t1024/t4096 still running. v1 training at step 65/105 (loss 0.43, ETA ~12:30 UTC). v5 LB submission 57631546 still PENDING after 19.5 h (scorer backlog); today's slot waits on it.
- New tools: `vm/eval_adapter_replica.sh` (package adapter -> serve base+LoRA on one T4 -> held-out-repo replica run -> paired comparison) and `REPO_FILTER` in `run_replica.sh` (cross-fit evaluation). Pipeline test with the 20-step smoke adapter on GPU 1 in progress.
- 11:10 UTC: **GPU 1 was taken by the other project** (`dual_v3_skel` training, 3.8 GB) as soon as our calibration server stopped; the E4B server cannot fit beside it. Our GPUs are now 2 (E4B experiment queue, then fitB training `e4b_r32_v1b` queued) and 3 (v1 training, then the held-out rich evaluation `e4b_v5_lora1_rich` on port 8003, queued). `eval_adapter_replica.sh` now waits for the card to be released before starting vLLM and supports `FIRST=n` smoke runs.
- 12:45 UTC: **E4B LoRA v1 trained** (`runs/e4b_r32_v1/final`: 105 steps, loss 0.43, 0 non-finite). Within a minute of the training process ending, **the other project took GPU 3** (two jobs) — the queued rich evaluation aborted ("GPU 3 is not free"). We now hold only **GPU 2**. Decisions: the E4B experiment queue (e6_t1024 at 5/56, no gain) and the fitB training waiter were stopped so GPU 2 stays ours; `serve_vllm.sh` gained `LORA_DYNAMIC=1` (runtime adapter load/unload, so later adapters are evaluated without a restart gap); the v1 rich evaluation now runs on GPU 2 / port 8002.
- 13:00 UTC: **all four VM GPUs now carry the other project's jobs** (GPU 2 was taken during the 60 s restart gap of our adapter server); the E4B replica and training are blocked until a card frees up. Fallback: the v1 adapter is uploaded as the private Kaggle dataset `aagneye/gemma4-e4b-lora1-adapter`; the Oct 31 G1 notebook will evaluate base vs adapter on the 42 rich (held-out) tasks on Kaggle L4 (replaces the smoke-adapter G1; the v5.1 control moves to the following week to stay within 30 GPU-h).
- 14:00 UTC: **v5 scored 0.18 on the public LB** (ref 57631546; our best so far; = ~10/58, consistent with the ~0.17-0.19 mean the paired eval predicts). The shipper submitted today's v5 draw automatically (ref 57668588, pending). LB history: 0.08 (12B), 0.15 (pub022), 0.17 (v3), 0.13 (v4), 0.17 (v3t2k), 0.18 (v5).
- 17:00 UTC: GPUs 1 and 3 freed up. **E4B LoRA v1b** (rich-trace mix, evaluated later on fastapi) training on GPU 3 (~12 h); the last E4B prompt experiment (e6_t4096) queued on GPU 1; v1 held-out rich evaluation running on GPU 2 (0/6 so far, base also 0/6).
- Commit policy (user, 2026-10-26): commits show aagneye only — no Claude Co-Authored-By trailer from now on.

## 2026-10-29 06:15 UTC — status
- LB draws: v5 0.18 (10-25), **0.12** (10-26), 10-28 pending -> v5 mean so far ~0.15 (noise SD ~0.03). **E4B first draw 0.01** (10-27; small-model board top 0.06) -> the hidden set is much harder for the E4B than our 71 public tasks (8/71 = 11%).
- **E4B LoRA v1 REJECTED**: held-out rich 0/42 vs base 4/42 (losses rich_3905, 2725, 3067, 3006). Failure mode: the adapter runs commands endlessly (1,208 run_command calls on 42 tasks, ~29/task; 18 NO_PATCH_CALLS, 15 runs hit the call cap) — it imitated the exploration-heavy OpenHands teacher data (91% of tokens). v1b (same recipe, rich traces) trained (loss 0.47) — same data mix, not evaluated; the Oct 31 Kaggle G1 test of v1 was removed from the schedule (saves ~9 GPU-h).
- Lesson: external OpenHands trajectories teach long exploration; next adapter must be trained mostly on short, successful own traces (31B, <= 20 calls) — or not at all. Kaggle quota: 0 h until Oct 31 00:00 UTC; E1 (00:05) and E2 (05:00) evals remain scheduled.

## 2026-10-31 — VM-first instruction loop (plan approved; user reviews each prompt draft)
- The VM had been deallocated Oct 30 20:12 UTC (not by the user); restarted 05:41 UTC; `/mnt/biohub` had to be re-created and mounted (the mount point lives on the ephemeral disk). Shipper back; daily draws so far: v5 0.18, 0.12, 0.15, 0.10 (mean ~0.14 = ~8/58), E4B 0.01; Oct 30 draw pending.
- Kaggle quota reset (30 h): E1 (verifier gate) and E2 (demonstration prompt) L4 evals pushed 05:45 UTC. E4B weekly slot dropped (hidden-set 0.01); fine-tuning paused.
- 31B replica server up on all 4 T4s (TP=4, KV 29k tokens); calibration/baseline run `v5_1_vm` started (50 Kaggle-sound tasks, concurrency 2, clock scale 4) — paired baseline for all VM comparisons.
- Draft `vm/prompts/system_v6_gates.md` (systems-thinking redesign: five-line STATE, six event-gated gates, budget override; 957 words / ~1,250 tokens, 13 must/never/always sentences vs 19 in v5.1, no count-based rules) — awaiting the user's review before any run.
- 06:10 UTC: user approved the v6 draft for the VM test (`research/ledger/prompt_reviews.md`). Bundle `submissions/v6_gates` built and compiled (spec `vm/specs/v6_gates.json`; same budgets as v5.1). Its 50-task replica run (`v6_gates_vm`) is queued to start automatically when the `v5_1_vm` baseline finishes; the paired comparison lands in `results/replica/v6_gates_vm/compare.txt`. Note: `build_v4.py --spec X --only X` builds nothing (the filter does not match spec names) — use `--spec` alone.
- 08:00 UTC (user decision): **no Kaggle GPU for testing; tests run on the VM only.** E1/E2 Kaggle evals to be cancelled (~2 h in; the API exposes no session id and has no cancel command, so the user stops them in the Kaggle UI). Stale E1/E2 `push_at` cron lines removed. Submissions are unaffected (CPU notebook, scored on Kaggle's machines). Scoring now takes ~24-26 h, so each daily draw starts ~2 h later than the last and some calendar days get none (~25 draws left before Dec 2).

## 2026-11-02 — v6 VM result; v6 shipped (user decision); second paired round running
- **VM paired run (50 Kaggle-sound tasks, same order, clock scale 4, 2 tasks at a time):** v5.1 21/50 → v6_gates **23/50** (+2; wins fastapi_15589, 14458, 14419, rich_2943; losses rich_3676, rich_3063; sign p = 0.69; fastapi 10→13, rich 11→10). By the +3 rule this is a REJECT; the user decided to ship whichever is higher, so v6 ships.
- Buckets v5.1 → v6: WRONG_PATCH 18→14, NO_PATCH_CALLS 4→7, NO_PATCH_TIMEOUT 6→6, WRONG_PATCH_TIMEOUT 1→0. Runs that ran a test 14→30 of 50 (with ≥1 test 19/30 resolved, without 4/20). New flaw: 11 `write_file("/tmp/repro.py")` refusals (path traversal) — the `/tmp/repro.py` example in the v6 prompt primes it; after-budget edit attempts 4→6.
- **VM calibration vs the Kaggle v5 run on the same 50 tasks:** 42/50 agree (84%, target 85%); Kaggle 25 vs VM 21. The VM is harsher only through timeouts (3 Kaggle-resolved tasks time out on the VM; Kaggle mean 276 s/task vs VM 1200 s = 4.35x > scale 4) → scale raised to 5.5 for the next runs.
- LB: v5 draws 0.15 (Oct 30, 57811591) and 0.15 (Oct 31, 57850509); seven v5 draws mean ≈ 0.14. Scoring now takes ~24-32 h, so Nov 1 got no submission.
- Ship: **v6 submitted 05:15 UTC, ref 57896193** (notebook `aagneye/gemma4-31b-v6-gates` v1, CPU), its zip byte-identical to `submissions/v6_gates`; `results/ship.txt` = v6 (line 1), v5_single (line 2). The shipper was held for 2 min (`ship.txt` commented out) so it would not send v5 first.
- Round 2 (`vm/run_pair.sh`, tmux `rep_r2`, from 05:10 UTC): v5.1 and v6 again, run at the same time on the one server (4 sequences), scale 5.5 → a second paired draw (100 paired tasks in total) and a recalibration check.
- `make_notebook.py`: the notebook description now names the bundle's model (was hard-coded "12B").
- 06:00 UTC: **user approved the v6.1 draft** (`research/ledger/prompt_reviews.md`). Bundle `submissions/v6_1` VALID + COMPILED; prompt byte-identical to the approved draft; agent/sampling/eval configs identical to v6 (one change only).
- Server load measured (the other project's training has left the GPUs): vLLM total generation ~14 tok/s with 1 request running, ~17 tok/s with 4 → the 31B server on 4xT4 is near saturation at one request. Running tests side by side buys fairness (same conditions), not more tasks per hour.
- Round 2 (v5.1 vs v6 at scale 5.5, 4 requests) **stopped after 1 h**: fastapi_15661 hit the scaled limit at 2,644 s in both runs (Kaggle 325 s; round 1 1,497 s), i.e. a task takes ~8-9x its Kaggle time with 4 requests vs ~5x with 2 → scale 5.5 was far too strict for that load. Partial results kept as `results/replica/*_r2_aborted_s5.5`.
- **Round 3** (tmux `rep_r3`, from 06:14 UTC): `run_pair.sh` v6 vs v6.1 at scale 9, 2 tasks each (4 requests); expected end early Nov 3 UTC. Readout: path-traversal refusals (11 in v6 round 1) and the paired resolved count. The second v5.1 vs v6 draw is deferred (v6 ships; revisit if its LB draws disappoint).
- 14:41 UTC leaderboard snapshot (4,409 teams): top 0.29 (Yurnero, alone), 0.24 ×8, 0.22 ×61, 0.20 ×270, 0.18 ×666. Ours: best 0.18 (v5, Oct 25) → rank 826. v6 (57896193) still scoring. Round 3 half-way: v6 11/26 solved (2 timeouts), v6.1 10/27 (3 timeouts).
- 15:00 UTC — **what stops 0.20** (user question). Public draws dataset (dariushafshar, 145 traced public draws, 119 configs): only 3 draws reached ≥ 0.20. Most-run configs: Budget-Fit V5 n=10 mean **0.166** (sd 0.016, max 0.18, never 0.20); flexonafft v2 V10 n=8 mean 0.156 (max 0.22); SuperAgent V8 n=4 mean 0.160. **Our v5: n=6 mean 0.142** (sd 0.026) → about 1.4 tasks below the best public profile (≈1.9 standard errors; probable, not certain). v5 beat pub022 on practice tasks (26/53 vs 22/50) but not on the hidden set → practice-set gains (2 public repos, likely seen in pretraining) transfer weakly.
- Our deviations from that profile: `timeout_seconds` 90 vs 240; graph tools not declared (6 vs 9 tools; they declare them and the prompt discourages them); own prompt (includes fastapi-specific hints). A command never hits the 90-s limit on practice tasks (0 tasks in `v5_1_vm`, `v6_gates_vm` and the Kaggle v5 eval), so the VM cannot measure that setting; it is the main untested suspect for unfamiliar repos.
- Odds of a ≥ 0.20 draw: ≈2 % per draw at mean 0.14 vs ≈4-7 % at 0.17 → over ~20 remaining submissions ≈ 1 in 3 vs ≈ 1 in 2 to 4 in 5. The leaderboard keeps the best draw; the private LB uses the real mean of the two final picks.
- 17:55 UTC — **v7 draft built** (user: "Yes, draft v7"). `vm/prompts/system_v7.md` + `vm/specs/v7.json` = v6.1 plus the proven public settings: `timeout_seconds` 90 → 240; the 3 graph tools declared (9 tools, as Budget-Fit and flexonafft) with one TOOL FACTS line forbidding their use; GATE 5 pytest wrapper `timeout 60` → `timeout 120` (otherwise the 240-s limit is inert under our prompt); the fastapi `docs_src/` hint replaced by a general documentation-example rule; the timeout sentence reworded. 1,007 words, no braces. Bundle `submissions/v7` VALID + COMPILED (9 tools, instruction 6,081 chars), prompt sha 56bdec38… identical to the draft. **Awaiting the user's review; nothing run.**
- Harness facts checked in `scorer-host-venv` (swegemma 0.2.11, adk_submission 0.2.13): (1) the grading pytest has its own `verification_timeout_seconds` = 300 (`budget.py:33`), so `timeout_seconds` caps only the agent's commands — the Budget-Fit author's reason for 240 ("the scoring pytest shares it") is stale; (2) a command's effective timeout = min(`timeout_seconds`, remaining budget, floor 5 s) (`tools/execution.py:39`), so 240 s cannot push a task past the 8-min budget and the 12-h-cap risk is unchanged; (3) the "Code Intelligence Tools" paragraph is appended after our instruction only for tools the bundle declares and only when graph + embedding files exist for the repo (`harness/agent_runner.py:442-466`); the VM replica has no graph files, so the 9-tool part is inert on the VM and only the hidden set exercises it; (4) 0 commands hit our own `timeout` wrappers (exit 124) and 0 hit the harness limit in `v5_1_vm` and `v6_gates_vm`, so the wrapper change is neutral on practice tasks.
- Test plan once approved: `run_pair.sh submissions/v6_1 v6_1_s9b submissions/v7 v7_s9` (scale 9, 2+2) after round 3 ends. This is a non-inferiority check, not the decision (the changed settings target the hidden set, which the VM cannot see): ship v7 if paired resolved ≥ v6.1 − 1 and no > 8 % mean-time regression; losses confined to `docs_src` tasks are expected and noted.
- Side findings: `build_v4.py --spec` also rebuilds the legacy bundles (v4_single, v4_phased, v5_single); digests re-checked afterwards: `v5_single` fb17cd0f and `v6_gates` dad46cd3 still match their shipped notebooks. `sub_status.py` must run under `.venv/bin/python` (kaggle 2.2.4; the system kaggle 1.7.4.5 lacks `page_number`). v6 (57896193) still PENDING at 17:45 UTC; round 3 at 17:38 UTC: v6 13/33, v6.1 12/35.
- 17:55 UTC — **user approved v7 for the VM test** (ledger updated). **Round 4 chained**: tmux `rep_r4` waits for `rep_r3` to end (`vm/after_session.sh`, exact-name match, 2-min poll; the vLLM server keeps the GPUs in between), then runs `SCALE=9 run_pair.sh submissions/v6_1 v6_1_s9b submissions/v7 v7_s9` (log `logs/run_pair_r4.log`). Expected start ≈ 23:00-00:00 UTC, end ≈ Nov 3 evening UTC. Readouts: paired resolved and mean time (ship v7 if ≥ v6.1 − 1 and ≤ +8 %; `compare_runs.py` will still print REJECT below +3, which is its adoption gate, not this test's), graph-tool calls (expected 0; no graph files on the VM), path-traversal refusals, exit-124 and harness timeouts, the `docs_src` tasks. Round 3 at 17:53 UTC: v6 13/34, v6.1 13/36.

## 2026-11-03 — round 3 result, round 4 half-way, own LB history by command limit
- 03:30 UTC status (user question). **No training is running**: all 4 GPUs are at 100 % on the 31B vLLM server (round 4). The local watcher started yesterday died overnight (exit 4, no output; the PC probably slept); the VM-side chain worked and round 4 started on time.
- **Round 3 final** (scale 9, 4 requests): v6 19/50, **v6.1 20/50** (+1; wins fastapi_13537, rich_3480, rich_2725; losses fastapi_14372, fastapi_14616; p = 1.0); path-traversal mentions in traces 11 → **0** (the v6.1 fix works); mean 2,311 s → 2,214 s. v6 itself went 23/50 (round 1, scale 5.5, 2 requests) → 19/50 (round 3): run-to-run spread of ±2-4 tasks on the same 50 tasks.
- **Round 4** (v6.1 vs v7) started 22:21 UTC. At 03:29: 17 common tasks, v6.1 7 vs v7 7, no wins or losses; v7 traces: graph-tool calls 0, path-traversal 0, exit-124 0, harness timeouts 0. Expected end ≈ 12:30 UTC.
- LB 03:30 UTC: 4,453 teams; top 0.29; 0.24 ×8, 0.22 ×61, 0.20 ×280, 0.18 ×686. Ours 0.18, rank 833 (350 teams above). v6 (57896193) still PENDING after 22 h; the shipper waits.
- **Own LB history by command settings (31B draws):** harness limit 240 s + prompt `timeout 150` pytest wrapper — pub022 0.15, v3_31b 0.17, v3t2k_31b 0.17 → **mean 0.163 (n = 3)**; harness limit 90 s + prompt `timeout 30`/`timeout 60` wrappers (introduced in v4) — v4_single 0.13, v5 0.18/0.12/0.15/0.10/0.15/0.15 → **mean 0.140 (n = 7)**. Δ 0.023 ≈ 1.3 tasks (≈ 1.5 SE), confounded with the v4/v5 prompt text and dates, but the same direction and size as the public comparison (Budget-Fit 0.166 vs our v5 0.142). The v4/v5 gains were measured on practice tasks, where no command ever hits a limit. Supports v7 (240 s, pytest wrapper 120 s; `python -c` checks keep `timeout 30`).
- 13:50 UTC — **round 4 final:** v6.1 21/50, v7 21/50 (+0; wins rich_3480, rich_3470; losses fastapi_11194, rich_3676); mean time −2.5 %; mean calls 22.5 vs 22.6.
  - v7 traces: graph calls 0, path-traversal 0, exit-124 0, harness timeouts 0.
  - **Correction of the Nov 2 note:** the VM replica *does* have the public graphs and embeddings (`data/comp/graphs`, `data/comp/embeddings`). All 50 v7 traces carry the "Code Intelligence Tools" paragraph, and v7 still made 0 graph calls.
  - v7 met its ship rule; notebook `aagneye/gemma4-31b-v7` v1 built, its zip byte-identical to `submissions/v7`.
- **v6 (57896193) failed: "Your submission notebook exceeded the allowed runtime"** (the 12-h cap).
  - The shipper had already re-submitted v6 at 12:46 UTC (57948041, pending; may fail the same way).
  - VM token profile on the same 50 tasks (model output per task): v5.1 7.0k, v6 8.0k (+14 %, round 1), v6.1 7.1–7.2k, v7 6.9k (rounds 3–4).
  - v6's extra generation plausibly pushed it past 12 h. v7 is about +3 % vs v5.1, plus the 240-s command limit, so its runtime risk is unknown.
- 15:00 UTC — **user decision: the next slots ship Budget-Fit V5** (public; files sha256 `c9829b6a…`; 10 of 10 public draws finished, mean 0.166).
  - `submissions/budgetfit_v5` was rebuilt from our saved copy of the public notebook (files hash matches the public config); VALID + COMPILED.
  - Notebook `aagneye/gemma4-31b-budgetfit-v5` v1, zip byte-identical.
  - `results/ship.txt`: budgetfit_v5, v5_single (fallback), `#HOLD` v7.
- 15:22 UTC — the 31B vLLM server was restarted with `LORA_DYNAMIC=1` (`--enable-lora --max-lora-rank 32`; KV cache 26,400 tokens).
  - GPU filler (tmux `rep_sw`): **Budget-Fit V5 vs v7 on the 17 practice swing tasks** (`results/lists/practice_swing17.txt`), 2 passes, scale 9. Readout: score and per-task token/time profile of v7 against the runtime-safe incumbent.
- **Plan adjustment (follows the user's choice):** the incumbent is now Budget-Fit V5.
  - Phase 2's EVAL pair becomes **Budget-Fit V5 vs v7**. v7 ships only with ≥ +3 on EVAL *and* no more output tokens / time per task than Budget-Fit.
  - The training data comes from the winner.
- **Phase 1 started:**
  - SWE-rebench metadata (3 parquet files, 245 MB) in `datasets/swe-rebench/`.
  - `vm/rebench_select.py` → 1,018 candidates from 448 repos. Filters: no competition or web repos, flat layout, 1–3 `.py` source files, no async, 1–20 F2P, issue/test llm scores ≤ 2, PRs since 2019, every non-dev package present in `scorer-host-venv`; cap 15 per repo.
  - `vm/run_replica.sh` now takes `ROOT` / `ORDER_CSV` / `TASK_LIST`.
- 16:00 UTC — `vm/build_rebench_tasks.py` tested on 12 candidates: 11 built, 1 export failure.
  - The snapshots match the official format: `./`-prefixed tgz, HEAD → main, branches main + export_ref, user Agent <agent@eval>, history up to `base_commit` only. Placeholder graph and embedding files are written per task.
  - Large histories cost time and space (sphinx: 688 MB, 185 s), so mirrors are capped at 400 MB.
  - **Full build running** (tmux `rb_build`, 16 workers, log `logs/rebench_build.log`); it clones and packs only.
- **Blocked:** the gold/empty soundness run executes the test suites of about 450 third-party GitHub repos on the shared VM. Claude Code's auto-mode safety check refused it as running external code. Waiting for the user's decision on isolation:
  - Docker with no internet, the container seeing only the task files and the model server;
  - or running directly on the VM with the internet cut off (`unshare -rn`).
  - The agent runs of Phase 2 execute the same code, so the same decision covers them.
- 16:20 UTC — **user decision: train the 31B on the VM's T4s after the agent tests, not on Kaggle.** Consequences:
  - Context drops to 8k: 16k does not fit 16 GB cards (the Kaggle trial peaked at 14.3–16.8 GiB allocated, 18.6 GiB reserved at 16k).
  - fp16 with GradScaler (T4s have no bf16), roughly 2× slower than L4: an estimated 20–25 ms/token, so about 12–20 h for 2–3M tokens.
  - Testing pauses during the run.
  - Next: a T4 trial (8k fit probe + 20 steps) in the gap after the swing pair ends (about 02:00–04:00 UTC Nov 4), then the vLLM server restarts.
  - The bf16 training base `gemma-4-31B-it-qat-q4_0-unquantized` (62 GB) is downloading (tmux `dl31b`).
- **Trainer session result** (Kaggle 4×L4 trial, details in `research/raw/12_kaggle_31b_training.md`):
  - The 31B with r32 trains at 16k on 4×L4 (10.9 ms/token; 1.4 h of quota).
  - The adapter (467 MiB fp16) passes packaging, bundle validation and a hot-swap on the VM server.
  - Its `vm/train_qlora.py` options (`--pipeline`, `--attn qchunk`, bf16 path, `--fit-probe`, `--deadline-min`, `--optim adamw`) serve the T4 run too. Reviewed (default E4B/12B paths unchanged; CPU equivalence test of qchunk vs eager attention passes) and committed.
- Swing pair at 16:18 UTC: Budget-Fit V5 3/3 and v7 3/3 of the first 3 tasks; about 3 tasks/h per run → both passes end about 02:00–04:00 UTC Nov 4.
- 16:45 UTC — **user decision: the new projects' code runs directly on the VM with the internet cut off.**
  - `vm/rebench_soundness.sh`: gold patch twice and empty patch once, inside `unshare -rn` (loopback up, `TMPDIR` on the data disk). "Sound" also requires gold setup + grading ≤ 180 s.
  - Trial on 11 tasks: **7 sound (64 %)**, gold runs 6–24 s.
- `vm/netns_run.sh` + `vm/netns_bridge.py` run a command in a no-internet namespace, with 127.0.0.1:8000 bridged to the host's vLLM through a unix socket.
  - Tested: the model list answers, HTTPS to huggingface.co fails, and no processes are left behind.
  - Phase 2 agent runs go through it.
- **Build:** 963+ snapshots (30 GB). The last two repos (sympy, sphinx: long histories, ~700 MB snapshots) are still exporting.
- **Queued on the VM:**
  - tmux `rb_sound`: soundness of all tasks once the build ends (CONC 16, est. 1.5–2 h).
  - tmux `t4trial` (`vm/t4_trial.sh`): after the swing pair, stop vLLM; run a 31B LoRA trial on the 4 T4s (20 steps, 8k, fp16, fit probe, 120-min deadline, 150-min timeout); then restart vLLM with LoRA.
  - The new trainer is deployed to `~/gemma4_vm`; the CPU equivalence test passes with the VM's versions (transformers 5.17, peft 0.21.2, torch 2.8).
- 31B training base downloaded: 59 GB, `models/gemma-4-31B-it-qat-q4_0-unquantized`.

## 2026-11-04 — overnight results; EVAL and TRAIN runs started
- **Swing pair** (Budget-Fit V5 vs v7, 17 practice swing tasks × 2 passes, scale 9):
  - Budget-Fit 9 + 9 = **18/34**, v7 11 + 9 = **20/34** (+2 in total; pass 1 3W/1L, pass 2 3W/3L): noise.
  - Per task, v7 used **+20 % calls** (23.7 vs 19.7), **+22 % output tokens** (8.3k vs 6.8k) and +7 % time (2,399 vs 2,235 s).
  - So v7 is **not runtime-safe** next to Budget-Fit (v6's +14 % over v5.1 already exceeded 12 h). It stays on hold.
- **T4 trial** (`vm/t4_trial.sh`, 03:00 UTC): the 31B LoRA r32 trains on the 4 T4s at 8k.
  - Fit probe at 8,192 tokens OK; peak 10.0–11.4 GB per card (reserved ≤ 12.9 of 15 GB).
  - **16.1 ms/token** (62 tok/s); 20 steps in 32.9 min; loss finite, 0 skipped.
  - A full run of 2–3M tokens ≈ 9–13 h. vLLM was back at 03:29 UTC with LoRA hot-swap.
- **Soundness:** 510 of 983 built tasks are sound (gold twice, empty fails) from 265 repos; finished 17:32 UTC Nov 3. Only 3 tasks passed with an empty patch.
- **Split** (`vm/rebench_split.py`, seed 0, by repo):
  - **EVAL 109 tasks / 61 repos** (difficulty 0:42, 1:45, 2:19, 3:3).
  - **TRAIN 339 tasks / 196 repos.**
  - 8 repos left out (more than 10 tasks or snapshots over 300 MB): sphinx, networkx, sympy, pyflakes, sqllineage, XlsxWriter, snewpy, fairlearn.
- **The GPUs sat idle 03:30–15:00 UTC:** the next run was not chained after the trial (scheduling gap).
- 15:01 UTC, tmux `rep_eval`, no internet through `vm/netns_run.sh`:
  - **EVAL pair Budget-Fit V5 vs v7** (~28 h);
  - chained with the **TRAIN pass of Budget-Fit V5** (concurrency 4, ~48 h). Budget-Fit is the shipped config, so its runs are the on-policy training data.
  - Only an EVAL result of v7 ≥ +3 with no more tokens/time than Budget-Fit would switch the TRAIN policy.
- **Kaggle:** v6 resubmission 57948041 still pending after 26 h; Budget-Fit V5 waits behind it.
  - LB 15:00 UTC: 4,626 teams; top 0.29; 0.24 ×9, 0.22 ×64, 0.20 ×307, 0.18 ×715.
  - Ours 0.18, **rank 856** (381 teams above).

## 2026-11-08 — Budget-Fit draws, EVAL verdict, training round started
- **Kaggle draws:**
  - v6 resubmission 57948041 **0.15** (it finished this time: v6 is borderline on the 12-h cap).
  - Budget-Fit V5: 57990279 **0.13** (Nov 4), 58017434 **0.17** (Nov 5), 58039243 **0.17** (Nov 6), 58073200 **0.17** (Nov 7). Mean 0.16 over 4, matching its public 0.166.
  - 58108880 (Nov 8, 00:12) pending. Scoring now finishes within the day, so the 00:10 slots are used daily again.
- **LB 05:30 UTC Nov 8:** 5,071 teams; top 0.29; 0.24 ×11, 0.22 ×67, 0.20 ×384, 0.18 ×841. Ours 0.18, **rank 928** (463 above).
- **EVAL pair** (109 unfamiliar-repo tasks, no internet, scale 9): **Budget-Fit V5 47/109 (43 %) vs v7 40/109 (37 %): −7** (2W/9L, sign test p = 0.065); v7 mean time +18 % (1,779 → 2,092 s).
  - On unfamiliar repos our v6/v7 instructions *hurt*, as the hidden-set draws suggested (v5 0.14 vs Budget-Fit 0.166).
  - The practice set showed the opposite (+2): **the EVAL set agrees with Kaggle, the practice set does not.**
  - v7 stays on hold. Budget-Fit V5 is the policy for TRAIN and for the adapter.
  - EVAL is easier than the hidden set (43 % vs ~17 %); the gate uses its informative tasks.
- **TRAIN pass** (Budget-Fit V5, 339 tasks): **132 resolved (39 %)**, finished 18:54 UTC Nov 7.
  - The GPUs then idled ~10.5 h (not chained, again). Everything after this point is chained.
  - Episodes after the `FT_DATA_SPEC` filters: **74 from 74 tasks** (dropped: protected-file edits 26, identical consecutive calls 15, over 24 calls 15, nudge 1, no submit 1), 171 windows.
  - That is **below the pre-registered floor of 100 episodes**.
- **05:32 UTC — training round chained** (`vm/rft_round.sh`, tmux `rft`, log `logs/rft_bf5_v2.log`):
  1. Second pass of Budget-Fit V5 at **temperature 0.6** on the 132 solved TRAIN tasks (`submissions/budgetfit_v5_t06`; `results/lists/bf5_train_solved.txt`; no internet; ~19 h).
  2. Episodes from both passes (≤ 3 per task), tokenized at 12k with the serving model's chat template.
  3. Floor check (≥ 100 episodes / ≥ 50 tasks, else no training).
  4. 31B LoRA r32 on the 4 T4s: vLLM stopped; fit probe at 12k with fallback 9k/6k; 1 epoch, LR 1e-4, grad-accum 8, 12-h deadline.
  5. vLLM restarted with LoRA hot-swap.
  - Expected: data ~01:00 UTC Nov 9, training done ~12:00–14:00 UTC Nov 9. Then the gate (adapter vs base on EVAL + practice swing set).

## 2026-11-10 — round 1 trained; adapter decode overhead; Gate 1 running
- **Kaggle:** Budget-Fit V5 drew 0.18 (Nov 8), 0.15 (Nov 9), 0.17 (Nov 10).
  - Its seven draws: 0.13, 0.17, 0.17, 0.17, 0.18, 0.15, 0.17 → **mean 0.163**.
  - Scores arrive 12.5–14 h after submission.
- **Round 1** (`vm/rft_round.sh`):
  - The T0.6 second pass re-solved 117 of the 132 solved TRAIN tasks.
  - Episodes: **145 from 101 tasks**. Dropped: protected-file edits 53, over 24 calls 27, identical consecutive calls 22, other 2.
  - 329 windows; 322 kept at 12k (7 too long); 2.18M tokens, 515k supervised.
  - Training on the 4 T4s:
    - fit probe at 12k OK (peak 11.9–13.7 GB, reserved ≤ 15.4 GB);
    - 41 steps, 1 epoch, 608.6 min, 16.45 ms/token;
    - final loss 0.29, 0 skipped steps.
  - Adapter: `runs/31b_bf5_v2_r32/final`. vLLM back at 05:27 UTC Nov 9.
- **The GPUs then idled 33 h:** Gate 1 was not chained (scheduling gap). From now on a default job is always queued behind the running one.
- **Bundle `submissions/budgetfit_v5_lora1`** = Budget-Fit V5 + `adapter: main_lora` (r32, 467 MiB fp16; G0 OK; harness-validated). Hot-loaded into the running server.
- **Adapter decode overhead on the T4s** (vLLM 0.19.1, punica Triton kernels):
  - one request: 32.1 → 9.1 tok/s (**3.5× slower**);
  - 4 concurrent: 87.6 → 32.0 tok/s total (**2.74× slower**).
  - The overhead on Kaggle's L4s is unknown (no public measurement; scottweeden's adapter eval never ran). It is the main risk for shipping any adapter: Budget-Fit's margin under the 12-h cap is unknown, and v6 at +14 % tokens already exceeded once.
- **Gate 1** (tmux `gate1`, from 14:19 UTC):
  - The adapter runs alone at concurrency 4 with the clock stretched to **scale 25** (= 9 × 2.74), so it gets the same Kaggle-equivalent token budget per task.
  - It is paired against Budget-Fit's existing `bf5_eval` run (scale 9, 2+2 load, pure base batches). A fresh pair would slow the base arm too, since mixed batches run the LoRA kernels.
  - Order: the 77 `test_score` ≤ 1 tasks first, then the 32 others (`results/lists/rebench_eval_ts.txt`), then the 17 practice swing tasks (`lora1_sw`).
  - ETA: the 77 by ~20:00 UTC Nov 11; all by ~15:00 UTC Nov 12.
- **Queued behind it** (tmux `after_g1`): Budget-Fit at T 0.6 on the 207 unsolved TRAIN tasks (`bf5t06_train3`), for new round-2 tasks.
- **Workstream B started** (CPU, beside Gate 1):
  - `scorer-host-venv-plus` = the Kaggle freeze + 32 test packages (`vm/extra_test_packages.txt`, each installed pinned to the existing versions; tmux `venvplus`). For TRAIN-pool tasks only; EVAL stays on the Kaggle-faithful venv.
  - `vm/rebench_select.py --extra-packages --exclude-repos-file results/lists/eval_repos.txt --exclude-ids-file data/rebench/build_log.csv --per-repo 20` → **611 candidates from 215 repos** (the 61 EVAL repos and the 873 tasks already built are excluded; difficulty 0:209, 1:254, 2:133, 3:15).
  - Snapshots: tmux `rb2_build` → `data/rebench2`.
  - Soundness: tmux `rb2_sound` with `VENV=scorer-host-venv-plus`, chained after both builds.
- **C1 draft** (`vm/prompts/budgetfit_c1.md`): Budget-Fit V5 + one bullet in step 3 ("Check the Behaviour, Not Just the Example"; 107 words, no braces). Waiting for the user's review.
  - It makes the one existing verification command cover 2–3 related cases plus the existing test file, without new calls.
  - Target: the ~45 narrow-fix failures of `bf5_eval`.
  - Budget-Fit's own text is now tracked in `vm/prompts/budgetfit_v5.md`.
- 17:50 UTC — user decisions (re-asked after the app restart):
  - **C1 approved for the VM test.**
  - **One short Kaggle 4×L4 speed check** (adapter on/off, no agent test) before any adapter takes a slot, only if Gate 1 is won.
- **Training pool 2:** 551 tasks built (5 clone failures, 55 too big); **248 sound** (gold twice; empty 0) with `scorer-host-venv-plus` (all 32 extras installed).
- **Gate 1 early read** (10 tasks, 17:10 UTC): adapter and base solved the same 1. The adapter writes fewer output tokens on most tasks (e.g. 5.1k vs 10.3k), but one task looped to the 80-turn limit.
- **Queue rebuilt** (tmux `round2`, `vm/chain_round2.sh`; the earlier `after_g1` queue was cancelled):
  1. C1 pair ×2 on `results/lists/c1_eval.txt` (50 EVAL tasks: 36 Budget-Fit-unsolved, 9 solved by Budget-Fit but not v7, 5 stable).
  2. `vm/verdict.py` (mean gain ≥ +3 per pass; calls/tokens/time ≤ ×1.08) picks the policy.
  3. T0.6 generation on rebench2 (248) and the 207 unsolved TRAIN tasks.
  4. Round-2 training (`rft_round.sh` `PER_TASK=2 DEADLINE_MIN=1380`).
  5. `lora2` packaged, hot-loaded and run on all 109 EVAL at scale 25.
  - Dropped from the plan: the 58 big-repo tasks (slow snapshots, famous repos).
  - Expected: C1 verdict ~Nov 13 10:00 UTC; generation ~Nov 14–16; round-2 adapter ~Nov 17; its EVAL run ~Nov 19.
- **Gate 1 automation** (tmux `l4check`, `vm/l4_speed_check.sh`): when `gate1` ends, `vm/verdict.py` applies the three parts of the rule:
  - ≥ +3 on the 77 `test_score` ≤ 1 tasks (`results/lists/eval_ts01.txt`);
  - not negative on all 109;
  - practice swing set ≥ −1;
  - calls and output tokens ≤ ×1.08. Time is excluded: the adapter arm runs on the stretched clock.
  - Only if all three pass: the adapter is uploaded as a private dataset (`aagneye/gemma4-31b-lora1-adapter`), and the speed notebook (`vm/make_kaggle_speed.py`, private `aagneye/gemma4-31b-lora-speed`; base vs adapter tokens/s at 1 and 4 requests plus a long prompt; no agent runs) is pushed on 4×L4 and read back.
  - Result in `results/replica/lora1_eval_gate.txt` and `logs/l4_speed_check.log`.
- `vm/verdict.py` gained `--tasks` (judge a subset) and `--cost-keys`. Checked on last week's v7 data: REJECT on EVAL (−7 on the 77) and on the swing set (+1).

## 2026-11-11 — instruction program (SWE-agent's method on SWE-rebench data); round-2 training paused
- **User approved a new plan** (`C:\Users\aagne\.claude\plans\sleepy-hatching-squid.md`):
  - Build the instruction set one line at a time on Budget-Fit V5 (v6/v7 changed everything at once and lost on EVAL).
  - Three feedback speeds: probe, screen, confirm.
  - Dev tasks come from the training pool; EVAL is used only for confirmation.
  - 31B round-2 training is paused. E4B work is parked.
- **Measured in Budget-Fit's runs** (`bf5_eval` 109 tasks, `bf5_train` 339 tasks):
  - **Garbled `edit_file` calls** (ADK error "mandatory input parameters are not present: old_string"):
    - EVAL: 38 of 293 edit calls (13%), on 5 tasks. TRAIN: 348 of 1,090 (32%), on 36 tasks, at most 61 in one task.
    - The next call is another failed edit 280 of 348 times (a loop).
    - v7: 80 of 286. T0.6 pass: 200 of 460. Adapter (`lora1_eval`): 3 of 267.
    - Cause: vLLM's `gemma4_utils._parse_tool_arguments` falls back to a `key:"value"` regex that cuts a value at an inner double quote.
    - Solves at T0.2: 13/36 with a garbled call vs 119/303 clean. At T0.6: 13/19 vs 104/113.
  - **Range-less reads:** 243 of 710 `read_file` calls (EVAL) and 867 of 2,260 (TRAIN); most are truncated at 150 lines. Tasks with ≥ 3 solve 11/39 vs 8/14 with none (EVAL), 44/128 vs 24/50 (TRAIN).
  - **No syntax check:** `py_compile` is never used. A Syntax/IndentationError was seen on 58 tasks, 14 of them solved.
  - **Search flooding is rare:** 12 of 470 searches over 4,000 characters. Shell-write edits are not harmful (9/16 solved).
  - **Grading outcome of unsolved tasks:** target tests not fixed only 51 (EVAL) + 163 (TRAIN); plus passing tests broken 6 + 20; only passing tests broken 0 + 1.
  - **Reason, 250 unsolved with a test log:** behaviour assertion 114; missing name / parameter / import 61 (44 with the name only in the gold patch, 16 with it in the issue); expected exception not raised 10; other 65.
  - **"Edit by call 12" does not separate outcomes:** tasks with a later first edit solve 8/17 (EVAL), 26/62 (TRAIN).
  - **Issue length:** competition public tasks median 418 characters, ours 602. Solve rate 35% under 300 characters vs 42–44% for 300–2,500.
  - **Exam-like tasks** (test_score ≤ 1, difficulty ≥ 1): 70/177 solved.
- **Gate 1 so far** (adapter vs Budget-Fit): 36 vs 36 on 83 common tasks; +0 on 55 of the 77 primary tasks (31 vs 31; 4 wins, 4 losses); tokens ×0.96, calls ×1.06.
  - `vm/gate_watch.sh` (tmux `gatewatch`) ends tmux `gate1` after `lora1_eval` if the main rule fails (the 17-task practice re-check is then skipped). `l4check` still applies the full verdict.
- **Queue swapped:** tmux `round2` (C1 pair on EVAL, round-2 data, training, second adapter test) cancelled. tmux `instr` runs `vm/chain_instr.sh` behind `gate1`:
  - **Screen A:** `sA_base` (Budget-Fit), `sA_c1`, `sA_e1r1`, `sA_d1` on `results/lists/dev48.txt` (4 arms × concurrency 1, scale 9, no internet, request log in `results/requests/screenA/`).
  - then `~/gemma4_vm/probe_round1.sh` if deployed;
  - then **Screen B:** `sB_base`, `sB_p1`, `sB_t2`, `sB_t1`;
  - then a filler second pass of Screen A.
- **Dev set** (`vm/dev_select.py`, seed 0): 48 TRAIN-pool tasks from 44 repos — 12 with garbled-edit loops, 12 partial-file failures, 12 narrow fixes, 12 solved at both T0.2 and T0.6. 46 are exam-like; none is an EVAL task.
- **Candidate bundles** (Budget-Fit V5 + one change; all validated and compiled):
  - `budgetfit_c1` (behaviour check);
  - `budgetfit_e1r1` (small edits, no resend of a garbled call, compile check; reads with a line range);
  - `budgetfit_d1` (5-line example session);
  - `budgetfit_p1` (sibling sweep);
  - `budgetfit_t2` (read the existing tests first);
  - `budgetfit_t1` (thinking 2,048).
- **Request log:** `REQ_DUMP=<dir> bash netns_run.sh ...` saves every request sent to the model (`c<pid>_<n>.http`, raw HTTP requests). Tested: the model answers, the internet is blocked, the dump is written.
- **Fresh test slice** (SWE-rebench-leaderboard monthly sets 2025_10 … 2026_03):
  - 361 tasks from 196 repos, created Oct 2025–May 2026, mostly Python 3.12/3.13. They carry no llm scores and no frozen requirements.
  - `rebench_select.py --allow-missing-scores` (web and compiled projects recognised from `install_config`) → 147 candidates from 101 repos.
  - Snapshot build + no-internet soundness running (tmux `fresh` → `data/rebench_fresh`, `results/rebench_fresh_soundness.csv`). The build started from a first list of 151 that still held 5 web repos; they are dropped when the list is made.
- **Judge step:** a subagent labels Budget-Fit's 62 EVAL failures from `research/runs/bf5_eval/judge_input.jsonl` → `judge.md`.
- **Proposed as separate sessions (cards):** the run log (`vm/autopsy.py`, `vm/arms_report.py`) and the probe tool (`vm/probe.py`).
- **Kaggle:** Budget-Fit V5 draws 0.13, 0.17, 0.17, 0.17, 0.18, 0.15, 0.17 (mean 0.163); Nov 11 pending.
- **Judge result** (`research/runs/bf5_eval/judge.md`, Budget-Fit's 62 EVAL failures; 27 are exam-like):
  - Labels: no real fix 15 (8 of them hit the 8-minute timeout, 5 after fewer than 10 calls); wrong idea 10; too narrow 8; name not in the issue 8; task problem 8; missed a second place 6; near miss 6; wrong place 1.
  - "Would have helped" (upper bounds): C1 8 (2 exam-like), E1 5 (1), T2 3 (3), P1 2 (1), none 44 (20 of the 27 exam-like).
  - Reading: 16 failures need something the issue never states, and no single line is worth more than 2–3 of 27 exam-like tasks. The larger lever is time: timeouts with few calls and 7 no-fix runs at the call cap. That raises the priority of T1 (thinking 2,048, Screen B) and of finding why tasks time out after under 10 calls (hung command vs slow generation; the run log's "hung gap" field).
- **Run log deployed** (built in its own session, reviewed here): `vm/autopsy.py` writes `autopsy.jsonl`, `brief.md` and `report.md` per run; `vm/arms_report.py` prints the side-by-side table.
  - It reproduces every target count on `bf5_eval`, `bf5_train` and `v7_eval` (table in `research/raw/13_run_log.md`).
  - `vm/run_replica.sh` now calls it at the end of every run, and `vm/run_arms.sh` prints the table after a screen.
  - First reports are in `research/runs/bf5_eval/`.
- **First table, Budget-Fit vs the adapter on 83 common EVAL tasks:**
  - solved 36 vs 36 (4 wins, 4 losses);
  - garbled edit calls 38 vs 3, looped tasks 3 vs 0;
  - output tokens ×0.96, calls ×1.03;
  - range-less reads 32% vs 30%; `py_compile` never used by either.
- **Probe tool** (`vm/probe.py`, `vm/probe_round1.sh`): written and tested offline in its own session. The check against real request dumps waits for Screen A; not deployed yet.
