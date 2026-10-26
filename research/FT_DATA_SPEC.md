# FT_DATA_SPEC — training-data rules for the E4B adapter (and a future 31B adapter)

Written 2026-10-25 (research sprint, Day 3). Companion to `vm/convert_traces.py` and `vm/prepare_data.py` (v3,
"adk-v3" schema): the rules below are the specification those scripts implement or must implement; flags are named
where they exist today. Evidence per rule is in `research/raw/11_ttc_and_data_recipes.md` Part B and
`research/raw/05_training_recipes_and_data.md`.

## 0. Fixed facts the data must match
- The scorer serves `gemma-4-E4B-it-qat-w4a16-ct` (int4) with an adapter of <= 3 GiB; training uses the bf16 QAT base
  `google/gemma-4-E4B-it-qat-q4_0-unquantized` (gate G0 verifies the id). Tokenisation and rendering use that
  checkpoint's own chat template (E2B/E4B emit no empty thought block; 12B/26B/31B do).
- What the model sees at test time: system prompt of the SHIPPED bundle, the harness user prompt (task header,
  issue, budget lines, execution rules, standard instructions, tree), JSON tool results (`{"status": "ok", ...}` /
  `{"status": "error", "error_type", "error_message"}`), `budget_warning` fields once <= 10 calls remain, ADK
  compaction above 14,336 tokens that keeps the last 5 events. **Every training sample is rendered in exactly this
  shape under the bundle it will ship with** (`--bundle submissions/<bundle>` derives system prompt, tool list and
  budgets). Scaffold mismatch costs 1-5 points (Open-SWE-Traces Table 5), so no SWE-agent/OpenHands tool names or
  observation formats survive conversion.
- Tool schema: run_command(command), read_file(filepath, start_line, end_line), edit_file(filepath, old_string,
  new_string, allow_multiple), write_file(filepath, content), get_status(), submit_patch(), plus the three graph
  tools only if the shipped bundle declares them (the current bundles do not).
- Thinking: the E4B bundle runs with thinking on (budget 2048). Thoughts are kept in tool-calling turns (the template's
  preserve_thinking rule) and dropped from earlier non-tool turns; the training target turn always carries its
  thought. Thought cap at tokenisation: **600 tokens for the E4B, 1,000 for the 31B** (`--thought-cap`), cut at a
  paragraph boundary, never mid-sentence; a capped thought ends with one sentence naming the next action.
- Loss: assistant-turn spans only (tool results, user turns, compaction summaries never contribute); masked turns
  (`train=False`) stay in context with no loss.

## 1. Source A — rejection-sampled own 31B traces (`--source harness-trace`, `convert_traces.py`)
Inputs: every `eval/` folder with `results.csv` + `agent_run/traces/trace_<instance>.json` (Kaggle runs copied to the
VM, VM replica runs, nightly 31B generation runs at T 0.7-1.0). Today: 83 resolved episodes over 29 tasks; +22-26 per
paired eval.

Keep an episode iff ALL of:
| # | Rule | Flag / code | Evidence |
|---|---|---|---|
| A1 | `results.csv` resolved == True (the grader's verdict, never the model's claim) | `collect()` | SWE-Gym, SWE-smith: resolved-only |
| A2 | model is the 31B (`--teacher 31b`); E4B self-traces go to Source C | `--teacher` | distillation = teacher traces |
| A3 | cut after the first successful `submit_patch` (patch_size > 0) that follows the last edit; trailing harmless calls (git status/diff, ls) dropped; the closing text kept or a one-sentence closing synthesised | `cut_episode` | the kept prefix produces exactly the graded patch |
| A4 | no edit_file/write_file on a protected path (tests/, test_*.py, *_test.py, conftest.py, pytest.ini, pyproject.toml, setup.cfg, tox.ini); /tmp scratch is not protected | `PROTECTED_RE` | SWE-Lego test-edit removal +0.6; grader discards those edits |
| A5 | 3 <= tool calls <= 24 (submit_patch not counted) | `--max-calls 24` | 80-90 % of what a model ever solves it solves within 30-40 calls; our cap is 28 |
| A6 | no identical consecutive calls; no multi-call steps; no continuation nudges in the episode | `cut_episode` | SWE-Prime S_redundancy = 0 on adjacent duplicates; nudges add user turns the student must not learn to need |
| A7 | at most 3 episodes per task, the shortest with the fewest masked turns first | `--per-task 3` | SWE-smith <= 3 per instance; SWE-Gym: keep more than one success |
| A8 | NEW: navigation streak (consecutive grep/ls/find/read_file calls) <= 8 | to add in `cut_episode` | SWE-Protégé k2 = 8; SWE-smith: a length-10 repeat implies 89 % failure |
| A9 | NEW: patch-size sanity against the public gold patch when the task is one of the 129 public tasks: files_changed(model) <= 2 x files(gold) and changed lines(model) <= 3 x lines(gold) | to add (gold patches are in the competition data) | SWE-Prime S_result; patch-size odds ratio 0.53 per doubling (08 round 3) |
| A10 | NEW: no git-history peeking before the first edit: drop if any run_command before the first edit contains `git log`, `git show`, `git reflog`, `git blame`, `git stash`, or `git diff <ref>` with a ref argument | to add | SWE-Prime S_git; Open-SWE-Traces AST scan (-27 % of corpus) |

