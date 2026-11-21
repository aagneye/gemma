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
- **Speed with an adapter** (the server's max rank = the adapter's rank, as the scorer sets it; slowdown against the
  base model; `results/speed/t4_r*.json`, `results/speed/l4_r*.txt`, round 1's `results/replica/lora1_l4_speed.txt`):

  | Rank | T4: 1 request | T4: 4 requests | L4 (Kaggle): 1 request | L4: 4 requests | L4: long prompt |
  |---|---|---|---|---|---|
  | 32 | ×3.58 | ×2.71 | ×1.214 | ×1.136 | ×1.075 |
  | 16 | ×2.92 | ×2.28 | ×1.128 | ×1.107 | ×1.055 |
  | 8 | ×3.06 | ×2.42 | ×1.158 | ×1.125 | ×1.064 |

  - Base speed on the T4s: 32.1 tokens/s at 1 request, 85.1 at 4 (plain server; the LoRA-enabled server serves the base
    at the same speed).
  - **Below rank 32 the rank no longer matters:** rank 8 is not faster than rank 16 on either GPU type (the gap is
    run-to-run noise). The cost is in the LoRA kernels running on all 410 wrapped layers, not in their size. The public
    figure of 8–9% at rank 8–16 is not reproduced: we measure 11–16%.
  - **The scorer runs the tasks one at a time** (`research/raw/01_competition_harness.md:72`), so the 1-request column
    applies: +12.8% at rank 16.
  - **The plan's step-1 rule (at most 10% slower on Kaggle's GPUs) is missed by both ranks.** By the plan the round stops
    here; the decision went to the user (Nov 19, 09:10 UTC).
  - What decides the 12-hour limit is slowdown × output tokens. Known points: Budget-Fit ×1.00 never exceeded (16 runs);
    v6 at ×1.14 exceeded once in two runs; round 1's adapter at ×1.10–1.17 (×1.214 × 0.91–0.96 tokens) exceeded. A rank-16
    adapter that writes ×0.91 of Budget-Fit's tokens, as round 1's did on the 77 EVAL tasks, lands at ×1.03.
- **Exact rendering** (`exact_data.py check-render`, plain server up): with message contents passed as strings the local
  text missed one token in 50 of 50 requests: the template adds a space after each part of the system message when the
  content is a list, and vLLM passes lists. With contents passed as lists of text parts, **400 of 400 logged requests
  tokenise exactly like the server** (3,098–16,427 tokens, before and after compaction). Round 1 trained on the
  string form.

## 6. Open
- L4 speed at ranks 16 and 8 (Kaggle notebook, speed only).
- The pilot (12 tasks), then the 40-hour note runs.
- The dataset builder and the held-out check in `exact_data.py`; `chain_r2.sh`.

## 7. Pilot A (Nov 19, 09:02–09:52 UTC): the approved note in a tool result
12 tasks (6 failed TRAIN tasks where the note comes on the recorded run, 6 rebench2 tasks), Budget-Fit V5 unchanged,
position A, the approved text. Report: `results/r2_pilot_a.md` on the VM.

| Measure | Result |
|---|---|
| Note given | 10 of 12 (6 at the first change attempt, 4 at the deadline) |
| Tests pass, noted runs | 7 of 10 |
| First block applied within 2 steps (pilot rule: at least 80%) | **4 of 10** |
| … at a first change attempt | 4 of 6 (one of the other two hit the clock bug below, one a shortened history) |
| … at the deadline | 0 of 4 |
| Leak words in Gemma's text after the note | 4 of 10 ("the private note says" three times, "was provided" once) |
| Clean examples | 3 of 10 |

