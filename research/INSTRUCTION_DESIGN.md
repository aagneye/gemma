# INSTRUCTION_DESIGN — ranked pattern cards, experiment queue and prompt drafts (research sprint, 2026-10-25)

Inputs: `raw/09a_bucket_ceilings.md` (our traces), `raw/09_swe_prompt_corpus.md` (scaffold prompts), `raw/10_kits_and_loops.md`
(kits and loops), `raw/11_ttc_and_data_recipes.md` (papers), `FT_DATA_SPEC.md` (data). Everything here is harness-native:
prompt text, tool subsets, SequentialAgent/LoopAgent, `eval_config` budgets, sampling. Nothing is adopted without the
paired gate in CLAUDE.md (>= +3 tasks on >= 50 common Kaggle-sound tasks, no time regression, bucket-shift table read).

## 0. The measured frame every card must respect
- v5single (current best, 53 Kaggle-sound tasks): 26 resolved; WRONG_PATCH 10 (ceiling 1), LOST_EDIT 10 (ceiling 3),
  NO_EDIT 9 (ceiling 1; 6 of them attempted an edit after the 28th call), TIMEOUT 4 (ceiling 0). 16/53 ran a test.
- On the 49 tasks common to the four main 31B runs: 16 always solved, 12 sometimes, 21 never by any bundle (E4B
  included). Union of all 31B runs 28; v5 25. **No procedure change can add more than ~+3 on this set; the paired
  gate (+3) is therefore at the ceiling of what one prompt change can show.** Beyond that is capability (the 21).
- Three wording-heavy variants moved the paired result by -1, +0, +3 over pub022 (v3t2k, v4single, v5). Forcing
  earlier edits alone turned timeouts into wrong patches (scottweeden, 48 paired: +1/-2). Multi-agent analyzers,
  voting, extra tools, skills, T 0/0.4 and 6-min caps measured worse by other teams; our 3-phase v4_phased lost 4
  tasks and 120 s/task.
- Prompt compliance decays like a product of per-rule rates (ManyIFEval); v5 carries ~45 rules; the E4B's IFBench is
  44 vs 76 for the 31B. Any new rule must pay for itself or replace an old one.
- `write_file` to /tmp is refused (27/53 v5 runs lost a call); fixed in v5.1 (one line); every draft below inherits it.

