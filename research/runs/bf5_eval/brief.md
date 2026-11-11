# Run brief: bf5_eval

## Headline
- Run: `results/replica/bf5_eval`. Finished tasks: **109**. Solved: **47** (43%).
- Unsolved: 62. 49 wrong patch, 4 no patch, 9 session timeout.
- edit_file calls: 293, of which 38 garbled on 5 tasks (3 tasks with a loop of 3 or more; at most 19 in one task).
- read_file calls: 710, of which 243 without a line range (34%) and 223 truncated.

## Outcomes
| Outcome | Tasks | Share | Calls per task | Seconds per task |
|---|---|---|---|---|
| solved | 47 | 43% | 17.9 | 1369 |
| wrong patch | 49 | 45% | 19.5 | 1686 |
| no patch | 4 | 4% | 29.0 | 2009 |
| session timeout | 9 | 8% | 11.7 | 4325 |

## Rule compliance
Solved counts compare the tasks that show the behaviour with the tasks that do not.
| Rule or behaviour | Tasks that show it | Share | Solved with it | Solved without it |
|---|---|---|---|---|
| submit_patch was called | 100 of 109 | 92% | 47 of 100 | 0 of 9 |
| at least one edit call succeeded | 97 of 109 | 89% | 46 of 97 | 1 of 12 |
| first edit by call 12 | 77 of 97 | 79% | 36 of 77 | 10 of 20 |
| a test or repro ran after the last edit | 86 of 97 | 89% | 43 of 86 | 3 of 11 |
| a test command (pytest, unittest) ran after the last edit | 32 of 97 | 33% | 20 of 32 | 26 of 65 |
| every read_file had a line range | 14 of 109 | 13% | 8 of 14 | 39 of 95 |
| no garbled edit_file call | 104 of 109 | 95% | 44 of 104 | 3 of 5 |
| no identical consecutive calls | 98 of 109 | 90% | 38 of 98 | 9 of 11 |
| no write to a protected file | 81 of 109 | 74% | 37 of 81 | 10 of 28 |
| no syntax or indentation error seen | 106 of 109 | 97% | 45 of 106 | 2 of 3 |
| py_compile used | 0 of 109 | 0% | 0 of 0 | 47 of 109 |
| check after the last edit contains py_compile (E1, D1) | 0 of 109 | 0% | 0 of 0 | 47 of 109 |
| check after the last edit runs an existing test file with pytest (C1) | 29 of 109 | 27% | 20 of 29 | 27 of 80 |
| check after the last edit exercises 3 or more cases (C1) | 50 of 109 | 46% | 23 of 50 | 24 of 59 |
| a grep ran between the first source edit and submit (P1) | 26 of 109 | 24% | 12 of 26 | 35 of 83 |
| a test file was read or grepped before the first source edit (T2) | 30 of 109 | 28% | 13 of 30 | 34 of 79 |

## Largest fixable failure type
- Largest fixable failure type: **wrong behaviour or value**, 14 of 62 unsolved tasks.
- Examples:
  - `operator_1598`: Wrong patch after 13 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file.
  - `temporals_7`: Wrong patch after 28 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file; no test or repro ran after the last edit.
  - `temporals_6`: Wrong patch after 18 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file.
- All types: 14 wrong behaviour or value; 14 no source edit in the patch; 11 other test error; 9 some gold files not edited; 4 missing name that is not in the issue (not fixable by instructions); 3 expected exception not raised; 2 wrong files edited; 2 syntax or import error in the patch; 2 missing name that is in the issue; 1 garbled edit loop.

## Runtime
| Per task | Mean | Median | Total |
|---|---|---|---|
| Duration, seconds | 1779 | 1430 | 193905 (53.9 h) |
| Calls (without submit_patch, get_status) | 18.5 | 18 | 2017 |
| Output tokens | 5414 | 5373 | 590145 |
| Prompt tokens | 179588 | 165041 | 19575110 |

- Tasks that reached the call cap: 14. Tasks that saw the budget warning: 54.
- Hung tasks (at least 120 s between the last trace event and the end): 8: craystack_16 (4160 s), numpydoc_429 (3158 s), deck_13 (4033 s), confuse_133 (2838 s), visvalingamwyatt_6 (3758 s).