What Gemma does with a note in a tool result:
- **It treats it as outside advice.** It names it ("Wait, the private note is giving me the fix. I should follow it but
  I'll double check"), argues with it ("the private note is usually very accurate for these tasks. However, the
  problem statement explicitly mentions…"), or first finishes its own plan (beniget_80 applied the fix 11 steps later).
- **At the deadline it mostly ignores it** (filesystemspec_1536 kept exploring until the calls ran out; conllu_35 wrote
  its own, wrong, variant). The review predicted this from the budget warning.
- **The code in the note shows escape marks.** A tool result is JSON, so the note's blocks appear with `\n` and `\"`.
  In mongoengine_2858 Gemma copied `\n` into the file as two characters.

Other findings:
- **Clock bug in half of the pilot:** `scorer-host-venv-plus` (the rebench2 environment) never had the stretched clock
  (`patch_replica_clock.py`), so the 6 rebench2 runs had 8 real minutes; 3 ended with "Agent exceeded session timeout".
  Fixed at 09:58 UTC: the patch is applied and the harness code is now identical in both environments.
- **The history was shortened after the note in 3 of the 6 TRAIN runs** (prompts above 10k tokens at the note). The
  relay moved the blocks not yet applied to the newest tool result, as designed.
- **Exact rendering on live data** (`exact_data.py check-journal`): local token count = server count in 97 of 97 plain
  requests; in 88 of 88 noted requests the lowered count equals the note-free local count.
- **Relay fixes after the pilot:** the call count now survives a shortened history (it restarted at the visible calls);
  blocks that change only comments or blank lines are left out of the note (`make_hints.py`).

**Verdict by the pilot rule:** position A fails (4 of 10 within 2 steps, 80% needed).

**Position C (proposed, needs the user's approval since it changes the note text):** the fix is appended to Gemma's own
thinking of the step that made the latest tool call, in the first person, so it reads as its own conclusion: plain text,
no escape marks, nothing outside to name. Text (`takeover_proxy.py` PLAN_HEAD / PLAN_TAIL):

```
I have seen enough. The correct fix is exactly this change:

File: <path>
Replace:
<old lines>
With:
<new lines>

Next step: state in two or three sentences what is wrong in this code and what has to change, naming the function, then make the change with edit_file, one call per block, copying each "Replace" text exactly.
```

Implemented in the relay; `takeover_check.py http` passes for C at a first change and at the deadline; the rendered
prompt shows the plan inside the model's thought channel right before its last tool call.

## 8. Pilots B and C (Nov 21): where the note goes
Same 12 tasks, Budget-Fit V5 unchanged, both pools on the stretched clock. B = the approved note at the end of the task
text (09:50–11:08 UTC). C = the fix inside Gemma's own latest thinking, first person (11:10–12:31 UTC; the user approved
piloting it on Nov 21). Reports: `results/r2_pilot_b.md`, `results/r2_pilot_c.md` on the VM.

| Measure | A (tool result, Nov 19) | B (task text) | C (own thinking) |
|---|---|---|---|
| Note given | 10 of 12 | 11 of 12 (7 first change, 4 deadline) | 11 of 12 (6 first change, 5 deadline) |
| Real tests pass, noted runs | 7 | 10 | 9 |
| First block applied within 2 steps | 4 | 7 (all 7 first-change cases; 0 of 4 at the deadline) | 6 (5 of 6 first-change cases; 1 of 5 at the deadline) |
| Runs where Gemma names the note | 4 | 4 | **0** |
| Clean note runs by the builder (`exact_data.py build`) | 3 | 7 | 7 under the first leak rule, **8** under the corrected one |
| Examples / rows at 14,336 tokens | – | 11 / 17 | 13 / 19 |
| Local token count = server count (`check-journal`) | 185 of 185 | 256 of 256 | 274 of 274 |

- **B is read as outside advice.** In its 4 leaking runs Gemma wrote "the private note" 38 times, for example "maybe the
  private note is the source of truth for what is expected for this task" and "if I follow the private note, I'm doing
  what's expected for the evaluation". Runs that pass the word filter may still carry that stance.
- **C reads as Gemma's own conclusion.** After the note it writes what is wrong and then edits ("The reproduction script
  confirmed the `TypeError`. Now I will apply the fix. In `jwt/api_jwt.py`, in `_validate_iat`: the line `int(iat)`
  should be `iat = int(iat)`"). No run names a note.
- **At the deadline both forms are slow:** Gemma finishes its own exploring first (B: 0 of 4 within 2 steps, C: 1 of 5),
  and applies the fix 6–9 steps later in about half of those runs. Those runs still give examples (deadline examples
  count once, first-change examples twice).
- **Chosen: C** (rule fixed before the pilots: more clean examples wins, a tie goes to C). The long run uses C.

**Leak rule corrected (Nov 21).** The first rule dropped pyjwt_847 in pilot C for "a `TypeError` when `iat` was provided
as a string". "provided / given / supplied" now counts only when a fix word (fix, patch, solution, change, diff, answer,
hint, replacement, block) stands right next to it ("the fix was provided", "the fix I was given", "the provided
solution"). A looser try ("provided to me") dropped nlpaug_169, where Gemma spoke of the harness's own summary after
the history was shortened. The other words are unchanged. All 39 real hits in pilot B still match; pilot C has none.
The report and the builder now share one rule (`note_report.LEAK_RX`).

**Other drops looked at by hand:** precommithooks_944 in pilot C changed a test file and changed it back (dropped,
correctly: Budget-Fit's rule is not to touch tests); conllu_35 and pythonapicore_577 in C did not apply the fix and failed.

## 9. The long run and the chain (started Nov 21, 12:42 UTC)
- **Note runs:** tmux `r2notes`: `POSITION=C BOX_HOURS=30 CHUNK=20 bash r2_notes_chain.sh`; the box closes Nov 22 18:42 UTC.
  Order: failed TRAIN tasks (84), rebench2 clean fixes (156), dev tasks for the held-out check (14), other rebench2
  tasks (66). The 12 pilot tasks are in none of these lists; pilot C's runs are added as examples (`EXTRA_TAGS`).
- **Chain:** tmux `r2chain`: `WAIT_FOR=r2notes EXTRA_TAGS="r2_pilot_train_c r2_pilot_rb2_c" bash chain_r2.sh`.

**How long an example may be decides how much is learned** (24 note examples of both pilots + 101 own wins, CPU):

| Length limit | Note examples kept | Learned tokens, notes | Own wins kept | Learned tokens, own | All tokens |
|---|---|---|---|---|---|
| 12,288 (round 1) | 22 | 45.6k | 70 | 110.7k | 1.10M |
| 13,312 | 23 | 53.8k | 79 | 138.4k | 1.30M |
| 14,336 | 23 | 61.5k | 89 | 160.2k | 1.49M |
| 15,360 | 24 | 70.6k | 98 | 183.3k | 1.70M |
| 16,384 | 24 | 71.7k | 100 | 186.3k | 1.74M |

- 15,360 holds almost everything: +55% learned note tokens and +66% learned own tokens over round 1's 12,288.
- **Memory:** round 1 (rank 32, 12,288 tokens, layers per card 8/18/17/17) peaked at 11.9 / 12.8 / 12.6 / 13.7 GB on
  16 GB cards: the last card is the limit and grows 0.57 GB per 1,024 tokens. Rank 16 saves about 0.5 GB per card.
  Estimate: 15,360 is on the edge with the trainer's own split and comfortable with 9/18/18/15.
  The split is sized from `--max-len`, so the fit test now runs one process per length (`chain_r2.sh`, `FIT_TRY`).
- **Time:** training costs about 12.8 ms + 0.39 ms per 1,000 tokens of row length, per token (round 1: 16.1 at 8k,
  17.7 at 12k), so about 18–19 ms per token here. The plan's 20-hour stop holds about 3.9M tokens. With about 100
  clean note runs the set would be about 4.4M. The tokenizer now takes a token budget (`--token-budget`, sized for 19
  hours from the fit test's speed). What gives way, the longest first: own wins (the model already does these; round 1
  trained on them alone and tied), then the second copies of first-change note rows. Every note row stays once.
  Sizes from the pilots at 15,360: a first-change run costs about 19k tokens per copy, a deadline run about 20k, an
  own win about 12.5k. So 130 clean runs would be about 2.6M once, 3.9M with the second copies, before any own win.
- **Trainer fixes before it runs for a day unattended** (`train_qlora.py`):
  - A restart from a checkpoint started the pass again at its first row, so the first rows were seen twice and the
    last never. It now skips the rows trained before the restart (same seed, same shuffle).
  - A row that does not fit killed the run. In the one-process pipeline it is now left out and logged (`oom_row`).
- **The answer-change check could stop a good round** (`adapter_effect.py`, found by reading it against the examples):
  it drew 20 prompts from all examples and compared tool calls only. About 4 in 10 examples are own wins, where the
  adapter is taught the base model's own answer, so an equal tool call is the wanted result; a working adapter could
  score under 15 of 20. Now: note prompts first, the whole answer is compared (thinking and call), the base model is
  asked twice on 5 prompts to show how repeatable temperature 0 is, and tool-call validity is judged against the base
  model's (give or take one, and at least 9 in 10). The rule "15 of 20 answers differ" is unchanged. A crash of the
  check no longer stops the chain (only its "fail" does); the test on the EVAL tasks decides either way.
- **GPU test at the first break of the note runs** (`r2_gpu_smoke.sh`, armed by `r2_smoke_trigger.sh`): fit test per
  length and split, a 4-update training with a full-length row and a row that cannot fit, a restart from a checkpoint,
  and `heldout_loss.py` on three rows. It restarts the note runs with the same box end and re-queues the chain. Cost:
  about 45 minutes of the box. Results in section 10.
