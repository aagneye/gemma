# Plan to win — approved 2026-10-25 (supersedes the Oct 24 version)

Source of truth for the Oct 25 – Dec 2 campaign. Progress is logged in `STATE.md` and `research/ledger/*.md`.

## Context
The user wants #1 on the main leaderboard and asked for a deep review of SWE-agent harnesses, Claude-Code-style agent kits, orchestration repos and papers, with the findings transferred into the Gemma agent's instructions and into fine-tuning. Decisions taken in this planning round: **free compute only** (shared 4×T4 VM + Kaggle 30 GPU-h/week), **daily slots mostly 31B with one E4B slot per week**, **no paid APIs for data**, **no paper track**.

Where we stand (measured this morning):
- **v5_single** (31B, prompt `vm/prompts/system_v5.md`) = 26/53 Kaggle-sound tasks, 276 s/task; paired vs the public "0.22" bundle **+3 (4 wins / 1 loss)**, vs v3t2k +1, vs v4_single +3. Best bundle we have; fastest too (9.1 h projection for 120 tasks).
- **E4B** with the same bundle = 8/75, 97 s/task, uses only 12.5 of 28 calls. Small-model board top is 0.06; our ~11% would lead it.
- Kaggle quota for this week is spent (0.66 h left; resets Sat Oct 31 00:00 UTC). This week is VM + research work.
- The auto-ship job got a 400 at 08:40 UTC while yesterday's 18:10 submission was still PENDING; cause unknown (leading hypothesis: Kaggle blocks a new code submission while one is scoring).
- Research already covers ~120 sources (SWE-agent ACI, OpenHands, Agentless, SWE-smith/Gym/RL, R2E-Gym, Kimi-Dev, test-time-compute papers, 20+ competition notebooks). **Gaps:** verbatim prompts of SWE-agent/mini-SWE-agent/OpenHands/Aider/Anthropic's scaffold, Claude Code kits and Ralph-style loops as *instruction* sources, small-model instruction-following evidence, and no design for using repeated attempts inside the harness.

