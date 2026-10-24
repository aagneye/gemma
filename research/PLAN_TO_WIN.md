# Plan to win (2026-10-24, 39 days to the Dec 2 deadline)

## Where we are
- Best public LB: **0.17** (31B, v3 prompt). Leaderboard top: 0.24 (4 teams), then a crowd at 0.22.
- Measured truth (paired, Kaggle-sound tasks): every 31B prompt variant ties at ~44 % (22-23/50). Public "0.22" configs
  average ~0.17 over repeated submissions; a single LB score moves +-3 tasks by luck (SD 1.56 tasks of 58).
- Today: v3t2k resubmitted (ref 57603042); v5 paired eval running; the daily auto-ship job guarantees no lost slots.

## Two prizes, two tracks
| Prize | Rule | Top today | Our position | Winnable? |
|---|---|---|---|---|
| Main track, $37k / $18k / $10k | top 3 on the private set (62 tasks), best of the 2 final picks | 0.24 public | ~0.17 mean | needs +4 tasks of true mean: hard |
| **Small Model bonus, $10k** | best submission whose base model is **Gemma E2B or E4B** (LoRA allowed); must be one of the 2 final picks | **0.06** public (24 teams) | not entered yet | **yes: the field is weak and E4B fits our T4s for evals and training** |

**Final selection (Dec 2):** pick 1 = best paired-eval 31B bundle (main track); pick 2 = best paired-eval E4B bundle
(Small Model prize; also counts for the main track). Rationale: a second 31B pick only adds ~+0.9 tasks of expected
luck, while the E4B pick is a direct shot at $10k.

## Track B — Small Model prize (new, highest expected value)
1. **Baseline E4B** (this week): download `gemma-4-e4b-it-qat-w4a16-ct` to the VM (fits one free T4), run the current
   best bundles with `model: gemma-4-e4b...` on the VM replica (16 -> 50 tasks) and one Kaggle L4 eval.
2. **E4B-shaped bundle**: shorter instructions (small models follow long prompts worse), more calls (E4B is ~5-8x faster
   than the 31B, so 40-60 calls fit the 12 h cap), thinking budget sweep (0 / 1024 / 2048). Time-projection gate < 10.5 h.
3. **Distill the 31B into E4B with LoRA** (trains on the T4s): rejection-sampled successful 31B trajectories from our
   Kaggle-environment runs (~70 resolved so far, more from every new eval) + the curated SWE trajectory set already
   converted to the harness format (`datasets/sft_v4_mid`). Verify end-to-end that a LoRA on E4B scores on the scorer's
   vLLM 0.19.1 (open forum question 752239) with a Kaggle-environment eval before relying on it.
4. **Ship**: put the best E4B bundle on the LB to appear on the small-model board; keep improving to the deadline.
Target: E4B >= 0.10 public (beats the current 0.06 field).

## Track A — Main track (31B)
1. **Daily draws** of the best paired-eval 31B bundle via `vm/daily_ship.sh` (`results/ship.txt`); the public LB keeps the
   best draw, so 30+ draws of a ~0.17-0.19 config make >= 0.22 on the public board likely.
2. **Raise the true mean** (each change gated: >= +3 paired tasks, 120-task projection < 10.5 h):
   - v5 prompt (reproduce-first, callers lookup) — eval running.
   - Budget headroom: 120 tasks take ~9.3-9.9 h of 12 h -> try 32-34 calls / 9 min.
   - 31B self-distillation LoRA (train on its own successful trajectories) — needs bigger GPUs than T4: Kaggle L4x4
     notebook (96 GB) within quota, or the VM when all 4 T4s are free.
3. Week of Nov 23: freeze; only confirmation draws.

## Weekly compute budget
- Kaggle L4: 30 GPU-h/week (~3.5 four-hour evals). Spend on 31B paired evals and one E4B check per week.
- VM T4s (shared): E4B evals + E4B/12B training whenever free; 31B replica only when all 4 GPUs are free.

## Risks
- Scorer outages (Oct 21): the host reruns failed submissions; post our failed ref 57491112 in thread 751339 (needs the user's OK).
- Small-variant LoRA might not load on the scorer's vLLM -> verify on Kaggle before shipping; fall back to prompt-only E4B.
- The small-model page also says "Submissions must be made by November 12" in one paragraph while the official post says
  "same deadlines as the main track": treat Nov 12 as the safe deadline for having an E4B entry on the board.
