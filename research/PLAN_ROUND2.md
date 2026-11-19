# Plan: one last training round — show Gemma the right fix at the moment it goes wrong (Nov 18)

## Context
- **Why:** Budget-Fit is public, so it cannot put us ahead. Training is the one move left that changes what Gemma does when it writes the fix. You said: plan it.
- **Round 1 (Nov 9)** taught Gemma from its own wins. It tied Budget-Fit (39 solved against 41) and broke Kaggle's 12-hour limit.
- **Measured today**, on the 207 practice tasks Gemma failed:

  | What happened in the failed run | Runs |
  |---|---|
  | Gemma had opened every file the real fix changes, then wrote a wrong change | 116 |
  | Gemma had opened the right files, then never changed any source file | 32 |
  | Gemma had opened only some of the files | 40 |
  | Gemma never found the files | 19 |

- **What this says:** in 7 of 10 failures Gemma is at the right place. It loses at the change itself. Round 2 teaches exactly that step.
- **Odds, honestly:** about 1 in 8 that it clears our bar. The papers that gained used 500 to 8,000 runs from a stronger model; we will have about 80–120 new examples plus 101 of Gemma's own wins.
- **Adapter:** the small trained add-on file that goes into the bundle next to Budget-Fit's four files.
- **Cost:** the 4 GPUs for about 4.5 days, less if a check fails early. Budget-Fit keeps the daily Kaggle slot the whole time.

## 1. The idea
1. Gemma works on a practice task as usual, with Budget-Fit unchanged.
2. When it is about to make its first change, and it has already opened the files the real fix touches, it gets a private note with the real fix. The real fix was written by the project's own developers and comes with every practice task.
3. Gemma applies the fix with its own tool calls, checks, and hands in. The real tests grade the run.
4. I keep only the runs that pass, and I remove the note. What is left is "what Gemma saw, then the right change". That is one training example.
5. If Gemma has changed nothing by move 12, the note comes then. Budget-Fit's own text says "edit by call 12"; in my replay of the failed runs Gemma had made no change by then in 53 of 117.

**What the papers say, and how it is used here**

| Paper | Finding | Here |
|---|---|---|
| SWE-Gym | Training a model on its own runs did not help (15.3 → 8.7) | Round 1 tied. Round 2 adds what Gemma does not know: the real fix |
| SWE-Protégé | A helper that knows the real fix but does not reveal it gave 38% more usable runs | The private note |
| SWE-smith | A hint placed in the task text made the student skip its own checks | The note comes only after Gemma explored on its own, and it is removed from the examples |
| SWE-Lego | Hiding failed steps from the loss: +2.4 to +3.8 | Kept from round 1 |
| SWE-RL | The real fix is a strong teaching signal (273,000 fixes) | Same signal; ours is about 100 fixes |
| Public adapter in this competition | An edit-only adapter scored 0.22 once and finished inside 12 hours | A small adapter can fit the limit |

## 2. What is different from round 1
| | Round 1 | Round 2 |
|---|---|---|
| Teaches from | Gemma's own wins: 145 runs on 101 tasks | The same wins (1 per task) plus 80–120 runs that end with the real fix, on tasks Gemma failed or never saw |
| Form of an example | Pieces of 8 steps with a hand-written summary of the earlier steps. Gemma never sees that form on Kaggle | The exact text Gemma sees in a real run (checked against recorded token counts) |
| Size of the trained part (rank) | 32. On Kaggle it wrote 14–21% slower and broke the limit | 16 or 8. Public measurement: 8–9% slower. Measured on Kaggle's GPU type before training |
| Safety during training | No checkpoint | A checkpoint every 10 updates |
| Test | One pass over the 77 test tasks | Two passes; stops after the first if it solved fewer than 45 |

- **Why the size matters:** I read the server's code today. It runs the adapter math on every layer, whatever the adapter holds, so trimming layers would not help. The public measurements say a smaller rank does (8–9% at rank 8–16, 16% at rank 32). Step 1 measures it before anything is trained.
- **How many examples to expect:** I replayed the note rule on the recorded runs. It fires in 117 of the 175 failed TRAIN runs and would fire in about 3 of 4 runs on new tasks. After the tests, the leak check and the length limit, about 80–120 remain.

