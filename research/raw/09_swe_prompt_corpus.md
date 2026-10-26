# 09 — SWE-agent prompt corpus: verbatim excerpts and pattern cards (Day 1, 2026-10-25)

Purpose: the exact instruction text of the scaffolds that work, so that our Gemma bundle borrows wording that has been
measured rather than wording that sounds right. Every excerpt is <= 40 lines, quoted from a read-only clone at a pinned
commit. Each pattern card ends with the measured fact it rests on (ours from `09a_bucket_ceilings.md` / `STATE.md`,
theirs from the papers in `03_swe_agent_literature.md`) and a kill criterion.

Measured facts used throughout (v5single, 53 Kaggle-sound tasks, 2026-10-24): 26 resolved; WRONG_PATCH 10 (ceiling 1),
LOST_EDIT 10 (ceiling 3), NO_EDIT 9 (ceiling 1), TIMEOUT 4 (ceiling 0); 16/53 ran a test (11/16 resolved vs 15/37);
27/53 wasted a call on `write_file` to /tmp; mean 276 s/task. Union of all 31B runs 28/49 vs v5 25/49.

## Sources (read-only shallow clones in the session scratchpad)
| Scaffold | Repo @ commit | Files |
|---|---|---|
| mini-SWE-agent | SWE-agent/mini-swe-agent @ 04d809ce | `src/minisweagent/config/benchmarks/swebench.yaml`, `config/default.yaml`, `config/mini.yaml` (the old `config/extra/` path no longer exists) |
| SWE-agent 1.x | SWE-agent/SWE-agent @ 3ea751c0 | `config/default.yaml` (formerly anthropic_filemap), `tools/edit_anthropic/config.yaml`, `trajectories/demonstrations/function_calling_simple.traj` |
| SWE-agent 0.7 | same | `config/sweagent_0_7/07.yaml`, `tools/windowed_edit_linting/config.yaml` |
| OpenHands CodeAct | All-Hands-AI/OpenHands tag 0.30.1 @ 0e67deee | `openhands/agenthub/codeact_agent/prompts/system_prompt.j2`, `evaluation/benchmarks/swe_bench/run_infer.py`; current wording in OpenHands/software-agent-sdk @ d2ee0cde `openhands-sdk/openhands/sdk/context/prompts/sections/static.py` (the `All-Hands-AI/OpenHands` main branch @ b185939d is now the app monorepo and holds no agent prompts) |
| Anthropic SWE-bench scaffold | anthropic.com/engineering/swe-bench-sonnet (Oct 2024) | per-task prompt template, two tools (bash, str_replace_editor) |
| Aider | Aider-AI/aider @ 5dc9490b | `aider/coders/editblock_prompts.py` |

## 1. mini-SWE-agent (bash only, one action per step, linear history)

### 1.1 `config/default.yaml` system + instance template (excerpt)
```
Your response must contain exactly ONE bash code block with ONE command (or commands connected with && or ||).
Include a THOUGHT section before your command where you explain your reasoning process.
...
## Recommended Workflow
This workflow should be done step-by-step so that you can iterate on your changes and any possible problems.
1. Analyze the codebase by finding and reading relevant files
2. Create a script to reproduce the issue
3. Edit the source code to resolve the issue
4. Verify your fix works by running your script again
5. Test edge cases to ensure your fix is robust
6. Submit your changes and finish your work by issuing the following command: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`.
   Do not combine it with any other command. <important>After this command, you cannot continue working on this task.</important>
