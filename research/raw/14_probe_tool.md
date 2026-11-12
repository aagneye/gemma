# 14. The probe tool (`vm/probe.py`): replay one moment, score the next action

Written 2026-11-11. Loop 1 of the instruction plan (`CLAUDE.md`, "Instruction program"). Status at the end of this file.

## What it is for
- A full task costs 10-20 minutes on the VM. One next-action generation costs about 20 seconds on an idle server.
- The probe replays a recorded moment of an agent run with a changed system prompt and looks only at the model's next
  action. It answers call-level questions: is the `edit_file` call well formed, does `read_file` carry a line range,
  does the check after an edit start with a compile step, what comes after the budget warning.
- It cannot say whether a task gets solved. Wordings are explored here; screens and the confirmation decide.

## How it works

**1. Decision points** (`probe.py points`). A point is "the request the harness sent just before a recorded action".

| Kind | The recorded action at the point | Available in `bf5_train` (early steps) |
|---|---|---|
| `edit` | an `edit_file` call (the record says whether it was garbled) | 491 (110 garbled) |
| `read` | a `read_file` call (the record says whether it had a range) | 1,634 (691 range-less) |
| `after_edit` | the action right after a successful `edit_file` | 322 |
| `submit` | the first `submit_patch` of the task | 114 |
| `after_warning` | the action right after the first result with `budget_warning` | 28 |

- Sampling goes round-robin over tasks, at most 6 points per task and kind (`--per-task`), seed 0.
- Edit points are drawn in two strata so that 32% are recorded-garbled calls, the whole-run rate (`--garbled-share`).
  Without this the sample holds under 10% garbled calls, because they sit in a few tasks.
- From traces only early steps qualify: the step's own prompt is at most 14,000 tokens and no earlier prompt of the
  task reached 14,336. That number is the harness's compaction threshold: ADK summarises the history once the latest
  prompt reaches it (visible in the traces as a drop, e.g. 16,366 → 7,232), and the trace does not record the summary.
- The budget warning starts at call 18 of 28, usually after compaction. For `after_warning` use `--from-dumps`.

**2. Request reconstruction.** Read from the harness code on the VM (google-adk 1.36.1 `LiteLlm`, adk_submission 0.2.13,
swegemma 0.2.11) and checked against two offline captures of what `LiteLlm` really sends (a fake local endpoint, no GPU).

- Body keys: `messages`, `model`, `max_completion_tokens` 8192, `temperature` 0.2, `tools`, `top_p` 0.95,
  `chat_template_kwargs {enable_thinking: true}`, `thinking_token_budget` 4096. No streaming.
- `tools`: the bundle's tool list (Budget-Fit V5 declares 9, graph tools included) from `vm/tool_declarations.json`.
- `messages`:
  - system = the bundle's prompt file + two newlines + `You are an agent. Your internal name is "swe_agent".`
    (ADK adds this identity line; it is not in the trace);
  - user = the task prompt (trace step 2);
  - per model turn one assistant message: `content` only if there was visible text, one `tool_calls` entry with
    `arguments` as a JSON string, and the thought twice (`reasoning_content` and `reasoning`; adk_submission mirrors it);
  - then a `tool` message (role `tool`, because the model name has no "gemma4" in it) with the result as
    `json.dumps(result, ensure_ascii=False)`;
  - a harness nudge ("Please continue…") is a user message; a turn with only a thought is dropped by ADK.
- One model reply is split by the trace recorder into consecutive agent steps with the same `extra.elapsed_s`
  (thought step, text step, tool-call step); the probe merges them back.
- `probe.py verify --run <run> --dumps <dump_dir> --bundle <bundle>` rebuilds every early step of a run and compares it
  with the dumped request of the same task and length, ignoring call ids. It reports equal / equal apart from
  whitespace / different, with the first differing field.
- `--from-dumps` skips reconstruction: points are the dumped bodies themselves. The recorded action of a dumped request
  is read from the next request of the same conversation (the one whose messages start with it). Works after compaction.