## 1. Ranked cards (expected gain in tasks per 50, honest)
| # | Card | Source | Bucket (ceiling) | Harness lever | Expected | Cost | Kill criterion |
|---|---|---|---|---|---|---|---|
| 1 | Verifier phase that refutes, runs repro + one targeted test, fixes once, submits (S2, TR1, LK1, TTC2) | SWE-agent review-on-submit, Trae, TestPrune, claude-flow reviewer | WRONG_PATCH (1) + protection of the 12 sometimes-solved | SequentialAgent [solver, verifier], per-phase tools, verifier thinking 2048 | +1 to +2 | +30-60 s on the 37 untested runs | paired < +2 or projection > 10.5 h |
| 2 | Worked 12-call trajectory instead of CALL PLAN/TOOL RULES (S4, TTC5) | SWE-agent demo (-1.7 without), harness study (planning: never-edit 68.6 -> 27.8 %) | NO_EDIT/after_budget (1-3), 28-call runs | prompt text (E2) | +1 to +2 | ~0 (replaces rules) | more WRONG_PATCH with no RESOLVED gain |
| 3 | Scratch files via run_command only (A1) | our traces (27/53 wasted calls) | calls, repro step | prompt line (shipped as v5.1) | +0 to +1 | 0 | refusals not at 0 |
| 4 | Edit anchoring: distinctive short anchors, "not found" -> check new text already there, re-read before retry, no edits after budget_warning <= 2 (AI1, MO1, S3) | Aider, Moatless, OpenHands docstring | LOST_EDIT (3) | prompt text (E4) | +0 to +1 (31B), +2 to +4 (E4B) | 0 | edit_err per run unchanged |
| 5 | Freeze after the first pass; never improve a passing fix; at most two fix attempts (TTC1, SP2, LK5) | Coherence Collapse, superpowers, oh-my-opencode | WRONG_PATCH, EDIT_THEN_EMPTY, giant late patches | prompt text; verifier "fix once" | +0 to +1 | 0 | patch-size p90 unchanged |
| 6 | Repro must FAIL before the edit and PASS after; honest PASS/NOT_RUN line (SP1, LK2) | superpowers TDD, ralph-claude-code | WRONG_PATCH | prompt text + verifier report | +0 to +1 | 0 | bundle with 1 |
| 7 | LOCATION + INTENDED BEHAVIOUR line before the first edit; 6 navigation calls then edit (AG1, ACR1, TTC7) | Agentless, AutoCodeRover, SWE-Protégé | NO_EDIT (1-3) | prompt text | +0 to +1 | ~60 tokens | NO_EDIT unchanged |
| 8 | Headroom 32 calls / 9 min (E8) | our durations (5 runs >= 470 s; 28/53 at the call cap) | TIMEOUT (0-2), after_budget | eval_config | +0 to +2 only with 1 in place | +25 s/task mean | projection > 10.5 h |
| 9 | Five rules first and last; 20-line control prompt (TTC8, S1) | ManyIFEval, IFScale, Anthropic scaffold | knowledge | prompt text (E3) | unknown sign | 0 | E3 <= v5 - 3 => rules matter |
| 10 | Rescue phase with the diff, not the history, and a sceptical note (TTC3) | Fail-Fast (Gemma4-31B 62.2 -> 65.2) | variance | SequentialAgent + include_contents none (E7) | E4B +1 to +3; 31B needs E8 | budget | < 2 rescues of 50 on the E4B replica |
| 11 | LoopAgent x3 over [solver, verifier] with 20 min / 60 calls for the E4B (TTC4) | Devstral iterative protocol | E4B wrong/empty/unfinished | LoopAgent + budgets (E5) | E4B 8 -> 12-16 / 75 | time | projection > 10 h or < +3 of 75 |
| 12 | <= 400-token E4B prompt: exact tool names, no git tool, one sentence then one call, one example (RF1, M1, TTC8) | Refact weak-agent, mini-SWE, harness study | E4B nudges (13 runs), hallucinated tools (11 calls), edit errors (72) | prompt text (E6) | E4B +1 to +3 | 0 | nudged runs not < 8/75 |
| 13 | Baseline run of the targeted test before the first edit (TTC2) | TestPrune config | WRONG_PATCH | prompt text (+1 call) | +0 to +1 | 1 call | pairs with 1; skip if calls are short |
| 14 | External state file in /tmp (LK4) | quickstarts, oh-my-opencode | compaction | prompt text (1-2 calls) | ~0 on the 31B | calls | not queued |

Not queued (measured worse or impossible in YAML): third phase (scout), analyzers/voting, extra tools, skills, bash-only
action space, lint-gated edit tool, last-5 history processor, long thinking, multi-sample replay, learned monitors.

## 2. Experiment queue (bundle names follow `vm/build_v4.py` SPECS where they exist)
Gate for all: paired on >= 50 common Kaggle-sound tasks via `vm/compare_runs.py`, >= +3, no time regression,
120-task projection < 10.5 h, no new error types, and the bucket-shift matrix as the primary readout (a change that
moves runs from NO_EDIT(after_budget) to WRONG_PATCH is real even at +0 total). Two draws at once for an adopted
config; LB slots never validate candidates.

