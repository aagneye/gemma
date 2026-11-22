# E4B side track: a bounded shot at the Small Model prize (approved by the user, Nov 22 2026)

Research behind it: `research/raw/20_small_model_prize.md`. Run ledger: `research/ledger/e4b_track.md`.
The main track (31B, round 2, the shipper, the Kaggle hold) is not touched by anything here.

## Why
- **The prize:** $10,000 for the best score on the hidden private tasks among entries whose base model is Gemma E2B or
  E4B. The entry must be one of our 2 final picks. Adapters are allowed. Ties go to the earlier submission. Deadline
  Dec 2, 23:59 UTC (Dec 3, 05:29 IST).
- **Where we stand:** our one E4B run (Oct 27, ref 57707213, our own long prompt) solved 1 of 58. The board's top is 7,
  31 teams have 6, 67 or more have 5 (Nov 21). The public Budget-Fit prompt on the E4B gets 4, 5, 4 for another team.
- **Speed:** one E4B fits one T4, so 4 tests run side by side: about 1,000 task-runs a day against 185 with the 31B.
  On Kaggle a run is only about 6 h shorter and shares the one-run-at-a-time queue with the 31B.
- **Honest odds:** 1 to 2 in 100. A pack-level entry cannot win: scores are small whole numbers, ties go to the
  earlier run, so a late entry must beat the whole field outright (about 9 of 62 where the pack averages about 4.6).
  That needs an agent 1.6 to 2 times as good as the public one. If screen 1 shows such a gain, about 1 in 10.
- **The one lever with public evidence that we never tried:** thinking switched off (one team: 16 against 10 solved of
  114 practice tasks; another: a tie between 1,024 and 4,096). Adapters make the E4B worse for everyone, us included.

## Rules of the track
1. **Idle resources only.** Tests start when round 2 has ended by its own word. The cards go back to the main track the
   moment it asks.
2. **No Kaggle run without a pass.** One run for a bundle that passes the confirmation; the bundle freeze is Nov 28
   for that one bundle.
3. **No training, no Kaggle GPU, no test on EVAL tasks before the confirmation.**
4. **Prompt text:** only the texts listed below run without a new review by the user.
5. **Final picks stay the user's call on Dec 1.** An E4B pick replaces a second Budget-Fit run (about 0.9 task on the
   main board).

## Bundles (`vm/e4b_build.sh`)
| Bundle | What it is |
|---|---|
| `e4b_bf5` (base) | Budget-Fit V5 files with three changes: model line → `gemma-4-e4b-it-qat-w4a16-ct`; the three graph tools off the tool list; prompt line 12 ("Do not use `search_similar_code`, …") removed. Thinking 4,096. |
| `e4b_bf5_t1k`, `_t256`, `_t0` | the base with `thinking_budget` 1,024 / 256 / 0. Nothing else differs. |
| `<base>_e1r1` (screen 2) | the same build from `budgetfit_e1r1`: the two lines approved on Nov 10–11 (reads with a line range; small edits, no resend of a garbled call, compile check). |

- **Why six tools in the base** (correction of the first draft, which kept nine): the public E4B runs that scored 4–5
  used six tools. With nine the E4B could call `get_code_subgraph`, the one tool with a list argument, and vLLM 0.19.1
  hangs on some list items (`vm/README.md`); only the 31B was cleared for that.
- **Thinking 0** makes the harness send `enable_thinking: false` and no thinking budget
  (`adk_submission/resolvers/generation.py`; seen in the stand-in test of `vm/e4b_selftest.sh`).

## Tests (`vm/e4b_chain.sh`, tmux `e4b_chain`)
All runs: one E4B server per card (ports 8001–8004), one task at a time per card, clock scale 3 (Oct 26: 69 of 71
tasks agree with Kaggle), internet cut off, run log + clock ledger + request log per arm.

