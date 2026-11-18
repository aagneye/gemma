# Clock ledger

- Runs: `results/replica/cf1_base_a`, `results/replica/cf1_base_b`, `results/replica/cf2_base_a`, `results/replica/cf2_base_b`.
- Tasks counted: **77** (finished in every pass). Games: 308.
- Solved: cf1_base_a 41, cf1_base_b 44, cf2_base_a 44, cf2_base_b 44 (mean 43.25 per pass).
- A minute is Kaggle-equivalent: run seconds / 9 / 60. A move is a tool call the harness counts.
- Loss types, first match: out of time (session timeout or turn cap); blank answer (empty patch, only scratch files, or no source file in the patch); wrong fix on the last moves (call cap reached, wrong patch); wrong fix inside the budget (the rest).

## 1. How the games end
| Outcome | cf1_base_a | cf1_base_b | cf2_base_a | cf2_base_b | Mean per pass | Of these, on tasks solved in some passes only (per pass) |
|---|---|---|---|---|---|---|
| Solved | 41 | 44 | 44 | 44 | 43.25 | 9.25 |
| Wrong fix inside the budget | 29 | 25 | 24 | 26 | 26.00 | 5.25 |
| Blank answer | 2 | 5 | 2 | 4 | 3.25 | 1.50 |
| Out of time | 4 | 2 | 4 | 0 | 2.50 | 1.50 |
| Wrong fix on the last moves | 1 | 1 | 3 | 3 | 2.00 | 0.50 |

- Clock-or-move losses: **7.75 of 33.75 losses per pass** (23%).
- On tasks solved in some passes only: 3.50 clock-or-move losses per pass. That is the most that better clock play could win back.
- Games on those tasks that stay inside the budget are solved 37 of 58 times (64%). At that rate the clock-or-move losses are worth about +2.2 solved per pass.

## 2. Wins are quick

**By minutes used**
| Minutes | Games | Solved | Share solved |
|---|---|---|---|
| under 3 | 179 | 125 | 70% |
| 3 to 5 | 82 | 36 | 44% |
| 5 to 7 | 31 | 10 | 32% |
| 7 or more | 16 | 2 | 12% |

**By moves used**
| Moves | Games | Solved | Share solved |
|---|---|---|---|
| up to 10 | 55 | 39 | 71% |
| 11-15 | 70 | 51 | 73% |
| 16-20 | 57 | 33 | 58% |
| 21-27 | 63 | 24 | 38% |
| 28 (the most any game used) | 63 | 26 | 41% |

**By the move number of the first source edit**
| First source edit at move | Games | Solved | Share solved |
|---|---|---|---|
| 1-6 | 101 | 72 | 71% |
| 7-12 | 91 | 53 | 58% |
| 13-18 | 50 | 30 | 60% |
| 19 or later | 42 | 14 | 33% |
| no source edit by a tool call | 24 | 4 | 17% |

**A typical game (medians)**
| Games | Count | Moves | Seconds | Written tokens | First source edit at move |
|---|---|---|---|---|---|
| Solved | 173 | 15 | 125 | 4930 | 7 |
| Not solved | 135 | 22 | 215 | 7756 | 10 |

## 3. The clock
- Share of the game time: model steps 99%, tools 0%.
- Fit on 6682 model steps: seconds per step = 1.9 - 0.07 per 1,000 prompt tokens + 2.24 per 100 written tokens. One written token costs about 22 ms.

**Written tokens per model step**
| Games | Steps | Median | 90th percentile | 99th percentile | Largest | Steps of 1,000+ (their share of all tokens) | Steps of 2,000+ (their share of all tokens) |
|---|---|---|---|---|---|---|---|
| Solved games | 3443 | 114 | 618 | 2794 | 8192 | 190 (39%) | 57 (20%) |
| Unsolved games | 3239 | 122 | 863 | 4026 | 8192 | 279 (49%) | 88 (26%) |

