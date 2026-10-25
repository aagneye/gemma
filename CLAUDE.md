# AI software factory: Gemma 4 Developer Agent competition

This project runs in **factory mode**. The user gives goals and specs; Claude researches, builds, measures and iterates
toward the goal without waiting to be asked. Read this file and `research/STATE.md` at the start of every session.

## Goal (spec from the user, 2026-10-22)
- Reach the **top of the public leaderboard** of Kaggle "Google - The Gemma 4 Developer Agent Competition"
  (competition slug `gemma-4-developer-agent`). Score must be **> 0.22** (top line on Oct 22 is 0.24).
- Do not wait for Kaggle scores to decide: replicate the public-score evaluation on the Azure VM (and in Kaggle notebooks)
  and decide from local, paired measurements. Train on whatever GPUs are free.
- Keep going until the goal is reached. Final deadline Dec 2 2026; paper track Nov 12.
- Second target (added 2026-10-24): the **$10k Small Model bonus** (best E2B/E4B-based submission; top public is 0.06).
  Final picks = best 31B bundle + best E4B bundle. Full plan: `research/PLAN_TO_WIN.md`.
- Daily slots ship automatically: `vm/daily_ship.py` (tmux `dailyship` on the VM, cron watchdog) submits at 00:10 UTC the
  per-day override in `results/ship_schedule.txt` or line 1 of `results/ship.txt` (line 2 = fallback). **Kaggle refuses a
  new submission while one is still scoring** (~13 h), so never submit manually late in the day.
- Slot policy (approved 2026-10-25): 31B best bundle every day, one E4B slot per week; LB slots never validate candidates;
  freeze new bundles Nov 24; final picks Dec 1 = earliest valid draw of the best 31B config + earliest valid E4B draw.
  Full plan: `research/PLAN_TO_WIN.md`.

## Factory loop (every build)
1. **Look back**: read `research/STATE.md` (what exists, what was tried, scores, open hypotheses) and the latest results.
2. **Diagnose**: run `vm/analyze_traces.py` on the newest eval; the largest failure bucket picks the next change.
   Write the post-mortem with the `agent-introspection-debugging` skill (capture -> diagnosis table -> recovery -> report).
3. **Research** before building: forum/notebooks (`research/raw/`), papers, harness source on the VM. Record findings in `research/raw/`.
4. **Build** one change at a time as a bundle (`vm/build_v4.py`, `vm/make_submission.py`) or a model (`vm/train_qlora.py`).
   Validate + compile every bundle (`build_v4.py` check). Never ship an unvalidated bundle.
5. **Measure** on the replica scorer (paired, same task order, Kaggle-sound tasks):
   VM (unlimited, overnight): `bash ~/gemma4_vm/run_replica.sh <bundle> <tag> 50 36 3` (31B via `MODEL=gemma-4-31b-it-qat-w4a16-ct bash ~/gemma4_vm/wait_vllm.sh`;
   host = `scorer-host-venv`, which matches Kaggle soundness on 69/71 tasks). Kaggle L4 (30 GPU-h/week): `vm/make_kaggle_eval.py agent`.
   Compare with `vm/compare_runs.py <baseline_dir> <candidate_dir>` - adopt only on >= +3 tasks paired and no time regression.
   The public LB is a draw (SD 1.56 tasks of 58): never decide from one LB score.
   Follow `benchmark-optimization-loop` (one hypothesis per variant, ledger row per run, stop when the gain is within noise)
   and report with `eval-harness` vocabulary (wins = capability, losses = regressions on tasks the baseline solved).
6. **Ship**: the daily Kaggle slot goes to the best paired-eval bundle (standing approval; `vm/submit_when_open.sh`).
7. **Record** in `research/STATE.md` (ledger row: date, artifact, change, paired result, LB) and `vm/README.md` (how-to, pitfalls).

Audit the loop itself with `loop-design-check` whenever its rules change: the done-criterion is the paired eval
(machine-decidable), the boundary is "no edits to tests or eval tasks", the judge is the replica/Kaggle grader (never
the agent's own claim), and a human (the user) owns the goal.

Project skills from affaan-m/everything-claude-code live in `.claude/skills/` (MIT; source in `third_party/ecc/`).

## Hard facts (verified; details in research/ and memory)
- Allowed models: gemma-4-{31b,12b,e4b,e2b}-it-qat-w4a16-ct. Scorer: vLLM 0.19.1 TP=4 on 4xL4, 32k context, 12 h for ~120 tasks.
- Bundles are declarative YAML only (no Python callbacks; CallbackRegistry is empty). Levers: prompts, tool subsets,
  `eval_config.yaml` budgets, sampling/thinking, workflow agents (Sequential/Loop/Parallel/AgentTool), LoRA adapters (<3 GiB).
- A final text ends a task only after `submit_patch`; sub-agent text hands over to the next sub-agent.
- Public evaluation = harness `Evaluator` with `sandbox='subprocess'`. Kaggle-sound public tasks: 71/129 (fastapi 29, rich 42).
- The VM is shared with other projects: never kill their GPU jobs; use free GPUs only.
- Kaggle GPU quota 30 h/week (L4 bills 2x); one submission per day; the LB is a noisy draw (same bundle: 0.15-0.22).

## Where things are
- `research/STATE.md` ledger · `research/ARCHITECTURE_V4.md` post-mortem + architecture · `research/PLAN_TOP10.md` plan history
- `vm/` all scripts (copied to `~/gemma4_vm/` on the VM) · VM project root `/mnt/biohub/kdata/gemma4`
