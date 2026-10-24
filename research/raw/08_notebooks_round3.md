# 08 — Public notebooks, round 3 (pulled 2026-10-22)

Pulled with `kaggle kernels pull` on the VM into `scratch/nb_round3/`. Text extracts (markdown + code + saved text outputs) are in
`research/raw/top_notebooks/<author>_<slug>/`. Supporting public datasets were also pulled where the notebook had no saved outputs:
- `dariushafshar_.../dataset/`: `public_config_draws.csv`, `board_blocks.csv` (CC BY 4.0)
- `scottweeden_.../kit_evidence/`: `SUBMISSIONS.md` and the evidence JSONs
- `robinamirbahar_optimizing.../dataset/`: the two small CSVs
- `jaikwang_.../paper/`: the embedded analysis scripts, decoded

Most notebooks were saved **without outputs**. Below, "measured" means a number that appears in saved output, in a pulled
dataset, or in an asserted constant. "Claim" means prose with no data behind it in what we pulled.

Unit conversion used throughout: **the public split is 58 tasks**. 0.17 = 10, 0.18 = 11, 0.20 = 12, 0.22 = 13, 0.24 = 14 tasks.

---

## 1. dariushafshar / gemma-4-most-run-public-config-averages-10-58 (priority 1, high value)

Census of 270 of 274 public notebooks' version histories (2026-10-22 06:35 UTC board). It finds 141 scored public versions and
traces 40 of them to an exact `files_sha256` of the submission bundle.

| Item | Measured value |
|---|---|
| Public split | 58 tasks (the only n ≤ 78 that reproduces all 15 displayed scores; data page says ~120 tasks split evenly) |
| Pooled within-config SD | **1.56 tasks** (23 df, 6 file sets, 29 draws). A binomial model would predict 2.79, so the measured SD is 0.56 of that, which means tasks differ in how solvable they are |
| 95% band for one draw | **±3.2 tasks** around the config mean |
| Budget-Fit Single Agent V5 (`c9829b6a`; T 0.2, 28 calls, 8 min, think 4096, 240 s) | n=10: 11,9,11,10,8,9,11,11,10,10 → **mean 10.00/58 (0.17)**, 95% CI 8.98–11.02 |
| Budget-Aware Coding Agent v2 V10 (`56010e9e`, the "public 0.22" config) | n=8: 13 first, then 8,7,10,10,10,7,9 → **mean 9.25**. Without the first run, 8.71 |
| SuperAgent V8 (`9f8886a9`) | n=4: 8,11,12,8 → 9.75 |
| honghanhhh Baseline V2 (`5d05a6e0`) | n=3: 8,11,9 → 9.33. V4 (`9335c6ba`): 9,8 |
| Patchsmith V1 | n=2: 5,6 |
| Best draw vs the mean of the other draws | +2.72 tasks on average (range 1.11–4.29) |
| Board (06:35 UTC, 22 Oct) | 0.24: 4 teams (median 15.5 subs); 0.22: 35 (12.0); 0.20: 148 (11.0); 0.18: 424 (9.0); 0.17: 555 (7.0) |
| Draws needed per arm (80% power, two-sided 5%) | 40 for a 1-task gain; 18 for 1.5; 11 for 2; 6 for 3 |
| Highest single draw of any public notebook | 13/58 (flexonafft V10). Next: 12 (jvnhonglei SuperAgent repro; prvsiyan v32). No public notebook has shown 14 |

Claims and modelled values: under a normal model the best of k draws beats the mean by 0.88 tasks (k=2), 1.81 (k=5), 2.40 (k=10)
and 2.91 (k=20). Going from 7 to 16 submissions explains only about 0.65 tasks of the 4-task gap between the 0.17 and 0.24
blocks. The rest is better configs or more effort, and a snapshot cannot separate the two. **Ties go to the earlier submission.**
Choose final submissions by the mean of identical draws. If the better of the two selected submissions sets private rank, two
draws of one config beat one by about 0.88 tasks.

