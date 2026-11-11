# Judge: why the Budget-Fit V5 fixes failed (bf5_eval, 62 failed tasks)

Judged from `judge_input.jsonl` only (issue, agent patch, gold patch, failing tests). One label per task. "(cut)" = the decisive part of a patch was cut, so the label is a best guess.

## 1. Summary

| Label | All tasks (62) | Hidden-like tasks (27) |
|---|---|---|
| A too narrow | 8 | 5 |
| B wrong idea | 10 | 5 |
| C missed a second place | 6 | 2 |
| D wrong place | 1 | 0 |
| E name not in the issue | 8 | 4 |
| F name in the issue | 0 | 0 |
| G no real fix | 15 | 4 |
| H near miss | 6 | 4 |
| I task problem | 8 | 3 |

Hidden-like = `test_score` 0 or 1 AND `difficulty` 1 or more.

| Would have helped | All tasks (62) | Hidden-like tasks (27) |
|---|---|---|
| C1 | 8 | 2 |
| P1 | 2 | 1 |
| T2 | 3 | 3 |
| E1 | 5 | 1 |
| none | 44 | 20 |

## 2. What the counts say

Instructions cannot fix most of these failures: 44 of 62 tasks (20 of the 27 hidden-like tasks) get "none". 16 tasks (E + I) need a name, a default value or a behaviour that the issue never states, and 15 tasks (G) have no fix at all: 8 of those hit the 8-minute timeout, 5 of them after fewer than 10 calls, so that is a speed problem and not a prompt problem.

C1 is the best single line to try next (8 tasks: fixes that were too narrow, or that the existing tests or the issue example would have shown to be wrong), but it helps on only 2 hidden-like tasks. T2 helps on 3 tasks (all hidden-like) and P1 on 2, so on hidden-like tasks no line is worth more than 2 or 3 tasks of 27, which is inside the noise of the paired eval.

E1 (5 tasks) is an upper bound: the record shows the budget ran out, but only one task (sqlparse_676) shows garbled writes. The larger gain is outside the instruction text: time per call (8 timeouts) and call budget (7 tasks ended at 28 calls with no fix).

## 3. One row per task