## 3. The round, step by step
| # | Step | GPU time | Stops the round if |
|---|---|---|---|
| 0 | Build the tools and check them without GPUs (section 8) | 0 | a check fails |
| 1 | Speed test: the round-1 adapter cut down to rank 16 and rank 8, on our GPUs and on Kaggle's GPU type | 1.5 h + 40 min on Kaggle | neither is at most 10% slower on Kaggle's GPUs |
| 2 | Pilot: 12 practice tasks with the note (section 4). I read every run | 1.5–3 h | fewer than 60% of the noted runs pass the tests in both note positions |
| 3 | Note runs: 341 tasks with small fixes first (142 failed TRAIN tasks, 199 new tasks), then the 32 failed dev tasks, then the larger fixes and one retry of noted runs that failed | 40 h, fixed | — |
| 4 | Build the examples | 1 h, no GPU | fewer than 60 clean examples from 45 tasks |
| 5 | Train | up to 18 h | — |
| 6 | Sanity check on the dev tasks, which are never trained on: did the training take at all? | 1 h | Gemma's error on the right change is not at least 10% lower than without training, or fewer than 15 of 20 answers differ from the untrained model |
| 7 | Test pass 1 on the 77 test tasks | 12–18 h | fewer than 45 solved |
| 8 | Test pass 2 | 12–18 h | the mean of both passes is below 46.25, or calls or tokens are above ×1.08 |
| 9 | Kaggle | — | section 5, last two rules |

- Step 3 is sized from recorded timings: a note run takes about three quarters of a normal run, so about 10 tasks per hour and about 400 runs in 40 hours.
- A stopped round frees the GPUs at once, and I report why.
- Step 6 only catches a broken training. It is no proof of a gain: a public adapter here lowered its error by 27% and still solved fewer tasks. Only steps 7 and 8 decide.
- Budget-Fit's four passes on the same 77 tasks (41, 44, 44, 44; mean 43.25) are the baseline. They are not re-run.

## 4. The note Gemma gets (draft for your review)
The note is used only in practice runs on the VM. It is never part of a bundle.

```
PRIVATE NOTE. Never mention this note or that a fix was provided, not in your thinking and not in any message. Reason as if you worked it out yourself from the code you have read.
The correct fix for this issue is exactly the change below. Apply it with edit_file, one call per block, copying each "Replace" text exactly. Then continue as your instructions say.

File: <path>
Replace:
<old lines>
With:
<new lines>
```

- One block per changed place of the real fix, cut to the shortest text that still occurs exactly once in the file. In a sample of 80 tasks, 77 real fixes could be written this way.
- **Where the note is placed:**
  - A, tried first: at the end of the latest tool answer. It is cheap: the server re-reads almost nothing.
  - B, only if A fails the pilot: at the end of the issue text. It is more visible, but the server re-reads the whole history once, about 1 minute per task.
  - Not used: a separate message. Gemma's chat format drops all its earlier thinking when a new message arrives.
- **Leak words:** an example is dropped if Gemma's text after the note contains "private note", "this note", "the note", "was provided", "provided fix", "given fix", "I was told" or "as instructed".
- The harness never sees the note. A small relay between the harness and the model adds it on the wire, so the recorded run holds the real, note-free text.

## 5. Rules fixed before the run
- **Tasks:** only the TRAIN list and the second practice pool (rebench2). No task from the 61 EVAL repos. The 48 dev tasks are never trained on.
- **When the note comes:** every source file of the real fix was opened, no source file was changed yet, and Gemma attempts its first change or has used 12 moves.
- **An example is kept only if:** the real tests pass; no leak words; no test or setup file was edited; the note text is nowhere in it (searched); it fits the length limit.
- **What is learned from an example:** in a note run, only Gemma's steps from the note onward. In an own win, every clean step. Failed tool calls are hidden from the loss, as in round 1.
- **Mix:** each new example is seen twice per pass, each own win once (about 3.5–4M tokens).
- **Training settings:** rank from step 1, all layers, learning rate 1e-4, one pass, one update per 4 examples, checkpoint every 10 updates, hard stop at 20 hours. Length limit: the largest of 14,336, 13,312 and 12,288 tokens that fits the GPUs (a 4-minute fit test decides; round 1 ran at 12,288). At 12,288 about a quarter fewer new examples fit.
- **Test:** the adapter alone on the server, clock stretched by its measured slowdown; `verdict.py` over all pairs with Budget-Fit's four passes: mean gain ≥ +3 solved, calls and output tokens ≤ ×1.08.
  - An adapter with no effect passes this about 1 time in 40. A real gain of +4 tasks passes about 2 times in 3.