| Order | Exp | Bundle | Change vs v5.1 | Hypothesis (bucket) | Kill criterion | Slot |
|---|---|---|---|---|---|---|
| 1 | E1 verifier gate | `e1_31b` (SequentialAgent solver -> verifier; solver tools run_command/read_file/edit_file/write_file; verifier adds get_status + submit_patch; verifier thinking 2048) | `vm/prompts/e1_solver.md` + `e1_verifier.md` (this sprint) or the E4B session's `phase_solver.md`/`phase_verifier.md`; see section 3 | 37/53 untested runs get one repro rerun + one targeted test; the fastapi_14463-type loss is caught; WRONG_PATCH -> RESOLVED +1-2 | paired < +2, or mean duration > 320 s/task, or the solver phase ignores its 18-call stop in > 20 % of runs (then budgets must be structural: LoopAgent or lower max_tool_calls) | Oct 31 (scheduled by the main session) |
| 2 | E2 demonstration prompt | single agent, `vm/prompts/e2_demo.md` | CALL PLAN/TOOL RULES replaced by the worked example; HARD LIMITS + EDIT PROTOCOL kept; 6-navigation rule; freeze rule | after_budget NO_EDIT 6 -> <= 2; calls/run down; WRONG_PATCH not up | more WRONG_PATCH than v5.1 with no RESOLVED gain (earlier edits became wrong patches in others' data) | Oct 31 (scheduled) |
| 3 | v5.1 control | `submissions/v5_1` | one line | baseline for the week; also measures variance against v5 | - | Oct 31 (scheduled) |
| 4 | E4 edit anchoring + checkpoint | single agent, v5.1 + cards 4-6 (short diff) | LOST_EDIT 10 -> <= 7; no edits after budget_warning <= 2 | edit_err per run unchanged | Nov 7 |
| 5 | E8 headroom | winner of 1-2 with 32 calls / 9 min | TIMEOUT/after_budget runs convert | projection > 10.5 h, or the extra calls are spent on exploration (calls at cap unchanged) | Nov 7, only if E1 left >= 1 h of projection headroom |
| 6 | E3 minimal-prompt control | 20-line Anthropic-style prompt + HARD LIMITS | tells whether the rule count matters at all; if it ties v5, every later prompt can be short | - (it is a measurement) | first free slot after Nov 7 |
| 7 | E7 rescue phase | SequentialAgent [solver, rescue(include_contents: none, "git diff first", sceptical note)] | variance: +1 to +3 on the E4B; on the 31B only with E8 | < 2 rescues of 50 on the E4B replica | E4B replica now; 31B after E8 |
| 8 | E5 budget use (E4B) | `e4b_e5` LoopAgent x3, 20 min / 60 calls / 120 turns | E4B 8 -> 12-16 / 75 | projection > 10 h or < +3 of 75 | E4B replica (E4B session) |
| 9 | E6 prompt shape (E4B) | `e4b_e6_t*` (`e4b_demo.md`, E4B session) and `e4b_e6r_t2048` (`e4b_short.md`, this sprint); thinking 1024/2048/4096 | nudges 13 -> < 8 runs; hallucinated tool names 11 -> 0; edit errors down; resolved up | no bucket moves | E4B replica now |
| 10 | Stack | E1 + E2 winner, then + E4 | the only route to the ceiling (+3) | as above | Nov 14 |

Readout for every run: resolved/50, mean and p90 s/task, 120-task projection, calls/run, bucket-shift matrix,
edit_err kinds, stop reasons, nudges, write_file refusals, tests-run share. Decide from the matrix and the total.

## 3. Prompt drafts (files only; no bundle built by this session)
| File | Base | What changed | ~tokens | Builder use |
|---|---|---|---|---|
| `vm/prompts/e2_demo.md` | v5.1 | CALL PLAN, TOOL RULES and PROCEDURE replaced by a 12-call worked example in the harness's own tool names (prose-bound calls, no JSON); HARD LIMITS + EDIT PROTOCOL kept; adds: no git tool, repro must fail first, "not found" -> check new text already there, freeze after pass, 6-navigation rule, honest final sentence | ~1,450 | single agent, 28 calls / 8 min |
| `vm/prompts/e1_solver.md` | v5.1 + E4B session's `phase_solver.md` structure | 31B solver: 18-call pass, repair-pass logic for nudge restarts, LOCATION line before the first edit, repro-must-fail rule, freeze rule, hand-over block CHANGED / REPRO / TEST; no submit | ~1,250 | `e1_31b` solver (uses @CALLS@/@MINUTES@) |
| `vm/prompts/e1_verifier.md` | E4B session's `phase_verifier.md` | refutation framing (break it, then submit), one neighbouring-input check as thinking, fix once, diff checklist, honest PASS/FAIL/NOT_RUN line, two-report cap then submit | ~900 | `e1_31b` verifier |
| `vm/prompts/e4b_short.md` | new | <= 400 tokens: 7 rules (one sentence then one call; four tools, no git tool; no test/config edits; scratch via run_command; batched search, edit by call 8; anchors; repro + one test, two fixes max; minimal diff) + one 8-call example | ~390 | `e4b_e6r_t2048` |

Differences from the E4B session's `phase_solver.md` / `phase_verifier.md` (both are valid E1 candidates): the sprint
drafts add the refutation framing, the LOCATION line, the repro-must-fail rule, the freeze rule, the "no git tool" fact
and the honest status line, and drop the CALL PLAN counting. If only one E1 slot exists, run the pair whose diff from
v5.1 is smallest (phase_*) so that the verifier effect is measured alone; the sprint drafts are the stacked version for
week 2. Both pairs must build through `build_v4.py` `check()`; placeholders @CALLS@/@MINUTES@ are rendered there.

Rules for every prompt: no curly braces (ADK templating); the five rules with measured consequences (no test/config
edits; write_file only under /workspace; one unique old_string copied from a fresh read; edit before the budget
ends; submit_patch then one sentence) appear first and are echoed last; tool calls are described in prose bound to
the tool name, never as shell-looking pseudo-calls (31 % vs 5 % malformed calls in G4KIT's replay); budgets through
placeholders where the builder renders them.

## 4. Suggested rewrite of STATE.md "Open hypotheses" (for the main session to paste)
1. E1 verifier gate: WRONG_PATCH -> RESOLVED +1-2 and protection of the 12 sometimes-solved tasks; cost 30-60 s/task.
2. E2 demonstration prompt: after-budget NO_EDIT runs 6 -> <= 2 without a rise in WRONG_PATCH; calls/run down.
3. E4 edit anchoring: LOST_EDIT 10 -> <= 7 (ceiling +3).
4. E8 headroom (32 calls / 9 min) converts TIMEOUT/after_budget runs only once E1 exists; projection gate 10.5 h.
5. E3 control: a 20-line prompt ties v5 (then rule count is irrelevant) or loses >= 3 (then rules matter).
6. E7 rescue phase: diff-carrying restart is worth +3 points on Gemma4-31B in Fail-Fast; test on the E4B first.
7. E5/E6 (E4B): loop x3 with 20 min / 60 calls, and a <= 400-token prompt; nudges, hallucinated tools and edit errors
   are the E4B's measured failure modes, not the budget.
8. Ceiling: the union of all 31B runs is 28/49; v5 is 25; the 21 never-solved tasks need the adapter or more time.

## 5. Risks and open questions
- SequentialAgent restart semantics: after a nudge the sequence restarts at the solver with the full history (verified
  for v4_phased); the solver prompts handle it ("REPAIR PASS"), but the number of restarts is bounded only by the
  3-nudge rule and the budget. `include_contents: none` for a rescue phase is a builder option; its interaction with
  nudges is untested.
- Time: the verifier adds a repro rerun and one pytest (20-60 s) to the 37 runs that never tested; v5 projects 9.1 h,
  so E1 must stay under ~320 s/task mean. The verifier's thinking 2048 keeps its turns short.
- Obedience: the 12B scout ignored its 8-call stop; the 31B solver's 18-call stop is also prompt-only. If it is
  ignored in > 20 % of runs, the structural alternative is a LoopAgent with per-phase `max_tool_calls` (not available
  per phase in eval_config today) or the E8 headroom.
- Ceilings: with +3 as the gate and +3 as the measured ceiling of all procedure changes, a true +2 will read as a
  tie in one paired run. Use the bucket-shift matrix, repeat the best candidate once, and stack (order 10) before
  concluding that wording is exhausted.
- E4B: the small-model prize needs one scored entry before Nov 12; E6 is the cheapest change and should take the
  first E4B slot after the Oct 27 baseline draw.
