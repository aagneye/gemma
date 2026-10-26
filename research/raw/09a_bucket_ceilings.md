# 09a — Failure-bucket ceilings from our own traces (Day 0 of the research sprint, 2026-10-25)

Question: of the runs that fail in each bucket (never edit, lost edit, unverified wrong patch, 8-min timeout), how many of
those *tasks* has ANY of our bundles ever resolved? That number is the recoverable ceiling a bucket-targeted change can
reach; the rest needs capability, not procedure. Second question: what stops the E4B runs (text without submit, empty
submit, malformed calls, nudges, timeouts)?

## Data (all Kaggle L4, same task order; traces copied read-only from the VM / Kaggle kernel outputs)
| Run | Bundle | Date | Tasks | Source |
|---|---|---|---|---|
| pub022 | exact public "0.22" bundle (31B, T 0.2, 28 calls / 8 min, thinking 4096, timeout 240) | 10-19 | 50 | VM `scratch/kev_pub022_out/eval` |
| v3t2k | v3 prompt + thinking 2048 | 10-21 | 52 | VM `scratch/kev_v3t2k_out/eval` |
| v4single | v4 prompt (tool rules + edit protocol), timeout 90 | 10-24 | 49 | VM `scratch/kev_v4single_out/eval` |
| v4phased | scout/fixer/finisher SequentialAgent | 10-24 | 37 | VM `scratch/kev_v4phased_out/eval` |
| v5single | `vm/prompts/system_v5.md`, timeout 90 | 10-24 | 53 | kernel `aagneye/gemma4-kaggle-eval-v5single` (output downloaded to VM `/tmp/rs_v5`) |
| e4b | E4B + v3t2k bundle (thinking 2048, timeout 240) | 10-24 | 75 | kernel `aagneye/gemma4-kaggle-eval-e4b-v3t2k` (VM `/tmp/rs_e4b`) |

All six were re-analysed with the same script, `vm/analyze_traces.py` at commit 7ce7a2d (adds `edit_err_kind`,
`stop_reason`, `nudges`), so the columns are uniform. The VM copies of `trace_analysis.csv` for pub022/v3t2k were made
with the older script and lack those columns; nothing on the VM was modified. Scripts used for the join live in the
session scratchpad (`analysis/buckets2.py`, `stops.py`, `editerrs.py`, `tmpwrite.py`, `halluc.py`); they only read.

Bucket definitions (one run can be in several; RESOLVED excludes all):
- NO_EDIT: no `edit_file`/`write_file` call ever returned ok.
- LOST_EDIT: at least one `edit_file` failed with `old_string not found`, `occurs N times` (ambiguous) or `BudgetExceeded`
  (edit attempted after the 28th call). `write_file` refusals are counted separately (see section 3).
- WRONG_PATCH: edited, non-empty final patch, finished under 470 s, no LOST_EDIT error.
- TIMEOUT: duration >= 470 s (the 8-min cap).
- EDIT_THEN_EMPTY: an edit succeeded but the graded patch is empty (reverted or restored).

## 1. Cross-run picture on the 49 tasks common to pub022, v3t2k, v4single and v5single
| Run | Resolved / 49 |
|---|---|
| pub022 | 22 |
| v3t2k | 23 |
| v4single | 22 |
| v4phased | 14 / 37 (its own subset) |
| v5single | 25 |
| e4b | 6 |

- Solved by k of the four main 31B runs (k = 0..4): **0: 21, 1: 3, 2: 2, 3: 7, 4: 16**. Tasks are mostly always-solved or
  never-solved (consistent with rho 0.59 in `08_notebooks_round3.md`).
- **Union of all 31B runs (pub022, v3t2k, v4single, v4phased, v5single): 28 / 49.** v5 (25) is 3 below the union.
  v5 misses that another 31B bundle solved: `rich_3063`, `fastapi_14463`, `fastapi_14616`. v5 solves one task nobody
  else did: `rich_3506`.
- **21 / 49 tasks (43 %) were never solved by any bundle, including E4B.** E4B adds nothing to the 31B union.
- The 16 always-solved tasks are the floor; the 12 sometimes-solved tasks (k = 1..3) are where variance and
  procedure changes act. **The maximum a procedure change can add on this set, without new capability, is about +3
  on v5 (25 -> 28).** Everything beyond that must come from the 21 never-solved tasks.

## 2. Buckets and their ceilings
"Ceiling" = tasks in the bucket that another 31B run resolved (E4B never adds one).