## 2. liuzewen123 / noise-above-the-ablation-supporting-notebook (low value)

| Config | n | Scores | Notes |
|---|---|---|---|
| One 3,975-byte bundle, md5 `1acc6381` (config not shown; its originator reported 0.12) | 3 byte-identical submissions on 3 days | **0.05 / 0.06 / 0.08** (3 to 5 tasks) | All three fall below the reported 0.12. 2 of 11 submissions returned **no score at all** (reported as None, not 0) |
| arm2 = arm1 + one skill (`73e2252d`) | 1 | not in the saved text | Paper's verdict: unresolvable at n=1 |

## 3. jaikwang / gemma-4-measuring-the-measuring-stick (high value for the statistics)

No outputs were saved, but the notebook **asserts** its numbers, so the values below are pinned. It uses Gluzdov's dataset
(692 agent outcomes: 8 configs on 70 dev tasks and 3 on 44 Rich tasks, 31B, seed 42) and busyaprime's grader audit.

| Item | Value |
|---|---|
| Docker soundness of the 129 public tasks (2 base runs + 3 gold runs, sandbox-shaped: no network, 2 CPU, 4 GB) | 104 sound, 15 env_blocked, 6 gold_fails, 4 base_passes. No flaky gold tests |
| Agreement with Gluzdov's audit | 100 both sound, 4 ours only, 14 theirs only, 11 neither; κ=0.473. **100 consensus-sound tasks** across all three audits (Fleiss κ 0.556); the list is `consensus_sound_tasks.txt` |
| Intra-task correlation ρ | 0.574 across 8 configs; **0.59 (95% CI 0.03–0.78)** from reruns of identical archives. Tasks are mostly always-solved or never-solved |
| Minimum detectable difference, one run each (n=58, p≈0.15) | 0.12 at ρ=0.6 (7 tasks); 0.19 at ρ=0 |
| Patch size | **Odds ratio 0.53 per doubling of gold source lines added** (full logistic model with config and repo fixed effects, SEs clustered by task) |
| Predicting which tasks are ever solved from anatomy alone (size + issue names the location + statement length) | AUC **0.83** (95% CI 0.68–0.95), leave-one-repo-out |
| Expected public/private gap | **SD 0.067** (about 4 tasks) at p=0.16 |
| P(a bundle with true mean 29/174 shows ≥0.22 in best of 5) | 0.26 at ρ=0.6; 0.46 at ρ=0.3 |

Public draws it lists in tasks/58, from Afshar: Budget-Fit `c9829b6a` scored 0.18 ×4, 0.17 ×3 and 0.13 once. Budget-Fit plus one
line scored 0.13 and 0.15. A Gluzdov coder-analyzer archive scored 0.12, 0.10 and 0.06.

## 4. robinamirbahar: three notebooks (NO evidence; treat as fabricated or simulated)

| Notebook | What is there | Verdict |
|---|---|---|
| optimizing-w4a16-thinking-budgets-under-time-caps | A 6-row CSV with no provenance. W4A16 at thinking 2048 and a 3-min cap reports a "72% resolve rate", 1024 → 64%, 512 → 52%. BF16/W4A16 at 4096 and a 1-min cap report 20–28% | Not a measurement. No harness, no task list, round numbers, and the figures are far outside every real result (all real results sit at 17–30%). **Ignore** |
| gemma-4-loop-breaker-ccr-trap-25-benchmark | A "4-arm ablation" on 25 synthetic trap tasks run with `BACKEND='markov-theory'`. Recovery probabilities are hard-coded (`p_recover = 0.12 if adaptive else 0.08`, exponential decay) and the gold patch is injected with that probability | **Simulated; zero evidence.** The useful part is the idea: loop detectors (same error signature twice; edit similarity ≥0.82 on the same file; action entropy <0.55 bits over 4 calls) that prune the looping turns into a "negative constraint" note |
| detecting-swe-agent-action-loops-with-jaccard | 10 hand-written command pairs. τ=0.80 Jaccard plus nonzero exit codes = "loop" | Toy data. Ignore the numbers |

