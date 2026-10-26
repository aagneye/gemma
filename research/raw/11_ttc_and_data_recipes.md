# 11 — Test-time-compute mechanisms and training-data recipes, as rules (Day 3, 2026-10-25)

Scope: the exact mechanisms behind the papers already summarised in `03_swe_agent_literature.md` and
`05_training_recipes_and_data.md`, turned into pattern cards (prompt rules, phase designs) and data rules (feeding
`FT_DATA_SPEC.md`). Paper specifics were extracted by a read-only subagent from the arXiv HTML/PDF texts (report kept
in the session scratchpad, `reports/day3_papers.md`) and checked against the earlier summaries; numbers below are
paraphrased, "(calc)" marks arithmetic of ours. Where the brief's premise was wrong the correction is stated.

Measured facts the cards rest on (from `09a_bucket_ceilings.md`): v5single 26/53; WRONG_PATCH 10 (ceiling 1),
LOST_EDIT 10 (ceiling 3), NO_EDIT 9 (6 of them an edit attempted after the 28th call), TIMEOUT 4; 7 empty submits;
union of all 31B runs 28/49 vs v5 25/49; E4B 8/75 with 72 edit errors, 13 nudged runs, 13.8 calls per run.

## Part A — test-time compute under a one-attempt, 28-call, 8-minute budget

### A1. Coherence Collapse (arXiv:2603.24631): the correct patch existed and was destroyed
Mechanism: in 16,758 trajectories, 60-69 % of capable-model failures edited the right functions and still shipped a
wrong patch. Of those edit-quality failures (SWE-Agent, Verified, n=914) 39.7 % are "coherence collapse": confused
thrashing (29.1 %: >= 3 edit attempts on the gold file, none surviving) + near-correct corrupted (10.6 %: an edit with
> 50 % gold-token overlap later overwritten). Collapse share rises from 21.7 % in the shortest-trajectory quartile to
63.7 % in the longest. The proposed rule: once an intermediate edit passes the existing tests, freeze it so a later
edit cannot overwrite it (the paper never built it; the 5/5 recovery is a retroactive existence proof on the 5
bit-identical-to-gold cases; ceiling 30 of 97 near-correct cases). A reference-free trigger (files viewed by >= 3 of
6 other models) gave +3.0 pp on GPT-5 (39 gained / 24 lost, p = 0.08). Worked example: the exact gold edit at turn 34
passed the suite; a str_replace at turn 48 whose old_str also covered an unrelated line dropped it.

**Card TTC1 — freeze after the first pass; narrow anchors.** Bucket: WRONG_PATCH (fastapi_14463: solved by every other
bundle, lost by v5 after a late re-edit), EDIT_THEN_EMPTY (rich_3470), giant late patches (rich_3468 6,846 chars at
485 s). Harness mapping (prompt text + E1 verifier): "Once the reproduction passes and the targeted test passes,
stop editing: run git diff and submit. Do not improve, refactor or extend a passing fix. Re-edit a passing hunk only
if a rerun shows a regression." and "old_string must contain only the lines you change plus 1-3 anchor lines; it
must never span an unrelated statement." In E1 the verifier is allowed exactly one corrective edit. Predicted effect:
+0 to +1 on the 31B (ceiling 1 in WRONG_PATCH; collapse is a long-trajectory phenomenon and our runs are capped at
28 calls); larger on E4B (195 edit calls / 75 runs). Cost: 0. Kill: patch-size p90 and the count of edits after the
first passing test unchanged on the replica.

### A2. TestPrune (arXiv:2510.18270): existing regression tests as reproduction and validation
Correction: the paper has no "fixes produced but not submitted" statistic. What it has: a selector (LLM narrows issue
-> files -> suspicious functions; LLM picks 10 test files; coverage-greedy keeps ~9-11 tests, 52 s vs 24 min for the
full suite; precision 0.63). Used for reproduction (F->P@1 +6-9 % relative) and validation (Agentless Claude-3.7
50.8 -> 55.6 % Verified; Trae 65.0 -> 70.2; SWE-agent Lite 56.7 -> 62.0; steps -5 to -10 %). Its agent config makes a
baseline run of the selected tests BEFORE any edit mandatory, and after the fix both the tests and the reproduction
rerun. The documented failure: 8 (SWE-agent) + 17 (Trae) previously-solved instances regressed because once the
selected tests passed the agent stopped exploring; "a passing existing suite is a weak stop signal".