**3. Replay** (`probe.py replay`). The base prompt text inside the system message is replaced by the variant's text
(everything else stays byte-identical) and the body goes to `http://127.0.0.1:8000/v1/chat/completions`.
- Stored per reply in `<out>/results.jsonl`: the tool call exactly as the server parsed it, text, finish reason,
  completion and prompt tokens, seconds. Re-running resumes; failed requests are retried.
- GPU rule built in: while a tmux session `gate1`, `instr` or `rep_*` exists, or a `run_arms.sh` / `run_replica.sh` /
  `run_pair.sh` process is alive, it sends at concurrency 1 and at most 30 requests per hour, counted in a ledger file
  shared by all probe runs (`results/probes/rate_ledger.txt`). When the cap is reached it stops and says how many are
  left (`--wait` makes it wait instead).
  `--allow-sessions instr` is for the job chain, which itself runs in `instr`. The process check still catches a screen
  running inside `instr` (added in review, Nov 12: before it, a hand-started round with the default `ALLOW=instr` would
  have run at full concurrency beside Screen A).
- `--deadline-min` / `--deadline-epoch` stop sending at a time limit; scoring uses the points answered by every variant.

**4. Scoring** (`probe.py score`), per variant, counts and shares:
- edit points: next action is `edit_file`; well formed (has `filepath`, `old_string`, `new_string`) vs garbled, also
  split by whether the recorded call was garbled;
- read points: `read_file` with a range vs without; `run_command` instead;
- after an edit: `run_command`; has `py_compile`; starts with it; pytest on a path; 3 or more cases (counted as
  `print(`/`assert` statements or the arguments of one `print(...)`: a heuristic);
- submit points: submit vs a grep first (sibling search) vs another edit;
- after the budget warning: edit or submit vs explore;
- mean completion tokens per kind and overall, seconds per request;
- paired against the base: points fixed / broken and a two-sided sign test.

**5. Calibration** (`probe.py calibrate`). With the unchanged prompt the replayed garbled share (of replies that call
`edit_file`) and range-less share (of replies that call `read_file`) must be within 5 points of the recorded shares
at the same points, on at least `--min-points` points each (150 by default; `probe_round1.sh` asks 90% of its 150, so
a few failed or late requests do not fail it on the count alone). Exit code 0 = pass, 3 = fail.

## Commands

Reference counts of a run (sanity check of the parsing; `bf5_train` gives 348 of 1,090 and 867 of 2,260):
```bash
python3 ~/gemma4_vm/probe.py stats --run results/replica/bf5_train
```

Probe round 1 (calibration, then V5 vs E1+R1 vs D1 on 150 edit + 150 read points; under 3 hours at concurrency 4;
writes `results/probes/round1.md`; exit code 0 only if the calibration passed):
```bash
bash ~/gemma4_vm/probe_round1.sh
```

A round by hand, any wording (run from `/mnt/biohub/kdata/gemma4`):
```bash
python3 ~/gemma4_vm/probe.py points --run results/replica/bf5_train --bundle submissions/budgetfit_v5 --kinds edit,read,after_edit,submit --n 150 --out results/probes/r2/points.jsonl
```
```bash
python3 ~/gemma4_vm/probe.py replay --points results/probes/r2/points.jsonl --base submissions/budgetfit_v5/prompts/system.md --variant v5=submissions/budgetfit_v5/prompts/system.md --variant new=/path/to/new_wording.md --concurrency 4 --allow-sessions instr --out results/probes/r2
```
```bash
python3 ~/gemma4_vm/probe.py score --out results/probes/r2 --base-name v5 --md results/probes/r2.md
```

