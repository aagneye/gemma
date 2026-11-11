# 13. The run log: `vm/autopsy.py` and `vm/arms_report.py`

Written Nov 11 2026. This is section 3 ("The log") of the instruction plan.
Both tools are CPU only and use the Python 3.10 standard library. They replace `vm/analyze_traces.py`.

## 1. How to run

```bash
# one run: writes autopsy.jsonl, report.md and brief.md (default: into the run dir)
python3 ~/gemma4_vm/autopsy.py results/replica/<tag> [--out <dir>]

# several runs side by side; the first one is the base
python3 ~/gemma4_vm/arms_report.py results/replica/<base> results/replica/<cand>... \
        [--groups results/lists/dev48.csv] [--out <file.md>]
```

- Run both from `/mnt/biohub/kdata/gemma4`. Relative paths that do not exist are also tried under that root.
- `--tasks` and `--build-log` take a comma-separated list. The default is `data/rebench/` plus `data/rebench2/`.
- A task that is not in `--tasks` still gets a record. Its gold-file and issue checks are empty, and the tool says how many tasks this affects.
- `autopsy.py` works on a run in progress. It reads `agent_run/task_results.jsonl` (one line per finished task) and skips a half-written last line. `results.csv` is the fallback.
- `arms_report.py` imports `autopsy.py` from its own folder. It reads the traces itself and writes nothing into the run dirs.
- Speed: 339 tasks take 0.7 seconds and 52 MB.
- Hook for `vm/run_replica.sh` (last line): `python3 ~/gemma4_vm/autopsy.py "$OUT" || true`.

## 2. Outputs
- `autopsy.jsonl`: one record per finished task (fields in section 3).
- `report.md`: headline, outcomes, grading, failure types, rules and behaviours, calls by kind, edited files against gold files, solved by task label, runtime, and one "why" sentence for every task.
- `brief.md`: at most 120 lines (55 lines on the test run). Fixed sections: Headline, Outcomes, Rule compliance, Largest fixable failure type (with 3 example tasks), Runtime.

## 3. Definitions

**Calls**
- Call kind: the tool name. `run_command` is classified by its command; the first matching pattern wins:
  `test` (`\bpytest\b|unittest`), `shell_write` (`sed -i|cat\s*>|tee |>>|>\s*[\w./-]+\.py`),
  `repro` (`python3? -c|python3? [\w./-]+\.py|python3? -? ?<<`), `search` (`git grep|\bgrep\b|\brg\b|\bfind\b|\bls\b|git ls-files`),
  `shell_read` (`\bcat\b|\bhead\b|\btail\b|sed -n|\bwc\b`), `git` (`git (diff|status|log|show|checkout|stash)`), else `other_cmd`.
- Call number: counts every call in the trace except `submit_patch` and `get_status`. `calls` is the last call number.
- `calls` can be higher than the harness's `tool_calls` (`harness_tool_calls`). The harness does not count garbled calls, and calls refused after the cap are still in the trace. The "why" sentence shows both numbers when they differ.
- Edit: an `edit_file` or `write_file` call with status ok. `first_edit_call` and `last_edit_call` use this.
- Source edit: an `edit_file` with status ok, or a `write_file` over a file the agent read or edited before. A `write_file` to a new file is a scratch script. `first_source_edit_call` uses this.
- `check_after_last_edit`: a `test` or `repro` command ran after the last edit. `test_after_last_edit`: a `test` command ran after the last edit.
- Garbled edit call: an `edit_file` call whose answer contains "mandatory input parameters are not present". `garbled_loop` is true at 3 or more.
- `edit_errors_other`: `edit_file` calls with an error that are not garbled (`old_string` not found, not unique, after the call cap, other).
- Range-less read: `read_file` with neither `start_line` nor `end_line` among its argument names. Truncated read: the answer has `is_truncated: true`.
- `syntax_error_seen`: a `run_command` answer contains SyntaxError, IndentationError or TabError. `py_compile_used`: any command contains `py_compile`.
- `identical_consecutive`: calls with the same tool and the same arguments as the call before (not `submit_patch`, `get_status`).
- `budget_warning_seen`: an answer carries `budget_warning`. `call_after_warning` is the kind of the next call.
- `hit_call_cap`: an answer has `error_type: BudgetExceeded`.
- `submit_empty`: `submit_patch` was called and its last answer has `patch_size` 0.
- `protected_writes`: files of successful `edit_file` or `write_file` calls that the harness's own rule protects (`_is_protected_test_or_config_path`, copied 1:1). Shell writes are not parsed.

**Outcome** (one per task, first match): solved; session timeout, turn cap, call cap (from the harness error text); harness error (any other error text, kept in `harness_error`); call cap (cap reached and `submit_patch` never called); no patch (patch size 0); wrong patch.