**Card TTC2 — one targeted existing test, before and after.** Bucket: WRONG_PATCH (37/53 v5 runs never tested; runs
with a test resolved 11/16). Harness mapping: no selector tool, so the rule is procedural: "Find the test file whose
name matches the module you will change (ls tests | grep -i name). Run `timeout 60 python -m pytest <file> -x -q -k
<keyword> 2>&1 | tail -30` once BEFORE the edit (baseline; failures there are pre-existing and never yours) and once
after. Passing existing tests do not prove the fix: the reproduction from the issue must also pass." In E1 the
verifier owns the after-run; the baseline costs one solver call and is optional when the issue has no test file hint.
Predicted effect: +1 (ceiling), fewer false "done" claims. Cost: +1 call, ~20-40 s. Kill: no reduction in WRONG_PATCH
runs that ran >= 1 test (currently 4/10 in v5).

### A3. Fail-Fast / restart-smart (arXiv:2608.03222): abort a doomed run, restart from its diff
Mechanism: a 0.6B monitor reads the issue + the last 8 steps (thought, command, error tag, self-test flag, patch flag,
truncated observation) and votes; no decision before step 20 of 100; on alarm ONE fresh rollout with NO prompt
history, only the interrupted run's repo diff as an optional overlay tool plus a sceptical note (the earlier attempt
was stopped as unlikely to finish; its edits may be right, incomplete or wrong; reproduce first, then switch the
overlay on and test it; never git checkout/reset). Results on 100 Verified instances x 5 runs: Qwen3.6-27B 66.6 ->
69.8 % (10 % FPR, +30 % tokens) / 71.8 (25 % FPR); **Gemma4-31B 62.2 -> 65.2 % at +20.5 % tokens**; Qwen3.5-9B 48.2 ->
52.2. Cold restart without the diff: +0.2 to +0.6 only. Net at 25 % FPR (27B): 33 runs repaired, 7 broken.