- Steps that write 4,096 tokens or more (the thinking budget is used up): 50, in 37 games (solved: 17 of 37, 46%).

**By written tokens per game**
| Written tokens | Games | Solved | Share solved |
|---|---|---|---|
| under 4,000 | 75 | 59 | 79% |
| 4,000 to 8,000 | 140 | 85 | 61% |
| 8,000 to 12,000 | 55 | 23 | 42% |
| 12,000 or more | 38 | 6 | 16% |

## 4. What a move costs (model steps with one tool call or none; medians)
| Move | Steps | Written tokens | Seconds | Size of the tool's answer (characters) |
|---|---|---|---|---|
| read a file | 1966 | 76 | 2.4 | 2203 |
| search | 1205 | 97 | 3.0 | 197 |
| edit a file | 931 | 314 | 7.8 | 508 |
| run Python | 871 | 33 | 1.4 | 241 |
| write a file | 454 | 384 | 9.4 | 63 |
| submit | 393 | 36 | 1.3 | 56 |
| text only, no tool call | 300 | 237 | 5.1 | 0 |
| other command | 184 | 132 | 3.1 | 80 |
| run tests | 160 | 58 | 2.2 | 668 |
| edit with the shell | 108 | 374 | 9.9 | 234 |
| git | 40 | 170 | 3.6 | 500 |
| ask the status | 37 | 24 | 0.5 | 297 |
| read with the shell | 33 | 89 | 3.8 | 2541 |

## 5. The budget warning
- Games that saw it: 162 of 308. It first appears at move 18 (median).

| At the first warning | Games | Solved | Share solved |
|---|---|---|---|
| A source edit is already made | 107 | 53 | 50% |
| No source edit yet | 55 | 17 | 31% |

**No source edit yet: the next move**
| Next move | Games | Solved | Share solved |
|---|---|---|---|
| read | 24 | 4 | 17% |
| edit | 14 | 5 | 36% |
| search | 14 | 7 | 50% |
| check | 2 | 1 | 50% |
| submit | 1 | 0 | 0% |

- Of these 55 games, 12 end as a blank answer.

## 6. Across the passes
- Solved in every pass: 34 tasks. In no pass: 25. In some: 18 (7 in 1 of 4, 3 in 2 of 4, 8 in 3 of 4).
- Tasks solved in some passes whose every loss is a clock-or-move loss: 6.
  - `azurefunctionspythonlibrary_172` (solved in 3 of 4): blank answer / solved / solved / solved.
  - `craystack_16` (solved in 1 of 4): out of time / out of time / out of time / solved.
  - `soupsieve_71` (solved in 3 of 4): solved / blank answer / solved / solved.
  - `soupsieve_88` (solved in 2 of 4): solved / blank answer / wrong fix on the last moves / solved.
  - `sqlparse_664` (solved in 3 of 4): out of time / solved / solved / solved.
  - `sqlparse_676` (solved in 1 of 4): solved / blank answer / out of time / blank answer.