## 5. xiuchisun / gemma-4-agent-budget-fit-31b-mainline (republish of Budget-Fit V5)

| Config | Notes |
|---|---|
| 31B; T 0.2, top_p 0.95, max_output 8192, thinking 4096, include_thoughts true; eval: 240 s / 28 calls / 8 min / 80 turns; 9 tools; prompt = official sample plus a budget section (edit by call 12; no new exploration after call 20; graph tools banned) | Byte-identical agent files to `c9829b6a` → **mean 10.0/58 over 10 draws** (see §1). The author claims a scored run at 8 min "finished in under 12 hours" |

Claims carried over from Henao: 129 local runs; at 4 min only about half of eventual fixes exist; no edit by call 12 → 87% fail.
`timeout_seconds 240` is there "because the scoring pytest uses the same timeout". **That reason is stale.** Our 07 notes say
swegemma 0.2.11 gave verification its own 300 s limit.

## 6. ryanholbrook / gemma-4-developer-agent-small-model-leaderboard (host)

| Item | Value |
|---|---|
| Small Model Prize board (2026-10-20 19:27 UTC) | Only **24 teams**. Top: **0.06** (3 teams); 4 teams at 0.05; 11 at 0.03 |
| Eligibility | The submission must be one of the team's two selected final submissions |

Notebook text does not define "small model". It is presumably 12B/E4B/E2B. **Verify this.** Our 12B baseline scored 0.08 in
round 2, which would top this board.

## 7. julesevers / loc32k-reproduction-notebook (method only, no numbers saved)

Training-free localizer under a token budget. It ranks with BM25 (file + function units), exact identifier hits from the issue,
IDF-weighted grep, git-history recency, and a 1-hop import/call-graph rerank (α=0.3 from the top 5 seeds), all fused with RRF.
The CLI script prints the top 10 files and top 25 functions within 4,800 characters, so it could ship as a `.py` in the bundle and
run via `run_command`. Gold annotations come from AST-mapping the gold patch. **No hit@k or end-to-end numbers survive in the
pulled version**, and the paper's e2e section is explicitly not reproduced.

## 8. honghanhhh / gemma-4-baseline-lb-0-24 (latest = "v5 (safe)", last run 2026-10-21)

| Version | Config | Scores |
|---|---|---|
| V2/V3 (`5d05a6e0`) | Budget-Fit-like | 8, 11, 9 (n=3) |
| V4 (`9335c6ba`) | + a whole-test-file verification run | 9, 8, and then "Notebook Timeout / Notebook Threw Exception" (the author suspects the whole-file test run) |
| **V5 (current)** | Base: flexonafft V10. Changes: **max_time 8 → 7**, **max_output 8192 → 6144**, everything else unchanged (T 0.2, think 4096, 28 calls, 240 s). Prompt = "CALL PLAN" (edit by call 12, verify 13–20, no exploration after 20) + protect pytest.ini/conftest; scratch only in /tmp; fix every parallel implementation; finish with `git status --short && git diff`; `timeout 150 pytest ... | tail -40`; keep behaviour for inputs the issue does not mention | **No score in our data.** Title still says 0.24, but no scored version ever showed 0.24 (best 0.18) |

This is essentially our CALL PLAN prompt.

## 9. scottweeden / gemma-4-developer-agent-tool-lora-writeup (high value: real harness numbers on 4×L4)

Real `swegemma eval`, vLLM 0.19.1 from the wheelhouse, TP=4, 32k context, thinking on. Bundle **A1** = one coder agent, 9 tools,
prompt with a "GRAPH decision line", T 0.2, top_p 0.95, max_output 8192, **thinking 4096**, eval 240 s / **32 calls** / 8 min / 80 turns.

