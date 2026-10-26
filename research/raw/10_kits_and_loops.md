# 10 — Agent kits and loops as instruction sources (Day 2, 2026-10-25)

Purpose: extract the *instruction patterns* (not the machinery) from pipeline scaffolds (Agentless, AutoCodeRover,
Moatless, Trae-agent, Refact) and from Claude-Code-style skill kits and long-running loops (superpowers, ECC, Ralph
loop, long-running-agent harness, claude-flow, Agent SDK). Only prompt-text, tool-subset, Sequential/Loop-agent,
budget and sampling ideas qualify (CLAUDE.md hard facts; multi-agent analyzers, voting, extra tools and skills measured
worse by other teams). Hooks, worktrees, parallel agents, sub-agent dispatch and schedulers are marked NOT
TRANSFERABLE, but the instruction text they carry is kept.

Sources (read-only clones in the session scratchpad; on-disk copies under `third_party/` and `.claude/skills/`):
| Source | Repo @ commit | Files |
|---|---|---|
| Agentless | OpenAutoCoder/Agentless @ 5ce5888b | `agentless/fl/FL.py`, `agentless/repair/repair.py` |
| AutoCodeRover | nus-apr/auto-code-rover @ 585d3e63 | `app/agents/agent_search.py`, `app/agents/agent_write_patch.py` |
| Moatless | aorwall/moatless-tools @ 011ead57 | `moatless/actions/string_replace.py` |
| Trae-agent | bytedance/trae-agent @ e839e559 | `trae_agent/prompt/agent_prompt.py` |
| Refact | smallcloudai/refact @ 27f86def | `refact-agent/engine/crates/refact-yaml-configs/src/defaults/modes/{agent,oss_weak_agent,debug}.yaml` |
| superpowers | obra/superpowers @ bb92a777 (on disk) | `skills/systematic-debugging/SKILL.md`, `verification-before-completion/SKILL.md`, `test-driven-development/SKILL.md` |
| ECC | affaan-m/everything-claude-code @ 90606c83 (vendored) | `.claude/skills/{agent-introspection-debugging,loop-design-check,benchmark-optimization-loop,eval-harness}/SKILL.md` |
| Loop kits | see section 6 | Ralph Wiggum plugin, Anthropic long-running-agent harness post + quickstart, claude-flow, Agent SDK examples |