### 2.1 pub022 (the bundle the post-mortem in `ARCHITECTURE_V4.md` was written from; 50 runs)
| Bucket | Runs | Ceiling (ever resolved by another 31B run) | Which |
|---|---|---|---|
| RESOLVED | 22 | - | - |
| NO_EDIT | 12 | **3** | rich_3063, rich_3480, rich_3506 |
| LOST_EDIT | 9 | **3** | rich_3063, fastapi_14616, fastapi_15589 |
| WRONG_PATCH | 9 | **1** | rich_3521 |
| TIMEOUT | 7 | **2** | rich_3480, rich_3506 (both 8-call runs stuck in one long command) |

Overlaps: NO_EDIT and LOST_EDIT share 5 runs (fastapi_14258, rich_3063, rich_3468, rich_3470, rich_3472): the model
searched for 28 calls, then tried to edit after the budget (`after_budget`) and submitted an empty patch. NO_EDIT and
TIMEOUT share 4 (rich_3105, rich_3180, rich_3480, rich_3506). So the four buckets cover only 28 distinct failing runs.

Stop reasons in pub022: submitted 36, submitted_empty 7, text_stop 7 (the model ended with text, harness captured the
working tree), 0 nudges. Only 13 / 50 runs ran a test.

### 2.2 v5single (current best; 53 runs)
| Bucket | Runs | Ceiling | Which |
|---|---|---|---|
| RESOLVED | 26 | - | - |
| WRONG_PATCH | 10 | **1** | fastapi_14463 (solved by pub022, v3t2k, v4single, v4phased AND E4B; v5 lost it) |
| LOST_EDIT | 10 | **3** | rich_3063, fastapi_14616, rich_3777 |
| NO_EDIT | 9 | **1** | rich_3777 |
| TIMEOUT | 4 | **0** | - |
| EDIT_THEN_EMPTY | 1 | 0 | rich_3470 |

Details that matter for the experiment queue:
- NO_EDIT in v5 is now mostly "edit attempted after the budget": 6 of the 9 have `after_budget` (fastapi_14258,
  rich_3472, rich_3772, rich_3777, fastapi_9425, plus rich_3063 in LOST_EDIT). The model does reach an edit; it reaches
  it at call 29. A call-count checkpoint ("by call 10") did not fix this in v3/v4/v5 wording.
- LOST_EDIT: `old_string not found` 6 errors, ambiguous 1, after_budget 6 (across the 53 runs). Only 3 of the 10 tasks are
  ever solved. **The 0/9 -> 3/9 ceiling from pub022 holds in v5: a perfect edit-anchoring fix is worth at most +3, and
  those three tasks were solved by other bundles at other times, so maybe +1 to +2 in expectation.**
- WRONG_PATCH: 1 of 10 recoverable. Nine of these tasks have never been solved by any bundle. **Verification cannot turn a
  never-solved task into a solved one; its value is in (a) catching the fastapi_14463-type loss (a task usually solved,
  lost by one bad edit) and (b) protecting the 12 sometimes-solved tasks.** Evidence for (b): in v5, runs that ran >= 1
  test resolved 11 / 16 (69 %), runs that ran none 15 / 37 (41 %); in pub022 9 / 13 vs 13 / 37. Correlation, not
  causation: easy tasks leave time for tests.
- Resolve by first-edit call in v5: <= 6: 4/5; 7-10: 6/12; 11-14: 7/11; > 14: 9/16; none: 0/9. Late edits still resolve
  (9/16), so "edit by call 10" is not a requirement; "edit at all before the budget ends" is.
- Stop reasons: submitted 40, submitted_empty 7, text_stop 5, calls_exhausted 1. Nudges: 3 in 53 runs (negligible).
- Durations: 5 runs >= 470 s; one resolved anyway (rich_3506, 484 s). v5 mean 276 s/task.

## 3. New finding: `write_file` to /tmp is refused, and every prompt since v3 asks for it
`write_file("/tmp/repro.py", ...)` returns `FileWriteError: Path traversal detected: '/tmp/repro.py' escapes workspace
root.` (the harness resolves paths under /workspace; `/tmp` is outside). The v3/v4/v5 prompts say "scratch files go in
/tmp only" and the model obeys with `write_file`:

| Run | Runs hitting the refusal | Wasted calls |
|---|---|---|
| pub022 | 0 / 50 | 0 |
| v3t2k | 17 runs ('other' edit errors) | 17 |
| v4single | 31 errors | 31 |
| v5single | **27 / 53 runs** | 29 |
| e4b | 3 / 75 | 3 |

