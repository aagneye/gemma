# 15. Public recipe at LB 0.22: Budget-Fit V5 + 40 tool calls (read Nov 16)

Source: Kaggle notebook "LB 0.22 | 3 tweaks, 40 tool calls, no training" (author bliverrigpdoge, run Nov 14 2026),
https://www.kaggle.com/code/bliverrigpdoge/lb-0-22-3-tweaks-40-tool-calls-no-training. It writes a 4-file bundle and
credits verracodeguacas' Budget-Fit Single Agent (version 5), the same bundle we ship as Budget-Fit V5.
A second notebook with the same lever: victorzhong0110 "Gemma4 Pack LB 0.22 40 Tool Calls" (Nov 16).

## What differs from Budget-Fit V5 (summary, not a copy)
- `eval_config.yaml`: `max_tool_calls` 28 → 40. `max_time_minutes` 8, `timeout_seconds` 240 and `max_turns` 80 are unchanged.
- `configs/sampling.yaml`: unchanged (T 0.2, top_p 0.95, thinking 4,096, max output 8,192).
- `agent.yaml`: unchanged (9 tools).
- `prompts/system.md`:
  - the budget heading and its first line say 40 tool calls instead of 28;
  - step 4 of the workflow ends with a one-word reply after `submit_patch` instead of a summary;
  - a new budget bullet: when a tool reply says the call budget is used up, call `submit_patch` at once;
  - a new last section, "the task statement, verbatim", holding `{problem_description}` and `{hints?}`. These are ADK
    state templates. Our harness fills them (`swegemma/harness/agent_runner.py:677-681` sets `problem_description`
    from the task's problem statement and `hints` when present), so the issue text stays in the system prompt after
    the history is compacted at 14,336 tokens.

## Why it could work where our lines did not
- More calls act on every task that Budget-Fit ends at the 28-call cap; our prompt lines only changed how calls are used.
- The pinned issue text matters after compaction, which our traces show on most long tasks (`research/raw/14_probe_tool.md`).

## Risks
- Runtime: tasks that stopped at 28 calls now run on toward the 8-minute cap, so the whole run gets longer. v6 (+14 %
  tokens) and the adapter (decode ×1.14–1.21) both exceeded Kaggle's 12-hour limit. Its LB score shows it finished at
  least once; failed runs are not visible on the leaderboard.
- `build_v4.py check` refuses `{` in prompt files on purpose (state templates); this bundle needs that check relaxed for
  the two known keys.

## Status
Nov 16: the user approved a test. The bundle is `submissions/pub40` on the VM; it was extracted with
`vm/bundle_from_notebook.py`, the digest matches, and the prompt is tracked as `vm/prompts/pub40.md`. Confirmation 2
(`vm/confirm2.sh`, two passes against Budget-Fit on the 77 EVAL tasks, runtime measured) started at 15:13 UTC.

Nov 18: **rejected.** −3 and −1 solved against Budget-Fit (mean −2.0 per pass; the rule needs +3), with calls ×1.12,
tokens ×1.14 and time ×1.11. The extra calls help only on the tasks Budget-Fit ends at 28 calls (+0 and +2 there).
Details are in `research/STATE.md` (Nov 18 05:45 entry).