**Edited files against gold files**
- Only non-test `.py` files count on both sides. "Test" is the harness's protected rule.
- `file_match` uses the files in `agent_run/patches/<id>.patch`: superset / overlap / disjoint / no edit.
- `file_match_trace` uses the files of successful `edit_file` and `write_file` calls. This is the definition of the earlier measurement.
- The two differ because the patch also holds scratch scripts (`repro.py`) and edits made with `sed -i`. `scratch_only_patch` is true when the patch holds only files the agent created and none of them is a gold file.

**Grading**
- Failed test ids: lines `^(FAILED|ERROR) (\S+)` in the test log; a closed trailing `[...]` is stripped. FAIL_TO_PASS and PASS_TO_PASS are normalised the same way.
- A parametrised test can be in both lists after this. It then counts as a failed target test and as a broken passing test. `failed_p2p_only` is the stricter count (not also a target test).
- Category: no test log; collection-import-syntax error (pytest exit code other than 0 or 1); target tests not fixed only; target tests not fixed + passing tests broken; only passing tests broken; other.
- `first_error_type`, `missing_name` and `fail_kind` are read from the log sections of the failing target tests (of the broken passing tests when no target test fails). The whole log is the fallback (`error_scope` says which).
- `missing_name`: the six patterns of the task (attribute, parameter, import, name), with `in_issue` = the name occurs in the issue text.
- `fail_kind`: missing name; exception not raised ("DID NOT RAISE"); wrong behaviour or value (AssertionError); other error.

**Runtime**: `output_tokens` and `prompt_tokens` from `final_metrics`; `duration_s`; `end_gap_s` = duration minus the last trace event's `elapsed_s`. `hung` is true at 120 s or more (the normal gap is 5 to 8 s). No per-call latency is reported.

**Behaviour measures** (true or false per task; "check" = the `run_command` calls after the last edit)
| Field | Candidate | True when |
|---|---|---|
| `b_check_py_compile` | E1, D1 | a check contains `py_compile` |
| `b_check_existing_test` | C1 | a check runs pytest and names no `.py` file, or names a `.py` file the agent did not create |
| `b_check_3_cases` | C1 | one check holds 3 or more `print(`, `assert` or `def test_`; the text of a script the agent wrote is counted when the check runs it (`check_cases` is the number) |
| `b_sibling_grep` | P1 | a `grep`, `git grep` or `rg` command ran after the first source edit and before the last `submit_patch` |
| `b_test_before_edit` | T2 | before the first source edit: a `read_file` of a test file, or a search or shell read whose command names a test path |

`b_check_3_cases` is a text count, not a run count. Read it as a trend between arms, not as an exact number.

**Failure type** (one per unsolved task, first match): harness error; garbled edit loop; no source edit in the patch; ran out of time before grading; syntax or import error in the patch; missing name that is not in the issue (marked not fixable by instructions); missing name that is in the issue; wrong files edited; some gold files not edited; passing tests broken; expected exception not raised; wrong behaviour or value; other test error.

**"Why" sentence**: built from the fields in a fixed order: outcome and calls; grading cause; files against gold; garbled calls; no check after the last edit; call cap; hung gap.

## 4. Validation (Nov 11, VM, outputs in `tmp/autopsy_test/`)

| Run | Measure | Target | Tool | Match |
|---|---|---|---|---|
| bf5_eval | tasks / solved | 109 / 47 | 109 / 47 | yes |
| bf5_eval | `edit_file` calls / garbled / tasks / most in one task | 293 / 38 / 5 / 19 | 293 / 38 / 5 / 19 | yes |
| bf5_eval | `read_file` calls / range-less / truncated | 710 / 243 / 223 | 710 / 243 / 223 | yes |
| bf5_eval | search commands / with `\| head` | 470 / 9 | 470 / 9 | yes |
| bf5_eval | grading: target only / target + passing / collection / no log | 51 / 6 / 2 / 3 | 51 / 6 / 2 / 3 | yes |
| bf5_train | tasks / solved | 339 / 132 | 339 / 132 | yes |
| bf5_train | `edit_file` calls / garbled / tasks / most in one task | 1,090 / 348 / 36 / 61 | 1,090 / 348 / 36 / 61 | yes |
| bf5_train | `read_file` calls / range-less | 2,260 / 867 | 2,260 / 867 | yes |
| bf5_train | grading: target only / target + passing / collection / no log / passing only | 163 / 20 / 7 / 16 / 1 | 163 / 20 / 7 / 16 / 1 | yes |
| bf5_eval | check after the last edit | 32 of 97 | 32 of 97 with `test_after_last_edit`; 86 of 97 with `check_after_last_edit` | yes, see note 1 |
| bf5_eval | tasks with identical consecutive calls | 11 | 11 | yes |
| bf5_eval | budget warning seen | 54 | 54 | yes |
| bf5_eval | `submit_patch` called / empty patch | 100 / 4 | 100 / 4 | yes |
| bf5_eval | tasks with protected-file writes | 28 | 28 | yes |
| bf5_eval | edited vs gold: superset / overlap / disjoint / no edit (solved) | 72 (41) / 18 (4) / 5 (0) / 14 | 72 (41) / 18 (4) / 5 (0) / 14 (2) with `file_match_trace`; 75 (43) / 17 (4) / 10 (0) / 7 (0) with `file_match` | yes, see note 2 |
| bf5_eval vs v7_eval | solved / wins / losses (`arms_report.py`) | 47 vs 40 / 2 / 9 | 47 vs 40 / 2 / 9 | yes |

