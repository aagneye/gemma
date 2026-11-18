# 17. The clock ledger: where Budget-Fit's moves and minutes go

Written Nov 18 2026, 15:00–16:10 UTC. No GPU was used.
- **Asked by the user (Nov 18):** moves and minutes are precious, like a chess clock. Couple our own work with Budget-Fit's economy of time and moves to score higher.
- **Sources** (all on the VM under `results/replica/`):
  - Budget-Fit V5, 4 passes on the 77 EVAL tasks: `cf1_base_a`, `cf1_base_b`, `cf2_base_a`, `cf2_base_b` (308 games, scale 9, after the Nov 12 cutoff fix);
  - our stack S2 (E1 + R1 + T2 + thinking 2,048): `cf1_stack_a`, `cf1_stack_b`;
  - the public 40-call recipe: `cf2_cand_a`, `cf2_cand_b`;
  - Budget-Fit and our v7 on the 109 EVAL tasks: `bf5_eval`, `v7_eval`;
  - Screen B on the 48 dev tasks: `sB_base`, `sB_t1` (thinking 2,048).
- **Tool:** `vm/clock_ledger.py` (new). Its output for the 4 Budget-Fit passes is `research/runs/bf5_cf/clock.md`.
- **Words:** a game is one task run. A move is a tool call the harness counts. A minute is Kaggle-equivalent (run seconds ÷ 9 ÷ 60).

## 1. Harness facts behind the ledger
Read from the harness source (`harness/src/swegemma-0.2.11/swegemma/`).
- **What counts as a move:** every `run_command`, `read_file`, `write_file`, `edit_file` and graph-tool call, also when the tool answers with an error.
- **What is free:** `get_status` and `submit_patch` (`tools/execution.py:76,119`). A garbled call (a missing parameter) is refused before it is counted.
- **After the last move:** further calls answer `BudgetExceeded`, "Tool call budget exhausted (28 calls)" (`context.py:480`). The session goes on until Gemma stops calling tools.
- **The clock:** wall clock from the start of the session. The time Gemma takes to write counts. The harness never shows the clock; only `get_status` returns `time_seconds_remaining`.
- **The warning:** from 10 moves left, every counted tool answer carries `budget_warning`: "Only 10 tool call(s) remaining (18/28 used). Finalize your edits and call submit_patch soon." (`tools/base.py:47-63`). With 28 moves it starts at move 18.
- **The end:** without `submit_patch` the working tree is graded, also after a timeout.
- **Size limits:** `read_file` returns at most 150 lines; a command's output is cut at 5,000 characters (`budget.py:30-31`).

## 2. Budget-Fit's ledger (308 games)

**How the games end, per pass**
| Outcome | Pass 1 | Pass 2 | Pass 3 | Pass 4 | Mean | On tasks solved in some passes only |
|---|---|---|---|---|---|---|
| Solved | 41 | 44 | 44 | 44 | 43.25 | 9.25 |
| Wrong fix inside the budget | 29 | 25 | 24 | 26 | 26.00 | 5.25 |
| Blank answer (no source file changed) | 2 | 5 | 2 | 4 | 3.25 | 1.50 |
| Out of time | 4 | 2 | 4 | 0 | 2.50 | 1.50 |
| Wrong fix on the last moves (cap reached) | 1 | 1 | 3 | 3 | 2.00 | 0.50 |

- **Clock-or-move losses: 7.75 of 33.75 losses per pass (23%).** The other 26 are wrong fixes handed in inside the budget.
- **Tasks:** 34 are solved in all 4 passes, 25 in none, 18 in some (7 once, 3 twice, 8 three times).
- **Ceiling:** 3.5 clock-or-move losses per pass are on tasks Gemma solves in other passes. Games on those tasks that stay inside the budget are solved 37 of 58 times (64%), so perfect clock play is worth about **+2.2 solved per pass**, and never more than +3.5.
- **6 tasks lose only on the clock or on moves:** `azurefunctionspythonlibrary_172`, `craystack_16`, `soupsieve_71`, `soupsieve_88`, `sqlparse_664`, `sqlparse_676`.

**Wins are quick**
| Minutes used | Games | Solved | | Moves used | Games | Solved |
|---|---|---|---|---|---|---|
| under 3 | 179 | 125 (70%) | | up to 10 | 55 | 39 (71%) |
| 3 to 5 | 82 | 36 (44%) | | 11–15 | 70 | 51 (73%) |
| 5 to 7 | 31 | 10 (32%) | | 16–20 | 57 | 33 (58%) |
| 7 or more | 16 | 2 (12%) | | 21–27 | 63 | 24 (38%) |
| | | | | all 28 | 63 | 26 (41%) |