**Card TTC3 — rescue phase = diff, not history, with a sceptical note (E7).** Bucket: variance (12 sometimes-solved
tasks), runs that end at 28 calls with a wrong or empty patch. Harness mapping: `SequentialAgent [solver, rescue]`
with the rescue sub-agent declared `include_contents: none` (fresh window; sub-agent sessions are never compacted),
its instruction = the Fail-Fast note: "A previous attempt on this issue ran out of budget. Run git diff first. Its
edits may be correct, incomplete or wrong; do not assume they are right and never git checkout or reset. Reproduce
the issue, then test the existing edit; keep what is right, fix or drop the rest, submit." The trigger is structural
(the solver's budget ends) because no monitor exists; the cost is budget: the 31B has no calls left after a failed
28-call run, so E7 needs E8 headroom (32-36 calls) or applies to the E4B (13.8 calls used of 28, 97 s/task).
Predicted effect: E4B +1 to +3 of 75; 31B untestable without headroom. Kill: rescue phase resolves < 2 of 50 on the
E4B replica.

### A4. SWE-Replay (arXiv:2601.22129): archive and branch
Mechanism: 10 trajectories per issue; each later run is a coin flip between explore (from scratch) and exploit
(branch from an archived trajectory at a step chosen by rarity of its explored-file state and richness of its
reasoning); regression-test filter on the archive; majority vote at the end; cost -11 to -17 % at +0.2 to +7.0 points
(Multilingual 31.0 -> 38.0). Not transferable (multi-sample). Offline use only: when generating 31B training traces on
the VM at T 0.7-1.0, branching from the archived prefix of a failed run at its last rich-reasoning step is a cheaper
way to get a second resolved trace per task than a full rerun (data rule D6).

### A5. Devstral's iterative protocol (arXiv:2509.25193 + OpenHands `run_infer.py` at ddda30d)
Correction: the paper does not define "empty"; the code does. Up to 3 attempts; attempt 1 at T 0, later at T 0.1;
an instance is rerun iff the previous record failed the critic: patch empty after strip() OR the last event is not
AgentFinishAction (cap hit, never finished). Table 3 (Devstral-Small): iteration 1: 43.0 % resolved, 7.6 % empty
(~38 of 500); iteration 2 reruns 191 -> 45.8 %, 0 empty; iteration 3 reruns 121 -> 46.8 %. Gain +3.8 points = ~19
tasks (calc): 14 from the first rerun. Iteration cap: 30 -> 36.8 %, 50 -> 46.8 %, 100 -> 46.8 %.

**Card TTC4 — rerun empty or unfinished attempts (E5 on the E4B).** Bucket: E4B SUBMIT_EMPTY 2 + TEXT_STOP 3 + the 44
wrong patches (the critic cannot see wrongness; only emptiness and non-finish). Harness mapping: `LoopAgent
max_iterations: 3` over [solver, verifier] where the verifier's instruction says "if git diff is non-empty and the
reproduction passes, submit and reply DONE; otherwise reply CONTINUE" (the harness's loop exit is a text reply; the
repeat sees the full history, which is the opposite of Devstral's fresh attempt, so the instruction must say "the
previous attempt failed; change the approach, do not repeat its commands"). Budgets for the E4B: 20 min / 60 calls /
120 turns (120-task projection must stay <= 10 h). Predicted effect: E4B 8/75 -> 12-16/75 (the plan's estimate; the
Devstral analogue says ~+4 % of instances). Kill: projection > 10 h, or < +3 on 75 replica tasks.

### A6. Harness-design study (arXiv:2609.20804): what a 30B model needs
Mechanism (Nemotron-3 30B, Verified, 128k, tier-4 context): full harness 25.2 %; planning OFF 13.6 % (-11.6);
bash-only 10.2 % (-15.0). Planning = a persistent plan through an update_plan tool + "for tasks of 3+ steps the FIRST
action must be update_plan; exactly one task in progress; resend the complete list each call". Without planning the
30B's median trajectory fell from 40 to 5 turns and runs ending without any edit rose from 27.8 % to 68.6 %
(bash-only 75.4 %); 66 % of bash-only Terminal-Bench runs ended after calls the harness could not execute. Context
tiers at 32k: none 9.4 %, elision 20.6, elision+recall 20.8, summarisation 23.8, elision-then-summarisation 21.2;
making elided content recoverable gave nothing. Stuck detection: reminder at 5 identical calls, termination at 8.
Base prompt content (paraphrased): explore with list/glob/grep/read before acting; read a file before editing it;
prefer targeted edit_file over write_file; run focused tests; end with a short summary of what changed and how it was
verified; never claim a test passed unless run; stay in the workspace.

**Card TTC5 — a written plan as the first act, no tool needed.** Bucket: NO_EDIT (planning cut never-edit runs from
68.6 % to 27.8 % for a 30B model: the largest single-lever number in the corpus). Harness mapping: prompt text only:
"Your first message contains a numbered plan of at most 5 steps (locate, reproduce, edit, verify, submit) with the
file and function you expect to change, then the first tool call. Keep exactly one step in progress; when a step is
done, say so in one sentence before the next call." The demonstration prompt (E2) shows this. Predicted effect: +1 on
the 31B (ceiling in NO_EDIT is 1-3; v5 already asks for a specification step without a tool call), more on the E4B.
Cost: ~80 output tokens once. Kill: NO_EDIT unchanged.

**Card TTC6 — the stuck reminder is ours to write.** Harness mapping: the harness has no stuck detector; the prompt
rule "never repeat a failed call; after 5 search/read calls without an edit, make your best-guess edit" is the
substitute (v5 has it in CALL PLAN form; 09a shows after-budget edits still happen 6/53). The structural substitute
is E1/E2's demonstration of tempo. Kill: n/a.

### A7. Loops (SWE-smith arXiv:2504.21798, SWE-Protégé arXiv:2602.22124)
SWE-smith: > 25 % of SWE-agent-LM-32B trajectories contain a repeated base-command run of length >= 10 (Claude 3.7
< 4 %); 73 % of the longest runs are file-view paging; a scaffold that warned at 4-6 repeats and resampled at 6-8
reduced repetition but not the resolve rate. SWE-Protégé: loop metric = fraction of trajectories with a contiguous
repeated normalised-action run longer than L (grep/find/view collapse into one navigation class); post-SFT 31 % (> 10),
post-RL 0.8 %; penalty allows the first streak 15 and later streaks 8 before costing reward; mean steps 60 -> 20.

**Card TTC7 — the navigation-streak rule.** Bucket: NO_EDIT search loops (fastapi_14306: 28 reads, never edited).
Harness mapping: prompt text: "grep, ls, read_file count as one kind of action. Never make more than 6 of them in a
row: after 6, edit." and data rule D7 (drop training episodes with a navigation streak > 8). Predicted effect: 31B
+0 to +1; the SWE-smith scaffold result (less repetition, same resolve rate) says do not expect more. Kill: n/a.

### A8. Gemma 4 guidance and instruction-following evidence (what the prompt length should be)
- Google's pages state no limit on system-prompt length or rule count; the model-card example system prompt is one
  line; thinking depth is steerable by instruction (a "LOW" instruction cut thinking tokens ~20 %); recommended
  sampling T 1.0 / top_p 0.95 / top_k 64 (we run T 0.2; other teams measured T 0 and 0.4 worse than 0.2).
- Tech report Table 5 (thinking): IFEval 98.9 (31B) / 96.7 (E4B); **IFBench 76.0 (31B) / 44.0 (E4B)**; tau2-telecom 69.3
  / 18.4; Terminal-Bench Hard 36 / 8. Simple instruction following is saturated at every size; the hard set halves
  from 31B to E4B. RULER 32k: 96.8 / 95.2 (context length is not the E4B's problem).
- ManyIFEval (arXiv:2509.21051): the probability that ALL n instructions are satisfied decays roughly like a product of
  per-rule rates: GPT-4o 0.94 -> 0.57 -> 0.21 at n = 1 / 5 / 10; Claude 3.5 Sonnet 0.95 / 0.72 / 0.48; Gemma2-9B 0.91 /
  0.37 / 0.04; Gemma2-2B 0.80 / 0.08 / 0.00. Size alone does not explain it (Qwen2.5-72B 0.02 at n = 10).
- IFScale (arXiv:2507.11538): at 50-100 instructions frontier models still hit 93-99 % per instruction, small/fast
  models 42-78 %; errors are mostly omissions; later instructions are violated more (last-third/first-third error
  ratio 1.5-2.2 for small models at 50-100 instructions).
- Lost in the Middle (arXiv:2307.03172) and the multi-turn study (arXiv:2505.06120): information in the middle of a
  long prompt is used least; instructions spread over turns degrade more than one consolidated statement.

**Card TTC8 — count the rules; put the five that matter first and last.** v5 carries ~45 imperative bullets. By the
ManyIFEval shape the chance that the 31B obeys all of them in one run is small even at 95 % per rule; the E4B (IFBench
44) is worse. Harness mapping: (a) E3 control = 20-line prompt (does rule count matter at all?); (b) in every prompt,
the five rules with measured consequences come first (no test/config edits; write_file only under /workspace; one
unique old_string copied from a fresh read; edit before the budget ends; submit_patch then one sentence) and are
repeated in one line at the end (primacy + recency); (c) E4B prompt <= 400 tokens with <= 8 rules and one example.
Predicted effect: unknown sign on the 31B (that is why E3 exists); E4B: fewer nudges and hallucinated tool names.
Kill: E3 <= v5 - 3 means rules matter and the long prompt stays.

### A9. Not transferable (and why)
SWE-Replay archives and majority voting (multi-sample), Fail-Fast's learned monitor (no Python), SWE-Protégé's expert
calls and RL rewards, harness-level stuck detection and context tiers (ours is fixed: compaction at 14k, keep 5),
TestPrune's coverage-based selector, Devstral's fresh-attempt rerun (our LoopAgent repeats see the history).

## Part B — data recipes as rules (what each paper actually filtered)
| Paper | Keep / drop rule | Numbers |
|---|---|---|
| SWE-Gym (2412.21139) | resolved-only rejection sampling; keep all successes per task (dedupe to 1/task gave 294 vs 491 and was worse); T 0.2-0.8 sampling; 32k training context | 491 trajectories -> +8.8/+12.4/+13.6 at 7B/14B/32B; resolved trajectories are not shorter than failed ones (18.6k vs 17.2k tokens) |
| SWE-smith (2504.21798) | resolved-only; 75-step cap; **at most 3 trajectories per task instance**; no loop or tool-error filter; student keeps only the 5 most recent tool outputs | 6,457 resolved of 17,906 attempts -> 5,016 kept; 40.2 % Verified (32B); issue-text style matters, difficulty does not; showing the failing test in the issue made the student skip reproduction (-66 %) |
| SWE-Lego (2601.01426) | **error masking: mask the loss on the assistant turn whose result was an error (regex over terminal output), keep it in context, keep the recovery turn; do NOT mask repro/test failures**; add semi-resolved trajectories (fail tests, but 100 % gold-file recall); remove resolved trajectories that edit tests; curriculum by turn count (0-50 / 50-70 / 70-100) | masking +2.8 (8B) / +3.8 (32B) with curriculum, +2.4/+3.0 alone; semi-resolved +1.2 (4.0k added to 14.1k); test-edit removal 14.6k -> 14.1k, +0.6 |
| SWE-Prime (2608.27449) | score = mean of 5 terms: inspected before first edit AND tested after last edit (binary); tool-call success-rate percentile; **0 if any two adjacent calls are identical**; 0 if git history reveals the fix before the first edit; patch no larger than gold in files and lines (min(F_gold/F_model,1) x min(L_gold/L_model,1)); then cluster issues by embedding and take the top per cluster; stage 2 keeps only segments an LLM scores >= 7/10, loss only on kept segments | 10 % curated 53.2 % vs 100 % resolved 51.0 % vs random 10 % 41.2 % (Qwen3-Coder-30B); retention 5/10/20/30 % = 46.2/50.2/49.6/49.2 |
| FLARE (2609.23808) | rank trajectories by a process score from a 4B generative reward model: penalises missing/narrow validation after non-trivial changes, shallow checks (only "it runs"), ignored failure signals, premature completion, wrong tool when a native one exists, ordering errors; top 3k of 18k | 53.0 vs 45.0 Verified (random top-3k) and 47.0 (rubric critic); ablation: severity -8.5 %, error importance -7.2 %, action rarity -6.1 % |
| Open-SWE-Traces (2606.16038) | drop: environment exceptions, iteration-limit or early-ended runs (even if resolved), empty patches, test-patch edits, illegal concurrent calls, repeated tool-usage errors; git-hacking AST scan of bash (reflog/blame banned; log/diff context-restricted) removed ~27 % (207k -> 151k); full corpus (resolved + unresolved) beat resolved-only by +2.1 to +7.5 | harness switch at train vs eval costs 1.0-4.2 (Verified) / 0.7-4.6 (Multilingual) points; OpenHands-trained models loop 5-10 % of the time |
| SWE-Protégé (2602.22124) | rejection sampling, resolved-only, ~4.8k trajectories; LoRA/QLoRA underperformed full SFT at 7B; loop metric as above | post-SFT loop rate 31 % (> 10 repeats) |
| Devstral (2509.25193) | two-stage SFT: stage 1 on a heuristic first-level filter, stage 2 only on the strictest filters, criteria undisclosed | iteration cap 50 sufficient |

Rules adopted in `FT_DATA_SPEC.md` (D1-D9): resolved-only with <= 3 per task (SWE-smith); keep all successes rather
than dedupe to one (SWE-Gym); error masking on tool-rejection turns only (SWE-Lego); the five SWE-Prime terms as a
rank key, with the gold-size term computable on the 129 public tasks; Open-SWE-Traces' drop list and git-hacking scan;
exact harness rendering (scaffold mismatch costs 1-5 points; our tools and JSON shapes, compaction-shaped windows);
navigation-streak cap (SWE-Protégé); semi-resolved localisation prefixes as an optional 10-20 % slice (SWE-Lego).
