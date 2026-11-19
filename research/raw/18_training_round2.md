# 18 — Training round 2: the real fix at the moment Gemma goes wrong (Nov 18–19)

- **Plan (approved by the user, Nov 19):** `research/PLAN_ROUND2.md`.
- **Why:** Budget-Fit V5 is public; prompt and settings changes never beat it; training is the one lever left.
- **This note:** the measurements behind the plan, what the independent review changed, and the results as they arrive.

## 1. Where Gemma loses (207 failed TRAIN runs, `results/replica/bf5_train`)
| What happened | Runs |
|---|---|
| Every file of the real fix had been opened before the first source edit; the edit was wrong | 116 |
| The right files had been opened; no source file was ever changed | 32 |
| Only some of the files had been opened | 40 |
| The files were never found | 19 |

- In 148 of 207 failures (71%) Gemma was at the right place. It loses at the change itself.
- Real fixes are small: 1 source file in about 70% of tasks, median 12–19 changed lines.

## 2. Facts found while planning
- **The harness shortens the history.** ADK compacts when a prompt reaches 14,336 tokens. In the request log of
  confirmation 2, 144 summary requests in 220 connections; the next agent request drops from a median of 28 messages
  to 8. So about 4 of 10 runs are shortened, typically near step 13.
- **Gemma's chat template drops earlier thinking after a new user message** (`thinking_gate` in `chat_template.jinja`:
  thinking is rendered only for assistant messages after the last user message). A hint sent as its own message would
  erase all earlier thinking from the prompt.
- **An adapter's cost on the server follows the server's max rank, not the adapter's layers.** vLLM 0.19.1 wraps every
  supported linear module when LoRA is on (`lora/model_manager.py::_match_target_modules` uses the server's
  `--lora-target-modules`), and `lora/layers/base_linear.py::apply` always calls `add_lora_linear` with a buffer of the
  stacked rank. The scorer sets the max rank to the largest rank in the bundle. So only a lower rank makes a trained
  Gemma faster; trimming layers does not.
- **Round 1's examples had a form the model never sees:** 8-step windows, a hand-written summary of earlier steps, old
  tool results replaced by a stub, thoughts capped at 1,000 tokens, rewritten arguments and sometimes an invented final
  text (`prepare_data.py`, `convert_traces.py`).
- **Whole runs are short enough to train on as they are:** solved TRAIN runs measure 9.9k tokens at the median
  (p75 12.8k, p90 14.0k); 94 of 132 fit 12,288 tokens and 127 fit 14,336.
- **Timing:** a note run takes about 0.75 of a normal run (1,404 s against 1,871 s on the replica clock), about 10
  tasks per hour.

## 3. What the independent review changed (Nov 19)
A second reader checked the design against the code. Its findings, and what I did:

| # | Finding | Change |
|---|---|---|
| 1 | The note makes the prompt longer, and ADK compacts on the server's `prompt_tokens`: note runs would be shortened earlier than real runs | The relay lowers `prompt_tokens` in the reply by the note's size |
| 2 | Both note places vanish at compaction; after it the first user message is the summary, so the task cannot be recognised by its issue text | Tasks are also recognised by tool-call ids; blocks not yet applied move to the newest tool result |
| 3 | A field in a tool result is where Gemma ignores advice (the budget warning: 14 of 55 edit next) | Pilot rule: first block applied within 2 steps in at least 80% of noted runs, else position B |
| 4 | "File opened" is not "lines seen": reads stop at 150 lines; `write_file` is mostly scratch scripts | The note comes only when every line of every block was shown by an earlier `read_file` or command, and never after a command that wrote to a file of the fix |
| 5 | The move-12 deadline is not supported by the data (first edits at moves 13–18 solve as often as 7–12) | Deadline examples count once, first-change examples twice |
| 6 | The harness re-sends a request after transport errors | The relay's state is per task and repeatable; a refused noted request falls back to the plain reply |
| 7 | The request log holds no replies and breaks at compaction | The relay journals every request and reply; examples are built from the journal, one sequence per stretch between compactions |
| 8–10 | `tokenize_file` trains every step when a mask does not line up, rewrites context, and fails on string arguments; `cut_episode` rewrites arguments and final text | New module `vm/exact_data.py` renders the logged request as it is; a row whose mask does not line up is skipped |
| 11 | No test proves that the local rendering equals the served prompt | `exact_data.py check-render` (server tokenizer) and `check-journal` (server `prompt_tokens`); train only when all agree |
| 12 | The first edit after the note often does not fit 12,288 tokens | Fit test from 15,360 down; the trainer reports dropped examples |
| 13 | Fixes whose new public names are not in the issue cannot be derived; first thoughts may only copy the note; hinted runs may skip the check | `make_hints.py` flags names the tests use and the issue lacks; `note_report.py` counts own words in the first thinking and requires a check after the last edit |
| 14 | Round 1 supervised everything and tied | Own wins are supervised from their first source edit only; alpha = 2 × rank; one update per 4 examples |
| 15 | Gate numbers | A no-effect adapter passes 1–4% of the time; +3.1 to +3.3 true gain gives 50%; pass 1 runs the 43 not-always-solved tasks first (45 needs 11 of them); clock scale = 9 × T4 slowdown ÷ L4 slowdown |
| 16 | Most likely tie: the adapter learns the shape of a noted run, not the fix | Step 6 measures the loss on the changed lines of the first real-fix edit on held-out examples, at steps 0, 10 and 20 |