| Stage | Question | Arms | Tasks | Rule |
|---|---|---|---|---|
| Screen 1 | Does less thinking make the E4B solve clearly more on unfamiliar projects? | thinking 4,096 / 1,024 / 256 / 0 | dev halves A and B: 64 + 64 tasks the 31B solves, 95 projects (`results/lists/e4b_devA.txt`, `e4b_devB.txt`) | The best level becomes the base at +2 solved per 64 tasks over `e4b_bf5`; else `e4b_bf5` stays |
| Screen 2 (only if it and the confirmation fit the time box) | Do the two E1+R1 lines add to it? | base ×2, base + E1+R1 ×2 | both halves | E1+R1 joins at +2 per 64 and failed `edit_file` calls per task at most 0.8 × the base's |
| Confirmation | Is the stack better than the pack's profile? | `e4b_bf5` ×2 against the stack ×2, two waves, cards swapped in the second | the 77 EVAL tasks (`eval_ts01.txt`), 4 paired passes | **Pass = mean gain of +3 solved per pass (`verdict.py`) and at most 270 Kaggle-seconds per task (9 h for 120 tasks)** |

- **Stop rules:** no arm reaches +2 per 64 → stop, cards released, nothing sent, the E4B stays parked. Time box Nov 27,
  18:00 UTC (23:30 IST): a stage starts only if it can end before it at the pace measured in screen 1.
- **Why 128 different tasks and not 64 twice** (correction of the first draft): same GPU time, more evidence, and the
  second half shows whether the first half's order repeats.
- **Result files:** `results/e4b/screen1.md`, `screen2.md`, `results/replica/e4b_confirm_verdict.txt`, `logs/e4b_chain.log`.

## Keeping away from round 2
- **When the chain may take the cards:** tmux `r2chain` and `r2notes` gone, none of round 2's processes alive, and
  `logs/r2_chain.log` holds `ROUND STOPPED:` after its last start line or ends with `chain_r2 done`. A missing session
  without that word starts nothing. Free memory is never the signal.
- **After a stop or a REJECT:** at once. **After an ADOPT:** 30 minutes later, and not while `results/e4b_wait.txt`
  exists. Never while a test still runs against the 31B server.
- **Giving the cards back:** the chain ends its arms and servers by itself within seconds when tmux `r2chain`,
  `r2notes` or `vllm` appears, or when `results/e4b_yield` exists. By hand: `bash ~/gemma4_vm/e4b_stop.sh`.
  Finished arms stay on disk; `tmux new -d -s e4b_chain "bash ~/gemma4_vm/e4b_chain.sh"` goes on behind them.
- Names: all tags, lists, bundles and tmux sessions of this track start with `e4b_`; port 8000 and tmux `vllm` stay
  the main track's. No file of the main track is changed (`daily_ship.py`, `chain_r2.sh`, `ship_adapter.sh`, the hold).

## After a pass (`vm/e4b_ship.sh`, tmux `e4b_ship`)
The bundle is validated, its private CPU notebook is pushed, and the notebook's zip is compared with the bundle file
by file. Then a dated line in `results/ship_schedule.txt` (the file made for the E4B slot) is kept for today's UTC date
until `results/ledger.csv` shows the run. `daily_ship.py` is not changed. **If the round-2 adapter holds the queue
(`ship_once.txt` or `ship_followup.txt` exists), nothing is handed over and the user decides which run gives way.**

## Checked before the chain was queued (Nov 22, no GPU)
`bash ~/gemma4_vm/e4b_selftest.sh` (with `PLUMB=1` for the last block): the task list is the same draw twice and holds
no EVAL task; the picker's rules on made-up runs; which ending a round-2 log shows (running, stop, REJECT, ADOPT,
stopped and started again); dry runs of every path of the chain and of the time box; the watchdog ends chain and arm
when a stand-in main-track session or the yield file appears; the ship script's dry run; and two arms on two tasks
against stand-in servers: each arm reaches only its own port, the internet is cut off, the requests carry six tools
and the bundle's thinking setting.