| Run | Fold | Concurrency | Resolved | fail_tests | no_patch | timeout |
|---|---|---|---|---|---|---|
| A1, A100, T 0.7, seed 0 | repo-train 81 (fastapi 67, requests 13, httpx 1) | 8 | 18 (0.222) | 27 | 6 | 30 |
| A1, A100, T 0.7, seed 1 | same | 8 | 17 (0.210) | 33 | 4 | 27 |
| A1, 4×L4, T 0.7, pass 1 | same | 8 | 10 | 12 | 2 | **57** |
| A1, 4×L4, T 0.7, pass 2 | same | 8 | 12 | 17 | 2 | **50** |
| A1, 4×L4, T 0.2 | rich 48 | 8 | 13 | 2 | 0 | 33 |
| **A1, 4×L4, T 0.2** | rich 48 | **2** | **14 (29%)** | 11 | 4 | 19 |
| graph-first (think **2048**, first edit by call 8, one graph call instead of more reads) | rich 48 | 2 | 13 | 15 | 6 | 14 |

- **Ablation, graph-first vs A1 (paired, n=48):** gains 1 task, loses 2. Median tool calls 21 vs 26; 5 fewer timeouts; 4 more test failures.
  Reading less turned saved time into wrong patches, not resolves.
- **Concurrency:** on 4×L4 the KV cache holds about 36k tokens (about 1.4 full sequences). Going from 8 to 2 concurrent tasks cut
  timeouts from 33 to 19. The scorer runs tasks **one at a time** (host, discussion 743063).
- A1 durations (rich, concurrency 2): p50 457 s, p90 485 s, max 723 s. Resolved-task durations (s): 111, 144, 163, 170, 181, 197,
  206, 210, 273, 318, 340, 383, 484, 485. So **3 of 14 resolves take more than 6 min.** None of the 19 timed-out sessions resolved.
- 12-hour projection (claim, modelled from these durations at 0.7–1.0× speed plus 45 s overhead): an 8-min cap means about
  12.4–14.2 h for 120 tasks, so the author ships 6 min. **This conflicts with §1/§5:** Budget-Fit V5 and the 0.22 config run at
  8 min and scored 10 and 8 times without a timeout.
- **Scorer incident (measured by the author's own submission, plus forum reports):** "Since about 04:00 UTC on 21 Oct many teams
  report 'Notebook Threw Exception' on zips byte-identical to ones that scored days earlier" (discussion 751339). The author's
  6-min A1 submission of 22 Oct failed with "Notebook Threw Exception". The author's MoE SequentialAgent (6 experts) scored **0.05** on 7 Oct.
- **LoRA (measured, but resolve rate not measured):** r=16, alpha 32, all 410 language-model projections, QLoRA nf4 on 4×L4.
  Training data: 83 of 176 samples, which are the model's own resolved turns from 14 tasks (rejection sampling, ≤2 runs per task,
  ≤8 turns each). Loss on assistant tokens went 0.17 → 0.11. Held-out tool-choice agreement went 0.990 → 0.985 (n=200, measured
  against base labels, so it measures drift, not quality). The **resolve-rate run is pending (GPU quota)**, and the shipped bundle
  has no adapter. Engineering notes: Gemma 4's global layers use head dimension 512, so SDPA falls back to the math kernel; 16k
  context needs query-chunked attention. The chat template renders visible text after tool calls in history, but generation puts it before.

## 10. Remaining notebooks