## Important Rules
1. Every response must contain exactly one action
2. The action must be enclosed in triple backticks
3. Directory or environment variable changes are not persistent. Every action is executed in a new subshell.
```
It then shows four "Useful command examples": create a file with a quoted heredoc, edit with `sed -i`, view with
`nl -ba filename.py | sed -n '10,20p'`, and "any other command".

### 1.2 `config/benchmarks/swebench.yaml` (the leaderboard config): submission protocol and templates
```
## Submission
When you've completed your work, you MUST submit your changes as a git patch.
Follow these steps IN ORDER, with SEPARATE commands:
Step 1: Create the patch file
Run `git diff -- path/to/file1 path/to/file2 > patch.txt` listing only the source files you modified.
...
Step 2: Verify your patch
Inspect patch.txt to confirm it only contains your intended changes and headers show `--- a/` and `+++ b/` paths.
Step 3: Submit (EXACT command required)
...
<CRITICAL>
- Creating/viewing the patch and submitting it MUST be separate commands (not combined with &&).
- If you modify patch.txt after verifying, you SHOULD verify again before submitting.
- You CANNOT continue working (reading, editing, testing) in any way on this task after submitting.
</CRITICAL>
```
Observation template: output over 10,000 chars is replaced by a warning plus head 5,000 / tail 5,000 ("Please try a
different command that produces less output ... use head, tail or sed ... a more selective search pattern"). Format
error template (truncation case): "Your previous response reached the output token limit ... before you produced a
tool call, so it was cut off. Respond more concisely and finish with exactly one bash tool call. If you need to think
more, do so briefly." Budgets: `step_limit: 250`, `cost_limit: 3`, command `timeout: 60`.

**Pattern card M1 — one action per response, thought first.** Mechanism: a fixed micro-format (THOUGHT, one command)
removes format decisions and makes every turn observable. Bucket: E4B text-stop / nudge loop (13/75 runs nudged, 12
answered a nudge with more text). Harness mapping: prompt text only; the ADK tool channel already enforces one call per
turn in practice, so the wording is "one or two sentences of reasoning, then exactly one tool call; never a message
without a tool call before submit_patch". Predicted effect: E4B nudges 13 -> ~3 runs; no change on 31B (3 nudges in 53).
Cost: none. Kill: E4B nudged runs not below 8/75 on the replica.

**Pattern card M2 — submit protocol as three separate verified steps.** Mechanism: "diff -> inspect -> submit" as
separate commands, with an explicit "you cannot continue after submitting". Bucket: wrong patch (10/53) and scratch
files in the patch. Mapping: prompt text; our v5 already has "git status --short && git diff, delete scratch, then
submit_patch". Add the inspection criterion from mini: "the diff must show only the source files you meant to change;
headers --- a/ +++ b/". Predicted effect: 0 to +1 (catches test-file or scratch-file edits; 26/46 host-trial patches
contained scratch files in raw/01). Cost: 0 calls (same final command). Kill: no change in patches touching non-source
files over 50 runs.

**Pattern card M3 — "output too long" rule stated as a recovery recipe.** Mechanism: the observation itself tells the
model what to do differently (head/tail/sed, narrower grep). Our harness caps stdout at 5,000 chars silently. Mapping:
prompt text in the TOOL RULES ("if an output was truncated, do not repeat the command; narrow it"). Bucket: no-edit
search loops. Predicted effect: small; our v5 already caps with head/tail. Cost: 0. Kill: not worth a slot alone.

## 2. SWE-agent 1.x (`config/default.yaml`, the Anthropic-filemap template that powers today's SWE-agent results)
```
I've uploaded a python code repository in the directory {{working_dir}}. Consider the following PR description:
<pr_description> {{problem_statement}} </pr_description>
Can you help me implement the necessary changes to the repository so that the requirements specified in the <pr_description> are met?
I've already taken care of all changes to any of the test files described in the <pr_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
Your task is to make the minimal changes to non-tests files in the {{working_dir}} directory to ensure the <pr_description> is satisfied.
Follow these steps to resolve the issue:
1. As a first step, it might be a good idea to find and read code relevant to the <pr_description>
2. Create a script to reproduce the error and execute it with `python <filename.py>` using the bash tool, to confirm the error
3. Edit the sourcecode of the repo to resolve the issue
4. Rerun your reproduce script and confirm that the error is fixed!
5. Think about edgecases and make sure your fix handles them as well
Your thinking should be thorough and so it's fine if it's very long.
```
Submit review message (`tools/review_on_submit_m`, `SUBMIT_REVIEW_MESSAGES`): on the first `submit`, the model gets
"1. If you made any changes to your code after running the reproduction script, please run the reproduction script
again ... 2. Remove your reproduction script ... 3. If you have modified any TEST files, please revert them ... `git
checkout -- /path/to/test/file.py` ... 4. Run the submit command again to confirm. Here is a list of all of your
changes: <diff> {{diff}} </diff>". History processor: `cache_control last_n_messages: 2` (no truncation in 1.x).

`tools/edit_anthropic/config.yaml` (docstring copied from OpenHands `function_calling.py`):
```
Notes for using the `str_replace` command:
* The `old_str` parameter should match EXACTLY one or more consecutive lines from the original file. Be mindful of whitespaces!
* If the `old_str` parameter is not unique in the file, the replacement will not be performed. Make sure to include enough context in `old_str` to make it unique
* The `new_str` parameter should contain the edited lines that should replace the `old_str`
```
Demonstration (`trajectories/demonstrations/function_calling_simple.traj`, 5 actions): find_file -> open -> edit
(search/replace of one line) -> `python tests/missing_colon.py` -> submit; each assistant message is one sentence of
reasoning plus one call; the edit observation says "Text replaced. Please review the changes and make sure they are
correct: 1. The edited file is correctly indented 2. The edited file does not contain duplicate lines 3. The edit does
not break existing functionality".

**Pattern card S1 — the 20-line Anthropic/SWE-agent prompt (suggested workflow, no imposed transitions).** Mechanism: the
model is told the five steps and trusted to order them; nothing about budgets or call counts. Bucket: control (E3).
Mapping: replace v5's CALL PLAN / TOOL RULES / PROCEDURE with this text plus our HARD LIMITS; keep EDIT PROTOCOL.
Predicted effect: unknown sign; this tells us whether the 60 rules in v5 add anything. Measured fact: three wording-
heavy variants (v3t2k, v4single, v5) moved the paired result by -1, +0, +3 over pub022, so wording is at most worth
+3; a 20-line prompt that ties v5 would free 700 tokens of context per turn. Cost: one paired eval. Kill: <= v5 - 3.

**Pattern card S2 — the "review on submit" message as a verifier phase (E1).** Mechanism: the first submit does not end
the run; the model receives its own diff and a four-point checklist (rerun repro, remove scratch, revert tests, submit
again). SWE-agent ships this in every 1.x config. Bucket: wrong patch (10/53) + scratch/test files in the patch.
Mapping: our harness ends the task on the first submit, so the checklist must live in a second sub-agent
(SequentialAgent solver -> verifier) whose instruction *is* this message: "Here is your diff (run git diff); 1. rerun
the repro 2. run one targeted pytest 3. revert test/config files 4. submit". Predicted effect: +1 (ceiling: 1 of 10
wrong patches is recoverable) plus protection of the 12 sometimes-solved tasks; cost 30-60 s per task on the 37 runs
that never tested. Kill: paired < +2 or 120-task projection > 10.5 h.

**Pattern card S3 — exact-match edit notes (str_replace docstring).** Mechanism: three sentences, repeated verbatim by
OpenHands, SWE-agent and Anthropic; "Be mindful of whitespaces!" and "include enough context to make it unique". Bucket:
lost edit (6 not-found + 1 ambiguous in v5; E4B 49 + 19). Mapping: prompt text in EDIT PROTOCOL and, for the E4B, one
worked `edit_file` example. Predicted effect: 31B +0 to +1 (ceiling 3); E4B larger (23 LOST_EDIT runs). Cost: 0. Kill:
edit_err per run unchanged on the replica.

**Pattern card S4 — in-context demonstration.** Mechanism: a complete short trajectory shows the format and the tempo
(find -> open -> edit -> run -> submit in 5 actions). Measured fact: SWE-agent ablation -1.7 points without the demo
(GPT-4 Turbo at 18 %, arXiv:2405.15793). Bucket: no-edit/after-budget (9/53) and 28-call runs. Mapping: prompt text
(E2): replace CALL PLAN + TOOL RULES with one ~700-token worked 12-call trajectory in the harness's own tool names.
Predicted effect: +1 to +2; ship after E1 because others measured that earlier edits alone became wrong patches
(scottweeden graph-first, 48 paired: +1/-2). Cost: ~300 extra prompt tokens if the rules are removed. Kill: more
WRONG_PATCH than v5 with no gain in RESOLVED.

## 3. SWE-agent 0.7 (`config/sweagent_0_7/07.yaml`): the classic tips
```
IMPORTANT TIPS:
1. Always start by trying to replicate the bug that the issues discusses.
  If the issue includes code for reproducing the bug, we recommend that you re-implement that in your environment, and run it to make sure you can reproduce the bug.
  Then start trying to fix it.
  When you think you've fixed the bug, re-run the bug reproduction script to make sure that the bug has indeed been fixed.
  If the bug reproduction script does not print anything when it successfully runs, we recommend adding a print("Script completed successfully, no errors.") command at the end of the file,
  so that you can be sure that the script indeed ran fine all the way through.
