# Run log: bf5_eval

Written by `vm/autopsy.py`. Definitions: `research/raw/13_run_log.md`.

## 1. Headline
- Run: `results/replica/bf5_eval`. Finished tasks: **109**. Solved: **47** (43%).
- Unsolved: 62. 49 wrong patch, 4 no patch, 9 session timeout.
- edit_file calls: 293, of which 38 garbled on 5 tasks (3 tasks with a loop of 3 or more; at most 19 in one task).
- read_file calls: 710, of which 243 without a line range (34%) and 223 truncated.

## 2. Outcomes
Each task has one outcome.
| Outcome | Tasks | Share | Calls per task | Seconds per task |
|---|---|---|---|---|
| solved | 47 | 43% | 17.9 | 1369 |
| wrong patch | 49 | 45% | 19.5 | 1686 |
| no patch | 4 | 4% | 29.0 | 2009 |
| session timeout | 9 | 8% | 11.7 | 4325 |

## 3. Grading of the unsolved tasks
62 tasks are unsolved.
| Grading category | Tasks |
|---|---|
| target tests not fixed only | 51 |
| target tests not fixed + passing tests broken | 6 |
| collection-import-syntax error | 2 |
| no test log | 3 |

Error kind, read from the log sections of the failing target tests (unsolved tasks with a log):
| Kind | Tasks |
|---|---|
| wrong behaviour or value | 28 |
| other error | 18 |
| missing name | 8 |
| exception not raised | 5 |
- Missing names: 8 tasks. In 6 of them the name is not in the issue text.

## 4. Failure types
One type per unsolved task; the first matching rule in this order wins.
| Failure type | Tasks | Fixable by instructions |
|---|---|---|
| garbled edit loop | 1 | yes |
| no source edit in the patch | 14 | yes |
| syntax or import error in the patch | 2 | yes |
| missing name that is not in the issue | 4 | no |
| missing name that is in the issue | 2 | yes |
| wrong files edited | 2 | yes |
| some gold files not edited | 9 | yes |
| expected exception not raised | 3 | yes |
| wrong behaviour or value | 14 | yes |
| other test error | 11 | yes |

- Largest fixable failure type: **wrong behaviour or value**, 14 of 62 unsolved tasks.
- Examples:
  - `operator_1598`: Wrong patch after 13 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file.
  - `temporals_7`: Wrong patch after 28 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file; no test or repro ran after the last edit.
  - `temporals_6`: Wrong patch after 18 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file.

## 5. Rules and behaviours
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

- Call right after the first budget warning (54 tasks): 21 read_file, 7 repro, 6 search, 5 submit_patch, 5 edit_file, 5 write_file, 2 other_cmd, 1 test, 1 shell_read, 1 shell_write.
- submit_patch was called on 100 tasks; on 4 of them the patch was empty.
- Tasks with a write to a protected file: 28.
- Tasks with identical consecutive calls: 11 (42 repeated calls).

## 6. Calls by kind
| Kind | Calls | Per task |
|---|---|---|
| read_file | 710 | 6.5 |
| edit_file | 293 | 2.7 |
| write_file | 137 | 1.3 |
| test | 49 | 0.4 |
| repro | 247 | 2.3 |
| search | 470 | 4.3 |
| shell_read | 15 | 0.1 |
| shell_write | 25 | 0.2 |
| git | 12 | 0.1 |
| other_cmd | 59 | 0.5 |
| submit_patch | 127 | 1.2 |
| get_status | 8 | 0.1 |

- Garbled edit_file calls: 38 on 5 tasks. Other edit_file errors: 34.
- read_file without a line range: 243 of 710. Truncated reads: 223.
- Search commands: 470, of which 9 with `| head`.

## 7. Edited files against the gold patch
Only non-test `.py` files count on both sides.
The patch columns use the files in the saved patch. The call columns use the files of successful `edit_file` and `write_file` calls.
| Edited files | Tasks (patch) | Solved (patch) | Tasks (calls) | Solved (calls) |
|---|---|---|---|---|
| superset | 75 | 43 | 72 | 41 |
| overlap | 17 | 4 | 18 | 4 |
| disjoint | 10 | 0 | 5 | 0 |
| no edit | 7 | 0 | 14 | 2 |
- Patches that hold only scratch files the agent created: 8.