Notes
1. The earlier 32 counted only test commands (pytest, unittest) after the last edit. With repro commands as well it is 86 of 97. Both fields are in the record.
2. The earlier numbers used the files of successful edit calls. The task asked for the files in the saved patch, so `file_match` uses the patch and `file_match_trace` reproduces the earlier numbers. The patch gives more "disjoint" because 8 patches hold only scratch scripts (`scratch_only_patch`).
3. Error kinds over both runs (250 unsolved tasks with a log): 117 wrong behaviour or value, 61 missing name (46 not in the issue), 9 exception not raised, 63 other. The plan had 114 / 61 (44) / 10 / 65. The difference is the scope: this tool reads the failing target tests' sections first.
4. Also tested: a run in progress (20 finished tasks plus a half-written line), a missing tasks file, a run on public tasks (`pub022`, no gold data), and `--groups results/lists/dev48.csv`.

## 5. Spot check of "why" sentences against the traces (by hand, bf5_eval)

| Task | Sentence | Checked in the trace, log and patch | Verdict |
|---|---|---|---|
| spacepacketparser_115 | Session timeout after 45 calls (the harness counted 26); no edit call succeeded; 19 garbled edit_file calls (loop). | 45 calls; calls 21-23 and 30-45 are garbled `edit_file` (3 + 16 = 19); no edit with status ok; no patch file | correct |
| operator_1087 | No patch after 30 calls (the harness counted 28); no edit call succeeded; the call cap was reached. | 30 calls plus `submit_patch`; only reads and searches; call 29 answers BudgetExceeded; patch size 0 | correct |
| pvl_102 | Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: ... (AssertionError); 4 test(s) that passed before now fail; the patch edits none of the gold files (gold: pvl/grammar.py); the call cap was reached. | target test `test_utf` fails with `assert 2 == 1`; 4 other test names fail (`test_comments`, `test_units`, `test_parse_error`, `test_broken_labels_LexerError`); patch has `pvl/parser.py` and `repro.py`; gold is `pvl/grammar.py` | correct after a fix (see below) |
| soupsieve_226 | Wrong patch after 30 calls (the harness counted 28); the tests could not be collected (SyntaxError, pytest exit code 2); the patch misses gold file(s) soupsieve/__meta__.py, soupsieve/css_match.py; 1 garbled edit_file call(s); no test or repro ran after the last edit; the call cap was reached. | log: SyntaxError in `css_parser.py` line 946 (a literal `\n` in the edit), exit code 2; patch has `css_parser.py` only; call 23 garbled; last ok edit is call 24, then only reads | correct |
| converter_180 | Wrong patch after 18 calls; 6 target test(s) still fail: the test log reports the missing attribute 'quantities', which is not in the issue text; the patch misses gold file(s) ... | log line 136: `'UsrbinScoring' object has no attribute 'quantities'`; the word is in the gold patch and the test patch, not in the issue; patch has 1 of 3 gold files | correct |
| azurefunctionspythonlibrary_172 | Solved in 29 calls (the harness counted 24); edited azure/functions/decorators/function_app.py; a test or repro ran after the last edit; 5 garbled edit_file call(s) on the way. | calls 12-15 and 18 garbled; source changed with `sed -i`; last edit is `write_file` at call 24, `python3 test_timer_alias.py` at call 25 | correct |

The spot check found one error, now fixed: the error kind was read from the whole test log. For pvl_102 the sentence said "an expected exception is not raised", but that error belongs to the broken passing tests; the target test fails with an AssertionError. The tool now reads the sections of the failing target tests first.

## 6. Limits
- A fix made only with `sed -i` or `cat >` is not an "edit" for the call-based fields. The patch-based `file_match` sees it.
- "Fixable by instructions" is a rule of thumb. Only "missing name that is not in the issue", "harness error" and "not graded" are marked not fixable.
- `duration_s` is wall-clock on the VM and includes grading. It is not comparable with Kaggle's 8 minutes.
