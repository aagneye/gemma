# 16. Public notebooks, Nov 18: no recipe beats Budget-Fit over repeated runs

Read Nov 18, 05:50–06:05 UTC.
- **Sources:**
  - the competition's notebook list, sorted by public score;
  - the newest notebooks (by run date and votes);
  - 10 notebooks pulled to `research_nb/2026-11-18/` on the VM and read as text, never run;
  - the small-model leaderboard table (`ryanholbrook/gemma-4-developer-agent-small-model-leaderboard` output).
- Asked for by the user (Nov 18): one last candidate to test before the Nov 24 freeze.

## What the public scores say
- **Top notebook score:** 0.22 (13 of 58 public tasks). No published notebook scores 0.24 or more. Four notebooks are at 0.22:
  - Budget-Aware v2 (flexonafft, October);
  - "Version 1 added Adaptor" (ayush04barai, Nov 8);
  - Repair Lab (denpugovkin, Nov 16);
  - the 40-call recipe (bliverrigpdoge, Nov 14). Our confirmation 2 rejected it.
- **Every 0.22 is a single run. Evidence that it is luck:**
  - dariushafshar's census (Nov 17–18 updates):
    - The same files vary by 1.56 tasks from run to run (SD), so 95 % of runs land within about ±3 tasks.
    - Budget-Fit V5 averages 10.0 of 58 over 10 runs.
    - Budget-Aware v2 V10 scored 13 first, then 7, 7, 8, 9, 10, 10 and 10 when other people re-ran its files (mean 8.7).
  - **Budget-Fit V5 itself has scored 0.22:** the notebook titled "LB 0.22 | 4 config files, no training" packages our exact Budget-Fit V5 files (digest `c9829b6ac709`, the bundle we ship).
  - The adapter notebook puts its author's usual range at 0.12 to 0.22.
  - Caveman Thinking (Budget-Fit plus a section asking for terse thinking): 5 runs, mean 10.2, against Budget-Fit's 9.8 over 5 runs. Not separable (dariushafshar).
- **Leaderboard, Nov 17** (5,990 teams):
  - Bronze, the top 10 %, is 0.20 = 12 tasks.
  - The teams at 0.24 have a median of 15.5 submissions; best-of-many runs explains part of their lead.

## The recipes, against Budget-Fit V5
| Notebook (public score) | What differs from Budget-Fit V5 | Evidence |
|---|---|---|
| Repair Lab exp021 = Patchsmith V7 (0.22) | A new prompt: extract the issue's behaviour contract; batch the known searches; read 80–120 lines; edit within 6–8 calls; after two failed edit matches, edit through `run_command` with a check that the old text occurs once; keep 4 calls and 75 s for finishing; compile after the last edit; stopping rules; review the diff. Also 6 tools (no graph tools) and a 60-s command timeout. Apache-2.0. | One run at 0.22. Repair Lab's one-change variants of it scored 0.12, 0.12 and 0.17. Patchsmith's own notebook shows 0.20 (version unknown). |
| Patchsmith V11 (Nov 17) | V7 with 40 calls | Not scored |
| Version 1 added Adaptor (0.22) | A Budget-Fit-like prompt plus an edit-only LoRA (4.5 h of training); max output 6,144 | One run; the author's usual range is 0.12–0.22 |
| Budget-Aware Lean Context (Nov 17) | A new prompt; thinking 2,048; 10-minute task cap | Not scored; its parent scored 0.17 |
| Dvorkin V46 (0.20) | Its next submission is the 40-call recipe | Own runs 0.20, 0.17, 0.17 |

## Checked against our own runs (Budget-Fit, confirmations 1 and 2: 308 runs)
- **60-s command timeout:** nothing to fix. No command in the 308 runs hit the 240-s limit (2,102 exited 0; 499 returned errors, none of them timeouts).
- **Dropping the 3 graph tools:** nothing to fix. Budget-Fit called them 0 times.
- **The edit fallback** aims at garbled-edit loops. Our E1 line reduced those loops but did not change how many tasks were solved (confirmation 1).

## Small-model board (updated Nov 17)
- Top 0.12 (7 tasks); several teams at 0.10.
- We are rank 1,048 of 1,143 at 0.01, from one E4B run on Oct 27.

## Conclusion
- No public recipe has an edge over Budget-Fit across repeated runs.
- The strongest recipe not yet tested is Patchsmith V7: a whole new prompt with one 0.22 run, and its variants scored 0.12–0.17.
- **For the final picks:** the E4B pick has no realistic chance at the small-model prize. A second Budget-Fit run in that slot is worth about +0.9 tasks of expected private score, because the better of two independent runs counts: E[max of 2] − mean = 0.56 × 1.56 tasks.

## Status
Nov 18: the user approved a test of Patchsmith V7 (2 passes, 77 EVAL tasks). Confirmation 3 started at 09:50 UTC on the exact
scored files, the zip embedded in Repair Lab as `parent_original` (`research/STATE.md`, Nov 18 09:50 entry).
Nov 18 10:09 UTC: the user stopped it before any task finished. Patchsmith V7 stays untested.
