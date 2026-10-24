# 07 — Forum + public-notebook intelligence, round 2 (2026-10-18, day 25)

## Leaderboard (public, 58 tasks) as of 2026-10-18
#1-2 0.24 (Yurnero, Yike Xu); #3-29 **27 teams at 0.22**; #30-49 at 0.20; 3,124 teams. Our 12B baseline (ref 57334428): **0.08**.
Ties are ordered by earlier submission, so "top 10" in practice means 0.24+ (14/58) held on the private 62, or 0.22 submitted early.

## The public 0.22 configuration (flexonafft, "Budget-Aware Coding Agent v2", 175 upvotes; lineage: matterhorn3838 "SuperAgent" 0.18 <- Wilmer Henao "Budget-Fit Single Agent" 0.18 <- official sample prompt)
- `gemma-4-31b-it-qat-w4a16-ct`, single LlmAgent, all 9 tools declared (graph tools present but the prompt forbids them), no sub-agent, no skills, no adapter.
- sampling: temperature 0.2, top_p 0.95, max_output_tokens 8192, thinking_budget 4096, include_thoughts true.
- eval_config: timeout_seconds 240, max_tool_calls 28, max_time_minutes 8, max_turns 80.
- Prompt structure (full text in `raw/top_notebooks/flexonafft_*/`): "smallest correct change to the SOURCE code so the hidden tests pass; the issue's exact names/messages/types ARE the spec" -> HARD LIMITS (28 calls / 8 min; an edit in the tree counts even without submit_patch; never touch tests; never run a full suite; never look outside /workspace; never use graph tools) -> CALL PLAN (calls 1-8 locate+read, 9-12 edit, **must have edited by call 12**, 13-20 verify/correct, >20 no new exploration, finish with git diff + submit_patch) -> PROCEDURE (1 extract the spec with no tool call; 2 locate with git grep -nF batched into ONE run_command, read ~40-line regions, read one caller/test; feature tasks copy the nearest sibling incl. registration points; 3 edit with exact old_string, retry smaller, after 2 failures use an inline python heredoc that asserts the old text occurs once; parallel implementations; docs_src for FastAPI docs tasks; 4 verify in <=2 calls with `timeout 150 python -m pytest file -x -q -k kw`; ignore pre-existing failures; 5 git diff, confirm only source changed, submit, confirm patch_size>0) -> DECISION RULES (literal reading of ambiguous issues; edit where the wrong behaviour is produced; if search returns nothing edit the best candidate anyway; never conclude nothing needs to change).
- Measured rationale from the Budget-Fit author (129 local runs at scorer speed): only ~half of eventual fixes exist after 4 min -> 8 min cap; runs still exploring after many calls almost never succeed -> 28 calls; **no source edit by call 12 => 87% failure**; max_output 16384 makes vLLM reject long requests (prompt+max_tokens > 32,768); timeout_seconds 240 because (pre-0.2.11) the grading pytest used the same timeout and `requests` test files need ~100 s; graph tools return nothing on the Sep builds.
- Variants: honghanhhh v3 (same config + "parallel implementations" rule + `git status --short && git diff` + /tmp scratch rule) scored **0.18** (titled 0.24); lynnsakurai "bounded rescue" 0.18; jvnhonglei reproduction 0.20. => prompt-only edits on top of 0.22 are inside the ±2-task noise.

## Harness facts learned since Oct 16 (verified in threads)
- **Build drift matters** (kimdonggyu1255, 748323): same 314 graph-tool calls returned results 82 -> 11 -> 270 -> 270 times across the Sep 25 / Sep 30 / Oct 8 / Oct 9-12 wheelhouses; since Oct 8 the graph tools answer most queries (median answer ~5,800 chars, 122/314 contained a node from a gold-patch file, 87 in the top 3). "Don't use graph tools" was right for the Sep 30 build and wrong since Oct 8.
- Since Oct 8: **the harness drops edits to test files from the submitted patch** and prunes the repo listing; **include_thoughts:false no longer disables thinking** (host confirmed, intended) — `thinking_budget: 0` is the off switch. swegemma 0.2.11 (Oct 12 repack): verification has its own 300 s limit.
- Budget-Fit run on the Oct 9 build: 105 of 524 edit_file/write_file calls rejected with "mandatory input parameters are not present" (ADK rejects before running), from 15 tasks, mostly byte-identical resends (up to 14x); only 2 involved triple quotes; in 47 the code leaked into argument names (argument boundary loss between model output and parser).
- `budget_warning` is appended once <=10 calls remain (needs max_tool_calls >= 20); it is call-based, not time-based; models ignore get_status instructions (750490).
- **Skills risk** (750350): one user's submission that only added a stdlib skill + prompt lines scored 0.00 (0.15 before); another keeps a skill since early Oct with best 0.15 and later 0.06-0.12; a third sees 0.18 -> 0.03/0.05 for "anything other than plain main agent with system.md". Unexplained; treat skills as high-variance until our own local smoke shows them invoked and harmless.
- Verification runs only the test files selected by test_patch (regressions elsewhere are not checked; 750175, unanswered by host).
- Scorer environment for fastapi public tasks resolves 0/64 gold patches with the published image vs 107/129 with pinned deps (750509) — consistent with our 21/129 soundness; the host says the hidden set validates 100%.
- Task anatomy (osama133 notebook, 743957): 57% of public fixes are single-file <=20 lines; **in ~76% the issue names neither the file nor the function**; ~1 in 6 touch async code; issue length does not predict fix size.
- Domain-shift question (745796) remains unanswered by the host.

## What this changes for us
1. Our 12B line is far below the cluster (0.08 vs 0.22). The 31B is mandatory for the main line.
2. Day-2 slot: submit an exact reproduction of the public 0.22 package (anchor + noise calibration), not our prompt.
3. Our prompt v2 and the 0.22 prompt agree on most rules; the 0.22 prompt adds the CALL PLAN with a forced edit by call 12 and the "never conclude nothing needs change" rule — both evidence-backed; adopt them.
4. Graph tools are usable again since Oct 8 (but 5.8k-char answers eat context); a bounded use (one `get_code_neighbors` on the located symbol to find callers/parallel implementations) is worth one local A/B.
5. Skills: keep, but gate on the local smoke (are they invoked? do they add latency?) and never ship them in the same submission as another change.
6. Re-check every "known fact" against the current wheelhouse build before each submission (build fingerprint notebook: kimdonggyu1255/gemma-4-agent-instruments-kit).