2. If you run a command and it doesn't work, try running a different command. A command that did not work once will not work the second time unless you modify it!
3. If you open a file and need to get to an area around a specific line that is not in the first 100 lines, say line 583, don't just use the scroll_down command multiple times. Instead, use the goto 583 command. It's much quicker.
...
6. When editing files, it is easy to accidentally specify a wrong line number or to write code with incorrect indentation. Always check the code after you issue an edit to make sure that it reflects what you wanted to accomplish. If it didn't, issue another command to fix it.
```
Plus: "You should only include a *SINGLE* command in the command section and then wait for a response", a
`demonstration_template` ("Here is a demonstration of how to correctly accomplish this task ... You do not need to
follow exactly what is done in the demonstration."), `history_processors: last_n_observations: n: 5`, and the lint-gated
`edit` tool whose docstring repeats "THIS COMMAND REQUIRES PROPER INDENTATION".

**Pattern card S5 — "a command that did not work once will not work the second time".** Mechanism: a one-line rule
against identical retries. Bucket: no-edit search loops (rich_3470 in pub022: 8 near-identical greps). Mapping: v5 has
"Never repeat a tool call that already failed with the same arguments"; keep, shorten. Measured fact: in v5, runs with
3+ repeated calls resolved 10/17 (repeats are often repro reruns, which are good), so the rule must target failed
repeats only. Cost 0. Kill: n/a (already in).

**Pattern card S6 — "print Script completed successfully" sentinel.** Mechanism: a reproduction script that is silent on
success is ambiguous; the sentinel makes pass/fail machine-readable. Bucket: wrong patch (verification that proves
nothing). Mapping: prompt text in the repro step: "end the script with print('OK') so that a passing run is visible".
Cost 0. Predicted effect: tiny alone; it is part of the E1 verifier checklist ("rerun repro, expect OK").

**Pattern card S7 — windowed viewer + last-5 observations.** Mechanism: cap context growth so the run survives. Not
transferable as tools (ours are fixed), partly transferable as behaviour: read_file windows of <= 120 lines once,
never re-read (v5 has this). The last-5 history collapse is a harness feature; our harness compacts at 14k tokens.
Mark: harness-level, not a prompt lever.

## 4. OpenHands CodeAct (0.30.1 `system_prompt.j2` + SWE-bench `run_infer.py` instruction)
```
<EFFICIENCY>
* Each action you take is somewhat expensive. Wherever possible, combine multiple actions into a single action, e.g. combine multiple bash commands into one, using sed and grep to edit/view multiple files at once.
* When exploring the codebase, use efficient tools like find, grep, and git commands with appropriate filters to minimize unnecessary operations.
</EFFICIENCY>
...
<PROBLEM_SOLVING_WORKFLOW>
1. EXPLORATION: Thoroughly explore relevant files and understand the context before proposing solutions
2. ANALYSIS: Consider multiple approaches and select the most promising one
3. TESTING:
   * For bug fixes: Create tests to verify issues before implementing fixes
   * For new features: Consider test-driven development when appropriate
