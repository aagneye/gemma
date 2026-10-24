# Plan to reach the top 10 — revision 2 (2026-10-18 evening; 45 days to Dec 2)

Supersedes revision 1 after reading the forum/notebook state (see `raw/07_forum_round2.md`, `raw/07b_top_notebooks_large.md`) and the first scored submission.

## Facts that drive this revision
- Public LB: 2 teams at 0.24, 27 at 0.22 (3rd-29th), 20 at 0.20. Our 12B baseline scored **0.08**. The 0.22 cluster is a single public notebook (flexonafft "Budget-Aware Coding Agent v2"): 31B, T=0.2, thinking 4096, 8 min / 28 calls / 80 turns / 240 s, and a prompt with a CALL PLAN that forces a source edit by call 12.
- Ties rank by submission time, so top 10 means 0.24+ (14/58) that also holds on the private 62. Per-run noise is ±2 tasks; prompt-only tweaks on top of 0.22 have so far landed at 0.18-0.20 (inside noise).
- Since the Oct 8 wheelhouse: graph tools answer most queries (median 5.8k chars), test-file edits are stripped from patches, `include_thoughts:false` no longer disables thinking (`thinking_budget: 0` does). The scorer runs only the test files named by test_patch.
- ~76% of public issues name neither file nor function; 57% of fixes are single-file <=20 lines; ~1 in 6 touch async code (absent from the graphs).
- Skills are high-variance: reports of 0.15 -> 0.00 and 0.18 -> 0.05 after adding a skill; our own smoke shows the 12B fumbling the skill call schema (wrong argument names, extra list/load calls) and, in the first two finished tasks, spending 44-45 of 50 calls with 10-23 skill invocations each and no resolution. Skills stay out of the main line; Day 6 happens only if a 31B smoke behaves differently.
- T4-only compute: 12B QLoRA ~24 h/625 steps; local eval ~40-80 min/task; 31B cannot be trained at scale here. One Kaggle slot/day, ~13 h scoring latency.

## Thesis (unchanged in spirit, sharper in execution)
Reproduce the proven 0.22 configuration exactly, then earn +1 to +3 tasks with changes that have evidence behind them and are tested one at a time: the forced-edit call plan is already in; the candidates are (a) hygiene and budget-warning rules in the prompt, (b) a bounded, deterministic localization step for the 76% of issues with no file named, (c) temperature/thinking-budget tuning for speed, (d) a small 31B or 12B adapter only if it is non-negative in paired local evaluation. Every submission changes one thing versus the previous best.

## Evidence from the six 0.17-0.18 public notebooks (`raw/07b_top_notebooks_large.md`)
- All are the same operating profile (8 min / 28 calls / 80 turns / 240 s; T 0.2; thinking 4096). Measured negatives on top of it: multi-agent coder+analyzer (16/70 vs 27/70 single coder, p=0.013, and 43% slower), two-reviewer voting (13/70), a 6-minute schedule (7/44), a hard 4-min self-cap (0.08), extra tools (never used), custom skills (0.05-0.06), command-only interface, temperature 0 or 0.4 (0.15 / 0.12 vs 0.18), a 23-task LoRA (2/32 vs 4/32 despite -27% NLL).
- Measured positives / near-positives: thinking budget 2048 (50/129 vs 48/129 locally, calls ~14 s thinking-on vs 3-6 s off), issue-contract-before-first-call, edit-by-call-8/12 "anytime patch", output caps for the 32k window (all 75 context-overflow runs ended with no patch; 28% of all runs ended with no patch), runs that finish in <=14 calls resolve 52% vs 5% for 15-20 calls.
- The 12B with the 0.22 bundle scored 0.18 on Kaggle (ours with our prompt: 0.08) -> our prompt, not only the model, was weak; the 12B is a viable fast fallback with the 0.22-style prompt.
- Time per task is the binding constraint on the scorer: 120-task projections run 11.6-13.0 h with the 8-min profile; anything slower risks the 12-h cap.