- A solved game takes a median of 15 moves, 125 seconds and 4,930 written tokens. An unsolved one takes 22 moves, 215 seconds and 7,756 tokens.
- First source edit at moves 1–6: 72 of 101 solved. Moves 7–12: 53 of 91. Moves 13–18: 30 of 50. Move 19 or later: 14 of 42.
- **Moves run out before time.** 63 games (20%) use all 28 moves; 10 games (3%) run out of time.

**The clock is the text Gemma writes**
- 99% of a game's time is model time; tools take under 1%.
- Fit on 6,682 model steps: seconds per step = 1.9 − 0.07 per 1,000 prompt tokens + 2.24 per 100 written tokens. So one written token costs about 22 ms, and the size of what Gemma reads costs nothing.
- The median step writes 114–122 tokens. Steps of 2,000 tokens or more are 145 of 6,682 (2%), and they hold 20% of the tokens of solved games and 26% of unsolved ones. They are long thinking: a median of 9,500 characters of thinking and 550 of tool arguments.
- 50 steps use up the whole thinking budget of 4,096 tokens, in 37 games (17 solved). One such step costs about 100 seconds of the 480.
- Games that write under 4,000 tokens: 59 of 75 solved. 12,000 or more: 6 of 38.
- Timeouts are games with several such steps, for example `craystack_16`: 631, 98, 4,133, 689, 528, 4,132 and 4,332 tokens in 7 steps.

**What a move costs (medians)**
| Move | Written tokens | Seconds |
|---|---|---|
| Read a file | 76 | 2.4 |
| Search | 97 | 3.0 |
| Run Python | 33 | 1.4 |
| Run tests | 58 | 2.2 |
| Edit a file | 314 | 7.8 |
| Write a file | 384 | 9.4 |
| Submit | 36 | 1.3 |

- 438 of 454 `write_file` calls create a new scratch script (1.4 per game).

**At the warning (move 18)**
| State at the first warning | Games | Solved |
|---|---|---|
| A source edit is already made | 107 | 53 (50%) |
| No source edit yet | 55 | 17 (31%) |

- With no source edit yet, the next move is a read in 24 games (4 solved), a search in 14 (7 solved) and an edit in 14 (5 solved). 12 of the 55 games end as a blank answer.
- After the cap message, Budget-Fit's next call is `submit_patch` in 23 of 27 games.