4. IMPLEMENTATION: Make focused, minimal changes to address the problem
5. VERIFICATION: Test your implementation thoroughly, including edge cases
</PROBLEM_SOLVING_WORKFLOW>
...
<TROUBLESHOOTING>
* If you've made repeated attempts to solve a problem but tests still fail or the user reports it's still broken:
  1. Step back and reflect on 5-7 different possible sources of the problem
  2. Assess the likelihood of each possible cause
  3. Methodically address the most likely causes, starting with the highest probability
  4. Document your reasoning process
</TROUBLESHOOTING>
```
SWE-bench instruction (`run_infer.py` 0.30.1) adds six numbered steps: EXPLORATION (find/grep, "identify all files
mentioned in the problem statement"), ANALYSIS ("propose 2-5 possible approaches ... select the most promising"), TEST
CREATION ("Look at existing test files in the repository to understand the test format/structure ... create a minimal
reproduction script"), IMPLEMENTATION, VERIFICATION ("Run existing tests related to the modified code"), FINAL REVIEW
("Carefully re-read the problem description and compare your changes with the base commit ... If any tests fail,
revise your implementation until all tests pass"), ending with "It's fine if your thinking process is lengthy". The
current SDK wording (`static.py`) keeps the same sections and adds "Do not use mocks in tests", "Always modify existing
files directly rather than creating new versions with different suffixes", "If you create temporary files for
testing, delete them after confirming your solution works".

**Pattern card O1 — EFFICIENCY: combine actions.** Mechanism: one `run_command` can carry several greps/seds. Bucket:
no-edit/after-budget (calls run out). Our v5 already batches the first search; extend to "batch the caller lookup with
the next read" (it does) and to the verification step ("rerun repro && pytest -k in one command"). Measured fact: v5
mean 26.7 calls, median 28; 28/53 runs hit the cap. Predicted effect: 1-3 calls saved per run. Cost 0. Kill: calls/run
unchanged.

**Pattern card O2 — TROUBLESHOOTING: 5-7 candidate causes, then the most likely.** Mechanism: forces hypothesis
breadth after a failed fix instead of re-editing the same spot (coherence-collapse pattern: 60-69 % of failures edit
the right code and thrash it, arXiv:2603.24631). Bucket: wrong patch after a failed test (v5 rule: "do not retry the
same edit: restate the objective, read the failing assertion, change hypothesis"). Mapping: prompt text, but shrink to
budget: "list three different causes in one sentence each, pick one, change the source once". Predicted effect: 0 to
+1 (ceiling 1 in WRONG_PATCH). Cost: ~150 thinking tokens per failed test. Kill: not separable; bundle with E1.

**Pattern card O3 — FINAL REVIEW against the issue text.** Mechanism: re-read the problem statement and compare the
diff to it before finishing. Bucket: wrong patch where the literal names/messages from the issue are missing. Mapping:
the verifier's checklist line "every name, message and type from the issue appears exactly in the diff" (already in
v4_finisher). Cost: 0 calls (thinking only). Predicted effect: part of E1.

## 5. Anthropic's SWE-bench scaffold (Oct 2024 post; 49 % Verified with Sonnet 3.5 new)
The page shows the per-task prompt (quoted at most partially): "I've uploaded a python code repository in the directory
{location} (not in /tmp/inputs) ... make the minimal changes to non-tests files ... Create a script to reproduce the
error and execute it ... Your thinking should be thorough and so it's fine if it's very long." The SWE-agent
`config/default.yaml` above is this prompt verbatim (its header says "heavily inspired by anthropic's computer use
demo"). Stated design principles (paraphrased from the post): keep the scaffold minimal and let the model control its
own path; avoid hardcoded workflows or strict transitions; keep the prompt suggestive rather than detailed; invest in
tool descriptions and "error-proof" them (absolute paths fixed a relative-path failure after `cd`); exact string
replacement was the most reliable edit mechanism tested, applied only on exactly one match, otherwise an error to retry.

**Pattern card A1 — error-proof the tool description, not the workflow.** Mechanism: the model's mistakes are fixed at
the tool boundary (absolute paths, unique match). Our tools are fixed, but the *description the model sees* is our
prompt. Bucket: lost edit; the write_file-to-/tmp refusal (27/53 runs). Mapping: a TOOL FACTS block in every prompt:
"write_file only creates files under /workspace; scratch files via run_command heredoc into /tmp; edit_file needs a
unique verbatim old_string (3-15 lines) copied from a read_file result; read_file returns raw lines without numbers;
grep exit 1 means no match". Predicted effect: +0 to +1 and 1-2 calls saved in half the runs. Cost 0. Kill: write_file
refusals not at 0.

**Pattern card A2 — "thinking can be very long" is the wrong rule for us.** Anthropic/OpenHands/SWE-agent all end with
"it's fine if your thinking is very long". Under a 4,096 thinking budget and 8 min on 4xL4 (decode ~9 tok/s on T4,
faster on L4) long thinking is time. Measured fact: v5 median per-call latency 98.7 s; a 3,000-token thought costs
minutes. Keep v5's "think in a few sentences, then act". Not transferable.

## 6. Aider `editblock_prompts.py` (exact-match edit discipline)
```
Every *SEARCH* section must *EXACTLY MATCH* the existing file content, character for character, including all comments, docstrings, etc.
If the file contains code or other data wrapped/escaped in json/xml/quotes or other containers, you need to propose edits to the literal contents of the file, including the container markup.
*SEARCH/REPLACE* blocks will *only* replace the first match occurrence.
Including multiple unique *SEARCH/REPLACE* blocks if needed.
Include enough lines in each SEARCH section to uniquely match each set of lines that need to change.
Keep *SEARCH/REPLACE* blocks concise.
Break large *SEARCH/REPLACE* blocks into a series of smaller blocks that each change a small portion of the file.
Include just the changing lines, and a few surrounding lines if needed for uniqueness.
Do not include long runs of unchanging lines in *SEARCH/REPLACE* blocks.
...
To move code within a file, use 2 *SEARCH/REPLACE* blocks: 1 to delete it from its current location, 1 to insert it in the new location.
```
The main system prompt adds a two-shot example (import math; remove factorial; replace the call) and "Think step-by-step
and explain the needed changes in a few short sentences" before the blocks.

**Pattern card AI1 — small, many, exact blocks.** Mechanism: several small replacements beat one big one; "just the
changing lines plus a few for uniqueness". Bucket: lost edit (ambiguous and not-found both come from long or
re-typed old strings; E4B: "occurs 130 times" when the anchor was one common line). Mapping: EDIT PROTOCOL text:
"3-15 lines, include one distinctive line (a def/class line or a unique string), never a long docstring; split a big
change into several edit_file calls; to move code, delete then insert". Predicted effect: 31B +0 to +1; E4B +2 to +4
(23 LOST_EDIT runs, 7 recoverable). Cost 0. Kill: E4B `not found`+`ambiguous` per run not down by half on the replica.

**Pattern card AI2 — worked example of the edit format.** Aider shows two complete assistant answers. For the E4B,
one example of `edit_file` with a 4-line old_string copied from a read result and the matching new_string is the
cheapest format teacher we have (E6 prompt). Cost ~120 tokens.

## 7. What is common to every scaffold above (and what is not)
Common: reproduce first (all); minimal change to non-test files (all); "tests are already taken care of, don't modify
them" (SWE-agent, Anthropic, OpenHands); one explicit submission protocol with a review step (mini, SWE-agent); exact
edit discipline stated in the tool description (all 1.x scaffolds); rerun the repro after the fix (all); edge cases
last (all). None of them counts tool calls, names call numbers, or forbids reading; all of them run with 100-250 steps
and a cost cap. Our constraint (28 calls, 8 min) is why v5 has a CALL PLAN; the corpus suggests replacing the counting
rules with (a) the five-step workflow, (b) a demonstration that *shows* the tempo, (c) tool facts, and (d) a verifier
phase that owns the review-on-submit checklist.

Not transferable: bash-only action space (mini; harness design study says +15 points for predefined tools at 30B),
lint-gated edits (tool-level), last-5 history (harness-level), long thinking, 250-step budgets, `undo_edit`
(a `git checkout -- file` via run_command is the substitute; v5 uses it for test files only).