## Daily submission schedule (one slot/day; each must be validated and its notebook output byte-checked)
| Day | Date (UTC) | Package | Purpose |
|---|---|---|---|
| 1 | Oct 18 | 12B base, our prompt | done: **0.08** |
| 2 | Oct 19 | `pub022` = exact public 0.22 reproduction (notebook `gemma4-31b-pub022-repro` v1, queued) | anchor + our own noise estimate |
| 3 | Oct 20 | `v3_31b` = 0.22 budgets/sampling + prompt v3 (0.22 prompt + edit-by-call-10, context-hygiene caps, protected-config list, /tmp scratch, parallel implementations, `git status --short && git diff`, budget_warning stop rule, no-repeat rule, "think briefly") | prompt delta (notebook `gemma4-31b-v3-prompt` v2 pushed) |
| 4 | Oct 21 | best of {pub022, v3} with thinking_budget 2048 (same 8 min / 28 calls) | speed delta: more calls land inside 8 min; locally 50 vs 48 of 129 |
| 5 | Oct 22 | best + bounded graph use (one `get_code_neighbors` on the located symbol) **only if** a local A/B wins | graph delta |
| 6 | Oct 23 | best + skills (`locate`,`finalize`) **only if** invoked correctly and non-negative locally (the forum's 0.00 reports make this the riskiest delta) | skills delta |
| 7+ | Oct 24+ | best + 12B fallback with the same prompt if time pressure shows up in timing runs; best + adapter only if non-negative locally | fallback, adapter |
Keep the two highest-scoring packages as the final picks; after Nov 28 only confirmation reruns.

## Workstreams
### A. Harness line (main; CPU work + local A/B on the VM)
1. Prompt v3 (done, notebook v2 verified) -> Day 3. Thinking 2048 (Day 4, config-only, no A/B needed beyond the public 129-run evidence). Bounded graph tools (Day 5) after a local A/B: 21 sound public tasks, 12B locally (the only model we can serve at speed), paired by task, win = >=2 tasks.
2. Skills: fixed to tolerate wrong argument names; keep as a Day-6 experiment, never bundled with another change.
3. Build-drift check before every submission: fingerprint the attached wheelhouse (kimdonggyu1255 instruments kit) and re-read the harness README diff.
### B. Training line (upside; T4s at night)
1. `12b_r32_v4mid`: fixed DDP trainer on 1,263 curated short trajectories (5,905 windows, ~15 h). Starts automatically after the skills smoke. Gate: SYNC_OK in the 3-step DDP check.
2. Evaluate ckpt vs base locally (21 tasks, paired). Ship as "best + adapter" only if non-negative. If positive, consider a 31B rank-16 adapter on the same subset with naive model parallelism (slow; ~2 days) — decision at Day 6.
### C. Evaluation infrastructure (revised 2026-10-19)
1. **Primary: score on Kaggle's own environment** (`vm/make_kaggle_eval.py`): the harness Evaluator with the subprocess sandbox, the 31B served exactly like the scorer on Kaggle L4s. Task set = the 71 Kaggle-sound public tasks (fastapi 29, rich 42; `results/kaggle_soundness.csv`), round-robin by repo, 4-h budget per run (~30 tasks at the 8-min profile, ~8 h of the 30 h weekly quota). Every candidate gets one run here before it gets a daily slot; pub022 is the paired anchor.
2. The VM's Docker grader agreed with Kaggle's sandbox on only 8 of its 21 "sound" tasks -> T4/Docker A/Bs are retired; the T4s are for training only.
### D. Paper track (Nov 12) — "scorer-faithful evaluation kit + soundness audit + localization benchmark"; most artifacts exist (`vm/gold_check.py`, `results/gold_soundness.csv`, `vm/skills/locate`, build-drift notes). Start the 3,000-word write-up on Oct 25.

## Decision gates
- G1 (Day 2 score): if pub022 reproduces 0.20-0.24 we are in the cluster; everything after is deltas. If it scores <0.18, suspect scorer drift and re-fingerprint before continuing.
- G2 (each delta): adopt only if local paired A/B wins by >=2 tasks AND the Kaggle score is not lower than the anchor by more than 2 tasks.
- G3 (adapter): ship only if non-negative locally AND the base package is already at >=0.22.

## Risks and mitigations
- Noise dominates single scores -> compare on local paired runs; never conclude from one Kaggle number.
- 12-hour cap overrun fails the whole run -> keep the 8-min/28-call budgets that are known to finish; any change that lengthens tasks needs a timing run.
- Skills/graph features can silently zero a submission -> never ship two new features at once; keep the pub022 package as final pick #1 until something beats it twice.

## Revision 3 (2026-10-21) — see `ARCHITECTURE_V4.md`
- LB results: pub022 (exact public 0.22 bundle) **0.15**, v3 prompt **0.17**, v3 + thinking 2048 submitted Oct 21 (ref 57491112). The public 0.22 is a lucky draw of a ~0.17-0.19 configuration; the LB cannot resolve +1-task changes.
- Kaggle-environment paired eval is now the decision tool: pub022 = 22/50 on Kaggle-sound tasks. Trace analysis: 10/50 runs never edit, 14/50 submit unverified wrong patches, 9/50 lose their edit (0 resolved), 7/50 hit the 8-min cap.
- Next candidates: `v4_single` (loop-breaking tool rules + edit protocol + timeout_seconds 90) and `v4_phased` (SequentialAgent scout -> fixer -> finisher). Daily slots go only to bundles that win the paired eval by >= 3 tasks; until then, slots are spent on the best paired bundle (no blind deltas).