## 8. Solved by task label
| Label | Tasks | Solved | Share |
|---|---|---|---|
| difficulty = 0 | 42 | 25 | 60% |
| difficulty = 1 | 45 | 17 | 38% |
| difficulty = 2 | 19 | 5 | 26% |
| difficulty = 3 | 3 | 0 | 0% |
| test_score = 0 | 57 | 33 | 58% |
| test_score = 1 | 20 | 8 | 40% |
| test_score = 2 | 32 | 6 | 19% |
| issue_score = 0 | 48 | 25 | 52% |
| issue_score = 1 | 41 | 15 | 37% |
| issue_score = 2 | 20 | 7 | 35% |

## 9. Runtime
| Per task | Mean | Median | Total |
|---|---|---|---|
| Duration, seconds | 1779 | 1430 | 193905 (53.9 h) |
| Calls (without submit_patch, get_status) | 18.5 | 18 | 2017 |
| Output tokens | 5414 | 5373 | 590145 |
| Prompt tokens | 179588 | 165041 | 19575110 |

- Tasks that reached the call cap: 14. Tasks that saw the budget warning: 54.
- Hung tasks (at least 120 s between the last trace event and the end): 8: craystack_16 (4160 s), numpydoc_429 (3158 s), deck_13 (4033 s), confuse_133 (2838 s), visvalingamwyatt_6 (3758 s).