| id | difficulty | test_score | label | would have helped | evidence |
|---|---|---|---|---|---|
| operator_1598 | 1 | 2 | E | none | Agent loads `charm-user` with default None; gold and test need the default `root`, which the issue does not state. |
| operator_1562 | 2 | 2 | B | none | Agent only catches NoSnapshotError in reemit; the test still sees the deferring observer run twice, so the real cause is elsewhere (cut). |
| softlayerpython_2203 | 0 | 2 | I | none | Agent sums the children like the issue asks; the test also needs a new extra parent row in `--details` output, which the issue does not ask for. |
| spacepacketparser_115 | 2 | 2 | G | none | No source change and timeout; gold adds `combine_segmented_packets` and `secondary_header_bytes` parameters that the issue does not name. |
| temporals_7 | 1 | 0 | H | T2 | Agent uses `<=` for date and DatePeriod; gold uses strict `<` there, the same rule the existing DatePeriod methods and tests already show. |
| temporals_6 | 1 | 0 | H | none | Agent uses `<=` on the shared boundary date; gold uses strict `<` (same date counts as overlap), which the issue does not say. |
| ar_17 | 1 | 0 | A | none | Agent applied the issue's own line (`find(b"\n")`); gold stops at `\x00` or `/`, and the tests use a Windows archive with `\x00` separated names. |
| spacepacketparser_63 | 2 | 2 | G | none | No source change after 28 calls; gold is a large refactor of `PacketData.read` into new methods like `read_as_bytes`. |
| crosstl_98 | 1 | 2 | I | none | Agent added ASSIGN_AND as asked; the test also needs ASSIGN_OR, ASSIGN_XOR and ASSIGN_MOD, which the issue does not ask for. |
| crosstl_97 | 2 | 1 | I | none | Agent added ASSIGN_SHIFT_LEFT in lexer, parser and codegen; the test fails on the DOUBLE and UINT types, which are not in the issue. |
| crosstl_96 | 2 | 2 | I | none | Agent added DOUBLE everywhere; the test fails on the UINT token, which the issue does not mention. |
| crosstl_63 | 1 | 1 | I | none | Agent added BITWISE_AND; the test also needs the OR, XOR, NOT and shift tokens, which the issue does not ask for. |
| altchalibpy_2 | 0 | 2 | I | none | Agent fixed the list-to-int crash in `extract_params`; the test needs a malformed `expires` value to return False, which the issue does not mention. |
| arrayapistrict_42 | 0 | 0 | D | C1 | Agent changed IndexError to TypeError inside `_validate_index` (breaks existing tests); gold adds `Array.__iter__` that raises TypeError. |
| text2num_113 | 0 | 1 | A | C1 | Agent removed two guards so the issue example parses; gold makes "hundred" a real multiplier, and the test input "sixty hundred" still fails. |
| ennemi_120 | 0 | 2 | C | C1 | Agent changed only `setup.py` and CI; gold also changes library code for NumPy 2, and two driver tests fail with "data must be finite" (cut). |
| converter_180 | 2 | 1 | B | none | Agent added a simple `AuxScore` dataclass in the parser with guessed JSON keys; gold builds USRBIN and AUXSCORE cards with filters in `scoring_card.py`. |
| operator_1087 | 1 | 2 | G | E1 | No source change after 28 calls; gold is a small change that prints uncaught exceptions to stderr when an action runs. |
| operator_1057 | 2 | 2 | A | none | Agent calls `os.chmod` after connect, which crashes for `:memory:`; gold skips `:memory:` and raises RuntimeError on OSError, which the issue does not state. |
| dissectcstruct_43 | 0 | 1 | C | P1 | Agent's newline-keeping replacer matches gold; gold also adds `+ 1` in `TokenParser._lineno`, which the agent did not touch. |
| operator_949 | 0 | 1 | C | C1 | Agent's `local_list` fix matches gold; gold also fixes the prefix check for prefix `.` in the path-building helper, so relative paths still fail. |
| craystack_16 | 1 | 1 | G | none | Only a repro file after 2 calls and a timeout; gold rewrites renormalization in `push_with_finer_prec` and `pop_with_finer_prec`. |
| djangoenviron_468 | 2 | 2 | E | none | Agent expands `${VAR}` once inside `read_env`; tests need `$VAR` without braces, expansion at lookup time and an error on recursion, none stated in the issue. |
| mousebender_79 | 1 | 1 | I | none | Agent switched lint config to Ruff as asked; the failing test is about a missing `href` in `simple.py` parsing, which the issue does not mention. |
| lapixdl_43 | 1 | 2 | I | none | Agent added the `union_area == 0` guard from the issue; the test needs `BBox.__post_init__` to raise ValueError, which the issue does not mention. |
| numpydoc_429 | 1 | 0 | G | none | Only a repro file, then timeout; gold changes the split from `" :"` to `" : "` in the parameter list parser. |
| sqlparse_676 | 0 | 0 | G | E1 | Only debug scripts (some with garbled `\"` quotes) after 28 calls; gold adds a `valid_next` check in `group_tzcasts`. |
| deck_13 | 0 | 0 | G | none | No source change after 8 calls and a timeout; gold adds an ace-low straight check in `get_poker_hand`. |
| faker_1630 | 2 | 0 | B | none | Agent added an unused `Generator.now()` method; gold re-seeds the random state before choosing the locale factory in `proxy.py`. |
| pvl_102 | 1 | 2 | B | none | Agent removed the parser error so bad input is accepted silently; gold makes the NULL character a reserved character in `OmniGrammar`. |
| featureengine_339 | 1 | 0 | A | none | Agent runs the type check for a single name; gold also treats `None` and an empty list differently (ValueError for an empty list), and tests still see no error (cut). |
| dynamicyaml_18 | 1 | 0 | B | C1 | Agent added a new `resolve()` method; gold adds `YamlList.__iter__`, so plain iteration (the issue's own example) still gives unresolved strings. |
| pythontabulate_152 | 0 | 2 | G | E1 | Only a repro file after 28 calls; gold makes `_afterpoint` accept numbers with thousands separators. |
| soupsieve_226 | 3 | 2 | B | none | Agent's edit has literal `\n` text and breaks the file with a SyntaxError; gold forgives empty selector slots, a different rule from the agent's `:not(*)` idea. |
| typedconfig_8 | 2 | 2 | E | none | Agent added a `post_read()` hook with no return value; tests need `post_read_hook()` that returns a dict of updates, a name the issue does not give. |
| ciexec_29 | 1 | 0 | E | none | Agent put "Ninja Multi-Config" into `other_generators`; the test needs a new class attribute `ninja_multi_generator`, which the issue does not name. |
| operator_567 | 2 | 2 | G | none | No source change after 28 calls; gold adds `Container.is_ready()` and a context manager class. |
| operator_556 | 0 | 2 | C | none | Agent raises ModelError in `start()` only; gold raises TypeError in both `start()` and `stop()`, and the issue does not state the exception type. |
| confuse_133 | 1 | 2 | B | none | Agent's check in `Sequence.value` raises an error and catches it itself, so nothing changes; gold adds a new `ConfigView.sequence()` method. |
| pygamemenu_324 | 1 | 0 | H | none | Agent's property setter keeps the effect colour in sync but converts the colour to 4 values `(241,125,1,255)`; the test expects the 3-value tuple unchanged. |
| pendulum_540 | 3 | 1 | E | none | Agent wrote its own Czech strings ("před několik sekund", "Po"); tests need the exact gold strings ("pár vteřin zpět", "po"). |
| bootpeg_13 | 1 | 2 | H | C1 | Agent's capture check walks into `Reference` clauses and crashes with UnboundReference when the grammar loads; gold stops at references. |
| pvl_85 | 1 | 2 | E | none | Agent added a new `PDS3VariantEncoder` class as the issue suggests; tests need `symbol_single_quote` and `time_trailing_z` arguments on `PDSLabelEncoder`. |
| visvalingamwyatt_6 | 0 | 0 | G | none | Only a repro file after 3 calls and a timeout; gold passes `closed=True` for Polygon and MultiPolygon rings. |
| pypopulation_16 | 2 | 1 | E | none | Agent's logic equals gold but names the module maps `_ALPHA_2`/`_ALPHA_3`; tests patch `_a2_map`/`_a3_map`. |
| sosw_216 | 1 | 2 | H | none | Agent raises TypeError for the wrong DynamoDB type; gold raises ValueError, and the issue only says "informative exception". |
| text2digits_32 | 0 | 0 | G | none | Only a repro file after 5 calls and a timeout; gold changes `has_large_scale` to match exact scale values. |
| ulid_455 | 1 | 0 | A | none | Agent added `__deepcopy__` only; gold adds `__getstate__` (returns the string) and `__setstate__`, so pickle still fails and the state format is not in the issue. |
| dynamicyaml_6 | 1 | 0 | B | none | Agent moved the classes to UserDict/UserList and every test hits RecursionError; gold rewrites them on abstract collection base classes. |
| sasdocs_44 | 2 | 0 | B | T2 | Agent replaced the proc parser by a regex over a new `body` field, which changes the object and drops inputs; gold only adds `sep_by` to the `outputs` parser. |
| sasdocs_16 | 3 | 0 | H | none | Agent makes `inputs` optional like gold, but its header regex also stops at `run`, so the text lands in `header`; gold leaves `header` None and the text in `body`. |
| sasdocs_5 | 1 | 0 | A | none | Agent builds `about` in `rebuild_macros` and stops at the first comment; gold builds it in `__attrs_post_init__` after newline removal, with default "No docstring found." (not in the issue). |
| faker_1049 | 0 | 2 | G | none | Only a repro file after 9 calls and a timeout; gold is cut and the failing tests also cover unrelated barcode functions. |
| faker_1046 | 1 | 1 | G | none | No source change after 3 calls and a timeout; gold is a one-line change `reg_pub[:-1]` in `_registrant_publication`. |
| pyshortcuts_22 | 0 | 2 | A | C1 | Agent rejects only `None`; gold rejects any non-string or empty string, and the test passes an empty string. |
| soupsieve_166 | 1 | 0 | G | E1 | No source change after 28 calls; gold adds `match_placeholder_shown` that checks the element text. |
| slurmee_4 | 1 | 0 | E | none | Agent added `get_array_job_id`, `get_array_task_id` and `get_array_task_bounds`; tests need one function `get_job_array_info`, a name not in the issue. |
| dockerexplorer_64 | 0 | 0 | B | none | Agent changed the mount device from `overlay` to `none`; gold keeps the device and removes the double quotes around the `lowerdir` value. |
| soupsieve_129 | 1 | 0 | C | P1 | Agent changed `RE_CSS_ESC` and `css_unescape`; gold also changes the `CSS_ESCAPES` pattern used by identifiers, so `span.foo\` is still a syntax error. |
| soupsieve_127 | 1 | 0 | C | T2 | Agent wrote `css_escape` in `css_parser.py`; gold also exports it as `soupsieve.escape` in `__init__.py`, and the tests call `sv.escape`. |
| faker_924 | 2 | 1 | A | C1 | Agent uses the limits only when both `min_value` and `max_value` are given; gold handles one alone and raises ValueError when min is greater than max. |
| soupsieve_96 | 0 | 2 | G | E1 | Only a repro file after 28 calls; gold makes tag name matching case sensitive for XML documents. |
