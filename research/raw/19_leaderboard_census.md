# 19. Leaderboard census (Nov 21 2026, 15:11 UTC)

**Why:** the user asked why we cannot win. The answer needs the whole public board, not its first page.
**Source:** `kaggle competitions leaderboard gemma-4-developer-agent --download` (kept on the VM as
`results/lb/public_lb_2026-11-21.csv`), our own submission list, five public notebooks published after the Nov 18 search.

## 1. How the score is built
- Public score = solved tasks / 58, **cut** to two decimals (not rounded).
- The board holds exactly the 15 values of 0 to 14 solved tasks and no other value:

  | Solved | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
  |---|---|---|---|---|---|---|---|
  | Score | 0.13 | 0.15 | 0.17 | 0.18 | 0.20 | 0.22 | 0.24 |

## 2. The board
- 6,343 teams, 56,174 submissions.

  | Best score | Solved of 58 | Teams |
  |---|---|---|
  | 0.24 | 14 | 16 |
  | 0.22 | 13 | 125 |
  | 0.20 | 12 | 604 |
  | 0.18 | 11 | 1,230 |
  | 0.17 | 10 | 1,167 |
  | 0.15 | 9 | 862 |
  | 0.13 | 8 | 496 |
  | 0.12 and lower | 0–7 | 1,843 |

- **Nobody is above 14.** The top line was already 0.24 on Oct 22 (CLAUDE.md); a month and tens of thousands of
  submissions later it is still 0.24.
- **We:** rank 718, best 12 solved (Nov 19), 32 submissions. The block of 0.20 covers ranks 142–745.
- Column `LastSubmissionDate` is the date of a team's last scored submission, not of its best one (our row shows
  Nov 20, our best is Nov 19). It says nothing about when the top scores were reached.

## 3. Best score against number of submissions
The board shows each team's best run.

| Submissions of the team | Teams | Share with best ≥ 0.20 | Share with best ≥ 0.22 | Teams at 0.24 |
|---|---|---|---|---|
| 1–4 | 2,860 | 2.0% | 0.3% | 1 |
| 5–9 | 1,433 | 9.5% | 1.2% | 3 |
| 10–19 | 1,263 | 16.7% | 3.0% | 3 |
| 20–29 | 468 | 38.0% | 6.6% | 1 |
| 30 and more | 319 | 51.1% | 14.4% | 8 |

- The share of teams at 12 or 13 solved grows steadily with the number of runs: the pattern of a best-of-many draw.
- Among the 3,142 teams with a best of 0.17 or more (42,177 submissions): one run of 14 per 2,636 submissions, one run
  of 13 or more per 299. These counts include those teams' weaker experiments, so a good bundle draws somewhat better.
- With 32 submissions we sit in the last row; half of those teams have 0.20 or more, one in seven has 0.22 or more.

## 4. Our own runs
- Budget-Fit V5, 16 scored runs: 8, 8, 8, 9, 9, 9, 10 (eight times), 11, 12 solved. Mean 9.6, SD 1.1 tasks.
- A team whose usual run were 13 would show 15 or 16 as the best of ten runs. The board's maximum is 14, so no team
  has shown a usual run clearly above the public recipes.

## 5. Public notebooks since the Nov 18 search
Skimmed by a search for score lines and settings, not read in full.

| Notebook (date) | What it is | What it reports |
|---|---|---|
| leoprovorov, "Score To / Gemma 4" (Nov 19) | The Budget-Fit files unchanged (same hash `c9829b6a` as our bundle) | "about ±2 tasks between identical submissions"; a neighbouring bundle's 0.22 was the best of eight draws that averaged 0.156; expects about 0.17, within 0.13–0.20 (ten draws) |
| mathleteutd, "Reproducible Bundle + 9 Submissions" (Nov 20) | A public config, unchanged | Unchanged: 0.20 and 0.18. Its own changes: 0.13 (two extra rules), 0.15 (rewritten prompt), 0.10 (40 calls, 6 minutes) |
| evgendvorkin, "Can Gemma 4 Become a Software Engineer?" (Nov 21) | An own mix on a 28-call public base | 0.12, 0.17, 0.22 (best), repeat 0.17, 0.13, 0.17; "one score does not establish stability" |
| flexonafft, "Budget-Aware Short-Prompt" (Nov 19) | Short prompt, thinking 1,024, 10 minutes, 28 calls | Its base scored 0.17 once; no repeated runs. Ten minutes per task is a runtime risk under the 12-hour limit |

- No notebook reports repeated runs above Budget-Fit's. Two of them say what our 16 runs say: an unchanged public
  bundle lands at 0.13–0.20, and each own change scored lower.

## 6. What follows
- **The top of the public board is a best-day draw.** Chance for us with Budget-Fit in the ten runs left before Dec 1
  (rough; from section 3 and from our 16 runs with SD 1.1–1.56): about 1 in 10 for one run of 13 (0.22), about 1 in 100
  for one run of 14 (0.24).
- **What a pass of round 2 would mean on the board:** the bar is +3 solved of 77 on EVAL (43 → 46, +7%). On a usual
  Kaggle run of 9.6 that is under one task if the gain carries over in proportion. It would be a real edge for the
  final ranking; it would not make a 14 likely.
- **Reaching the top by skill** would need a usual run of about 13 (+35% over the public recipe). No team among 6,343
  has shown half of that.
- **Final pick (Dec 1), to raise then:** if a whole run can be slow or fast (a slow Kaggle machine), the public and the
  private score of one run move together. Then the run with the best public score is the better pick than the earliest
  one, and it costs nothing if the two are independent.
- The forum measurement of Oct (raw/00b, thread 747168) fits: stronger models in Gemma's seat solved 10 of the 60
  tasks Gemma failed twice; the limit is the test (short issue text, 32k context, about 5.5 minutes per task, an
  unsound grader on 58 of the 129 public tasks), not the model's reasoning.