- **Needs the user's word:** the review also proposes one more sentence in the note (ask for a short derivation before
  the first edit). The note text is part of the approval, so the pilot runs with the approved text and the question
  goes to the user with the pilot's thoughts as evidence.

## 4. Tools (all in `vm/`)
| Tool | What it does |
|---|---|
| `make_hints.py` | Real fix → "Replace / With" blocks, checked against the snapshot |
| `takeover_proxy.py` | The relay: adds the private note on the wire, journals requests and replies |
| `takeover_check.py` | `sim`: where the rule fires on recorded runs; `http`: the relay end to end against a stand-in server |
| `note_runs.sh`, `r2_pilot.sh` | A pool and task list through the relay with the internet cut off; the 12-task pilot |
| `note_report.py` | Per run: note, blocks applied, leak words, own words, check after the last edit, tests |
| `exact_data.py` | Exact rendering and its two checks (the dataset builder follows) |
| `slice_adapter.py`, `lora_speed.py`, `t4_lora_speed.sh`, `l4_rank_speed.sh` | Cost of a rank before an adapter of that rank exists |

## 5. Results so far
- **Blocks** (`datasets/r2/hints_*.jsonl`): failed TRAIN tasks 190 of 207 usable, 115 clean (small fix, no other file, no
  unknowable name); rebench2 228 of 248 usable, 161 clean. Not usable: the fix adds, deletes or renames a source file
  (16), the blocks do not reproduce the fix (13), a block is not unique (2), others (6).
- **Where the note would come** (`takeover_check.py sim` on the 175 non-dev failed TRAIN runs, rule of finding 4):
  87 runs at deadline 12 (55 at the first change attempt, 32 at the deadline); 52 runs changed a source file before the
  lines were on screen; 21 never had them on screen; 15 have no blocks. At deadline 16: 85 runs (64 and 21) but 25
  prompts above 12.8k tokens against 13. The deadline stays at 12.
- **Relay over HTTP against a stand-in server** (`takeover_check.py http`): all checks pass for a first-change case in
  positions A and B and for a deadline case (requests without a note byte-identical; note in the latest tool result;
  same note at the same place later; note-free `prompt_tokens`; journal complete and note-free).
- **Speed on the T4s** (`results/speed/t4_r*.json`; the server's max rank = the adapter's rank):

  | Rank | 1 request | 4 requests | Long prompt |
  |---|---|---|---|
  | 16 | ×2.92 | ×2.28 | ×1.27 |

  Round 1 at rank 32 measured ×3.5 and ×2.74 (a different, shorter test). Ranks 8 and 32 and the Kaggle L4 numbers follow.

## 6. Open
- L4 speed at ranks 16 and 8 (Kaggle notebook, speed only).
- The pilot (12 tasks), then the 40-hour note runs.
- The dataset builder and the held-out check in `exact_data.py`; `chain_r2.sh`.