## 10. Every task
Unsolved tasks first, in run order.
| Task | Outcome | Failure type | Calls | Why |
|---|---|---|---|---|
| operator_1598 | wrong patch | wrong behaviour or value | 13 | Wrong patch after 13 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| operator_1562 | wrong patch | some gold files not edited | 23 | Wrong patch after 23 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch misses gold file(s) docs/custom_conf.py. |
| softlayerpython_2203 | wrong patch | some gold files not edited | 16 | Wrong patch after 16 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch misses gold file(s) SoftLayer/fixtures/SoftLayer_Billing_Invoice.py, SoftLayer/transports/xmlrpc.py. |
| spacepacketparser_115 | session timeout | garbled edit loop | 45 | Session timeout after 45 calls (the harness counted 26); no edit call succeeded; 19 garbled edit_file calls (loop). |
| temporals_7 | wrong patch | wrong behaviour or value | 28 | Wrong patch after 28 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file; no test or repro ran after the last edit. |
| temporals_6 | wrong patch | wrong behaviour or value | 18 | Wrong patch after 18 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| ar_17 | wrong patch | wrong behaviour or value | 10 | Wrong patch after 10 calls; 4 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| spacepacketparser_63 | no patch | no source edit in the patch | 29 | No patch after 29 calls (the harness counted 28); no edit call succeeded; the call cap was reached. |
| crosstl_98 | wrong patch | other test error | 27 | Wrong patch after 27 calls; 1 target test(s) still fail: first error SyntaxError; the patch edits every gold file. |
| crosstl_97 | wrong patch | other test error | 22 | Wrong patch after 22 calls; 1 target test(s) still fail: first error SyntaxError; the patch edits every gold file; no test or repro ran after the last edit. |
| crosstl_96 | wrong patch | some gold files not edited | 27 | Wrong patch after 27 calls; 1 target test(s) still fail: first error SyntaxError; the patch misses gold file(s) setup.py; no test or repro ran after the last edit. |
| crosstl_63 | wrong patch | other test error | 22 | Wrong patch after 22 calls (the harness counted 15); 1 target test(s) still fail: first error SyntaxError; the patch edits every gold file. |
| altchalibpy_2 | wrong patch | other test error | 16 | Wrong patch after 16 calls; 1 target test(s) still fail: first error ValueError; the patch edits every gold file. |
| arrayapistrict_42 | wrong patch | expected exception not raised | 28 | Wrong patch after 28 calls; 1 target test(s) still fail: an expected exception is not raised; 2 test(s) that passed before now fail; the patch edits every gold file. |
| text2num_113 | wrong patch | some gold files not edited | 18 | Wrong patch after 18 calls; 1 target test(s) still fail: first error ValueError; the patch misses gold file(s) text_to_num/lang/english.py. |
| ennemi_120 | wrong patch | some gold files not edited | 8 | Wrong patch after 8 calls; 2 target test(s) still fail: first error ValueError; the patch misses gold file(s) ennemi/_driver.py, ennemi/_entropy_estimators.py. |
| converter_180 | wrong patch | missing name that is not in the issue | 18 | Wrong patch after 18 calls; 6 target test(s) still fail: the test log reports the missing attribute 'quantities', which is not in the issue text; the patch misses gold file(s) converter/fluka/cards/scoring_card.py, converter/fluka/input.py. |
| operator_1087 | no patch | no source edit in the patch | 30 | No patch after 30 calls (the harness counted 28); no edit call succeeded; the call cap was reached. |
| operator_1057 | wrong patch | other test error | 10 | Wrong patch after 10 calls; 2 target test(s) still fail: first error OSError; 12 test(s) that passed before now fail; the patch edits every gold file. |
| dissectcstruct_43 | wrong patch | wrong behaviour or value | 27 | Wrong patch after 27 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| operator_949 | wrong patch | other test error | 18 | Wrong patch after 18 calls; 1 target test(s) still fail: first error RuntimeError; the patch edits every gold file. |
| craystack_16 | session timeout | no source edit in the patch | 2 | Session timeout after 2 calls; 1 target test(s) still fail: first error ValueError; the patch holds only scratch files the agent created (reproduce_bug.py); 4160 s passed between the last trace event and the end. |
| djangoenviron_468 | wrong patch | expected exception not raised | 19 | Wrong patch after 19 calls; 3 target test(s) still fail: an expected exception is not raised; the patch edits every gold file. |
| mousebender_79 | wrong patch | other test error | 24 | Wrong patch after 24 calls; 1 target test(s) still fail: first error KeyError; the patch edits every gold file; no test or repro ran after the last edit. |
| lapixdl_43 | wrong patch | wrong files edited | 9 | Wrong patch after 9 calls; 1 target test(s) still fail: an expected exception is not raised; the patch edits none of the gold files (gold: lapixdl/formats/annotation.py). |
| numpydoc_429 | session timeout | no source edit in the patch | 19 | Session timeout after 19 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (reproduce_issue.py); 3158 s passed between the last trace event and the end. |
| sqlparse_676 | wrong patch | no source edit in the patch | 29 | Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (debug_parse.py, debug_stages.py); the call cap was reached. |
| deck_13 | session timeout | no source edit in the patch | 8 | Session timeout after 8 calls; the only edits were to scratch or protected files; 4033 s passed between the last trace event and the end. |
| faker_1630 | wrong patch | some gold files not edited | 29 | Wrong patch after 29 calls (the harness counted 28); 5 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch misses gold file(s) faker/proxy.py; no test or repro ran after the last edit; the call cap was reached. |
| pvl_102 | wrong patch | wrong files edited | 29 | Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); 4 test(s) that passed before now fail; the patch edits none of the gold files (gold: pvl/grammar.py); the call cap was reached. |
| featureengine_339 | wrong patch | some gold files not edited | 9 | Wrong patch after 9 calls; 2 target test(s) still fail: an expected exception is not raised; the patch misses gold file(s) feature_engine/selection/target_mean_selection.py. |
| dynamicyaml_18 | wrong patch | wrong behaviour or value | 14 | Wrong patch after 14 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| pythontabulate_152 | wrong patch | no source edit in the patch | 29 | Wrong patch after 29 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (repro.py); the call cap was reached. |
| soupsieve_226 | wrong patch | syntax or import error in the patch | 30 | Wrong patch after 30 calls (the harness counted 28); the tests could not be collected (SyntaxError, pytest exit code 2); the patch misses gold file(s) soupsieve/__meta__.py, soupsieve/css_match.py; 1 garbled edit_file call(s); no test or repro ran after the last edit; the call cap was reached. |
| typedconfig_8 | wrong patch | wrong behaviour or value | 12 | Wrong patch after 12 calls; 4 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| ciexec_29 | wrong patch | missing name that is not in the issue | 15 | Wrong patch after 15 calls; 1 target test(s) still fail: the test log reports the missing attribute 'ninja_multi_generator', which is not in the issue text; the patch edits every gold file. |
| operator_567 | no patch | no source edit in the patch | 28 | No patch after 28 calls; no edit call succeeded. |
| operator_556 | wrong patch | other test error | 10 | Wrong patch after 10 calls; 2 target test(s) still fail: first error ModelError; the patch edits every gold file. |
| confuse_133 | session timeout | missing name that is in the issue | 11 | Session timeout after 11 calls; 5 target test(s) still fail: the test log reports the missing attribute 'first', which is in the issue text; the patch misses gold file(s) confuse/core.py; 2838 s passed between the last trace event and the end. |
| pygamemenu_324 | wrong patch | some gold files not edited | 28 | Wrong patch after 28 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch misses gold file(s) pygame_menu/_widgetmanager.py, pygame_menu/version.py. |
| pendulum_540 | wrong patch | wrong behaviour or value | 19 | Wrong patch after 19 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| bootpeg_13 | wrong patch | syntax or import error in the patch | 28 | Wrong patch after 28 calls; the tests could not be collected (bootpeg, pytest exit code 2); the patch edits every gold file. |
| pvl_85 | wrong patch | missing name that is not in the issue | 26 | Wrong patch after 26 calls; 2 target test(s) still fail: the test log reports the missing parameter 'symbol_single_quote', which is not in the issue text; the patch edits every gold file; no test or repro ran after the last edit. |
| visvalingamwyatt_6 | session timeout | no source edit in the patch | 3 | Session timeout after 3 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (reproduce_bug.py); 3758 s passed between the last trace event and the end. |
| pypopulation_16 | wrong patch | other test error | 11 | Wrong patch after 11 calls; 3 target test(s) still fail: first error AttributeError; the patch edits every gold file. |
| sosw_216 | wrong patch | other test error | 15 | Wrong patch after 15 calls; 1 target test(s) still fail: first error TypeError; the patch edits every gold file. |
| text2digits_32 | session timeout | no source edit in the patch | 5 | Session timeout after 5 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (reproduce_issue.py); 3825 s passed between the last trace event and the end. |
| ulid_455 | wrong patch | wrong behaviour or value | 12 | Wrong patch after 12 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| dynamicyaml_6 | wrong patch | some gold files not edited | 28 | Wrong patch after 28 calls; 1 target test(s) still fail: first error RecursionError; 11 test(s) that passed before now fail; the patch misses gold file(s) dynamic_yaml/__init__.py. |
| sasdocs_44 | wrong patch | wrong behaviour or value | 30 | Wrong patch after 30 calls (the harness counted 28); 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); 3 test(s) that passed before now fail; the patch edits every gold file; no test or repro ran after the last edit; the call cap was reached. |
| sasdocs_16 | wrong patch | wrong behaviour or value | 27 | Wrong patch after 27 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| sasdocs_5 | wrong patch | wrong behaviour or value | 23 | Wrong patch after 23 calls; 1 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| faker_1049 | session timeout | no source edit in the patch | 9 | Session timeout after 9 calls; 10 target test(s) still fail: the test log reports the missing parameter 'leading_zero', which is not in the issue text; the patch holds only scratch files the agent created (repro.py); 2613 s passed between the last trace event and the end. |
| faker_1046 | session timeout | no source edit in the patch | 3 | Session timeout after 3 calls; no edit call succeeded; 4151 s passed between the last trace event and the end. |
| pyshortcuts_22 | wrong patch | expected exception not raised | 12 | Wrong patch after 12 calls; 1 target test(s) still fail: an expected exception is not raised; the patch edits every gold file. |
| soupsieve_166 | no patch | no source edit in the patch | 29 | No patch after 29 calls (the harness counted 28); no edit call succeeded; the call cap was reached. |
| slurmee_4 | wrong patch | missing name that is not in the issue | 6 | Wrong patch after 6 calls; 3 target test(s) still fail: the test log reports the missing attribute 'get_job_array_info', which is not in the issue text; the patch edits every gold file. |
| dockerexplorer_64 | wrong patch | wrong behaviour or value | 14 | Wrong patch after 14 calls; 2 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| soupsieve_129 | wrong patch | other test error | 12 | Wrong patch after 12 calls; 2 target test(s) still fail: first error SelectorSyntaxError; the patch edits every gold file. |
| soupsieve_127 | wrong patch | missing name that is in the issue | 11 | Wrong patch after 11 calls; 6 target test(s) still fail: the test log reports the missing attribute 'escape', which is in the issue text; the patch misses gold file(s) soupsieve/__init__.py, soupsieve/util.py. |
| faker_924 | wrong patch | wrong behaviour or value | 18 | Wrong patch after 18 calls; 3 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch edits every gold file. |
| soupsieve_96 | wrong patch | no source edit in the patch | 30 | Wrong patch after 30 calls (the harness counted 28); 9 target test(s) still fail: the fix gives a value or behaviour the tests do not accept (AssertionError); the patch holds only scratch files the agent created (reproduce_issue.py); the call cap was reached. |
| softlayerpython_2188 | solved |  | 9 | Solved in 9 calls; edited SoftLayer/CLI/search.py; no test or repro ran after the last edit. |
| crosstl_95 | solved |  | 28 | Solved in 28 calls; edited crosstl/src/translator/parser.py; no test or repro ran after the last edit. |
| dbtpumpkin_28 | solved |  | 11 | Solved in 11 calls; edited dbt_pumpkin/storage.py; a test or repro ran after the last edit. |
| dissectcstruct_88 | solved |  | 17 | Solved in 17 calls; edited dissect/cstruct/expression.py; a test or repro ran after the last edit. |
| sqlparse_764 | solved |  | 11 | Solved in 11 calls; edited sqlparse/keywords.py; a test or repro ran after the last edit. |
| gitbrowse_65 | solved |  | 7 | Solved in 7 calls; edited git_browse/sourcegraph.py; a test or repro ran after the last edit. |
| pysxm_24 | solved |  | 9 | Solved in 9 calls; edited pysxm/pysxm.py; a test or repro ran after the last edit. |
| dissectcstruct_66 | solved |  | 26 | Solved in 26 calls; edited dissect/cstruct/compiler.py, repro.py; a test or repro ran after the last edit. |
| operator_1038 | solved |  | 11 | Solved in 11 calls; edited ops/charm.py; a test or repro ran after the last edit. |
| mashumaro_159 | solved |  | 21 | Solved in 21 calls; edited mashumaro/jsonschema/schema.py; a test or repro ran after the last edit. |
| mypyextensions_47 | solved |  | 9 | Solved in 9 calls; edited mypy_extensions.py; a test or repro ran after the last edit. |
| text2num_96 | solved |  | 14 | Solved in 14 calls; edited text_to_num/parsers.py; a test or repro ran after the last edit. |
| edk2pytoollibrary_379 | solved |  | 29 | Solved in 29 calls (the harness counted 28); edited edk2toollib/log/ansi_handler.py, repro.py; a test or repro ran after the last edit. |
| edk2pytoollibrary_365 | solved |  | 17 | Solved in 17 calls; edited edk2toollib/uefi/edk2/parsers/dec_parser.py; a test or repro ran after the last edit. |
| dynamicyaml_27 | solved |  | 14 | Solved in 14 calls; edited dynamic_yaml/yaml_wrappers.py; a test or repro ran after the last edit. |
| azurefunctionspythonlibrary_172 | solved |  | 29 | Solved in 29 calls (the harness counted 24); edited azure/functions/decorators/function_app.py; a test or repro ran after the last edit; 5 garbled edit_file call(s) on the way. |
| typinginspect_94 | solved |  | 25 | Solved in 25 calls; edited typing_inspect.py; a test or repro ran after the last edit. |
| pandasdataclasses_120 | solved |  | 28 | Solved in 28 calls; edited pandas_dataclasses/core/typing.py; a test or repro ran after the last edit. |
| bigo_44 | solved |  | 9 | Solved in 9 calls; edited big_o/complexities.py, reproduce_bug.py; a test or repro ran after the last edit. |
| text2num_77 | solved |  | 14 | Solved in 14 calls; edited text_to_num/lang/spanish.py; a test or repro ran after the last edit. |
| auth0python_354 | solved |  | 16 | Solved in 16 calls; edited auth0/v3/management/auth0.py; a test or repro ran after the last edit. |
| sqlparse_664 | solved |  | 31 | Solved in 31 calls (the harness counted 19); edited sqlparse/keywords.py; no test or repro ran after the last edit; 12 garbled edit_file call(s) on the way. |
| operator_702 | solved |  | 30 | Solved in 30 calls (the harness counted 28); edited ops/model.py; a test or repro ran after the last edit. |
| soupsieve_234 | solved |  | 15 | Solved in 15 calls; edited soupsieve/css_parser.py; a test or repro ran after the last edit. |
| pythontabulate_139 | solved |  | 21 | Solved in 21 calls; edited tabulate.py; a test or repro ran after the last edit. |
| sqlparse_633 | solved |  | 25 | Solved in 25 calls; edited sqlparse/sql.py; a test or repro ran after the last edit. |
| pygamemenu_357 | solved |  | 25 | Solved in 25 calls; edited pygame_menu/widgets/widget/rangeslider.py; a test or repro ran after the last edit. |
| binpacking_16 | solved |  | 11 | Solved in 11 calls; edited binpacking/to_constant_volume.py; a test or repro ran after the last edit. |
| operator_507 | solved |  | 13 | Solved in 13 calls; edited ops/model.py; a test or repro ran after the last edit. |
| slpp_32 | solved |  | 12 | Solved in 12 calls; edited slpp.py; a test or repro ran after the last edit. |
| msgpacknumpy_43 | solved |  | 23 | Solved in 23 calls; edited msgpack_numpy.py; a test or repro ran after the last edit. |
| pythontabulate_79 | solved |  | 26 | Solved in 26 calls; edited tabulate.py; a test or repro ran after the last edit. |
| numpydoc_283 | solved |  | 23 | Solved in 23 calls; edited numpydoc/docscrape.py; a test or repro ran after the last edit. |
| synthimpute_33 | solved |  | 8 | Solved in 8 calls; edited synthimpute/rf_impute.py; a test or repro ran after the last edit. |
| binpacking_12 | solved |  | 15 | Solved in 15 calls; edited binpacking/to_constant_bin_number.py, binpacking/to_constant_volume.py; a test or repro ran after the last edit. |
| junkie_4 | solved |  | 11 | Solved in 11 calls (the harness counted 10); edited junkie/core_context.py; a test or repro ran after the last edit; 1 garbled edit_file call(s) on the way. |
| privacypanda_23 | solved |  | 7 | Solved in 7 calls; edited privacypanda/addresses.py; a test or repro ran after the last edit. |
| uroboros_41 | solved |  | 14 | Solved in 14 calls (the harness counted 8); edited uroboros/option.py; a test or repro ran after the last edit. |
| uroboros_34 | solved |  | 29 | Solved in 29 calls (the harness counted 28); edited reproduce_issue.py, uroboros/command.py; no test or repro ran after the last edit. |
| uroboros_29 | solved |  | 9 | Solved in 9 calls; edited uroboros/command.py; a test or repro ran after the last edit. |
| apigwsgi_80 | solved |  | 11 | Solved in 11 calls; edited apig_wsgi.py; a test or repro ran after the last edit. |
| soupsieve_131 | solved |  | 20 | Solved in 20 calls; edited soupsieve/__init__.py, soupsieve/css_match.py; a test or repro ran after the last edit. |
| dequindre_52 | solved |  | 27 | Solved in 27 calls; edited dequindre/__init__.py; a test or repro ran after the last edit. |
| soupsieve_88 | solved |  | 29 | Solved in 29 calls (the harness counted 28); edited debug_xml.py, repro.py; a test or repro ran after the last edit. |
| soupsieve_80 | solved |  | 10 | Solved in 10 calls; edited soupsieve/css_parser.py; a test or repro ran after the last edit. |
| soupsieve_71 | solved |  | 28 | Solved in 28 calls; edited reproduce_pickle.py, soupsieve/css_types.py; a test or repro ran after the last edit. |
| pipelib_27 | solved |  | 12 | Solved in 12 calls; edited examples/serialize_pipeline.py, pipelib/core.py; a test or repro ran after the last edit. |