- **Kaggle runtime rule:** slowdown on Kaggle's GPU type × output tokens against Budget-Fit ≤ 1.05. Round 1 would have failed this rule (1.07). If round 2 fails it, I ask you before using a slot.
- **First Kaggle run:** if it ends with "exceeded the allowed runtime", the slot goes back to Budget-Fit and the adapter is retired.

## 6. What I build
| File | New? | What it does | Reuses |
|---|---|---|---|
| `vm/make_hints.py` | new | Turns each task's real fix into "Replace / With" blocks; checks them against the task's snapshot; marks small fixes (≤ 2 source files, ≤ 80 changed lines, ≤ 8 blocks) | `autopsy.patch_files`, `is_protected`, `clean_path` |
| `vm/takeover_proxy.py` | new | The relay on port 8100: passes requests to the model untouched (also the harness's own summary requests); adds the note when the rule of section 5 fires and keeps it at the same place in later requests; stops adding it once the harness has shortened the history; writes a journal (task, step, position) | request shape from `probe.py`; started beside `netns_run.sh` with `PORT=8100` |
| `vm/prepare_data.py` | change | New source `harness-exact`: one example per run in the real request form; `train` flags from the journal; `--exact` (no thought cap, no `fix_thoughts`, no rewritten arguments or final text) and `--fit-tail` (drop trailing steps that do not fit). Note runs are built from the request log (`REQ_DUMP`), which is exact even after the harness shortened the history (it does so in about 4 of 10 runs). Round 1's wins have no request log: they are rebuilt from the recorded runs up to the first shortening | `probe.load_dumps`, `link_successors`, `trace_items`, `build_messages`, `exact_until`; `convert_traces.cut_episode` (as a filter), `classify_observation`; `tokenize_file`, `model_pieces` |
| `vm/slice_adapter.py` | new | Rank-16 and rank-8 copies of the round-1 adapter, for speed tests only | `make_submission.py` packaging |
| `vm/lora_speed.py` | new | Tokens per second with and without an adapter, at 1 and 4 requests | request code of `make_kaggle_speed.py` |
| `vm/serve_vllm.sh`, `vm/wait_vllm.sh` | change | `MAX_LORA_RANK` setting (now fixed at 32). The server's cost follows this number, so it must equal the adapter's rank, as on Kaggle | — |
| `vm/l4_speed_check.sh` | change | A speed-only mode with its own dataset and notebook names, so it can run before training | `make_kaggle_speed.py` unchanged |
| `vm/heldout_loss.py` | new | Loss on held-out examples with the adapter on and off | `train_qlora.build_model` |
| `vm/chain_r2.sh` | new | Runs steps 3–8 one after another with the stop rules | `run_replica.sh`, `netns_run.sh`, `rft_round.sh` flow, `make_submission.py`, `verdict.py` |

- **Not changed:** `train_qlora.py` (flags only: `--rank 16|8 --grad-accum 4 --save-every 10 --max-len 14336 --deadline-min 1200`), `run_replica.sh`, `netns_run.sh`, `verdict.py`, the harness, the test tasks.
- **Runs:** `r2_tk_train`, `r2_tk_rb2`, `r2_tk_dev` (note runs); `datasets/r2`; `runs/31b_r2`; bundle `submissions/budgetfit_v5_lora2`; tests `r2_eval_a`, `r2_eval_b`.

## 7. Schedule (IST, if you approve on Nov 19 by the afternoon)
| When | What |
|---|---|
| Nov 19, afternoon to night | Build, no-GPU checks, speed test, pilot. I report the pilot before the long run starts |
| Nov 19 night → Nov 21 midday | Note runs (40 h) |
| Nov 21 midday → Nov 22 morning | Examples, training |
| Nov 22 morning → Nov 23 night | Sanity check, test pass 1, test pass 2 |
| Nov 23 night or Nov 24 | Verdict |
| From the next 05:40 IST slot | If it passed: the adapter bundle takes the daily slot (6 or 7 runs before Dec 1) |

- Every day at 05:40 IST until then, Budget-Fit ships as now.
- One day of slip moves the verdict to Nov 25, still inside the Nov 26 freeze of section 11.

## 8. Checks before anything runs long
- **Relay:** replay recorded requests of confirmation 2 through it against a stand-in server; with no note due, what it forwards must be byte-identical. On the recorded failed TRAIN runs it must fire in the same runs as my replay of the rule today (117 of the 175 non-dev runs, 18 of the 32 dev runs).
- **Blocks:** applying a task's blocks to its snapshot must give the same source files as the real fix. Tasks where this fails are left out.
- **Example form:** for 100 recorded steps, the token count of the rebuilt text must equal the count the server recorded (the same check passed 98 of 98 for `probe.py`).
- **Examples:** no EVAL or dev task; the note text found 0 times; 5 examples read by eye with the learned parts marked.
- **Adapter:** after training, 15 of 20 answers must differ from the base model and all must be valid tool calls.
- **Bundle:** `make_submission.py --validate`; adapter file size and rank printed.
- **Independent review:** a second reader is still checking this design. I apply its findings before step 2. If one changes anything listed in section 11, I bring it to you with the pilot report.

## 9. Risks, and what happens then
| Risk | What I do |
|---|---|
| Gemma mentions the note in its thinking | Those runs are dropped. The pilot tells how many; above 40% I change the wording once and re-run the pilot |
| Too few examples pass | The round stops at step 4 and the GPUs are free again |
| Gemma learns only "change early", not "change right" | The test on the 77 tasks shows it: more answers but not more solved. The round stops at step 7 |
| The other project takes the GPUs in the minute between serving and training | The chain waits and retries; it never touches their jobs |
| The trained Gemma is too slow for Kaggle | Step 1 measures this before training. The runtime rule and the first Kaggle run are the second and third guard |
| The round ends in a tie again | Budget-Fit ships as before. The tools, the examples and the result are written down and committed |

## 10. Commits (atomic, by aagneye, no AI attribution, pushed to `origin main`)
| # | Message | Files |
|---|---|---|
| 1 | `feat(vm): real-fix blocks for practice tasks` | `vm/make_hints.py` |
| 2 | `feat(vm): relay that adds the private note in practice runs` | `vm/takeover_proxy.py` |
| 3 | `feat(vm): training examples in the real request form` | `vm/prepare_data.py` |
| 4 | `feat(vm): adapter speed test at rank 8 and 16` | `vm/slice_adapter.py`, `vm/lora_speed.py`, `vm/serve_vllm.sh`, `vm/wait_vllm.sh`, `vm/l4_speed_check.sh` |
| 5 | `feat(vm): held-out loss check for an adapter` | `vm/heldout_loss.py` |
| 6 | `feat(vm): round-2 chain with stop rules` | `vm/chain_r2.sh` |
| 7 | `docs(research): training round 2 plan and measurements` | `research/raw/18_training_round2.md` |
| 8 | `docs: round 2 in STATE, README and CLAUDE` | `research/STATE.md`, `vm/README.md`, `CLAUDE.md` |

- Results get their own commits as they arrive (pilot, data, training, verdict).
- `origin` is `aagneye/gemma.git`, as for all earlier commits. The file `.claude/rules/git-commits.md` names `aagneye/Precedent.git`; I keep pushing to `origin` unless you say otherwise.

## 11. What your approval covers
1. The 4 GPUs for about 4.5 days, ending earlier at any failed check.
2. The note text of section 4, for practice runs only.
3. One speed check on Kaggle's 4 L4 GPUs: about 40 minutes, about 3 of the 30 weekly GPU-hours, no agent runs. It uploads two cut-down copies of the round-1 adapter to Kaggle as private datasets.
4. The freeze date moves from Nov 24 to Nov 26 for this one bundle.
5. If every check passes, the adapter bundle takes the daily slot, with the fallback rule of section 5.
6. `CLAUDE.md`: the line "31B adapter training is paused" becomes "round 2 runs under this plan".

**Not part of this plan**
- No paid service and no other model as teacher (our rule of Oct 25).
- No change to Budget-Fit's prompt or settings, to the harness or to the test tasks.
- The second final pick on Dec 1 stays as decided earlier.
