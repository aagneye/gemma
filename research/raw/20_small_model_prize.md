# 20 — The Small Model prize: rules, the board, what others measured (read Nov 22 2026)

Asked by the user on Nov 22: are we eligible, what is the prize, how long does it take, is it worth it.
Sources: the Kaggle overview and rules pages, host thread 751104, the host's small-model leaderboard notebook
(`ryanholbrook/gemma-4-developer-agent-small-model-leaderboard`, updated Nov 21 23:53 UTC), threads 760014, 760595,
760471, 760140, the public notebook `dheerajpiduru/gemma-4-e4b-what-moved-the-score-and-what-didn-t` (Nov 18), and the
harness code in `scorer-host-venv` (swegemma 0.2.11, adk_submission 0.2.13). Forum texts are given in our own words.

## 1. Rules (settles the open points of `PLAN_TO_WIN.md`)
| Point | Answer |
|---|---|
| Prize | $10,000, on top of the main prizes |
| Who wins | the highest-ranking submission that uses Gemma E2B or E4B as its base model; the 12B does not count |
| Scored on | the private test set (host post 751104) |
| Condition | the entry must be one of the team's two final selected submissions (picked by hand or automatically); a team without one is dropped from the small-model board |
| Adapters | allowed, as in the main track |
| Deadline | the main track's: final submissions Dec 2, 23:59 UTC. The "Nov 12" on the overview page belongs to the paper track |
| Both prizes | an eligible entry stays eligible for the main awards and the paper track |
| Ties | the submission entered first wins (rules 3.7b; "same tie-breaking" in the prize text) |
| Winner's duties | code and write-up under an open-source licence that allows commercial use |
| Other limits | one submission a day, two final picks, team of at most five |

## 2. The board (Nov 21 23:53 UTC, top 100 shown by the host)
- 7 of 58 (0.12): 2 teams. 6 of 58 (0.10): 31 teams. 5 of 58 (0.08): ranks 34–100 and beyond (67 or more).
- About 1,150 teams have a small-model run (1,143 on Nov 17). Ours: 1 of 58 (0.01), rank about 1,048.
- The top has stood at 7 since Nov 17. Scores are cut to two decimals: n solved of 58 shows as 0.01, 0.03, 0.05, 0.06,
  0.08, 0.10, 0.12 for n = 1…7.

## 3. What other teams measured on the E4B
| Source | Setup | Result |
|---|---|---|
| Public notebook, Nov 18 | six Kaggle runs of one team | starter agent with the E4B: 3 of 58. Budget-Aware prompt and budgets with six tools: 4. The same without the stale line about graph tools: 5, and 4 on a second run of the same files. Own prompt edits: 3. Its own harness on the 31B: 12. |
| same | adapter distilled from 31B runs, 29 held-out tasks × 3 | plain 6 of 87, adapter 3 of 87; with the adapter 76 of 87 runs hit the call cap and 56 sent no patch |
| Thread 760014 (a team that withdrew), Nov 18 | 114 local tasks from the practice projects, 1,800+ runs | organiser baseline with thinking 4,096: 10 solved; with thinking off: 16; best own system 15. Ten runs of one config: 11–15, SD 1.52. Thinking 768–1,024 was best for their own systems. Hiding thoughts raised broken tool-call arguments from 3 to 132; a smaller output limit doubled edit errors. Adapters from a 31B teacher lost to the plain model. Prompt budgets ("finish within 9 calls") were ignored in 61% of tasks. Critic and arbiter stages broke as many tasks as they repaired. |
| Thread 760595, Nov 20 | 91 gradable practice tasks | baseline 8 of 91; 56 of its 83 failures had edited the right file; median 91 s and 11 calls of 80 (it submits early). Two mechanical checks after an edit: 11 of 91 locally, 0.03 against 0.06 on Kaggle (noise). All its E4B runs on Kaggle fall between 0.01 and 0.06; one config scored 0.06 and 0.03. |
| Reply in 760595 | about 2,000 task-runs | thinking 4,096 against 1,024: a tie, the lower one cheaper. A compile-check instruction was followed after 24% of edits. `write_file("/tmp/…")` is refused as a path traversal. |
| Thread 760471 (staff), Nov 18 | the queue | about 8–9 h waiting, 9–10 h run for a usual bundle, 2–2.5 h scoring; growing. An E4B run itself takes about 3.5 h (ours on Oct 24: 95 s per task). |
| Thread 760140, Nov 19 | an E4B bundle that ended in an exception | `max_tool_calls: null` and `max_time_minutes: null` in `eval_config.yaml` break the starter notebook's budget reader. Our bundles carry numbers. |

## 4. Reading
- **The pack's profile is the public Budget-Fit prompt with six tools**: 4–5 of 58. Our 1 of 58 came from our own long
  31B prompt, the same pattern as on the 31B (own prompts lose on unfamiliar projects).
- **Nobody shows a config clearly above the pack.** With about 1,150 teams and several runs each, a pack mean near 4.3
  and a run-to-run spread near 1.3 gives dozens at 6 and a few at 7, which is the board. A config with a true mean of
  6–7 would have shown 9 or more by now.
- **The private result is a fresh draw.** A run's public and private tasks differ, so a team's best public run is not
  its private score. With ties going to the earlier entry and scores of 0–9, a late entry must be strictly above the
  field: about 9 of 62 where the pack averages about 4.6. That needs an agent 1.6–2 times as good as the pack's.
- **The one lever worth a test: thinking off.** The 16-against-10 result is on the practice projects, which misled us on
  the 31B, and the board has not moved since it was posted. It is one setting, and we never ran 0 (our E4B runs used
  1,024 to 4,096). The test must be on unfamiliar projects.
- **Not worth a test:** adapters (three independent failures, ours included), critics and arbiters, more calls or time
  (the E4B uses 12 of 28 calls and 95 of 480 seconds).

## 5. Harness facts checked for the test
- `thinking_budget: 0` is valid (range 0–32,768) and stays 0: `adk_submission/limits.py` fills a default only when the
  key is missing. `apply_thinking_config_to_model` then sets `chat_template_kwargs.enable_thinking = false` and drops
  `thinking_token_budget`. `include_thoughts` no longer switches thinking off once a budget is set.
- Seen end to end without a GPU (`vm/e4b_selftest.sh`, stand-in servers): the 4,096 bundle sends
  `enable_thinking: true` with `thinking_token_budget: 4096`; the 0 bundle sends `enable_thinking: false` and no budget.
  Both send six tools.
- `get_code_subgraph` is the only declared tool with a list argument; vLLM 0.19.1's gemma4 parser hangs on some list
  items (`vm/README.md`). Budget-Fit never writes one on the 31B (0 of 2,999 replies); the E4B was never checked, and
  it invented tool names 11 times in our 75 Kaggle runs. Hence six tools for every E4B bundle.

## 6. Cost of an E4B final pick
A second Budget-Fit run in that slot is worth about 0.9 task on the main board (note 16). We are near rank 720 of
6,400; the top 10% gets a medal. The pick is the user's call on Dec 1.