| Notebook | Config / content | Measured | Notes |
|---|---|---|---|
| engziadsamer / clean-self-distillation-cpu | CPU pipeline. Builds SFT samples from the model's own resolved harness runs: cut each episode at the first successful `submit_patch`; keep only runs that are resolved, touch a gold-fix file, contain no test or scratch files, have ≤3 failed calls in a row, ≤2 repeats and ≤2 rereads | **No resolve numbers** | Documented behaviour of the base model (from their trial logs): **it keeps calling `submit_patch` after submitting ("Bye."/"End." turns), up to 81 calls in one resolved run.** Final replies are sometimes malformed: the thought channel leaks into the content, or a tool call is written as plain text. The chat template drops the thinking of a final turn without tool calls. The harness sometimes drops earlier thoughts from history, and ADK compaction rewrites the prompt |
| yunyijian / exp002-agent-4-developer-agent | Starter fork. eval 120 s / 40 calls / 5 min / 60 turns. Local Evaluator with `EventsCompactionConfig(interval 15, overlap 2, token_threshold 14336, retention 5)` and context cache (min 2048 tokens) | Ran 2 tasks; no output saved | Nothing measured |
| philgear / swe-gemma-local-kaggle-sandbox-evaluator | "Sovereign Loom v19". Base64 bundle; claims `include_thoughts false`, thinking 3072, max_output 8192; wheelhouse swegemma 0.2.11 / adk_submission 0.2.13 | None saved | Branding-heavy; no evidence |
| sadiqguru / does-the-code-graph-find-the-bug | Offline retrieval benchmark: graph tools vs BM25/TF-IDF, file recall@k, with the issue as query and gold files from `patch` | Numbers are generated at run time; **none saved** in the pulled version | Method notes: `get_code_subgraph` only returns the nodes it is given, so it cannot discover anything. `search_similar_code` excludes the anchor itself and splits 5,000 characters across k results. `get_code_neighbors` returns at most 50 names. Its recommendation logic is "keyword search first, graph only to widen around a found symbol" (outcome unknown) |

---

## Cross-cutting facts

- **Thinking budget.** 4096 is used by every config that has scored ≥0.17 in repeated draws. 2048 appears only bundled with other
  changes (the graph-first prompt; the "reduced-thinking Budget-Fit" variant in 07b), so it has no isolated result. No notebook in
  this round reports a thinking_budget value that *breaks* scoring. The only "thinking" numbers that look like a sweep are robinamirbahar's, and they are fabricated.
- **max_output_tokens.** vLLM rejects prompt + max_output > 32,768. 8192 is standard; honghanhhh v5 uses 6144 to leave about 2k more for history.
- **Scorer failures.** "Notebook Threw Exception" has hit byte-identical zips since about 04:00 UTC on 21 Oct (discussion 751339,
  reported by scottweeden). honghanhhh v4 failed with Timeout/Exception after adding a whole-test-file run. liuzewen123 had 2 of 11
  submissions return no score. No notebook in this round uses the exact phrase "unhandled error while rerunning your code".
- **12-hour cap.** About 120 tasks run sequentially in one 12 h window. 8-min/28-call configs have completed many times (Budget-Fit
  n=10, 0.22 config n=8). The 12.4–14.2 h projection is a model built on 4×L4 local durations, not a scorer observation.
- **Variance.** SD 1.56 tasks per draw (pooled, n=29 draws). Task-level ρ≈0.59. Expected public/private gap SD ≈4 tasks.
- **LoRA / self-distillation.** No public resolve-rate gain in round 3. scottweeden's run is pending; engziadsamer's is pipeline
  only; 07b's LoRA diagnostic failed its gate. Forum consensus (00b) is that the top is not driven by fine-tuning.

---

## What this means for us (ranked by expected gain in resolved tasks)

1. **Final selection, +0.9 private tasks expected at zero engineering cost, and it is the biggest lever we can bank now.** Pick the
   final two submissions as **two separate scored draws of our best-mean config**, not the single highest public draw. Assuming the
   better of the two selected submissions counts on private (normal model, SD 1.56), that gives about +0.88 tasks over one draw.
   Our 0.22 (13/58) sits about 2 SD above the measured mean of this config family (Budget-Fit 10.0, n=10; the 0.22 config itself
   9.25, n=8). **This confirms our belief that 0.22 is a lucky draw of a ~0.17 config.** Since ties go to the earlier submission,
   our early 0.22 already holds its place on the public board; it does not predict private.
