# Post-mortem and architecture v4 (2026-10-21)

## 1. Where we stand
| Day | Package | Public LB | Note |
|---|---|---|---|
| Oct 18 | 12B, our prompt, 50 calls / 5 min | **0.08** | wrong model + weak prompt |
| Oct 19 | `pub022` = byte-exact copy of the public 0.22 notebook (31B) | **0.15** | same config others list at 0.22 |
| Oct 20 | `v3` = pub022 + edit-by-call-10, output caps, hygiene rules | **0.17** | +1 task, inside noise |
| Oct 21 | `v3t2k` = v3 + thinking_budget 2048 | pending (ref 57491112) | Day-4 delta |

Kaggle-environment evaluation (our new tool, `vm/make_kaggle_eval.py`, the scorer's own sandbox and L4 serving): pub022 resolves **22/50 = 44 %** of Kaggle-sound public tasks (fastapi 12/25, rich 10/25), 291 s mean per task (120-task projection 9.7 h of the 12 h cap).

## 2. Why the score is not increasing
1. **The leaderboard number is a noisy draw.** 58 tasks, one sample per day: ±2-3 tasks is ±0.035-0.05. The public "0.22" is the best draw among dozens of teams who submitted the same notebook (27 teams sit at exactly 0.22 because ties are visible, the lower draws are not). The same bundle gave us 0.15. Prompt tweaks worth +1 task cannot be seen on the LB.
2. **We measured on the wrong tasks.** Our VM Docker grader agreed with Kaggle's sandbox on only 8 of its 21 "sound" tasks (Kaggle-sound: 71/129 = fastapi 29 + rich 42; requests/httpx gold patches fail there). All earlier local A/Bs (skills, adapter) were measured mostly on unsound tasks.
3. **The failures are behavioural loops that a prompt cannot enforce** (trace analysis of the 50 runs, `vm/analyze_traces.py`):

| Mode | Runs | What happens |
|---|---|---|
| Resolved | 22 | median 21.5 calls, first edit at call 10 |
| Wrong patch, submitted | 14 | edited, but only 13/50 runs ever ran a test; patch never checked |
| No edit, calls exhausted | 7 | 28 calls of searching/reading; "edit by call 10" ignored |
| Wrong patch / no edit, 8-min timeout | 7 | a single command (repro with an infinite loop) burns the 240 s command timeout; or very long thinking |

Concrete loops seen in traces:
- `grep` with no match exits 1, the harness reports `CommandError`, and the model retries near-identical greps (rich_3470: 8 retries).
- Drip-feed reading: `grep -B 50`, `grep -B 100`, then `read_file` of 30-line windows of the same function (fastapi_14306: 28 calls, never edited).
- `python -c` repro without `timeout` runs into an infinite loop; 240 s gone (rich_3480 found the bug, then timed out).
- **Every run with a failed edit_file was lost (0/9)**: 6 edits attempted after the budget was gone (call 29), 5 `old_string not found`, 1 ambiguous match.
- Runs that used all 28 calls resolve 6/20 (30 %); runs that finished in 15-27 calls resolve 13/23 (57 %).
4. **Spent effort with no score path:** skills (0/4 locally, forum 0.15 -> 0.00), T4 local scoring on unsound tasks, 12B adapter training before the base 31B configuration was understood.

## 3. Constraints that shape the design (verified in the harness source)
- No competitor Python: the YAML compiler resolves callbacks against a `CallbackRegistry` that the scorer leaves empty. All control is: instructions, tool subsets, budgets (`eval_config.yaml`), sampling/thinking, adapters, and **workflow agents** (`SequentialAgent`, `LoopAgent`, `ParallelAgent`, `AgentTool`).
- The outer runner (`swegemma/harness/agent_runner.py`) ends a task on a final text response **only if `submit_patch` was already called**. A sub-agent's final text therefore hands control to the next sub-agent of a `SequentialAgent` in the same turn; if the whole sequence ends without a submit, the harness nudges (max 3) and the sequence restarts from its first phase with the full history visible.
- Budgets are global (28 calls / 8 min / 80 turns for the whole tree); `budget_warning` appears once <= 10 calls remain. The per-command timeout (`timeout_seconds`) is separate from verification (300 s since swegemma 0.2.11).
- Measured negatives from other teams: coder + analyzer AgentTool (16/70 vs 27/70), reviewer voting (13/70), extra tools, skills, 6-min schedules, T=0/0.4. These all **add calls or summaries**; phase switching on a shared history adds none.

## 4. Architecture v4: phase-structured agent ("Scout -> Fixer -> Finisher")
```
agent.yaml: SequentialAgent swe_pipeline                     (shared history, one budget)
 ├─ scout     tools: run_command, read_file                  (cannot edit)
 │    goal: one batched anchor search, read the implementation once (<=120 lines),
 │          stop after <=8 calls with a text block LOCATION / ROOT CAUSE / CHANGE / ALSO-CHANGE
 ├─ fixer     tools: read_file, edit_file, write_file, run_command
 │    goal: first call is edit_file; implement CHANGE and ALSO-CHANGE (parallel implementations),
 │          one compile check; stop with CHANGED: ...
 └─ finisher  tools: run_command, read_file, edit_file, get_status, submit_patch
      goal: one targeted test with `timeout 60`, fix once if a related failure, git status/diff, submit_patch
```
Why this targets the measured failures:
- **No-edit loops (10/50):** the scout cannot edit and is told to stop once it can name the location; the fixer's only job is the edit. The "edit by call N" rule becomes a phase boundary instead of a counter the model has to keep.
- **Unverified wrong patches (14/50):** the finisher exists only to test and submit; today 37/50 runs never test.
- **Lost edits (9/50):** the fixer instruction carries the edit protocol (copy `old_string` verbatim from a fresh read, smaller unique snippet on failure, never after budget_warning <= 2).
- **Time sinks (7/50):** `timeout_seconds` 240 -> 90, and every python/pytest command is wrapped in `timeout`.
- Restart safety: after a nudge the scout sees the history; its instruction says "if a source file was already edited, reply DONE with no tool call", so the sequence falls through to the finisher.

Cross-cutting tool rules (all phases): grep exit 1 = no match (append `|| true`, never retry a variation more than once); output caps (`| head -40`, `2>&1 | tail -30`); never re-read a region already in context; scratch files only in /tmp.

## 5. Variants and how they are decided
| Bundle | What changes vs pub022 | Purpose |
|---|---|---|
| `v4_single` | single agent, prompt v4 (v3 + the loop-breaking tool rules + edit protocol), timeout_seconds 90 | isolates the rule/timeout gains without the workflow |
| `v4_phased` | SequentialAgent scout/fixer/finisher, same rules, timeout_seconds 90 | the architecture |
| thinking 2048 vs 4096 | decided by `v3t2k` (LB + paired Kaggle-env run, in progress) | applied to whichever v4 wins |
| 12B + `12b_r32_v4mid` adapter | 2x faster model, 40 calls | speed/quantity alternative, one Kaggle-env run when quota allows |

Decision protocol (replaces LB-driven decisions):
1. Every candidate runs in the Kaggle environment on the same task order (71 Kaggle-sound tasks, round-robin fastapi/rich, 4 h budget ~ 50 tasks) -> paired comparison with pub022 (22/50).
2. Adopt only with >= +3 tasks paired AND no time regression (120-task projection < 10.5 h).
3. Only adopted bundles get a daily LB slot; final picks = the two best paired-eval bundles, not the two best LB draws.
4. After each run: `vm/analyze_traces.py` -> failure-mode table -> next change targets the largest bucket.

Quota: 30 GPU-h/week at 2x for L4 = ~3.5 four-hour runs per week. Week of Oct 24: v4_phased, v4_single, then the winner + thinking choice.

## 6. Targets
pub022 = 44 % on Kaggle-sound public tasks ~ 0.15-0.22 on the LB. The top-10 line is 0.22-0.24 today and will rise. If v4 converts half of the no-edit runs and a third of the unverified wrong patches, the paired eval moves from 22/50 to ~28/50 (56 %), which corresponds to ~0.24-0.28 on the LB scale (the hidden set is harder than the sound public subset).