Measured facts the cards rest on (from `09a_bucket_ceilings.md`): v5 = 26/53; NO_EDIT 9 (6 of them "edit after the
budget"), LOST_EDIT 10 (ceiling 3), WRONG_PATCH 10 (ceiling 1), TIMEOUT 4; 16/53 ran a test; union of all 31B runs
28/49 vs v5 25/49; E4B 72 edit errors in 75 runs, 13 runs nudged.

## 1. Agentless (localise -> repair -> validate, no agent loop)
`FL.py` asks three successive questions, each with a fixed answer format:
```
Please look through the following GitHub problem description and Repository structure and provide a list of files that one would need to edit to fix the problem.
...
Please only provide the full path and return at most 5 files.
The returned files should be separated by new lines ordered by most to least important and wrapped with ```
```
then, on skeletons of those files:
```
Identify all locations that need inspection or editing to fix the problem, including directly related areas as well as any potentially related global variables, functions, and classes.
For each location you provide, either give the name of the class, the name of a method in a class, the name of a function, or the name of a global variable.
```
then, on the full content of those elements:
```
Please provide the class name, function or method name, or the exact line numbers that need to be edited.
The possible location outputs should be either "class", "function" or "line".
```
`repair.py` (`repair_prompt_combine_topn_cot`): "Please first localize the bug based on the issue statement, and then
generate `edit_file` commands to fix the issue." with the line-range edit API documented inline and the warning "THE
`edit_file` FUNCTION REQUIRES PROPER INDENTATION. If you would like to add the line '        print(x)', you must fully
write that out". There is also an *irrelevant folders* prompt ("provide a list of folders that are irrelevant to fixing
the problem ... safe to ignore").

**Card AG1 — localisation as three answered questions (file -> element -> line).** Mechanism: the model must *write
down* a file list, then element names, then line numbers, each in a fixed format, before any edit; later stages only
see what earlier stages named. Measured: file recall 78.7 % from the tree alone, 81.7 % with embeddings; skeleton
format beats full files 58.3 vs 53.7 (arXiv:2407.01489). Bucket: NO_EDIT/after_budget (9/53) and search loops.
Harness mapping: prompt text, zero extra calls: "Before the first edit, state in one line: FILE: path; ELEMENT:
Class.method or function; LINES: a-b; WHY: one sentence. If you cannot fill all four from what you have read, make one
more targeted read, then fill them with your best guess and edit." Predicted effect: converts after-budget runs into
edits (+0 to +1; ceiling 1 in v5 NO_EDIT) but, per scottweeden's paired data, earlier edits alone become wrong patches,
so pair with E1. Cost: ~60 output tokens. Kill: NO_EDIT not reduced on the replica.

**Card AG2 — irrelevant-folder pruning as a reading rule.** Mechanism: name what *not* to read. Mapping: v5 already says
"prefer library source over tests, docs and examples"; add "never read docs/, examples/, scripts/ or tests/ unless the
issue names them". Cost 0. Effect: small; part of AG1.

Not transferable: 4 location sets x 10 patches at T 0.8 and majority vote (sampling budget), skeleton generation (needs
code), reproduction-test generation at scale.

## 2. AutoCodeRover (search APIs + a context-sufficiency gate)
`agent_search.py`:
```
Your task is to invoke a few search API calls to gather sufficient code context for resolving the issue.
The collected context will later be sent to your colleage for writing a patch.
...
Let's analyze collected context first.
If an API call could not find any code, you should think about what other API calls you can make to get more context.
If an API call returns some result, you should analyze the result and think about these questions:
1. What does this part of the code do?
2. What is the relationship between this part of the code and the bug?
3. Given the issue description, what would be the intended behavior of this part of the code?
...
Based on your analysis, answer below questions:
1. do we need more context: construct search API calls to get more context of the project. If you don't need more context, LEAVE THIS EMTPY.
2. where are bug locations: buggy files, classes, and methods. Only include the necessary locations that need to be fixed. For each bug location, you should also describe the intended behavior of the code at that location, in order to resolve the issue.
```
`agent_write_patch.py`: "You should only make minimal changes to the code to resolve the issue. Your patch should
preserve the program functionality as much as possible." and the retry feedback "Your patch is invalid. {validation_msg}.
Please try again" / "Your edit could not be applied to the program ... Please try again."

**Card ACR1 — the "do we need more context?" gate with an "intended behaviour" answer.** Mechanism: every search round
ends with a forced binary decision; the exit answer must name locations *and* the intended behaviour, which is the
specification the patch is written to. Bucket: NO_EDIT (search loops), WRONG_PATCH (patch written without a stated
intended behaviour). Mapping: prompt text: after each read or search, "answer silently: do I need more context? If
no: write LOCATION + INTENDED BEHAVIOUR (one sentence each) and edit." Combine with AG1 (same slot). Predicted effect:
+0 to +1. Cost 0. Kill: same as AG1.

**Card ACR2 — invalid-patch feedback loop.** Our harness already returns `FileEditError` with the reason; ACR's extra is
the *instruction to re-read before retrying*. Mapping: EDIT PROTOCOL (v5 has it: "read those exact lines again and retry
once with a smaller unique snippet"). Keep.

Not transferable: the AST search APIs (search_class, search_method_in_file...) — ours are grep/read_file; the
reproducer and reviewer agents (multi-agent measured worse here).

## 3. Moatless `StringReplace` (what a good error message tells the model)
Tool docstring: "The old_str parameter must match EXACTLY one or more consecutive lines ... Whitespace and indentation
must match exactly ... must be unique within the file - include enough surrounding context ... Do not include line
numbers in old_str or new_str". Error texts (the model's recovery hints), excerpt:
```
No changes were made. The provided old_str was not found, but a similar code block was found. To replace this code, the old_str must match exactly:
...
The content matches but the indentation is different. ... Please update old_str to match the exact indentation shown above.
...
Multiple potential matches found with different formatting: ... Try including more surrounding context to create a unique match.
...
New string '{new_str}' already exists in {path}. No changes were made.
...
String '{old_str}' not found in {path}. Remember to write out the exact string you want to replace with the same indentation and no placeholders.
```
Our harness has a three-tier matcher (exact -> whitespace-flexible -> regex), so indentation drift is mostly absorbed;
what remains in our traces is `old_string not found` (re-typed or stale text) and `occurs N times` (anchor too short).

**Card MO1 — "new_str already exists" = the edit was already applied.** Mechanism: a not-found error after a successful
edit usually means the model is re-applying its own change (coherence-collapse thrash). Bucket: LOST_EDIT and
EDIT_THEN_EMPTY (rich_3470 in v5). Mapping: EDIT PROTOCOL line: "If old_string is not found, first grep for your
new_string: if it is already in the file, the edit is done; do not retry." Cost: 0 (one grep replaces a blind retry).
Predicted effect: +0 to +1. Kill: no `not_found` errors follow a successful edit on the same file (then the card is
moot).

**Card MO2 — "no placeholders, no line numbers" in old_string.** Our `read_file` returns raw lines without numbers, so the
line-number failure does not occur; the placeholder failure ("...") does. Mapping: one clause in EDIT PROTOCOL. Cost 0.

Not transferable: the auto-indentation correction and similarity search (tool code).

## 4. Trae-agent (`agent_prompt.py`): the done checklist
```
3.  Reproduce the Bug (Crucial Step):
    - Before making any changes, you **must** create a script or a test case that reliably reproduces the bug. This will be your baseline for verification.
...
6.  Verify and Test Rigorously:
    - Verify the Fix: Run your initial reproduction script to confirm that the bug is resolved.
    - Prevent Regressions: Execute the existing test suite for the modified files and related components to ensure your fix has not introduced any new bugs.
    - Write New Tests: Create new, specific test cases (e.g., using `pytest`) that cover the original bug scenario. ...
    - Consider Edge Cases: Think about and test potential edge cases related to your changes.
7.  Summarize Your Work: ...
If you are sure the issue has been solved, you should call the `task_done` to finish the task.
```
Also: "All tools that take a `file_path` as an argument require an **absolute path**" with a worked example, and a
sequential_thinking tool guide ("Set total_thoughts to at least 5").

**Card TR1 — the verifier's done checklist.** Mechanism: "done" is defined as four observable checks (repro passes,
existing tests for the modified file pass, edge cases considered, summary) and the finish tool is called only "if you
are sure". Bucket: WRONG_PATCH (10/53, 37/53 never tested). Mapping: the E1 verifier instruction = this list minus
"write new tests" (test files are discarded by the grader) with budgets: repro rerun 1 call, one `timeout 60 pytest -x
-q -k` on the test file nearest the changed module, edge cases as a thinking step only. Cost: 1-2 calls, 30-60 s.
Predicted effect: +1 (ceiling) plus regression protection on the 12 sometimes-solved tasks. Kill: E1 paired < +2.

**Card TR2 — absolute-path example.** Our tools take workspace-relative paths; the equivalent is "paths are relative
to /workspace; never write outside /workspace with write_file" (card A1 in 09). Cost 0.

## 5. Refact (mode prompts; the weak-model fallback is the interesting one)
`oss_weak_agent.yaml` (match_models `*3b*`, `*7b*`, `*8b*`, `*small*`, `*mini*`):
```
Use native tool calling if available.
If native tool calling fails, emit exactly one strict fallback tool call in one of these formats:
...
Additional rules:
- Never emit more than one fallback tool call in a single response.
- Do not add explanation before or after the fallback tool call.
- Use exact tool names and valid JSON object arguments.
- After a tool result, continue with either another tool call or a plain answer.
```
`debug.yaml`: "3. Form hypotheses - List 2-3 most likely causes - Rank by probability 4. Investigate systematically -
Check each hypothesis with targeted searches ... 5. Deliver diagnosis - Root cause with evidence - Location
(file:line)". `agent.yaml`: "Iterate until checks pass or the blocker is evidenced and clearly reported." and "**Be
conclusive**: When done, summarize what was accomplished. Don't end with trailing questions."

**Card RF1 — weak-model rules: exact tool names, one call, no prose around it.** Bucket: E4B hallucinated tool names
(`git_status`, `git_status_diff`, 11 calls) and text-only turns (13 runs nudged). Mapping: E4B prompt: "The only tools
are run_command, read_file, edit_file, submit_patch. There is no git tool: run git through run_command. One tool call
per turn; a message without a tool call ends the task." Cost 0. Predicted effect: E4B +1 to +2 runs saved (11 wasted
calls, 23 nudges). Kill: hallucinated names not at 0 on the replica.

**Card RF2 — ranked hypotheses before investigating.** Same family as OpenHands TROUBLESHOOTING and superpowers Phase
3; keep the shortest form: "name 2-3 causes, pick the most likely, test it with one command". Already covered by card
O2 in 09.

Not transferable: subagent(), delegate(), ask_questions(), cron, trajectories memory.

## 6. Claude-Code-style kits: superpowers and ECC (on disk)
`superpowers/skills/systematic-debugging/SKILL.md`:
```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
...
### Phase 3: Hypothesis and Testing
1. **Form Single Hypothesis** - State clearly: "I think X is the root cause because Y" ...
2. **Test Minimally** - Make the SMALLEST possible change to test hypothesis - One variable at a time - Don't fix multiple things at once
3. **Verify Before Continuing** - Did it work? Yes -> Phase 4 - Didn't work? Form NEW hypothesis - DON'T add more fixes on top
...
4. **If Fix Doesn't Work** - STOP - Count: How many fixes have you tried? - If < 3: Return to Phase 1, re-analyze with new information - **If >= 3: STOP and question the architecture**
```
`verification-before-completion/SKILL.md`:
```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
...
1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
...
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Agent completed | VCS diff shows changes | Agent reports "success" |
```
`test-driven-development/SKILL.md`: "If you didn't watch the test fail, you don't know if it tests the right thing";
Verify RED ("Test passes? You're testing existing behavior. Fix test."), then GREEN, "Test fails? Fix code, not test."

ECC `agent-introspection-debugging`: "Prefer these interventions in order: 1. Restate the real objective in one
sentence. 2. Verify the world state instead of trusting memory. 3. Shrink the failing scope. 4. Run one discriminating
check. 5. Only then retry." and "Bad pattern: retrying the same action three times with slightly different wording".
ECC `loop-design-check`: done-criterion must be machine-decidable, defined *together with a boundary* ("what it must
NOT do" — the anti-Goodhart clause: "only gates on all tests pass -> agent deletes the tests"), the judge must be
independent of the builder and deterministic, retry cap then escalate. `benchmark-optimization-loop` and
`eval-harness` are process skills for us (one hypothesis per variant, ledger rows, pass@k vocabulary), not agent text.

**Card SP1 — evidence before claims: the repro must FAIL before the edit and PASS after.** Mechanism: TDD's "watch it
fail" applied to the reproduction script: a repro that already passes proves nothing (wrong repro or wrong
understanding). Bucket: WRONG_PATCH with a passing-but-irrelevant check. Mapping: v5 step 3 ("prove the bug first")
plus one clause: "If the reproduction does not fail before your edit, it does not test the issue: fix the reproduction
before editing." and in the verifier: "a claim of success requires the repro output after the edit in your context".
Cost: 0 extra calls (the rerun already exists). Predicted effect: +0 to +1. Kill: bundle with E1.

**Card SP2 — one hypothesis, one change, then re-verify; after two failed fixes change the hypothesis, after three
stop editing and submit the best state.** Mechanism: a retry cap with an explicit "do not stack fixes" rule.
Bucket: LOST_EDIT/EDIT_THEN_EMPTY thrash and WRONG_PATCH_TIMEOUT (rich_3468: 6,846-char patch after 485 s). Mapping:
prompt text (v5 has one line; make the cap explicit: "at most 2 fix attempts after the first edit; then git diff and
submit"). Cost 0. Predicted effect: fewer timeouts (4) and giant patches; +0 to +1. Kill: patch size p90 unchanged.

**Card SP3 — "verify the world state instead of trusting memory".** Mechanism: before claiming an edit exists, run
`git diff --stat`; before re-editing, re-read. Bucket: EDIT_THEN_EMPTY, after-budget submits with patch 0 (7 submitted
empty in v5). Mapping: the final-check line already in v5; add "if git diff is empty you have not edited: edit now".
Cost 0 (the diff call exists). Predicted effect: catches the 7 empty submits only if calls remain (most are at 28):
+0. Record as a verifier rule, not an expectation.

**Card SP4 — done-criterion + boundary, independent judge.** Mechanism (loop-design-check): the builder cannot grade
itself; the acceptance condition must be stated with what must not change. Mapping: this *is* the E1 design: solver
(no submit tool) hands over; verifier (own instruction, own tool subset incl. submit_patch) owns the done test (repro
passes, targeted test passes, no test/config files in the diff) and submits. Measured facts: multi-agent analyzers and
voting measured worse by other teams, and our v4_phased (3 phases) lost 4 tasks and 120 s/task; the E1 design must
therefore be two phases, not three, and the verifier must get a small budget (2-4 calls). Kill: as E1.

NOT TRANSFERABLE from these kits: SessionStart hooks, `/loop`, cron, subagent dispatch (subagent-driven-development),
git worktrees, "ask your human partner", TodoWrite-style task lists (no tool), red-flag tables as prompt text (too
long for a 28-call budget; keep one line each).

## 7. Long-running loops and orchestrators (Ralph loop, long-running-agent harness, claude-flow, Agent SDK)
Extracted by a read-only subagent (full report with line-numbered excerpts: scratchpad `reports/day2_loops.md`;
clones under `repos_loops/`). Licence note: `anthropics/claude-code` (the ralph-wiggum plugin) is all-rights-reserved
and the two blog posts are copyrighted, so those are paraphrased; verbatim lines below come from MIT files only.

| id | Source @ commit | What it is |
|---|---|---|
| RW | anthropics/claude-code `plugins/ralph-wiggum` @ 318b7e6a | Stop hook re-feeds the same prompt until an exact-match `<promise>` appears; max-iterations cap |
| GH/PB | ghuntley.com/ralph; ClaytonFarr/ralph-playbook @ 8f58cace (MIT, same PROMPT_build.md as ghuntley/how-to-ralph-wiggum @ 88d488a1) | `while :; do cat PROMPT.md | claude ; done`; plan file on disk; tests as backpressure |
| SR | snarktank/ralph @ 6c53cb0b (MIT) | prd.json stories with `passes`, append-only progress.txt, `<promise>COMPLETE</promise>` stop |
| AE/QS | anthropic.com "Effective harnesses for long-running agents"; anthropics/claude-quickstarts @ 930ad10b (MIT) `autonomous-coding/prompts/*` | initializer + coding prompt; feature_list.json is the source of truth, only `passes` may flip; progress file; baseline check before new work |
| CF | ruvnet/claude-flow (ruflo) @ 31f554c7 (MIT) | swarm/hook/memory orchestration; "truth score" is a design note over commands that do not exist (its own SKILL says so) |
| SP/SD | anthropics/claude-agent-sdk-python @ 0e89b298, claude-agent-sdk-demos @ 826b2685 | one-line prompts and dispatch-only orchestrators; nothing to transfer |
| RC | frankbria/ralph-claude-code @ a4ea748f (MIT) | status block per reply (STATUS, TESTS_STATUS, EXIT_SIGNAL), circuit breaker on repeated test-only loops |
| RO | mikeyobrien/ralph-orchestrator @ b5789dfb (MIT) | "hats" (investigator -> tester -> fixer -> verifier) selected by events; build.done rejected without evidence lines |
| OM | code-yeongyu/oh-my-opencode `ulw-loop` component @ 6f37e91b (MIT component) | goal with binary criteria + evidence artifacts; ledger; "tests alone never prove done" |

Verbatim excerpts (MIT files):
```
snarktank/ralph prompt.md L94-101
## Stop Condition
After completing a user story, check if ALL stories have `passes: true`.
If ALL stories are complete and passing, reply with:
<promise>COMPLETE</promise>
If there are still stories with `passes: false`, end your response normally (another iteration will pick up the next story).

claude-quickstarts autonomous-coding/prompts/coding_prompt.md L50-51, L126
The previous session may have introduced bugs. Before implementing anything
new, you MUST run verification tests.
**ONLY CHANGE "passes" FIELD AFTER VERIFICATION WITH SCREENSHOTS.**

ralph-claude-code templates/PROMPT.md L69-74
Set EXIT_SIGNAL to **true** when ALL of these conditions are met:
1. All items in fix_plan.md are marked [x]
2. All tests are passing (or no tests exist for valid reasons)
3. No errors or warnings in the last execution
4. All requirements from specs/ are implemented
5. You have nothing meaningful left to implement

ralph-orchestrator presets/debug.yml L57-58, L113-116
      5. Form exactly one falsifiable hypothesis.
      6. If the bug is already fixed, cannot be reproduced, or an existing debug note already captures the answer, your hypothesis MUST say that explicitly and name the evidence you just gathered.
      3. Run one experiment that directly tests the hypothesis.
      4. Run one nearby adversarial or neighboring failure-path case.

oh-my-opencode ulw-loop/directive.md L12-16, L430-434, L477-480
Deliver EXACTLY what the user asked, end-to-end working, proven by
captured evidence: the changed behavior RUN through its real surface,
sized by the tier below, with the tests the repository keeps for it
still green. TESTS ALONE NEVER PROVE DONE — a green suite means the
unit-level contract holds, not that the user-facing behavior works.
- Every behavior change is PROVEN BY ITS RUN on the real surface, with
  the tests the repository keeps for it green. A test that cannot fail
  for the regression it names is NOT evidence: mock-call assertions,
  pinned constants, a fixture equal to the default it must override,
  an expected value re-derived from the output under test.
- After 2 identical failed attempts at one step, surface what was tried
  and ask the user before another retry.
- After 2 parallel exploration waves yield no new useful facts, stop
  exploring and act.
```

**Card LK1 — "a completed run is unverified": the verifier refutes, it does not confirm.** (CF nested-reviewer:
"Adversarially refute this finding. Default to refuted=true if uncertain"; RO code-assist: "You MUST try to break the
increment, not merely confirm the happy path"; QS: only flip `passes` after verification.) Bucket: WRONG_PATCH. Mapping:
the E1 verifier instruction is written as a refutation task ("your job is to find the reason this patch is wrong:
rerun the repro, run the targeted test, try one neighbouring input; submit only when you failed to break it") rather
than a confirmation checklist. Cost 0 beyond E1. Predicted effect: part of E1 (+1 ceiling). Kill: as E1.

**Card LK2 — done = ALL conditions true, listed; otherwise say what still fails.** (RC EXIT_SIGNAL list; SR stop
condition; OM stop goal.) Mapping: the verifier's decision rule and the solver's hand-over block ("CHANGED / REPRO /
TEST"), and the final one-sentence reply after submit_patch stating "repro passes; test <file> -k <kw> passes (or
NOT_RUN)". Honest NOT_RUN is allowed (RC TESTS_STATUS NOT_RUN); a claim of PASSING without a run in context is
forbidden (superpowers verification-before-completion). Cost 0.

**Card LK3 — baseline before new work; one item per pass.** (QS "the previous session may have introduced bugs ...
run verification tests"; SR "pick the highest priority story where passes: false"; PB "choose the most important
item".) Single-shot mapping: run the targeted existing test once before editing (card TTC2) and work one hypothesis at
a time (card SP2). The multi-session memory (progress file + git log) is NOT needed in a 28-call run; sub-agent
restarts after a harness nudge already see the full history, so the "re-read your notes first" rule becomes "read
the VERIFIER REPORT first; do not start over" (as the E4B session's `phase_solver.md` already does).

**Card LK4 — external state file.** (QS claude-progress.txt + feature_list.json; SR progress.txt; OM notepad re-read
after context loss; PB plan file.) Transferable only partly: our harness compacts at 14k tokens keeping 5 events, so a
one-line plan kept in the *thought* is lost after compaction, but a file is not. Mapping: optional rule "after
locating, write one line LOCATION/CHANGE/TEST to /tmp/plan.txt via run_command and `cat` it after any compaction";
cost 1-2 calls of 28, benefit only for runs that get compacted (long runs that mostly fail anyway). Verdict: do not
spend calls on it in the 31B; revisit for the E4B loop (E5) where the verifier report already carries the state.

**Card LK5 — stop rules: two identical failures mean change approach; once the evidence answers the task, stop and
submit (no polish pass).** (OM L477-480; RC "do NOT refactor code that is already working fine"; RW README: near the
cap, document the blocker.) Bucket: thrash/timeouts and coherence collapse. Mapping: one line in every prompt;
matches TTC1 and SP2. Cost 0.

**Card LK6 — search before assuming something is missing; no stubs or placeholders.** (PB L5/L8 and L17; RO
builder.) Mapping: v5's "find the closest existing sibling and copy its pattern" covers the first; add "never leave a
pass, TODO or NotImplemented in the patch". Cost 0. Bucket: WRONG_PATCH on feature tasks.

NOT TRANSFERABLE from the loop kits (instruction text noted above where it exists): the Stop hook and promise parser
(RW), bash restart loops (GH, SR, RC), ScheduleWakeup/cron autopilots (CF), worktrees and parallel fan-out (PB "up to
500 parallel Sonnet subagents", RC up to 100, CF swarms, OM team mode), sub-agent dispatch (CF nested-reviewer, SD lead
agent, OM spawn_agent), MCP memory and CLIs (CF, RO), runtime evidence gates (RO payload check, OM ledger and git
tree stamps), the computer-use advisor tool (QS). Cautions: "it's fine if it takes a long time" wording (QS, CF)
contradicts an 8-min cap; RW's never-exit rule invites a false "done" in a single shot (our budget is the exit; the
prompt must say what to do at the cap: submit the best patch); RC's "limit testing to 20 % of effort" conflicts with
verify-first and is not copied; any scratch-file rule must name a path the harness can write (/tmp via run_command
only, cf. the v5.1 fix) and keep the file out of the patch.

## 8. Pattern table (what goes into the drafts)
| Pattern | Sources | Transferable? | Wording (one line) | Bucket |
|---|---|---|---|---|
| Name FILE/ELEMENT/LINES before editing | Agentless, ACR | yes, prompt | "Before the first edit write LOCATION, INTENDED BEHAVIOUR in one line each" | NO_EDIT |
| Context-sufficiency gate | ACR | yes, prompt | "After each read ask: do I need more? If not, edit now" | NO_EDIT |
| Not-found after a success = already applied | Moatless | yes, prompt | "grep for new_string before retrying an edit" | LOST_EDIT |
| Small unique anchors, several edits | Aider, Moatless, OpenHands | yes, prompt | "3-15 lines with one distinctive line; split big changes" | LOST_EDIT |
| Repro must fail before, pass after | superpowers TDD | yes, prompt | "a repro that passes before the edit is wrong; fix it first" | WRONG_PATCH |
| Done checklist owned by a verifier | Trae, SWE-agent review, loop-design-check | yes, SequentialAgent | E1 verifier instruction | WRONG_PATCH |
| One hypothesis per fix; cap 2 retries, then submit | superpowers, ECC introspection | yes, prompt | "at most two fix attempts; then diff and submit" | TIMEOUT, thrash |
| Restate objective; verify state; shrink; one check; retry | ECC introspection | yes, prompt (v5 has it) | keep | WRONG_PATCH |
| Exact tool names, one call per turn, no prose-only turns | Refact weak-agent, mini-SWE | yes, prompt (E4B) | "no git tool; one call per turn; never end without submit" | E4B nudges |
| Boundary with the done criterion | loop-design-check | yes, prompt | "tests pass AND no test/config file changed" | hygiene |
| Verifier refutes, never confirms | claude-flow reviewer, ralph-orchestrator, quickstarts | yes, SequentialAgent prompt | "find the reason this patch is wrong; submit only when you failed to break it" | WRONG_PATCH |
| Done = all conditions true; honest NOT_RUN | ralph-claude-code, snarktank, oh-my-opencode | yes, prompt | final line "repro PASS; test <file> -k <kw> PASS/NOT_RUN" | reporting |
| Two identical failures -> change approach; stop at done, no polish | oh-my-opencode, ralph README | yes, prompt | "after two failed fixes submit the best state; never refactor a passing fix" | thrash, TIMEOUT |
| External state file | quickstarts progress file, snarktank, oh-my-opencode notepad | partly (costs calls; only helps compacted runs) | optional /tmp/plan.txt line; not for the 31B | compaction |
| Hooks, worktrees, parallel agents, subagent dispatch, restart loops | all kits | NO | | |