What the v5 model did after the refusal (27 runs): `python -c` inline 12, heredoc via run_command 6, `write_file` again
3 (one run twice), read_file 3, other 3. 15 of the 27 affected runs still resolved, so the cost is mostly one or two
calls and some confusion, but it is pure waste and it lands exactly in the reproduce-first step we want to strengthen.
Fix (prompt only): "write_file can only create files under /workspace. Create scratch scripts with run_command and a
quoted heredoc into /tmp, then run them with timeout 30 python /tmp/repro.py." Raw/01 section 2.4 already recorded the
rule (MAUK: a /tmp write landed in the workspace on older harness builds; now it is refused). This goes into every draft.

## 4. E4B stop-reason taxonomy (75 runs, bundle v3t2k, 8 resolved, 97 s/task, 13.8 calls mean, median 13; 5 runs at 28)
| Stop reason | Runs | Resolved |
|---|---|---|
| submit_patch with a non-empty patch | 70 | 7 |
| ended with text, never submitted (working tree captured) | 3 | 1 |
| submit_patch with an empty patch | 2 | 0 |
| 8-min timeout | 0 (max 482 s; two runs over 400 s) | - |

- **Nudges: 13 runs received a continuation nudge (23 nudges total, max 4 in one run).** The E4B ends its turn with
  text before submitting in 28 runs; the harness nudges ("Please continue your work using the available tools, or call
  submit_patch ..."). First action after a nudge: text again 12, submit_patch 5, run_command 3, read_file 2, edit_file 1.
  The text-again cases are the "I will now provide the final summary" habit: the model writes a summary, is nudged,
  writes another summary. In the 31B runs nudges are rare (3 in v5, 0 in pub022).
- **Malformed tool calls written as text: 0.** The E4B produces well-formed calls. It instead hallucinates tool names:
  `git_status` 6, `git_status_diff` 4, `git_status_and_diff` 1 (all `ValueError`, 11 calls in 11 runs), i.e. it invents a
  tool for the "git status && git diff" step the prompt asks for. One `read_file` with start_line 73000.
- **Edit errors dominate: 72 `FileEditError` in 75 runs** (49 `old_string not found`, 19 `occurs N times`, 4 "old and new
  identical"), 1 BudgetExceeded. 23 runs fall in LOST_EDIT; 7 of those tasks are 31B-solvable.
- The E4B *does* run tests (64 / 75 runs ran >= 1 pytest) because the v3t2k prompt asks for it, yet 44 runs submit a
  wrong patch; 17 of those 44 tasks are solved by some 31B run. **E4B's ceiling from fixing wrong patches alone is 17
  tasks; from fixing lost edits 7; realistic near-term target 12-16 / 75 as in the plan.**
- Tool usage: run_command 433, read_file 318, edit_file 195, submit 75, write_file 1. Mean calls 13.8 of 28: the E4B
  stops early by choice (submits after one test run that fails for an unrelated reason such as a missing `dirty_equals`
  fixture, which it correctly ignores, then submits whatever it has).

## 5. Implications (feed INSTRUCTION_DESIGN.md)
1. **Ceilings are small and overlapping.** On the common set: no-edit +3 at most (pub022) / +1 (v5), lost-edit +3,
   wrong-patch +1, timeout +2. The honest expectation for any single bucket fix is +1 to +2 tasks on 50, i.e. inside
   the SD 1.56 noise of one LB draw and at the edge of the paired-eval gate (>= +3).
2. **The only way past 28 / 49 is new capability on the 21 never-solved tasks**: better localisation on the ones where
   the fix is found but wrong, more time per task where the repro loops, or a different model (adapter).
3. **Procedure changes should be judged by the bucket-shift table**, not the total: a change that moves 3 runs from
   NO_EDIT(after_budget) to WRONG_PATCH is a real effect even when the total stays at 25.
4. **Cheap, certain win: stop asking for `write_file` to /tmp.** 27 / 53 v5 runs waste a call there.
5. **E4B**: the stop-reason mix says the budget is not the problem (13.8 calls, no timeouts); edit anchoring and the
   post-summary text loop are. A shorter prompt that forbids summaries before submit and shows one exact `edit_file`
   example is the right first E4B experiment (E6), before the budget-raising E5.

## Reproduction
- Join and ceilings: `python -I analysis/buckets2.py <dir with one folder per run holding trace_analysis.csv>`.
- Uniform columns: run `vm/analyze_traces.py <eval_dir>` (commit 7ce7a2d or later) on each copied `eval/` folder.
- E4B/v5 kernel outputs: on the VM `python ~/gemma4_vm/kev_status.py <slug> --output /tmp/<dir>` (needs `.venv`).