## 7. Clock-or-move losses, one line each
- `crosstl_97` (cf1_base_a, solved in 0 of 4 passes): out of time; 21 moves, 8.0 minutes, 15791 written tokens. Session timeout after 43 calls (the harness counted 21); 1 target test(s) still fail: first error SyntaxError; the patch misses gold file(s) crosstl/src/translator/parser.py; 22 garbled edit_file calls (loop); no test or repro ran after the last edit; 283 s passed between the last trace event and the end.
- `craystack_16` (cf1_base_a, solved in 1 of 4 passes): out of time; 7 moves, 8.0 minutes, 14543 written tokens. Session timeout after 7 calls; 1 target test(s) still fail: first error ValueError; the patch holds only scratch files the agent created (reproduce_bug.py); 1224 s passed between the last trace event and the end.
- `azurefunctionspythonlibrary_172` (cf1_base_a, solved in 3 of 4 passes): blank answer; 28 moves, 2.6 minutes, 6063 written tokens. No patch after 30 calls (the harness counted 28); the edits left no patch; no test or repro ran after the last edit; the call cap was reached.
- `sqlparse_664` (cf1_base_a, solved in 3 of 4 passes): out of time; 17 moves, 8.0 minutes, 17848 written tokens. Session timeout after 37 calls (the harness counted 17); no edit call succeeded; 20 garbled edit_file calls (loop); 506 s passed between the last trace event and the end.
- `operator_702` (cf1_base_a, solved in 1 of 4 passes): blank answer; 28 moves, 5.0 minutes, 9690 written tokens. Wrong patch after 29 calls (the harness counted 28); 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (repro.py); the call cap was reached.
- `dynamicyaml_6` (cf1_base_a, solved in 0 of 4 passes): wrong fix on the last moves; 28 moves, 4.1 minutes, 7307 written tokens. Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); 1 test(s) that passed before now fail; the patch misses gold file(s) dynamic_yaml/__init__.py; the call cap was reached.
- `sasdocs_44` (cf1_base_a, solved in 1 of 4 passes): out of time; 23 moves, 8.0 minutes, 14671 written tokens. Session timeout after 23 calls; 1 target test(s) still fail: first error TypeError; 3 test(s) that passed before now fail; the patch edits every gold file; 830 s passed between the last trace event and the end.
- `temporals_6` (cf1_base_b, solved in 0 of 4 passes): wrong fix on the last moves; 28 moves, 4.3 minutes, 8802 written tokens. Wrong patch after 29 calls (the harness counted 28); 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file; the call cap was reached.
- `craystack_16` (cf1_base_b, solved in 1 of 4 passes): out of time; 9 moves, 8.0 minutes, 18078 written tokens. Session timeout after 9 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file; 158 s passed between the last trace event and the end.
- `sqlparse_676` (cf1_base_b, solved in 1 of 4 passes): blank answer; 28 moves, 7.7 minutes, 16382 written tokens. Wrong patch after 28 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (debug_reindent.py, reproduce_issue.py).
- `pygamemenu_324` (cf1_base_b, solved in 0 of 4 passes): blank answer; 28 moves, 3.9 minutes, 4906 written tokens. No patch after 29 calls (the harness counted 28); no edit call succeeded; the call cap was reached.
- `dynamicyaml_6` (cf1_base_b, solved in 0 of 4 passes): out of time; 18 moves, 8.0 minutes, 18280 written tokens. Session timeout after 18 calls; 1 target test(s) still fail: first error RecursionError; 4 test(s) that passed before now fail; the patch misses gold file(s) dynamic_yaml/__init__.py.
- `soupsieve_166` (cf1_base_b, solved in 0 of 4 passes): blank answer; 28 moves, 2.4 minutes, 4668 written tokens. No patch after 30 calls (the harness counted 28); no edit call succeeded; the call cap was reached.
- `soupsieve_88` (cf1_base_b, solved in 2 of 4 passes): blank answer; 28 moves, 1.6 minutes, 5723 written tokens. No patch after 30 calls (the harness counted 28); the only edits were to scratch or protected files; the call cap was reached.
- `soupsieve_71` (cf1_base_b, solved in 3 of 4 passes): blank answer; 28 moves, 1.3 minutes, 5876 written tokens. Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: first error AttributeError; the patch holds only scratch files the agent created (repro.py); no test or repro ran after the last edit; the call cap was reached.
- `craystack_16` (cf2_base_a, solved in 1 of 4 passes): out of time; 14 moves, 8.0 minutes, 18827 written tokens. Session timeout after 14 calls; 1 target test(s) still fail: first error ValueError; the patch holds only scratch files the agent created (repro.py).
- `mousebender_79` (cf2_base_a, solved in 0 of 4 passes): out of time; 15 moves, 8.0 minutes, 16957 written tokens. Session timeout after 33 calls (the harness counted 15); 1 target test(s) still fail: first error KeyError; the patch has no source .py file; 10 garbled edit_file calls (loop); 372 s passed between the last trace event and the end.
- `sqlparse_676` (cf2_base_a, solved in 1 of 4 passes): out of time; 26 moves, 8.0 minutes, 16579 written tokens. Session timeout after 35 calls (the harness counted 26); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (debug_format.py, reproduce_bug.py); 9 garbled edit_file calls (loop).
- `faker_1630` (cf2_base_a, solved in 0 of 4 passes): blank answer; 28 moves, 3.4 minutes, 7263 written tokens. No patch after 29 calls (the harness counted 28); no edit call succeeded; the call cap was reached.
- `pygamemenu_324` (cf2_base_a, solved in 0 of 4 passes): wrong fix on the last moves; 28 moves, 4.1 minutes, 7176 written tokens. Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the test log reports the missing attribute 'selection_color', which is in the issue text; 2 test(s) that passed before now fail; the patch misses gold file(s) pygame_menu/_widgetmanager.py, pygame_menu/version.py; no test or repro ran after the last edit; the call cap was reached.
- `text2digits_32` (cf2_base_a, solved in 0 of 4 passes): out of time; 21 moves, 8.0 minutes, 16316 written tokens. Session timeout after 21 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (reproduce_issue.py).
- `dynamicyaml_6` (cf2_base_a, solved in 0 of 4 passes): wrong fix on the last moves; 28 moves, 4.0 minutes, 9377 written tokens. Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch misses gold file(s) dynamic_yaml/__init__.py; the call cap was reached.
- `soupsieve_166` (cf2_base_a, solved in 0 of 4 passes): blank answer; 28 moves, 3.4 minutes, 6499 written tokens. No patch after 29 calls (the harness counted 28); no edit call succeeded; the call cap was reached.
- `soupsieve_88` (cf2_base_a, solved in 2 of 4 passes): wrong fix on the last moves; 28 moves, 4.6 minutes, 9447 written tokens. Wrong patch after 29 calls (the harness counted 28); 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file; no test or repro ran after the last edit; the call cap was reached.
- `ar_17` (cf2_base_b, solved in 0 of 4 passes): wrong fix on the last moves; 28 moves, 5.4 minutes, 12868 written tokens. Wrong patch after 29 calls (the harness counted 28); 3 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); 1 test(s) that passed before now fail; the patch edits every gold file; the call cap was reached.
- `dissectcstruct_43` (cf2_base_b, solved in 0 of 4 passes): wrong fix on the last moves; 28 moves, 3.4 minutes, 8812 written tokens. Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file; the call cap was reached.
- `sqlparse_676` (cf2_base_b, solved in 1 of 4 passes): blank answer; 28 moves, 4.0 minutes, 7878 written tokens. Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (repro.py, reproduce_bug.py); the call cap was reached.
- `pygamemenu_324` (cf2_base_b, solved in 0 of 4 passes): blank answer; 28 moves, 4.7 minutes, 9121 written tokens. No patch after 29 calls (the harness counted 28); no edit call succeeded; the call cap was reached.
- `soupsieve_166` (cf2_base_b, solved in 0 of 4 passes): blank answer; 28 moves, 2.0 minutes, 4651 written tokens. No patch after 30 calls (the harness counted 28); no edit call succeeded; the call cap was reached.
- `soupsieve_129` (cf2_base_b, solved in 1 of 4 passes): wrong fix on the last moves; 28 moves, 5.0 minutes, 12373 written tokens. Wrong patch after 29 calls (the harness counted 28); 2 target test(s) still fail: first error SelectorSyntaxError; the patch edits every gold file; no test or repro ran after the last edit; the call cap was reached.
- `soupsieve_127` (cf2_base_b, solved in 0 of 4 passes): blank answer; 28 moves, 7.0 minutes, 13496 written tokens. Wrong patch after 28 calls; 6 target test(s) still fail: the test log reports the missing attribute 'escape', which is in the issue text; the patch holds only scratch files the agent created (verify_escape.py).