## Honest odds (from the strategy model; estimates)
Private board = 62 tasks, best of two picks, per-draw SD ≈ 1.6 tasks. The expected winning private score is ≈ 16–17/62 (~0.27) because hundreds of near-equal teams each get a lucky draw. Our v5 projects to ≈ 12–13/62 → P(#1) ≈ 1–3 %, P(top-3) ≈ 2–6 %. Each extra true task in the 13–15 range roughly doubles those odds. The E4B $10k prize is the highest-probability money (P ≈ 15 % at par with the board, 40–50 % at +2 tasks). **Biggest single unlock we are not doing: a 31B LoRA, which needs a rented 80 GB GPU (~$30–60 per run).** The plan keeps a decision point for it after the E4B adapter result; the user can reopen that choice then.

## Workstream 0 — ship v5 and make the daily slot reliable (today, Oct 25)
1. Build the v5 submission notebook (`/tmp/make_nb.py` on the VM → `submissions/nb_v5_single`, slug `gemma4-31b-v5-single`), push, byte-check its `submission.zip` against `submissions/v5_single`, set `results/ship.txt` to it. Fallback line = v3t2k.
2. Diagnose the 400: capture the error body through `KaggleApi.competition_submit` (the CLI only prints the last line), check whether 57603042 is still PENDING, resubmit as soon as it scores (if that succeeds before 00:00 UTC, the "blocked while pending" hypothesis holds → never submit late in the day).
3. Rewrite `vm/daily_ship.sh`: truth from the API submission list (not CLI text), attempt at 00:10 UTC then every 30 min, classify errors (pending/quota → wait; kernel/file → fall back to line 2 of `ship.txt` after 2 failures), sha256 of the bundle checked against the kernel output before submitting, ledger row appended (date, ref, bundle, sha, role), alert line in the log if nothing is submitted by 02:00 UTC; run under a supervisor (tmux + a cron `@reboot`/watchdog so the Oct 23 "queue ended" loss cannot recur).
4. First E4B leaderboard draw on **Tue Oct 27** with the validated `submissions/e4b_v3t2k` (notebook + byte-check first), then one E4B slot per week; all other days 31B.
5. Fix `research/STATE.md` "Current best" (v5) and record the v5/E4B numbers.

## Workstream 1 — research sprint (Oct 25–29, no GPU needed)
Method: subagents clone each repo read-only into the scratchpad, extract the exact prompt/config files, and I write **pattern cards** (source + commit, verbatim excerpt ≤ 40 lines, mechanism, failure bucket it targets, harness mapping, predicted effect with the measured fact it rests on, cost, kill criterion). Only harness-native ideas (prompt text, tool subsets, Sequential/Loop agents, budgets, sampling) become experiments.

| Day | Sources | Output |
|---|---|---|
| 0 | Our own traces: for the 10 no-edit and 9 lost-edit tasks, are they *ever* solved by any bundle? E4B stop-reason taxonomy (text-without-submit, empty submit, malformed calls → nudges) | `research/raw/09a_bucket_ceilings.md` (sets the ceiling per failure bucket) |
| 1 | **mini-SWE-agent** (`config/extra/swebench.yaml`, `default.yaml`: workflow, one-action rule, format/timeout templates), **SWE-agent** (`config/default.yaml`, demonstration `.traj`), **OpenHands** CodeAct `system_prompt.j2` + SWE-bench instruction (problem-solving workflow, troubleshooting "5–7 sources → 1–2 likely"), **Anthropic SWE-bench Sonnet prompt**, **Aider** `editblock_prompts.py` (exact-match edit rules) | `research/raw/09_swe_prompt_corpus.md` + pattern cards |
| 2 | **Agentless** (file→element→line localisation questions), **AutoCodeRover** ("is context sufficient?" gate), **Moatless** (StringReplace error hints), **Trae-agent** (done checklist), **Refact**; Claude Code kits: `third_party/superpowers` (systematic-debugging, verification-before-completion, TDD), ECC skills, Ralph-loop / long-running-agent repos and "hundreds of agents" orchestrators (e.g. claude-flow, Agent SDK examples) — extract the *instruction patterns* (claims need evidence, one hypothesis at a time, external state file); mark hooks, sub-agent dispatch, worktrees, parallel agents as **not transferable** (measured worse or impossible in YAML) | `research/raw/10_kits_and_loops.md` |
| 3 | Papers: Coherence Collapse, TestPrune, Fail-Fast (restart-smart), SWE-Replay, Devstral iterative protocol; data papers SWE-Gym, SWE-smith, SWE-Lego (error masking), SWE-Prime/FLARE (curation), Open-SWE-Traces (scaffold mismatch), SWE-Protégé (loop penalty), harness-design study 2609.20804; Gemma 4 prompting guidance; small-model instruction-following evidence | `research/raw/11_ttc_and_data_recipes.md`, `research/FT_DATA_SPEC.md` |
| 4 | Synthesis | `research/INSTRUCTION_DESIGN.md`: ranked cards, experiment queue with kill criteria; STATE.md hypotheses rewritten; draft prompts for E1/E2/E5/E6 in `vm/prompts/` |

## Workstream 2 — 31B experiments (Kaggle paired evals, 3 per week from Oct 31)
Gate unchanged: ≥ +3 tasks on ≥ 50 common Kaggle-sound tasks via `vm/compare_runs.py`, no time regression, 120-task projection < 10.5 h, no new error types; an adopted config is confirmed on the remaining 21 sound tasks before it gets more than 2 slots. Primary readout = **bucket-shift table** (where runs moved), not only the total.

| Pri | Experiment | Bucket | Change | Expected |
|---|---|---|---|---|
| 1 | **E1 verifier gate** | 14 unverified wrong patches | `SequentialAgent [solver: run_command, read_file, edit_file, write_file (v5 minus the submit step; hands over "CHANGED / REPRO / TEST -k")] → [verifier: run_command, read_file, edit_file, get_status, submit_patch; thinking 2048; reruns repro + one `timeout 60 pytest -x -q -k`, fixes once, diff checklist, submits]` | +1 to +3; costs 30–60 s on the 37 runs that never tested → watch the 10.5 h gate |
| 2 | **E2 demonstration prompt** | 10 no-edit + 28-call runs | replace CALL PLAN/TOOL RULES prose with one ~700-token worked 12-call trajectory (grep batch → read → /tmp repro → edit → rerun → pytest -k → diff → submit); keep HARD LIMITS + EDIT PROTOCOL | +1 to +2 (SWE-agent demo +1.7) — ship only *after* E1 (earlier edits alone became wrong patches in others' data) |
| 3 | **E4 edit anchoring + checkpoint** | 9 lost edits (0/9 resolved) | Aider exactness text; ≤ 6-line anchors verified unique with `git grep -c`; mandatory re-read before retry; `cp file /tmp/good_*` once the repro passes; no edits after `budget_warning ≤ 2` → submit | +0 to +1 (ceiling from 09a) |
| 4 | **E8 headroom** | 7 timeouts / 7 exhausted | 32 calls / 9 min, config only | +1 to +2, only if E1 left headroom |
| 5 | **E3 minimal-prompt control** | knowledge | Anthropic-style 20-line prompt | tells us whether rules matter at all |
| 6 | E7 rescue phase (`include_contents: none`, `{problem_description}`, "git diff first") | variance | test on E4B first (31B has no calls left after failures) | +1–3 on E4B |

Week plan: Oct 31 → E1, E2; Nov 7 → E4/E8 + confirmation of the winner; later weeks → stacking the winners and the adapter gates. `vm/build_v4.py` becomes a generic phase builder (per-sub-agent tool subsets, per-phase `generate_content_config`, Loop/Sequential, `include_contents`). `vm/analyze_traces.py` gains edit-error subtype and stop-reason columns.

## Workstream 3 — E4B track (VM T4s, starts now; weekly LB slot)
1. Serve E4B on one free T4 (`serve_vllm.sh`: TP=1 variant, fp16) and calibrate the replica against the Kaggle E4B run (per-task agreement on the same 75 tasks; set `REPLICA_TIME_SCALE` from measured speed). Nightly: one config per T4 over the 71 sound tasks.
2. **E5 budget use**: 20 min / 60 calls / 120 turns, `LoopAgent(max_iterations=3)` over [solver, verifier] with "if a submit with patch_size > 0 exists, reply DONE"; gate: 120-task projection ≤ 10 h. Expected 8/75 → 12–16/75.
3. **E6 prompt shape**: ≤ 400-token prompt + one demo + "one sentence then one call"; thinking 1024/2048/4096 sweep.
4. Best E4B config takes the weekly slot; keep ≥ 1 successfully scored E4B entry before **Nov 12** (deadline wording is ambiguous).

## Workstream 4 — fine-tuning on free compute (E4B distillation; 31B gated)
Data (all free, all publishable):
- **Own 31B traces**: 83 resolved episodes over 29 tasks already on the VM (`scratch/kev_*_out/eval/agent_run/traces`), +22–25 per paired eval, more from 31B VM-replica nights at T 0.7–1.0 when all four T4s are free. Filters: resolved, cut after the first successful `submit_patch`, no protected-file edits, ≤ 24 calls, no identical consecutive calls, ≤ 3 per task. New converter `--source harness-trace` in `vm/prepare_data.py`; **leakage rule**: adapters are evaluated only on tasks whose traces were not trained on (fastapi↔rich cross-fit, plus the hold-out gate G4).
- **Converted OpenHands sets** (`datasets/sft_v4_mid`, 1,263 traj / 5,905 windows; `sft_v4_wide` in reserve): re-render with the **shipped** prompt + budgets (the current header is the retired 5 min / 50-call profile — fix `prepare_data.py` to derive the header from a bundle), keep ≤ 24 steps, first edit ≤ step 10, ≥ 1 test command; ≥ 50 % of tokens stay external-repo to limit fastapi/rich overfitting.
- Error masking (mask assistant turns whose call returned `FileEditError`, keep the recovery turn); thoughts kept but capped below the shipped thinking budget; E4B needs its own tokenisation (different chat template).

Training (reuse `vm/train_qlora.py`): download `google/gemma-4-E4B-it-qat-q4_0-unquantized` (verify it exists; it is the bf16 base the scorer's int4 adapters expect); add the E4B load path (multimodal class so PEFT keys carry `language_model.layers.N`; PLE kept fp16; no `prepare_model_for_kbit_training`); NF4 QLoRA r32 α64 all language projections, lr 1e-4 cosine, eff. batch 16, max-len 7168 (fallback 6144), 1 epoch ≈ 250 steps ≈ 10–13 h on 2 T4s; round 2 (+1 epoch on own/RFT data at 5e-5). 12B adapter retired (wrong header, not prize-eligible). **31B**: not feasible on T4 or within Kaggle quota; decision point in week 3 — if the E4B adapter passes G2 and the user allows ~$30–60 of H100 time, run the same recipe on the 31B.

Gates (all before any slot is spent): G0 export checks (`make_submission.py` adapter packaging, E4B base id) → **G1 load + effect on Kaggle** (smoke adapter, `VllmServer` + `discover_adapters` exactly as the scorer; ≥ 15/20 T=0 outputs differ from base, all parse as tool calls, decode tok/s recorded; ~1 GPU-h, first thing on Oct 31 — answers the open forum question 752239 for us) → G2 paired eval on the replica (E4B) / Kaggle (31B) → G3 time projection → G4 held-out-repo check → G5 one LB load test.

## Workstream 5 — strategy and operations
- **Slots (37 left):** 31B best bundle every day except one E4B day per week; LB slots never validate candidates (a +2 gain needs ~11 draws/arm); a new adopted 31B config gets 2 draws at once; demote a config whose 6-draw LB mean is ≥ 2 tasks below its predecessor (transfer failure). Freeze new bundles **Nov 24**; Nov 25–30 spares + E4B draws; nothing a pick depends on scored after Nov 30.
- **Final picks (Dec 1):** pick 1 = **earliest valid scored draw** of the best 31B config (private ties go to the earlier submission); pick 2 = earliest valid E4B draw unless the 31B LB mean reaches ≥ 13/58 while the E4B is merely at par with the small board; verify both show scores on Dec 1 and again Dec 2.
- **Weekly cadence:** Sat 00:05 UTC eval A, ~05:00 eval B, Sun eval C / G1; ≥ 3 GPU-h reserve; Mon–Fri trace analysis → next cards; VM nightly E4B runs + training on free T4s; 31B replica only via the opportunistic queue.
- **Ledger:** every run/submission appends a row (date, ref, bundle id + sha, base model, delta vs parent, paired n/base/cand/W/L/p, projection, LB tasks/58, status/error, role, pick-eligible); `STATE.md` "Current best" auto-updated.
- **Merge (Nov 25):** decline unless a team shows ≥ 8 identical draws averaging ≥ 12/58 or a scored adapter; our offer would be the validated replica scorer + eval pipeline.
- **Risks:** scorer outages (≥ 2 valid draws per pick config; resubmit byte-identical, never debug on slots); hidden-set shift (report fastapi/rich separately, refuse fastapi-only wins, no repo-specific prompt text); 12-h cap (p90 durations, only proven time profiles); adapter not applied by vLLM (G1 first, prompt-only fallback); quota (crashed notebooks still bill; VM for E4B).

## Timeline
| Week | Milestones |
|---|---|
| Oct 25–31 | WS0 done today; research sprint (09a, 09, 10, 11, FT_DATA_SPEC, INSTRUCTION_DESIGN); E4B replica calibrated, E5/E6 nightly; harness-trace converter + bundle-derived header; E4B bf16 base + trainer path; smoke adapter ready; first E4B LB draw Oct 27 |
| Oct 31–Nov 7 | Kaggle: G1 smoke-adapter test, E1, E2 paired evals; E4B LoRA v1 trained → G2 on replica; best E4B to the small-model board |
| Nov 7–14 | E4/E8 + confirmation of the winner; E4B v2 (+self-RFT, round 2); E4B scored entry before Nov 12; **31B-LoRA decision point** |
| Nov 14–21 | stack winners; adapter G1–G5 if any; LB draws of the adopted config |
| Nov 21–28 | freeze Nov 24; confirmation draws; package code/data/adapters for open-sourcing |
| Nov 28–Dec 2 | spares; final picks Dec 1; re-verify Dec 2 |

## Verification
- Submissions: notebook `submission.zip` byte-identical to the validated bundle (existing cmp loop); success = a new ref dated today in the API list; `sub_status.py` shows score or error text.
- Experiments: `vm/compare_runs.py` paired tables (gain, W/L, sign p, mean and p90 duration, 120-task projection) and the bucket-shift table from `vm/analyze_traces.py`; results and decisions appended to `research/STATE.md`.
- Replica: per-task agreement of the E4B replica run with the Kaggle E4B run on the same 75 tasks (target ≥ 90 % agreement on resolved flags).
- Adapters: G0–G5 as listed; G1 output (differ-count, parse rate, tok/s) recorded in the ledger.
- Every bundle compiles through `build_v4.py`'s `check()` (validate_directory + compile_submission) before any eval or submission.

## Files to create or change
- New: `research/raw/09a_bucket_ceilings.md`, `09_swe_prompt_corpus.md`, `10_kits_and_loops.md`, `11_ttc_and_data_recipes.md`, `research/FT_DATA_SPEC.md`, `research/INSTRUCTION_DESIGN.md`; prompts `vm/prompts/{e1_solver,e1_verifier,e2_demo,e4b_short}.md`; `vm/convert_traces.py` (or `--source harness-trace` in `prepare_data.py`); `vm/make_g1_notebook.py` (adapter load + effect test).
- Modify: `vm/daily_ship.sh` (robust ship), `vm/sub_status.py` (error capture, per-config mean/SE, earliest-valid ref), `vm/compare_runs.py` (p90, per-repo split, bucket shift), `vm/analyze_traces.py` (edit-error subtype, stop reason), `vm/build_v4.py` (generic phase builder, E4B budgets/model), `vm/prepare_data.py` (bundle-derived header, error masking, call-cap cut, E4B template), `vm/train_qlora.py` (E4B path), `vm/serve_vllm.sh`/`run_replica.sh` (E4B TP=1 + adapter), `vm/make_submission.py` (E4B adapter base id), `research/STATE.md`, `research/PLAN_TO_WIN.md`, `CLAUDE.md` (slot/pick policy), git commits after each step and push to `origin/main`.
