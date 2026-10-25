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