Per-turn masking (loss off, context kept): the assistant turn whose tool result was a harness rejection
(FileEditError, FileWriteError, FileReadError, ValueError, BudgetExceeded, ADK parameter rejection, hallucinated tool
name) — `classify_observation`. **CommandError is never masked** (a failing reproduction or a red test is the
intended signal, SWE-Lego). The recovery turn that follows stays trainable. Episodes with > 3 masked turns are
dropped (quality_ok's "errs < 4" rule applies to the last 6 steps for external corpora; apply the same to own traces).

Rank key within a task (ties by A7): (1) SWE-Prime workflow term: read or grep BEFORE the first edit AND a test or
reproduction command AFTER the last edit; (2) fewer masked turns; (3) fewer calls; (4) earliest run.

Leakage rule (non-negotiable): an adapter is evaluated only on tasks whose traces were not in its training set.
Splits: `--split-by-repo` (fastapi vs rich cross-fit: train on fastapi traces, evaluate on rich tasks and vice versa)
and the hold-out gate G4 (a fixed list of 20 Kaggle-sound tasks never used for training). Record the task ids of
every training episode in `stats.json`.

Temperature for new 31B generation runs: T 0.7-1.0 (SWE-Gym sampled at 0.2-0.8; variety matters, the student is
evaluated at 0.2). Branching (optional, SWE-Replay offline use): rerun a failed task from the archived prefix of its
best run at the last rich-reasoning step instead of from scratch.

## 2. Source B — converted OpenHands trajectories re-rendered under the shipped prompt (`--rerender`)
Inputs: `datasets/sft_v4_mid/all.jsonl` (1,263 trajectories / 5,905 windows, converted from nebius-openhands and
swe-hero; `sft_v4_wide` in reserve), raw corpora via `--source nebius-openhands|swe-hero`.

| # | Rule | Flag / code | Evidence |
|---|---|---|---|
| B1 | header = the SHIPPED bundle (system prompt, tools, budgets); the old 5-min / 50-call header is retired | `--bundle` | scaffold mismatch 1-5 points |
| B2 | tool mapping: execute_bash/bash -> run_command; str_replace_editor view -> read_file(start,end); str_replace -> edit_file; create -> write_file; insert -> edit_file with anchor; submit/finish -> submit_patch; `think` content -> the thought | `map_call` | 05 section B |
| B3 | drop trajectories with > 25 % unmappable calls | `quality_ok` n_dropped_calls | |
| B4 | <= 24 tool steps (`--max-steps 24`), >= 4 steps | `--max-steps` | our 28-call cap |
| B5 | first successful edit by step 10 (`--first-edit-by 10`) | `--first-edit-by` | tempo demonstration; note 09a: 31B late edits still resolve 9/16, so this is a teaching choice, not a correctness filter |
| B6 | >= 1 test or reproduction command (`pytest`, `python -m unittest`, `python <script>` or `python -c`) after the last edit (`--min-tests 1`) | `--min-tests` | SWE-Prime workflow term; FLARE penalises missing validation |
| B7 | NEW: Open-SWE-Traces drop list: environment exceptions, iteration-limit or early-ended runs, empty patches, test-file edits, concurrent tool calls, >= 3 consecutive tool-usage errors; git-hacking scan as A10 | to add to `quality_ok` | -27 % of their corpus; their resolved-only vs full-corpus result does not apply because we only have "resolved" rows |
| B8 | no identical consecutive calls; navigation streak <= 8 | `quality_ok` + A8 | |
| B9 | repo cap 20 trajectories per source repo (`--repo-cap 20`); >= 50 % of training TOKENS from repos other than fastapi/rich | `--repo-cap`, stats.json | repo diversity ~log(#repos); fastapi/rich depth only helps those repos |
| B10 | observations re-emitted in the harness JSON shape, clipped to 2,000 chars (`MAX_OBS_CHARS`; harness cap 5,000 — the smaller cap keeps 7k windows feasible on T4), `budget_warning` added from the bundle's call budget | `to_adk_observation`, `budget_warn` | |
| B11 | windows of 8 tool steps (`WINDOW_STEPS`); steps before the window summarised as a compaction block (commands run, files read/edited/created, last reasoning) + "Continue from here using the tools."; inside the window only the last 5 observations are kept verbatim (`KEEP_LAST_OBS`), older ones replaced by `[earlier output compacted]` | `window_samples` | ADK compaction keeps 5 events; SWE-smith's student kept 5 outputs |
| B12 | thought handling: OpenHands `reasoning_content` or `think` text -> thought; visible text before a call folded into the thought (the template renders text after the tool response) | `_from_openai_style`, `iter_harness_traces` | template rule |

## 3. Source C — the E4B's own resolved traces (self-RFT, round 2)
Same rules as Source A with `--teacher e4b`, taken from the E4B replica nights (71 sound tasks x nightly configs)
and any Kaggle E4B eval. Cap: <= 3 per task; because the E4B resolves 8/75 at 13.8 calls, expect 5-10 episodes per
night; round 2 trains 1 epoch at lr 5e-5 on Source C + the Source A slice for the same tasks. Never train the E4B on
E4B traces of tasks in the G4 hold-out.

## 4. Optional slice — semi-resolved localisation prefixes (SWE-Lego +1.2)
Unresolved 31B episodes whose first edit touches a gold-patch file (public tasks only, gold known) are cut at that
first edit: the prefix (search, read, plan, first edit) is kept as a localisation demonstration with the final
assistant turn being the first edit call. Cap at 10-20 % of samples; label `source = semi`; never include the turns
after the first edit (that is where the wrong fix lives). Try only after the resolved-only adapter passes G2.

## 5. Mixture and size
| Slice | Share of samples | Source |
|---|---|---|
| own 31B resolved episodes (A) | 30-50 % | 83 today; target 150-250 by the time of round 1 |
| re-rendered OpenHands/SWE-Hero windows (B) | 50-70 % | 1,263 traj -> expect 600-900 after B4-B9 |
| semi-resolved prefixes (section 4) | 0-20 % | optional |
| E4B self-traces (C) | round 2 only | |
Targets: >= 75 % of samples carry a thought (Unsloth guidance to preserve thinking); >= 50 % of tokens non-fastapi/rich;
no task with > 3 episodes; total 2k-5k windows (the knee for <= 12B models is 2k-5k trajectories; we have fewer, so one
epoch on 1,500-3,000 windows is the realistic round 1).

## 6. 31B -> E4B distillation rendering (what differs from the 31B rendering)
- Template: the E4B checkpoint's template; `enable_thinking=True`; no empty thought block (E4B emits none); BOS added
  once by the tokenizer, never as literal text; EOS/turn ids 1 and 106.
- Thought cap 600 tokens (31B thoughts average far more); cap at a paragraph boundary and append a one-sentence
  "Next: <action>" so the capped thought still ends in a decision. Measure the capped fraction in `stats.json`
  (`thought_tokens`, `capped`); if > 50 % of 31B thoughts are capped, prefer episodes with shorter thoughts in the
  rank key rather than truncating harder.
- Sequence length 7,168 (fallback 6,144) on T4; windows longer than that are dropped, not truncated, so the final
  submit turn is always inside a window.
- Label fraction: >= 8 supervised tokens per window (`no_labels` skip) and report the supervised-token share; expect
  10-20 % of tokens supervised in agent data.
- Masking as Source A; additionally mask any 31B turn that calls a tool the E4B bundle does not declare (graph tools).

## 7. Gates before any slot is spent (from PLAN_TO_WIN, unchanged)
G0 export checks (adapter packaging, base id) -> G1 load + effect on Kaggle (>= 15/20 T=0 outputs differ from base,
all parse as tool calls, tok/s recorded) -> G2 paired eval on the E4B replica (>= +3 on 50 common tasks, no new error
types) -> G3 120-task projection <= 10 h -> G4 held-out-repo check (adapter trained on fastapi traces evaluated on
rich tasks, and the 20-task hold-out) -> G5 one LB load test.

## 8. Stats every build must print (`stats.json`)
episodes kept / dropped by reason (A1-A10, B3-B9), masked turns and reasons, windows per source, tokens per repo,
thought coverage and capped fraction, supervised-token share, task ids used (for the leakage check), bundle hash.