## 3. Our own changes under the clock view
| Change | Clock view | Measured |
|---|---|---|
| R1: read with a line range (SWE-agent's 100-line window) | Saves reading size, which is free. Costs a move: a search before each read | In S2: searches 3.9 → 5.3 per game, calls 19.3 → 20.5, games using all 28 moves 20% → 25%, blank answers 3.25 → 6.0 per pass |
| T2: read the existing tests first | Costs moves | Not followed: tests were read before the edit in 28% of games, against 27% without the line |
| E1: small edits, never resend a broken edit | Aims at broken-edit loops | Games with such a loop are solved as often as the rest (12 of 22). Under E1 one loop still ran 65 times (`soupsieve_80`, a task Budget-Fit always solves) |
| "At the warning, edit now" (v7's budget rule) | Aims at blank answers | Not followed: with no edit at the warning, the next move was an edit in 2 of 27 games (7%), against 2 of 20 (10%) for Budget-Fit on the same 109 tasks |
| 40 moves instead of 28 (public recipe) | Buys moves with time | Blank answers 3.25 → 0 per pass, but out-of-time 2.5 → 7.5 and games of 12,000+ tokens 12% → 19%; 41 and 41 solved against 44 and 44 |
| Thinking cap 4,096 → 2,048 tokens (T1) | Halves the cost of one long thinking step | Gemma reaches the cap 3–4 times as often: 30 steps in 19 of 48 games against 8 in 8 (Screen B); 89 steps in 51 of 154 games (S2). Tokens ×0.95. Out-of-time 2.0 against 2.5 per pass (S2). Dev tasks: +4, then −1 on the re-run |

- **Lesson:** Gemma does not follow clock rules written in the prompt. Settings change its play, but the two we have (more moves, shorter thinking) show no gain we can measure.
- **Why S2 lost (−1 and −1):** R1 costs moves and T2 was not followed. Of S2's 7 failed games on tasks Budget-Fit always solves, 3 are blank answers at the cap and 1 is the 65-call loop.
- **The trained adapter cannot be coupled:** on Kaggle's L4s it writes each token 14–21% slower, the bundle went over the 12-hour limit, and on EVAL it solved 39 against 41.

## 4. Papers on budgets, against our numbers
| Paper | Finding | Ours |
|---|---|---|
| SWE-agent (arXiv:2405.15793) | Solved runs are short: a median of 12 steps, against a mean of 21 for failures | The same: 15 moves against 22 |
| SWE-smith (arXiv:2504.21798) | 53% of a 32B model's failures hit a cost, step or time limit; repeat warnings cut the repeats, not the failures | 23% of Budget-Fit's losses are clock-or-move losses; warning rules were not followed |
| Devstral protocol (arXiv:2509.25193) | A cap of 30 steps solves 36.8%, 50 steps 46.8%, 100 steps the same | 28 → 40 moves: no gain here |
| Harness-design study (arXiv:2609.20804) | A 30B model often ends with no edit; reaching an edit is most of the gain | Blank answers are 3.25 per pass; removing them (40 moves) did not add solved tasks |
| Fail-fast (arXiv:2608.03222), SWE-Replay (arXiv:2601.22129) | Restart or re-sample a failing run | Not possible: a bundle cannot restart a run |

## 5. Conclusion
- **The chess-clock view is right about our own prompts.** v7 lost 7 of its 9 losses to the call cap or the clock (`vm/arms_report.py` on `bf5_eval` and `v7_eval`), and S2 lost through extra searches.
- **Budget-Fit itself has little left to win on the clock:** about +2.2 solved per pass with perfect play. The bar to ship is +3, and identical passes differ by up to 3.
- **No candidate is in reach.** Prompt rules are not followed; more moves turn blank answers into timeouts; the thinking cap saves 5% of the tokens and no timeouts.
- **Decision (user, Nov 18):** record the findings, no GPU test. Budget-Fit V5 keeps the daily slot. `submissions/budgetfit_t1` (thinking 2,048) stays untested on the 77 tasks.
- **What stays:** `vm/run_replica.sh` now writes `clock.md` after every run.

## 6. Limits
- **Scale:** the 22 ms per token is a replica figure divided by the scale of 9. On Kaggle's L4s we measured 39.8 tokens per second for one request (25 ms per token), so Kaggle seconds are about 13% above the figures here.
- **Source edit:** the first-edit table counts tool calls only. A fix made with `sed -i` is in the row "no source edit by a tool call" (4 solved games).
- **The warning table shows what happened, not what causes what:** a game that reads after the warning may already be lost.
- **Task classes** (always, sometimes, never solved) come from 4 passes. More passes would move some tasks between classes.
- **EVAL tasks were only read.** Nothing was tuned on them.
- **Independent check:** a separate review of these numbers put the chance that a no-effect candidate passes the +3 rule at about 6%, and a true +1 at about 15%.

## 7. Commands
```bash
cd /mnt/biohub/kdata/gemma4
# the 4 Budget-Fit passes (section 2); the output is research/runs/bf5_cf/clock.md
python3 ~/gemma4_vm/clock_ledger.py results/replica/cf1_base_a results/replica/cf1_base_b \
        results/replica/cf2_base_a results/replica/cf2_base_b --thinking 4096 --out tmp/clock_test/bf5_cf.md
# S2 and the 40-call recipe (section 3)
python3 ~/gemma4_vm/clock_ledger.py results/replica/cf1_stack_a results/replica/cf1_stack_b --thinking 2048
python3 ~/gemma4_vm/clock_ledger.py results/replica/cf2_cand_a results/replica/cf2_cand_b
# Screen B, thinking 4,096 against 2,048
python3 ~/gemma4_vm/clock_ledger.py results/replica/sB_base --thinking 4096
python3 ~/gemma4_vm/clock_ledger.py results/replica/sB_t1 --thinking 2048
```
- The counts of searches, calls and tests read before the edit come from `vm/autopsy.py` records (`searches`, `calls`, `b_test_before_edit`).
- The v7 and cap-message counts come from the traces of `bf5_eval`, `v7_eval` and the 4 passes: the first call after the first `budget_warning` or `BudgetExceeded` answer.