2. **Measure on our local paired eval, never on LB deltas.** Seeing a 2-task gain needs 11 draws per arm, so the LB cannot rank
   configs. Filter our local set to jaikwang's **100 consensus-sound tasks** (we use about 50 Kaggle-sound tasks, so check the
   overlap). Weight analysis toward **small-patch tasks** (odds ratio 0.53 per doubling of patch size; AUC 0.83 from anatomy):
   gains will come from the "sometimes solved" small tasks.
3. **Local concurrency may be inflating our 7/50 "hit the 8-min cap" bucket.** scottweeden: going from 8 to 2 concurrent tasks cut
   timeouts from 33/48 to 19/48 on 4×L4, while the scorer runs one task at a time. If our paired eval runs concurrent sessions on
   one vLLM, re-measure the cap-hit rate at concurrency 1–2 before spending effort on speed. This could move about 2–4 of our 7 cap
   cases into resolved or wrong-patch.
4. **Forcing earlier edits or less reading converts timeouts into wrong patches, not resolves.** Paired n=48: graph-first gained 1
   and lost 2, with 5 fewer timeouts and 4 more test failures. This fits our profile (14/50 unverified wrong patches is already the
   largest bucket). **Contradiction with the idea of "push the 10 search-loop runs to edit sooner":** expect most of those to land
   in the wrong-patch bucket unless verification improves. The evidence favours spending saved time on verification (reproduce,
   then targeted test), not on an earlier first edit.
5. **Add post-submit loop control and fix malformed final turns (cheap and plausible; no resolve-rate measurement exists).**
   engziadsamer documents `submit_patch` being called repeatedly after submission (up to 81 calls in one run), thought-channel
   leaks, and tool calls written as text. This bears on our "9/50 lose their edit (edit_file errors / editing after budget)"
   bucket. A prompt rule ("after submit_patch returns patch_size>0, reply with one sentence and stop") plus loop detection
   (same error signature twice, or near-identical edits) is low-risk. robinamirbahar's thresholds (0.82 edit similarity, 2 repeated
   error signatures) are untested ideas, not evidence.
6. **Time cap: keep 8 min, with 7 min as the hedge only if a run fails.** No scorer observation shows an 8-min/28-call config
   exceeding 12 h (Budget-Fit and the 0.22 config completed 18 draws between them). scottweeden's 6-min choice rests on a 4×L4
   projection and gives up 3 of 14 resolves (those over 360 s). honghanhhh's 7 min + 6144 max_output is unscored. Do not cut the cap on this evidence.
7. **Treat "Notebook Threw Exception" since 21 Oct 04:00 UTC as a platform incident** (discussion 751339) before blaming a bundle.
   Resubmit byte-identical before changing anything, and do not burn slots diagnosing it.
8. **Small Model Prize board is thin (top 0.06, 24 teams on 20 Oct).** Our 12B baseline scored 0.08 in round 2. Verify which
   models count as "small". If 12B qualifies, selecting a 12B submission as one of the final two may take that prize, at the cost
   of a main-board slot. This is a strategic call, not a resolve-rate gain.
9. **Deprioritise LoRA and self-distillation.** No resolve gain has been shown publicly; the one adapter built on on-policy successes
   barely changes tool choices (0.990 → 0.985 agreement). If we do train, scottweeden's lesson is to train on recoveries after
   failures and near-timeouts, not on easy successes.
10. **Re-check `timeout_seconds: 240`.** Its stated rationale (verification shares the timeout) predates swegemma 0.2.11, where
    verification has its own 300 s. Agent commands hit 240 s about 0.05% of the time, so this is neutral. Leave it unless a trace shows otherwise.

**Contradictions with our findings:** none on the core claim. The public "0.22 config" averages 9.25/58 over 8 draws, and the
config family (ours included) averages about 10/58. The only tension is item 4: public paired evidence says that saving
search/time budget mostly creates wrong patches, so our "10 never edit" fix should be paired with a verification fix, not shipped alone.