Exact points from the request log (after Screen A; `--base` keeps only the Budget-Fit arm's requests):
```bash
python3 ~/gemma4_vm/probe.py points --from-dumps results/requests/screenA --base submissions/budgetfit_v5/prompts/system.md --kinds edit,read,after_edit,submit,after_warning --n 150 --out results/probes/r3/points.jsonl
```

Check the reconstruction against the request log of the same run:
```bash
python3 ~/gemma4_vm/probe.py verify --run results/replica/<screenA base tag> --dumps results/requests/screenA --bundle submissions/budgetfit_v5
```

## What it cannot measure
- **Solving.** One action is not a fix. A wording that produces tidy calls can still lose tasks (v6, v7 did).
- **Loops and recovery.** The 61-fold resend of a garbled call is a multi-step behaviour; the probe sees one step of it.
  It can show whether the step after a garbled result is garbled again, not whether the loop ends.
- **Effects that need a different history.** The variant only changes the system prompt; the earlier turns were
  produced under the base prompt. A rule about the first action (search before reading) changes later moments in a
  real run, and the replayed history does not show that.
- **Calls and time per task.** Tokens of one reply are measured, not the number of calls a task takes.
- **Late moments from traces.** After compaction only the request log is exact.
- **Small differences.** At 150 points a share has a 95% interval of about ±8 points; the paired sign test is the
  number to read. Sampling at temperature 0.2 adds run-to-run variation on top.
- **Thought whitespace from traces.** The trace stores thoughts and text stripped; the real request keeps the model's
  leading/trailing whitespace. `verify` reports this separately.

## Status
Nov 12, 05:30 UTC. Tested from `/mnt/biohub/kdata/gemma4/tmp/probe_test/` only; not deployed to `~/gemma4_vm/`, not committed.

**Done and checked**
- Parsing: `stats` gives 348 of 1,090 garbled edits and 867 of 2,260 range-less reads for `bf5_train` (the reference).
- Reconstruction against the real request log (Screen A base arm `sA_base`, 16 tasks finished, 1,565 agent requests):
  `verify` compared 223 early steps. 34 are equal to the dumped request apart from call ids. 189 differ only in the
  trailing newlines of earlier thoughts (the model ends a thought with 0 to 4 newlines; the trace stores it stripped,
  so they cannot be restored). None differs in any other way. `verify` passes on "at least 20 equal, none different".
- Those newlines do not change the prompt: the server counted exactly the recorded number of prompt tokens for
  98 of 98 rebuilt requests in the calibration below (and 10 of 10 in the dry run). `calibrate` prints this count.
- Calibration, unchanged prompt, 100 points of `bf5_train` (50 edit, 50 read, seed 1; run at 30 requests per hour):
  **passed**.

  | Rate | Recorded at these points | Replayed | Difference |
  |---|---|---|---|
  | garbled `edit_file` | 16/48 (33%) | 12/38 (32%) | -2 points |
  | range-less `read_file` | 22/50 (44%) | 19/45 (42%) | -2 points |

  This is under the 150 points per rate the plan asks for; `probe_round1.sh` runs the full 150 + 150 as its first step.
- `probe_round1.sh` dry run on 10 points (5 edit, 5 read) x 3 prompts = 30 requests: ran to the end, wrote the table,
  exit code 3 because the calibration cannot pass on 5 points. Re-running resumes without sending anything.
- `points --from-dumps` on the real log: 187 candidate points in the base arm so far (edit 38, read 111, after_edit 33,
  submit 11, after_warning 7), including moments after compaction.

**Found on the real log and fixed**
- After compaction the first user message is a list of text parts (the summary), not a string; the dump loader crashed
  on it. Such a conversation gets its own task key, so `--per-task` counts it apart from the same task before compaction.
- The log also holds the compaction summariser's requests (no `tools`); they are skipped.

**Not verified**
- Calibration on 150 + 150 points (needs a GPU gap).
- Scoring of `after_edit` and `submit` ran live on 2 points each taken from the real log (replies scored as expected);
  `after_warning` has no live reply yet (its 2 requests were still in flight at hand-over; they end by themselves and
  land in `tmp/probe_test/real/results.jsonl`).

**Timing for round 1.** 900 requests. At concurrency 4 on an idle server this fits in 170 minutes if a request takes
45 s or less. Measured beside running agents at concurrency 1: about 120 s per request, and the 100-point calibration
got about 15 requests per hour. Beside Screen A on Nov 12 a request took about 300 s. The script stops sending at 170 minutes and reports the points answered under all
three prompts, so beside a running screen it gives a partial table.
