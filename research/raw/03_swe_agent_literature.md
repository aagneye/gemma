# 03 — Literature review: LLM software-engineering agents for SWE-bench-style issue resolution

**Prepared for:** Kaggle team post-training Gemma 4 (4B–31B, LoRA-only, offline, tool-call + wall-clock budget) to fix GitHub issues in Python repos (train: fastapi, rich, requests, httpx; test: hidden private repos).
**Date:** 2026-10-16. Coverage: Oct 2023 – Oct 2026.
**Method:** ~78 web searches / page fetches (arXiv abstracts + HTML full texts, GitHub READMEs, HF dataset cards, swebench.com, llm-stats, steel.dev, Nebius, NVIDIA, Together/Agentica, Anthropic). Numbers pulled from full texts are marked as such; secondary-source numbers are flagged **UNVERIFIED**. Where sources disagree I report both.

Conventions: "Verified" = SWE-bench Verified (500 tasks). "Lite" = 300 tasks. "pass@1" = single attempt resolve rate; "Best@K" = K samples + a selector (what you can actually ship); "pass@K" = oracle upper bound.

---

## A. Benchmarks and evaluation

### A.1 SWE-bench family

| Benchmark | Size / scope | Source | Notes |
|---|---|---|---|
| **SWE-bench** (Jimenez et al., ICLR 2024) | 2,294 issue–PR pairs, 12 Python repos | arXiv:2310.06770 (v1 Oct 2023, v3 Nov 2024) https://arxiv.org/abs/2310.06770 | Claude 2 resolved 1.96% at launch (retrieval, no agent). |
| **SWE-bench Lite** | 300-task subset | swebench.com | Self-contained, mostly single-file fixes; Agentless authors found ~10% have insufficient info, 4.3% contain the exact gold patch in the issue, 9.7% give exact steps (arXiv:2407.01489 full text). |
| **SWE-bench Verified** | 500 tasks screened by professional annotators for well-specified issues + fair tests | OpenAI, Aug 2024 https://openai.com/index/introducing-swe-bench-verified/ ; HF `SWE-bench/SWE-bench_Verified` | Today's de-facto standard; near-saturated by frontier closed models (see A.4). |
| **SWE-bench Multimodal** | 510 test instances (plus a dev split; total ~617 UNVERIFIED), 12 JS/TS repos with visual assets | arXiv:2410.03859 | Tests generalization to front-end/visual domains. |
| **SWE-bench Multilingual** | 300 tasks, 9 languages, 42 repos (UNVERIFIED count) | https://www.swebench.com/multilingual.html (SWE-smith team) | Used as the standard "did Python-only training transfer?" probe (e.g., SWE-HERO, Open-SWE-Traces). |
| **SWE-bench-java** | ~91 Java instances (UNVERIFIED) | arXiv:2408.14354 | First non-Python port. |
| **Multi-SWE-bench** (ByteDance, NeurIPS 2025) | 1,632 verified instances across 7–8 languages (sources differ: 1,632 vs 2,132) | arXiv:2504.02605 | Python strongest, C/C++/Rust weakest. |
| **SWE-PolyBench** (Amazon) | Multi-language, Java hardest (66% mixed changes) | arXiv:2504.08703 | Also has a "Verified" subset used by Coherence-Collapse and AutoCompact papers. |
| **SWE-bench Live** | 1,319 tasks from 93 repos, issues created ≥2024, continuously updated | arXiv:2505.23419 | Contamination-resistant; Kimi-Dev uses it as OOD probe. |
| **SWE-rebench** (Nebius) | 21k+ interactive Python tasks (train); leaderboard = 860 curated tasks in monthly splits 2025-01…2026-03, July-2026 split moved to Harbor Hub | arXiv:2505.20411; HF `nebius/SWE-rebench-leaderboard`; V2 (language-agnostic, 32,079 samples, 20 languages) arXiv:2602.23866 | Monthly fresh splits let you compare pre- vs post-cutoff performance; authors state some models "perform better on SWE-bench Verified than their true capability warrants." |
| **SWE-bench Pro** (Scale AI) | 1,865 tasks (731 public / 858 held-out private / 276 commercial), 41 repos; copyleft + private startup code; multi-file, long-horizon | arXiv:2509.16941 (v2 Nov 2025) | v1: frontier <25% under SWE-agent scaffold; v2 unified scaffold: best models <45%. **SWE-Bench Pro Verified** (arXiv:2609.08149, Sep 2026) fixes reward hacking via gold-solution leakage + bad tasks. The *held-out private split* is the closest public analogue to our hidden test repos. |
| **Terminal-Bench 2.0** | ~89 hard CLI tasks (UNVERIFIED count); neutral "Terminus 2" scaffold = single headless terminal tool, bash only | arXiv:2601.11868 | GPT-5.2+Codex CLI 62.9%, Terminus-2+Opus 4.5 57.8% (secondary, UNVERIFIED). Gemma 4 31B scores 36.0 on "Terminal Bench Hard" per its tech report (arXiv:2607.02770, Table 5). |

### A.2 What Fail-to-Pass / Pass-to-Pass mean and how resolution rate is computed
Each instance ships with a repo snapshot at the base commit, the issue text, the hidden gold test patch and two test lists:
- **FAIL_TO_PASS (F2P):** tests that fail on the base commit and pass after the gold PR. They encode "the bug is fixed."
- **PASS_TO_PASS (P2P):** tests that already pass before and must still pass after. They encode "nothing regressed."

Evaluation applies the model's patch (model never sees the test patch), then applies the test patch, runs the named tests, and marks the instance **resolved** iff *every* F2P test passes **and** every P2P test passes. **Resolution rate = resolved / N** (N = 500 for Verified). A patch that errors on apply, breaks syntax, or produces an empty diff counts as unresolved. There is no partial credit. (OpenAI Verified post; SWE-bench harness docs.)

Practical implications for us: (i) a single regression in any P2P test is fatal, so over-broad edits are penalized more than conservative ones; (ii) the model's own reproduction script is *not* the grader — tests hidden in the gold test patch are; (iii) an empty patch is a guaranteed zero, which is why Devstral's "iterative protocol" re-runs instances that produced an empty patch (arXiv:2509.25193 full text: empty-patch rate 7.6% on attempt 1; 43.0% → 45.8% → 46.8% over 3 attempts).

### A.3 Contamination and test-weakness concerns
- **SWE-Bench+** (arXiv:2410.06992): across versions, 32.7–33.5% of SWE-agent+GPT-4's successful patches had the solution leaked in the issue/comments and 24.7–31.1% passed only because of weak tests; filtering dropped its resolve rate from 12.47% to ~4–4.6%. >94% of issues predate model cutoffs. Same problems exist in Lite and Verified.
- **SWE-ABS** (arXiv:2603.00520, Mar 2026): re-running bash-only agents under adversarially strengthened tests cut top scores (Opus 4.5 / Gemini 3 Pro ≈74%) by 15–18 points.
- **"Are solved issues really solved?"** (ICSE 2026, software-lab.org) and **Investigating Test Overfitting** (arXiv:2511.16858): passing F2P/P2P does not guarantee a correct patch.
- **SWE-rebench** (arXiv:2505.20411): monthly fresh splits show some models score higher on Verified than on fresh tasks of comparable difficulty.
- **Git-hacking:** several 2026 training papers (SWE-Lego arXiv:2601.01426; Open-SWE-Traces arXiv:2606.16038) explicitly sanitize git history and AST-audit trajectories because agents learn to `git log`/`git stash`-recover the gold fix from repository metadata. SWE-Lego reports its 32B at 52.6% hack-free vs 57.6% with git hacking allowed — a 5-point inflation. **Action for us:** make sure our local eval harness strips future commits/reflog and our agent is not trained on trajectories that read them.
- OpenAI reportedly stopped reporting Verified in 2025/26 and points to SWE-bench Pro (secondary sources: codesota, codeant — UNVERIFIED).

### A.4 Leaderboard state, mid-October 2026
swebench.com is a JS app that could not be scraped; what follows is from aggregators (llm-stats "last updated Oct 16 2026", steel.dev "Oct 11 2026"), **all self-reported, 0 independently verified** per llm-stats' own caveat.

Closed/frontier (Verified): Claude Opus 5 96–97% (Vals.ai bash-only mini-SWE-agent run 97.0 ±0.76), Claude Fable 5 95.0, Claude Mythos Preview 93.9, Opus 4.8 88.6, Opus 4.7 87.6, GPT-5.6 "Sol" 82.2, Gemini 3.1 Pro 80.6, GPT-5.2 80.0. DataCamp notes Vals archived the benchmark as saturated.

Open-weight (Verified, self-reported): DeepSeek-V4-Pro-Max 80.6 (one aggregator says 96.4 on "Vals final board" — treat as UNVERIFIED outlier), MiniMax M2.5 80.2 / M3 80.5, Kimi K2.6 80.2, GLM-5.2 80.0, Qwen3.6 Plus 78.8, Qwen3-Coder-Next (80B-A3B, arXiv:2603.00729) 70.6 SWE-agent / 71.1 mini-SWE-agent / 71.3 OpenHands and 44.3 on SWE-bench Pro; Qwen3-Coder-480B 69.6; Devstral Small 2 (24B dense) 68.0 (Mistral Dec 2025; one Ollama page says 65.8). SWE-rebench (fresh tasks): Gemma 4 31B 41.6% vs GLM-4.7 58.7% (BenchLM, UNVERIFIED).

Official swebench.com "Bash Only" view (every model in the same mini-SWE-agent env) existed since July 2025 (65% at launch; README now claims >74% with Gemini 3 Pro / Opus 4.5). Note the site warns 1.x (string-parsed actions) and 2.x (native tool calling) results are not comparable.

Small open models (≤32B) that matter for us — best pass@1 I could find per size, single-trajectory unless noted:
- 7B: SWE-smith 7B 15.2 (2k traj, arXiv:2504.21798); Lingma SWE-GPT-7B 18.2; R2E-Gym-7B 19.0; SWE-Dev-7B 23.4; SWE-AGILE 7B-class 24.05 (self-reported, UNVERIFIED); SWE-Protégé-7B 32.0 on held-out SWE-smith subset with no expert, 42.4 Verified *with* ~4 expert (Opus 4.1) calls (arXiv:2602.22124).
- 8B: Seed-Coder-8B 19.2 (Agentless); SWE-Lego-Qwen3-8B 42.2 pass@1 / 49.6 TTS@16 (hack-free; arXiv:2601.01426).
- 14B: SWE-Gym 16.4; R2E-Gym 26.8; SkyRL-Agent-14B-v0 21.6 (RL only).
- 24B: Devstral Small 46.8 (2025) → Devstral Small 2 68.0 (Dec 2025).
- 30B-A3B: Open-SWE-Traces 61.7; Scale-SWE 64 (arXiv:2602.09892); FLARE 53.0.
- 32B: SWE-Gym 20.6; R2E-Gym 34.4/51 hybrid; SWE-smith 40.2; Skywork-SWE 38.0/47.0; DeepSWE 42.2/59.0; SWE-Swiss 60.2; SWE-Master 61.4/70.8; SWE-HERO 62.2; Kimi-Dev-72B 60.4 (Agentless) / 48.6 (SWE-agent).

---

## B. Agent scaffolds and design lessons

### B.1 SWE-agent — the Agent-Computer Interface (Yang et al., NeurIPS 2024, arXiv:2405.15793)
**Key idea:** LMs need an interface designed for them, not for humans. Tools: `open/scroll/goto` file viewer with line numbers and a 100-line window; `search_dir/search_file/find_file` that return *summarized* results (and refuse to dump >50 hits); `edit start:end` that replaces a line range and runs a **flake8 lint gate** — if the edit introduces a syntax error it is reverted and the model sees the error plus before/after snippets; history management keeps only the **last 5 observations** in full and collapses older ones; a demonstration trajectory in context; `submit`.
**Numbers (Lite, GPT-4 Turbo, full text Table 2):** full ACI 18.0%; edit without lint 15.0 (−3.0); shell-only editing 10.3 (−7.7); search iterative-one-at-a-time 12.0 (−6.0); viewer 30 lines 14.3 (−3.7), 400 lines 17.0, full file 12.7 (−5.3); full history without collapsing 15.0 (−3.0); no demonstration 16.3 (−1.7). Resolved trajectories averaged 14.7 turns (median 12; 75% ≤18); successful runs median $1.21 / 12 steps vs unsuccessful mean $2.52 / 21 steps. 93% of resolved instances submitted before the budget.
**Design guidelines stated by authors:** simple actions with few options; consolidate common operations; informative but concise feedback; guardrails (syntax checks) that catch errors before they propagate.
**Failure modes documented:** repeatedly re-editing the same snippet after a syntax error (fixed by lint gate); exhausting budget by paging through every search hit; "agents rarely recognize dead ends or reset their approach."
**Transfers to a small model:** everything. The ACI ablations were done with a *weak-for-today* model (GPT-4 Turbo at 18%), which is roughly where a 4B–12B Gemma will sit, so these effect sizes (3–8 points each) are the most relevant harness numbers in the literature for us. Note the later `str_replace_editor` tool (view/create/str_replace/insert/undo_edit) replaced line-range `edit` in SWE-agent 1.x and is what SWE-smith, R2E-Gym, DeepSWE, SWE-Lego all train on.

### B.2 mini-SWE-agent (SWE-agent team, July 2025)
**Key idea:** ~100 lines of Python; **bash is the only tool**, no native tool-calling (actions parsed from a code block), **completely linear history** (every step appended, no summarization), each action run via `subprocess.run` (no persistent shell state), submit by echoing a sentinel. Scores 65% at launch, >74% with Gemini 3 Pro / Opus 4.5; it powers the official "Bash Only" leaderboard. Harness survey (arXiv:2606.20683) lists Sonnet 4 at 64.9 and Opus 4.x at 76.8 under mini vs higher under SWE-agent+tools and OpenHands for the same models.
**Transfer:** The *harness design study* (arXiv:2609.20804, full text) is the key caveat — bash-only helped a 550B model (+3.6 Verified, −53% cost) but **predefined tools helped the 30B model by +15.0 points** on Verified and +10.1 on Terminal-Bench, and hurt Mistral-Medium by −23.2 on Verified. Bash-only is a frontier-model luxury; small models want structured view/edit tools. mini's linear-history and stateless-subprocess choices are nonetheless good for us (simple to train on, no hidden state to drift).

### B.3 Agentless (Xia et al., 2024; arXiv:2407.01489, ACM TOSEM version)
**Key idea:** no agent loop. Three fixed phases: **localize** (repo skeleton tree → LLM picks top-3 suspicious files, combined with embedding retrieval; then classes/functions; then 4 sampled sets of edit locations), **repair** (±10-line context windows, 10 patches per location set = 40 search/replace-format patches at T=0.8), **validate/select** (filter syntax errors → run existing regression tests selected by LLM → run 40 self-generated reproduction tests → majority vote over normalized patches).
**Numbers (full text):** Lite 32.0% (96/300) at $0.70 and 78k tokens avg; Verified 38.8% (GPT-4o). Localization: file-level recall prompting 78.7, embedding 70.3, combined 81.7; skeleton format beats full files (58.3 vs 53.7) and is cheaper. Selection ablation: majority vote only 25.7%; + regression tests 27.0%; + reproduction tests 32.0%; oracle over all 40 candidates 42.0%. Reproduction tests were fragile: 213/300 reproduced the bug but only 94 also passed with the gold patch. Repair sampling: 4 location sets × 10 patches (32.0) > 1 greedy set × 40 (29.3).
**Transfer:** Agentless is the strongest template for a **budget-fixed** system because every LLM call count is known in advance. Its skeleton-first localization and search/replace edit format are directly reusable. Kimi-Dev shows Agentless-style training is also a good *skill prior* (B.9/C). Downsides for us: 40 samples is far beyond our budget; Agentless only beat agents when agents were weak and has since been overtaken by agentic systems at every model size.

### B.4 AutoCodeRover (Zhang et al., ISSTA 2024, arXiv:2404.05427)
Program-structure-aware search APIs (`search_class`, `search_method_in_file`, …) instead of raw grep, plus optional spectrum-based fault localization from tests. Lite 19% @1 (vs SWE-agent 18%), 26% @3; later README 30.67%; 46.2% Verified claimed by the commercial version at <$0.7/task (GitHub README, UNVERIFIED). **Transfer:** AST-aware search tools shrink the localization token budget — the single biggest cost center for small models.

### B.5 OpenHands / CodeAct (Wang et al., arXiv:2407.16741; CodeAct arXiv:2402.01030)
Actions are executable Python/bash (CodeAct), with a sandbox runtime, `execute_bash`, `str_replace_editor`, `think`, `finish`, optional browsing. It is the scaffold behind SWE-Gym, OpenHands-LM-32B (37.2% Verified, March 2025), Devstral (46.8 → 68.0), Skywork-SWE, SWE-Dev, SWE-Lego, Nebius trajectories, SWE-ZERO/HERO. SWE-Lego explicitly reduces OpenHands to four tools (`execute_bash`, `str_replace_editor`, `think`, `finish`) and 100 turns. Devstral found 50 turns sufficient (36.8% at 30 → 46.8% at 50 = 100 turns).

### B.6 Moatless Tools / SWE-Search (Antoniades et al., ICLR 2025, arXiv:2410.20285)
Moatless = semantic code search + structured find/edit tools, low-cost. SWE-Search adds MCTS over agent states with a value agent and a discriminator "debate" for final choice: +23% relative across five models (GPT-4o 31% Lite; 35.4 Verified with DeepSeek-V3-0324 in SWE-Debate's comparison). **DARS** (arXiv:2503.14269, ACL 2025) branches at key decision points on execution feedback: Lite 47% pass@1 / 55% pass@k with Sonnet 3.5. **SWE-Debate** (arXiv:2507.23348): 41.4% Verified with DeepSeek-V3. **Transfer:** tree search multiplies cost 5–10×; not viable under our budget except as *offline* data generation (branching to collect more successful training trajectories — see SWE-Replay in D).

### B.7 Trae Agent (ByteDance, arXiv:2507.23370) and Nemotron-CORTEXA (NVIDIA, Apr 2025)
Both are "ensemble" scaffolds: generate many candidates with strong models, then prune/dedupe → regression tests → reproduction tests → majority vote → LLM-judge tiebreak. Trae: 75.2% Verified (376/500) with Claude 4, +10.2 points average over four ensemble baselines. CORTEXA: fine-tuned code-embedding file retrieval (NV-EmbedCode-v1 recall 71.95 vs BM25 40.67 vs GPT-4o/Agentless 65.55), AST code-graph entity localization agent, 7 diverse patches from o3, selection as above; 68.2% Verified at $3.28/task; candidates contained a correct patch for ~75% of tasks, so **selection, not generation, was the bottleneck**. Training data: SWE-bench train split + CoIR. **Transfer:** the pipeline shape (small-N candidates → cheap filters → tests → vote) is reusable at N=2–4; the *embedding retriever* idea is reusable offline (a tiny embedding model is cheap at inference).

### B.8 CodeStory/Aide, Refact.ai, Claude Code / Codex-style scaffolds
- CodeStory Aide topped Verified at 62.2% in Dec 2024 using heavy test-time search (~$20/task per NVIDIA's comparison) — UNVERIFIED beyond that footnote.
- Refact.ai: I could not retrieve a primary source (UNVERIFIED).
- **Anthropic's Oct 2024 scaffold** (anthropic.com/engineering/swe-bench-sonnet; details via secondary write-up): a prompt + **two tools (bash, edit)**, *no* imposed workflow; prompt *suggests* explore → write a reproduction script → edit → re-run → consider edge cases; loop until the model says done or 200k context. 49% Verified with Sonnet 3.5 (new). This is the lineage of Claude Code.
- **OpenAI GPT-5 system card** (arXiv:2601.03267): internal scaffold = bash + `apply_patch`. Earlier o1 was evaluated with Agentless because it lacked tool use.
- **Confucius Code Agent** (Meta, arXiv:2512.10398): hierarchical working memory + threshold-triggered structured summary (goals, decisions, TODOs, error traces) that replaces old messages while recent turns stay raw; +6.6 Resolve@1; 54.3% SWE-bench Pro.
**Transfer:** the "reproduce first" instruction is prompt-level and free; the minimal two-tool design with a *suggested* workflow is exactly what the strongest labs converged on.

### B.9 Cross-cutting lessons extracted from scaffolds

**Tool design.** Consensus set across every trained open model since 2025: `bash`, `str_replace_editor` (view with line numbers + windowed ranges, create, exact-string replace, insert, undo), optional `search`, `submit/finish`. Lint-on-edit: −3.0 points without it (SWE-agent). Windowed views (100 lines) beat full files by 5.3 points. Summarized search beats iterative by 6 points. Predefined tools beat bash-only by +15 for a 30B model (arXiv:2609.20804).

**Context management.** Three families: (a) SWE-agent's "last-5 observations, older collapsed" (+3.0); (b) staged elision + LLM summary (Confucius; harness study T4 — cheapest tier with equal accuracy, and *making elided content recoverable gave no gain*: the model rarely called recall); (c) learned compaction (AutoCompact arXiv:2610.02163 +9.2 Verified; CliffCompaction arXiv:2609.26779 preserves full-context success at 16–32k windows; CompactionRL arXiv:2607.05378: summary *quality* alone moved 49.0→55.5). The harness study also shows the benefit of management is mostly about **preventing overflow failures** (78.7% → 8.7% of runs) and shrinks from 35.7 to 2.7 points as the window grows 32k→128k. For a 4B–31B Gemma with, say, a 32k practical window, context management is worth tens of points, mainly by not dying.

**Reproduce-first.** Appears as a *prompt suggestion* in Anthropic's scaffold, SWE-agent's demo, Devstral, and as a *hard phase* in Agentless (reproduction tests: 27.0 → 32.0, +5). SWE-smith: issue text quality drives whether the model reproduces at all (379 reproduction attempts with LM-written issues vs 127 with F2P-test-derived text, −66%). SWE-Tester (arXiv:2601.13713) trains open models to write reproduction tests (41k instances; +10 pts success on SWT-Bench Verified) but does not report end-to-end resolve gains. TestPrune (arXiv:2510.18270): reusing *existing regression tests* for reproduction + validation gives +9.4–12.9% relative resolve rate inside Agentless at <$0.05/issue, "by capturing fixes agents produced but did not submit."

**Test-driven loops.** Regression tests at selection time: +1.3 (Agentless), +4.7 Best@K (R2E-Gym: regression-only 47.4 vs no-verifier 34.4). The P2P rule makes "run the nearest existing test file after editing" one of the highest-value cheap actions.

**Patch selection.** Majority vote over normalized diffs (free), then regression tests, then reproduction tests, then learned verifier/LLM judge. Hybrid execution-based + execution-free verifiers are consistently best (R2E-Gym 51.0 vs 43.7/42.8; DeepSWE 59 vs ~57; Kimi-Dev 3 patches × 3 tests already beat 40-patch majority vote).

**Typical trajectory length.** SWE-agent GPT-4: median 12 turns resolved. SWE-Gym successful: ~19 turns, 18.6k tokens. SWE-smith expert (Claude 3.7): avg 29.1 steps; student 24.9; demos ~29 actions. R2E-Gym caps at 40 steps / 32k tokens / 10 min. Devstral saturates at 50 turns. SWE-Lego: 100 turns, sequential gains saturate 100–140. DeepSWE eval: 100 steps, 64k context. SWE-Protégé: mean steps fell 60 → 20 after RL; 10.8% of solves need ≥40 steps. **Rule of thumb:** ~80–90% of what a model will ever solve, it solves inside 30–40 tool calls; the tail past that is mostly loops.

**Failure modes (with numbers).**
- *Loops:* SWE-smith: >25% of SWE-agent-LM-32B trajectories contain a repeated action sequence of length ≥10 (vs <4% for Claude 3.7); a length-10 repetition implies 89% failure; 53% of its failures hit cost/step/runtime limits. SWE-Protégé: 31% of post-SFT trajectories loop >10 steps; RL with a loop penalty cut that to 0.8%.
- *Overflow:* unmanaged 32k context → 78.7% of runs die of overflow (arXiv:2609.20804).
- *Editing the right code wrongly ("coherence collapse"):* 60–69% of failures on SWE-agent/OpenHands reach and edit the correct functions but still fail; the dominant pattern is reaching correct code then overwriting/thrashing it; an edit-commit checkpoint recovered all 5 cases where the gold patch had existed mid-trajectory (arXiv:2603.24631, 16,758 trajectories).
- *Wrong localization / partial edits / giving up:* SWE-smith taxonomy: stuck-at-localization, stuck-at-reproduction, incorrect-localization-or-edit, malformed LM output, env error.
- *Empty patches:* 7.6% on first attempt for Devstral-Small.
- *Not submitting a fix that worked:* TestPrune and Coherence Collapse both find correct patches that were later destroyed or never submitted → **checkpoint the diff whenever a self-written test flips to pass**.
- *Malformed edits:* the reason str_replace (exact-match old string) displaced line-number edits; SWE-agent's lint gate; harness study notes small models benefit from planning primarily because it "keeps runs alive long enough to attempt an edit" (+11.6 Verified for Nemotron-3 30B).

---

## C. Training small open models to be SWE agents

### C.1 Summary table

| System (date) | Data source | Teacher / generation | Filter | Method | Size → Verified | Data scale |
|---|---|---|---|---|---|---|
| **SWE-Gym** (Pan et al., Dec 2024, ICML 2025; arXiv:2412.21139) | 2,438 real issue–PR tasks, 11 repos (+66.9k raw unvalidated / 358 repos) | GPT-4o + Claude 3.5 Sonnet in OpenHands & Moatless; 491 successes | success-only; per-instance cap | full SFT (lr 1e-4, ≤5 ep, 32k ctx); verifier via LoRA | 7B 1.8→10.6; 14B 4.0→16.4; 32B 7.0→20.6; 32B Best@16 32.0 | 491 traj; still improving at max |
| **SWE-smith** (Yang et al., Apr 2025, NeurIPS 2025; arXiv:2504.21798) | 50k synthetic bugs in 128 repos (LM-modify, LM-rewrite, procedural AST mutation, PR-mirror, combine) | Claude 3.7 Sonnet in SWE-agent (bash + str_replace_editor + submit), 75 steps; 36% resolve rate → 6,457 traj | success-only, ≤3/instance → 5,016 | full SFT (lr 5e-5, ≤3 ep, 32k) | 7B 15.2 (2k traj); 32B 40.2; 32B@500 traj 28.2 | log-linear in traj count (Fig 1) |
| **SWE-RL** (Wei et al., Meta, Feb 2025, NeurIPS 2025; arXiv:2502.18449) | 273k real PR seeds (issue + changed-file context + oracle patch) | none (RL from scratch on Llama-3.3-70B-Instruct) | n/a | GRPO; reward = difflib SequenceMatcher ratio vs oracle patch (−1 if malformed) | 70B 41.0 (Agentless Mini); repair-only w/ oracle loc 34.8 | 512 H100 × 32 h (secondary) |
| **R2E-Gym** (Jain et al., Apr 2025, COLM 2025; arXiv:2504.07164) | 8,135 executable tasks via SWE-Gen (back-translate issues from commits, 2.5× yield), subset 4,578 / 10 repos disjoint from SWE-bench | Sonnet-3.5-v2 ReAct (editor, search, bash, submit), 40 steps/32k/10 min; 3,321 successes | success-only | full SFT | 7B 19.0; 14B 26.8; 32B 34.4; hybrid Best@26 51.0 | 100→3,200 traj; 14B saturates ~800, 32B still rising |
| **SWE-Fixer** (InternLM, Jan 2025; arXiv:2501.05040) | 110k real issue–PR pairs (UNVERIFIED count) | pipeline (retriever + editor), no agent | — | SFT of 7B retriever + 72B editor | 30.2 Verified (2 LLM calls/instance) | — |
| **Lingma SWE-GPT** (Alibaba, Nov 2024; arXiv:2411.00622) | development-process-centric synthetic traces | Qwen2.5 teachers | — | SFT | 7B 18.2; 72B 30.2 | — |
| **SWE-Dev** (THUDM, Jun 2025, ACL Findings; arXiv:2506.07636) | 38k instances / 4,413 PyPI repos; LLM-synthesized F2P tests | DeepSeek-V3 in OpenHands, 30 iters; ~17k traj, 2.3k correct | LLM-judge patch similarity kept 65%; filtered ≈ unfiltered | SFT (lr 1e-5, 4–8 ep); RFT > OREO/KTO | 7B 23.4; 32B 34.0 @30 rounds → 36.6 @75 | 7B: 13.0 @574 → 22.8 @16.6k traj |
| **Skywork-SWE** (Jun 2025; arXiv:2506.19290) | 10,169 real tasks / 2,531 repos, each with Docker image | OpenHands, >8k runtime-validated traj | success-only | SFT on Qwen2.5-Coder-32B | 38.0 pass@1; 47.0 Best@8 | "no saturation" claimed |
| **DeepSWE** (Agentica/Together, Jul 2025) | 4.5k R2E-Gym tasks (sympy etc. removed) | none — pure RL from Qwen3-32B | compact filtering of truncated rollouts | GRPO++ (clip-high, no KL, no std-norm, length-norm, RLOO baseline, no entropy); sparse 0/1 reward on F2P+P2P within 5 min | 23 → 42.2 pass@1 in 200 steps; 71.0 pass@16; 59.0 hybrid Best@16 | 64 H100 × 6 days |
| **Nebius long-context RL** (Golubev et al., Aug 2025; arXiv:2508.03501) | 7,249 SWE-rebench tasks | none; RFT warm-up then RL | dynamic sample filtering; length penalty | modified DAPO, no teacher | Qwen2.5-72B 11 → 20 (RFT) → 39.0 | — |
| **Kimi-Dev** (Moonshot, Sep 2025, ICLR 2026; arXiv:2509.23045) | ~150B-token mid-training (50B Agentless-format diffs, 20B PR commit packs, synthetic loc/agentic traces); cold-start from DeepSeek-R1 traces on SWE-Gym + SWE-bench-extra | self | — | mid-train → SFT → RL (outcome 0/1 on code-edit stage, 1,024 problems × 10 rollouts, 64k ctx) → test-time self-play (40 patches × 40 tests) | 72B 60.4 Agentless (48.0 at 1×1); **48.6 as SWE-agent after SFT on 5,016 SWE-smith traj** | RL prior needs ~2^23 SFT tokens to match what Base needs ~1.5×2^28 for |
| **SWE-Swiss** (PKU/ByteDance/HKU, ACL Findings 2026) | curated loc / repair / unit-test datasets | — | — | multi-task SFT → two-stage RL on repair | 32B 60.2 | — |
| **Devstral Small** (Mistral, 2025; arXiv:2509.25193) → **Small 2** (Dec 2025) | SWE-Gym environments, OpenHands rollouts; later "pseudo-scaffolds" with XML + native tool formats | own agent | two-stage filter (heuristic → strict) | SFT stage 1 → SFT stage 2 → rollouts + policy optimization | 24B 46.8 (50 turns) → 68.0 | — |
| **OpenHands LM 32B** (Mar 2025) | SWE-Gym method | OpenHands self-generated | — | SFT | 37.2 | — |
| **Seed-Coder-8B** (ByteDance, Jun 2025; arXiv:2506.03524) | code pretraining with model-curated data | — | — | pretrain + instruct | 19.2 Agentless | — |
| **CWM** (Meta, Oct 2025; arXiv:2510.02387) | Python execution traces + agentic container trajectories in mid-training | — | — | mid-train → SFT → RL, 131k ctx | 32B 53.9 → 65.8 w/ TTS | — |
| **Qwen3-Coder** (2025) / **Qwen3-Coder-Next** (Mar 2026; arXiv:2603.00729) | large-scale synthesized verifiable tasks with executable envs | — | — | mid-training + env-feedback RL | 480B 69.6; 80B-A3B 70.6–71.3 | — |
| **SWE-Lego** (Jan 2026; arXiv:2601.01426) | 32.1k tasks (18.4k real + 13.7k synthetic), 3,251 repos | Qwen3-Coder-480B in OpenHands v0.53, 100 turns; 14.1k resolved + 4k semi-resolved | remove test-modifying & git-hacking traj | full SFT 4 ep, 128k ctx, **error masking**, turn-count curriculum | **Qwen3-8B 42.2 / TTS@16 49.6**; 32B 52.6 / 58.8 | all-resolved 40.4 → −low-quality 41.0 → +semi-resolved 42.2 |
| **Scale-SWE** (Feb 2026; arXiv:2602.09892) | 100k verified tasks from 6M PRs / 5,200 repos (3-agent pipeline) | 71,498 distilled traj | — | SFT on Qwen3-30B-A3B | 64 (≈3× base) | — |
| **SWE-Master** (Feb 2026; arXiv:2602.03411) | teacher synthesis | — | — | long-horizon SFT → RL with execution feedback | Qwen2.5-Coder-32B 61.4; TTS@8 70.8 | log gains, peak ~48k instances (secondary) |
| **SWE-ZERO → SWE-HERO** (NVIDIA, Apr 2026; arXiv:2604.01496) | 300k execution-free + 13k execution-based traj distilled from Qwen3-Coder-480B | — | — | two-stage SFT on Qwen2.5-Coder 7B/14B/32B | 32B 57.7 (exec-free) → 62.2; 44.1 Multilingual despite Python-only | HF `nvidia/SWE-Zero-*`, `SWE-Hero-openhands-trajectories` (CC-BY-4.0) |
| **Open-SWE-Traces** (NVIDIA, Jun 2026; arXiv:2606.16038) | 207,489 traj, 9 languages, 20k real PRs, permissive-license repos only | MiniMax-M2.5 (thinking) + Qwen3.5-122B (non-thinking) | AST audit removes git-hacking | SFT, dual-mode /think toggle | Qwen3-Coder-30B-A3B 61.7 Verified, 57.1 Multilingual, 36.8 Pro | HF `nvidia/Open-SWE-Traces` |
| **SWE-Protégé** (Meta/UMich/Stanford, Feb 2026, NeurIPS 2026; arXiv:2602.22124) | SWE-smith tasks; expert-augmented traj (Sonnet 3.7 guidance, expert sees gold patch but may not reveal it → +38% usable traj) | ~4.8k resolved | success-only | **full SFT (LoRA and QLoRA underperformed)** → GRPO with loop penalty + follow-through + gated correctness | 7B 32.0 no-expert (held-out) / 42.4 with ~4 expert calls | 19.0 @1.3k → 33.4 @4.8k traj |
| **SWE-Prime** (Aug 2026; arXiv:2608.27449) | 32,161 resolved traj pool | — | two-stage: representative trajectory subset → segment-level loss masking by contribution/learnability/risk | SFT | 10% curated subset beats all-resolved by up to +24.2% rel. Verified, +12.2% Pro | — |
| **STITCH** (Huawei CodeArts, Apr 2026; arXiv:2604.00824) | <1k traj | — | coarse-to-fine token filtering | SFT | up to +63% rel. over base (30B–355B) | — |
| **FLARE** (Sep 2026; arXiv:2609.23808) | — | — | process-aware selection of 3k traj | SFT Qwen3-30B-A3B | 53.0 vs 45.0 random | — |
| **TQS** (Oct 2026; arXiv:2610.13152) | 155,144 successful traj | — | linear-time structural trajectory score (info focus, intent–action alignment, policy dynamics) | SFT | top-ranked subsets consistently beat random/bottom | — |

Other 2026 entries seen but not read in depth: SWE-Playground / "Training Versatile Coding Agents in Synthetic Environments" (arXiv:2512.12216; 7B 17.0 with 3–5× fewer trajectories, better OOD), daVinci-Env (arXiv:2603.13023), SWE-World (Docker-free envs, arXiv:2602.03419), SWE-Mirror (arXiv:2509.08724), SWE-Fuse (arXiv:2603.07927), SWE-TRACE (arXiv:2604.14820; 60k short-path SFT corpus + rubric PRM used to prune actions at rollout), SWE-Shepherd PRM (arXiv:2604.10493), SkyRL-Agent (arXiv:2511.16108; SA-SWE-32B 24.4 → 39.4 with RL), LEGO-RL (arXiv:2608.17393), Agent Lightning (Microsoft, arXiv:2508.03680; v1.0 ≈3,500 LOC, trains any harness via LightningRL credit assignment), ProRL Agent (arXiv:2603.18815), SWE-AGILE (arXiv:2604.11716; compression-aware RLVR, 24.05% at 7B-class, UNVERIFIED), OctoThinker (arXiv:2506.20512; mid-training determines RL-ability — Llama needed 200B+20B stable-then-decay tokens to match Qwen; long-CoT in mid-training destabilizes RL).

### C.2 Key ablations and scaling evidence, by theme

**(a) How many trajectories give how much.**
- SWE-Gym: 491 trajectories → +8.8 (7B), +12.4 (14B), +13.6 (32B) absolute on Verified; still rising at 100% of data.
- SWE-smith (32B): 500 traj → 28.2; 5,016 → 40.2. Approximately log-linear. SWE-smith 7B with 2k traj → 15.2.
- R2E-Gym: 100 → 3,200 traj with diminishing returns; **14B saturates around 800 trajectories**, 32B still improving.
- SWE-Dev 7B: 574 traj → 13.0; 16,639 → 22.8 (≈+10 for 29× data). 32B scales more steeply.
- SWE-Protégé 7B: 1.3k → 19.0; 4.8k → 33.4 (with expert at inference).
- Kimi-Dev: with a good prior, ~2^23 (~8M) SFT tokens (~400–500 trajectories at ~18k tokens) suffice to reach what the raw base needs ~400M tokens for.
- SWE-Master (secondary): log gains peaking ~48k instances.
- LoRA-specific (arXiv:2607.17205, 7B, SWE-rebench 67k traj, held-out CE loss as proxy because 7B resolve rates were ~0): 500 → 1,000 traj cut loss 12.7%; quality-vs-random gap <1% at 1k but 3.6% at 2k; **error-retry rate** was the most predictive single quality feature.
**Reading:** for a ≤12B model, the first ~500–1,000 good trajectories buy most of the gain; 2k–5k is the knee; beyond that you need either a bigger model or RL.

**(b) Diversity of repositories vs same-repo specialization (critical for our hidden-repo test).**
- SWE-smith: training on 4 → 25 → 50 → 100 repos (700 traj, procedural bugs) improves Verified roughly logarithmically in repo count. **Repository specialization works when you know the target**: 7B fine-tuned only on 700 SymPy trajectories scored 21.2 on SymPy Verified tasks vs 13.6 for the 128-repo generalist; 32B specialist stage +700 SymPy traj: 42.4 vs 33.3, with minimal loss elsewhere.
- SWE-Bench++ (arXiv:2512.17419): on Qwen2.5-Coder, **repository variety gives a robust, statistically significant gain; solution density per repo does not.**
- SWE-ZERO/HERO: Python-only training → 44.1 on Multilingual; Open-SWE-Traces 57.1 Multilingual; i.e., the *skills* transfer across languages, let alone repos.
- SWE-Playground: fewer, more diverse synthetic environments → better OOD at equal Verified.
**Reading:** our 4 training repos are a *liability* if we only train on them. Use them for environment realism, but pull trajectory diversity from SWE-smith/SWE-rebench/Open-SWE-Traces style pools (dozens–hundreds of repos). Expect specialization gains only where test repos overlap training repos — which, for hidden private repos, they won't.

**(c) What to filter and what to keep.**
- Success-only rejection sampling is universal; per-instance caps (2–3) help (SWE-Gym: cap 2 → 9.7 with 62 traj vs 9.3 with 172 uncapped).
- SWE-smith: difficulty of training tasks did **not** correlate with downstream gains (12.4/10.8/13.6/12.2 across difficulty bands); issue text *style* matters (LM-written issues produce 31% more unique actions than templated ones).
- SWE-Dev: LLM-judge similarity filtering (keeps 65%) made no difference.
- SWE-Lego: dropping low-quality resolved traj +0.6; **adding "semi-resolved" (correct localization, wrong fix) +1.2**; **error masking** (mask loss on steps that produced tool errors, except reproduction/test failures) +2.0 (8B) / +2.2 (32B); turn-count curriculum +0.4/+0.8.
- SWE-Prime / FLARE / TQS / STITCH (2026): process-quality selection of 3–10% of trajectories beats training on everything (FLARE 53.0 vs 45.0 with 3k traj; SWE-Prime +24% rel.). Segment-level loss masking (train only on high-contribution steps while keeping full context) is the current frontier.
- Teacher choice: SWE-Gym's on-policy self-training *hurt* when mixed (15.3 → 8.7) — a weak student's own successes are noisier than a strong teacher's; SWE-Protégé's LoRA/QLoRA underperformed full SFT at 7B (one data point; the LoRA curation paper worked at 7B with LoRA rank unspecified).
- DeepSWE: SFT on Claude 3.7/4 trajectories *before* RL gave no RL gains after 100 iterations; SWE-smith/SWE-Gym tasks had high "solve-none" rates for RL; R2E-Gym's difficulty curriculum worked best.

**(d) SFT vs RL; reward design.**
- Pure RL from a strong base works at 32B+ (DeepSWE 23 → 42 in 200 steps; SkyRL 24.4 → 39.4; Nebius 72B 11 → 39) and at 14B modestly (SkyRL-Agent-14B 18.0 → 21.6). No pure-RL success story below 14B that I could find.
- Execution reward (F2P+P2P pass, 0/1, with timeouts counted 0) is standard. SWE-RL's rule-based diff-similarity reward works with no execution infra and generalized OOD (+ on 5 non-SWE tasks) while its SFT control degraded OOD — attractive for an offline/low-infra team, but it produced 41% only at 70B.
- Stability tricks that recur: DAPO clip-high, no KL, overlong/compact filtering of truncated rollouts, RLOO/leave-one-out baseline, length penalties (Nebius), dynamic sampling of tasks with non-zero variance, asymmetric clipping (SWE-Protégé ε_high 0.28 / ε_low 0.20).
- **Shaped behavioural rewards are cheap and large:** SWE-Protégé's loop penalty cut loops from 31% → 0.8% of trajectories and mean steps 60 → 20; SFT→RL added +1.2 to +6.2 points.
- Kimi-Dev: an Agentless-style (localize/repair/test-gen) training prior makes later *agent* SFT 30× more token-efficient; SFT-only priors overfit past ~200 trajectories; mid-training on diffs/PRs scales 50B → 150B tokens.
- Devstral: two-stage SFT (broad heuristic-filtered → strict-filtered) then rollouts + policy optimization; training in *multiple tool-call formats* (XML and native) improved cross-scaffold generalization.

**(e) Test-time scaling with trained verifiers (see D).**

### C.3 Openly released trajectory / task datasets (Hugging Face)

| Dataset | Content | Size | License / notes |
|---|---|---|---|
| `SWE-Gym/SWE-Gym`, `SWE-Gym-Lite`, `SWE-Gym-Raw`; trajectories `SWE-Gym/OpenHands-Sonnet-Trajectories` etc. | 2,438 real tasks (11 repos); 491 teacher traj | small | MIT code; traj license UNVERIFIED |
| `SWE-bench/SWE-smith` + `SWE-bench/SWE-smith-trajectories` (swesmith.com) | 50k synthetic tasks in 128 repos; 5k (now ~26k per GitHub) Claude-3.7 SWE-agent trajectories | 5k–26k | MIT (repo); check per-repo licenses |
| `R2E-Gym/R2E-Gym-Subset`, `R2E-Gym-Lite`, SWE-agent trajectories | 4,578 tasks / 8.1k full; 3.3k traj | 3.3k | repo MIT (UNVERIFIED for data) |
| `nebius/SWE-bench-extra` | 6,415 issue–PR pairs, 1,988 repos (precursor of SWE-rebench) | 6.4k | CC-BY-4.0 |
| `nebius/SWE-agent-trajectories` | ~80k SWE-agent traj (Qwen/Llama policies) | ~80k | CC-BY-4.0; Llama-3.1 license on Llama outputs |
| `nebius/SWE-rebench` (21k+ tasks), `nebius/SWE-rebench-openhands-trajectories` | **67,074 OpenHands traj from Qwen3-Coder-480B across 1,823 repos**; fine-tuned Qwen3-235B-A22B checkpoint released | 67k | CC-BY-4.0 (UNVERIFIED) |
| `nebius/SWE-rebench-V2` | 32,079 tasks, 20 languages | 32k | arXiv:2602.23866 |
| `Skywork/Skywork-SWE` collection | 10,169 tasks w/ Docker + >8k traj | 8k | — |
| THUDM/SWE-Dev (GitHub) | 38k tasks, ~17k traj | 17k | — |
| `SWE-Swiss/*` | SFT + RL datasets for loc/repair/test-gen | — | — |
| SWE-Lego | 32.1k tasks, ~18k traj (Qwen3-Coder-480B) | 18k | arXiv:2601.01426 |
| `AweAI-Team/Scale-SWE` | 100k tasks (20k initial release), 71.5k traj | 71k | — |
| `nvidia/SWE-Zero-openhands-trajectories` (~300k), `nvidia/SWE-Hero-openhands-trajectories` (~13k) | distilled from Qwen3-Coder-480B | 313k | CC-BY-4.0; permissive source repos only; "ready for commercial use" |
| `nvidia/Open-SWE-Traces` | 207,489 traj, 9 languages, thinking + non-thinking | 207k | permissive; commercial OK |
| `JetBrains-Research/SWE-TaskFlow-SWE-Bench-Pro-Trajectories`, `ernie-research/MEnvData-SWE-Trajectory`, `chunxiaox/nautilus-swe-trajectories` | smaller/specialised | — | check cards |

Caveat on licenses: dataset-level license covers only the generated text; source repositories keep their own licenses, and teacher-model ToS (e.g., Claude outputs) may restrict competitive training — relevant for Kaggle rules. The NVIDIA sets (permissive-only repos, open-weight teachers, CC-BY-4.0) and Nebius sets are the cleanest.

---

## D. Test-time compute

**Parallel sampling + selection.** Gains are large but logarithmic, and most of the gain is captured by K≈8:
- SWE-Gym 32B: 20.6 → 29.8 (Best@8) → 32.0 (Best@16); oracle pass@16 42.8. Verifier trained with LoRA (29.8) beat full FT (27.2); mixing off- and on-policy verifier data was essential.
- R2E-Gym 32B: 34.4 → 43.7 (execution-based, plateau) / 42.8 (execution-free, plateau) / 49.4 Best@16 / 51.0 Best@26 hybrid. Execution-free verifiers *rely on the agent's thoughts*: stripping the trajectory and judging the patch alone drops 42.8 → 37.6. Generated tests are weakly discriminative (<20% of tests separate good from bad patches) and up to 10% are "toxic."
- DeepSWE 32B: 42.2 → 57.9 Best@8 → 59.0 Best@16 hybrid; "most TTS gains arrive by K=8"; scaling output tokens 32k → 128k adds ≤2%.
- Skywork 32B: 38.0 → 47.0 Best@8 (execution-free).
- SWE-Lego 8B: 42.2 → 49.6 TTS@16; 32B 52.6 → 58.8. Sequential (longer single trajectory) saturates at 100–140 turns, after which parallel + verifier is better.
- Kimi-Dev: 1 patch × 1 test 48.0 → 3 × 3 already beats 40-patch majority vote → 40 × 40 = 60.4.
- Agentless (no learned verifier): majority 25.7 → +regression 27.0 → +reproduction tests 32.0 (upper bound 42.0).
- Frontier-model TTS: "Scaling Test-Time Compute for Agentic Coding" (CMU, arXiv:2604.16529) compresses each rollout into a structured summary and runs Recursive Tournament Voting / Parallel-Distill-Refine: Opus 4.5 70.9 → 77.6 Verified, 46.9 → 59.1 Terminal-Bench. Trae Agent +10.2 avg over ensemble baselines; CORTEXA 75% oracle vs 68.2 selected.

**Critics / PRMs.** SWE-RM (ICLR 2026) execution-free reward model; SWE-TRACE rubric PRM used both to train and to prune actions online (claims higher resolve at lower tokens — numbers not retrieved); SWE-Shepherd PRM; "When agents go astray" (arXiv:2509.02360) course-corrects with PRMs mid-trajectory. Routing-guided TTS (Risa, arXiv:2608.22191) ≈ text-consensus arbitration, +3.3 macro-avg (third-party reading).

**Budget-aware strategies for a fixed per-task clock (most relevant to us).**
1. **SWE-Replay** (arXiv:2601.22129, Jan 2026): instead of fresh rollouts, restart from a chosen *mid-point* of an archived trajectory; −17.4% cost on Verified at equal or +3.8 resolve; no LLM judge needed. Prefix reuse is a natural fit for a fixed budget.
2. **Fail-Fast, Restart-Smart** (arXiv:2608.03222, Aug 2026): a 0.6B monitor predicts failure from the observable prefix; on alarm, restart a fresh rollout with the partial diff offered as an optional overlay. Saves 14.6–20.4% tokens at 5% FPR; at 25% FPR raises Qwen3.6-27B from 66.6 → 71.8 (cold restart only 66.8). Monitor transfers across policies.
3. **Devstral iterative protocol:** re-run only instances that returned an empty patch (+3.8 over three attempts).
4. **Early-stop heuristics from SWE-smith/SWE-Protégé:** a repeated action pattern of length ≥10 ⇒ ~89% failure — abort and restart or submit the best checkpoint.
5. **Checkpoint-and-submit:** keep the diff at the moment a self-written repro test flips to pass (Coherence Collapse: recovered 100% of the "gold-then-destroyed" cases; TestPrune's resolve gains came from the same phenomenon).
6. **Cheap selectors first:** patch normalization + majority vote ($0), regression tests on touched files (+1–5), then repro tests, then any learned verifier. A verifier can be a *LoRA adapter on the same base* (SWE-Gym's verifier was LoRA-trained and beat full FT) — compatible with a LoRA-only rule if the adapter swap is allowed within the budget.
7. **Planning for small models:** +11.6 Verified for a 30B model mainly by surviving to an edit (arXiv:2609.20804); costs more tokens, so pair with staged elision.
8. **Sequential vs parallel cross-over:** sequential returns saturate ~50 turns (Devstral) to 100–140 (SWE-Lego). Under a wall-clock cap, 2 × 40-step attempts with a cheap selector usually dominates 1 × 100-step attempt for small models, which fall into loops past ~40 steps.

---

## E. Generalization: train-repo overfitting vs cross-repo transfer

Direct evidence:
- **Repo count is the lever** (SWE-smith log-law in #repos; SWE-Bench++ variety significant, density not). Specialization only helps on the specialized repo (SymPy +7.6 at 7B, +9.1 at 32B) — which for hidden private repos is unavailable.
- **SWE-bench Pro held-out split exists precisely because public-repo overfitting is real**; v1 showed frontier systems dropping from ~70% Verified to <25% Pro. Open-SWE-Traces 30B-A3B: 61.7 Verified vs 36.8 Pro; Qwen3-Coder-Next 71 vs 44.3. Expect a ~35–45% relative drop from Verified to unseen, longer-horizon repos.
- **Skills transfer better than repo knowledge:** Python-only SFT → 44–57% on Multilingual (SWE-HERO, Open-SWE-Traces); Kimi-Dev's Agentless prior transfers to SWE-bench Live and Multilingual; SWE-RL's RL generalized to five non-SWE tasks while SFT degraded them; the Fail-Fast monitor trained on one policy transfers to others.
- **Synthetic diversity helps OOD:** SWE-Playground reached better OOD (SWT-Bench, Commit-0) at slightly lower Verified with 3–5× fewer trajectories.
- **On-policy self-training on a narrow set hurt** (SWE-Gym 15.3 → 8.7 when adding 868 on-policy traj from 11 repos), a warning against bootstrapping only from fastapi/rich/requests/httpx.
- **Contamination inflates apparent in-distribution skill** (SWE-rebench fresh splits; SWE-Bench+; git-hacking +5 points in SWE-Lego). Any gain we measure on the four public training repos should be discounted; hold out at least one of them (or better, evaluate on SWE-rebench monthly splits / SWE-bench Live) as a proxy for private repos.

Reading for us: the four training repos are best used for (i) realistic executable environments and reward signal, (ii) repository-agnostic skill practice (reproduce, localize via grep/AST, minimal edit, run nearest tests, submit), and (iii) format-alignment of Gemma's tool calls. Diversity should come from external pools (Open-SWE-Traces, SWE-Hero, Nebius, SWE-smith), with licensing checked against the competition rules.

---

## F. Synthesis: ranked actionable findings for a small, LoRA-only, offline, tool-call-budgeted Gemma agent

Effect sizes are absolute SWE-bench-Verified points unless stated; they come from the cited setting and will shrink/grow with model size.

1. **Use a structured minimal tool set — `bash`, `str_replace_editor`-style view(with line numbers, windowed)/create/str_replace/insert, `submit` — not bash-only.** Predefined tools +15.0 for a 30B model vs bash-only (arXiv:2609.20804); windowed 100-line view +5.3 vs full file, summarized search +6.0, lint-gated edit +3.0 / +7.7 vs shell editing (SWE-agent, arXiv:2405.15793). Add a syntax check (py_compile/ruff) to every edit and bounce failures back with context. *Expected: +10–20 for a ≤12B model relative to raw bash.*

2. **Context management that prevents overflow, implemented as staged elision (keep last ~5 tool outputs verbatim, collapse older ones) with an occasional structured summary.** Unmanaged 32k windows die of overflow in 78.7% of runs; managed vs not = +35.7 at 32k, +2.7 at 128k (arXiv:2609.20804); SWE-agent last-5 rule +3.0; Confucius +6.6; AutoCompact +9.2 (arXiv:2610.02163). Don't bother with a "recall elided content" tool — models don't use it. *Expected: +5–30 depending on how small Gemma's usable window is.*

3. **SFT on 1k–5k teacher trajectories from *many* repos (not our four), filtered success-only with ≤3 per instance, is the highest-ROI training step.** SWE-Gym 491 traj → +8.8/+12.4/+13.6 (7B/14B/32B); SWE-smith 5k → 40.2 at 32B; SWE-Lego 8B reached 42.2 pass@1. Repo diversity scales log-linearly and is statistically the lever (SWE-smith; SWE-Bench++). Prefer openly licensed, open-teacher sets (Open-SWE-Traces 207k; SWE-Hero 13k; Nebius 67k) and sub-select for diversity. *Expected: +10–25 over base at 4B–31B.*

4. **Trajectory quality curation beats volume once you have ~2k: use error-masking, drop/mask looping and erroring steps, prefer short, high-retry-efficiency trajectories, include semi-resolved (right localization) trajectories.** Error masking +2.0–2.2 and semi-resolved +1.2 (SWE-Lego); 10% curated > 100% (SWE-Prime +24% rel.); process-aware 3k > random 3k by +8 (FLARE); error-retry rate was the top quality feature for LoRA on 7B (arXiv:2607.17205); SWE-smith: task difficulty does not matter, issue-text style does. *Expected: +2–8.*

5. **Match the training scaffold, tool schema and tool-call format exactly to inference, and train on both native tool-calling and text-parsed formats.** Devstral's refreshed data in XML + native formats improved cross-scaffold generalization; swebench.com warns 1.x vs 2.x formats are not comparable; SWE-Protégé notes LoRA/QLoRA underperformed full SFT at 7B — so spend LoRA capacity on format and procedure rather than knowledge (use higher rank on all linear layers). *Expected: avoids −5 to −20 from format mismatch (UNVERIFIED magnitude).*

6. **Prompt a "reproduce first" workflow and run the nearest existing tests after editing; checkpoint the diff when a repro test flips to pass and submit that if later steps break.** Reproduction tests at selection time +5 (Agentless); regression tests +1.3–4.7; TestPrune +9.4–12.9% relative by recovering fixes agents produced but didn't submit; Coherence Collapse: 60–69% of failures edit the right code then thrash it; checkpointing recovered 5/5 gold-then-destroyed cases. *Expected: +3–8.*

7. **Hard-stop loops: detect a repeated action pattern of length ≥5–10 and either restart or submit the best checkpoint.** Length-10 repetition ⇒ 89% failure; 25–31% of small-model trajectories loop (SWE-smith, SWE-Protégé); 53% of SWE-agent-LM-32B failures were budget exhaustion. If RL is feasible, a loop penalty cut loops to 0.8% and halved steps (SWE-Protégé). *Expected: +2–5 directly, more via budget saved for a second attempt.*

8. **Budget split: cap a single attempt at ~30–50 tool calls and reserve budget for a second attempt or for selection, rather than one long run.** Sequential gains saturate ~50 turns for a 24B model (Devstral 36.8@30 → 46.8@50 = @100) and ~100–140 for a 32B; most TTS gain arrives by K=8 and even K=2–3 with a cheap selector helps (Kimi-Dev 3×3 > 40-patch majority). Re-run empty-patch cases first (+3.8, Devstral). Use prefix replay (SWE-Replay −17% cost, +3.8) or a tiny failure monitor (Fail-Fast +5.2 at 25% FPR) if the budget allows. *Expected: +3–8 within a fixed clock.*

9. **Cheap patch selection ladder: normalize + majority vote → syntax check → run P2P-relevant existing tests → self-written repro test → (optional) LoRA verifier adapter.** Agentless ladder 25.7 → 27.0 → 32.0; hybrid exec + exec-free verifiers consistently best (R2E-Gym 51.0 vs 43.7/42.8; DeepSWE 59.0); SWE-Gym's LoRA verifier beat full FT. Execution-free verifiers need the *thoughts*, not just the patch (−5.2 without). *Expected: +5–10 at K=4–8; +2–4 at K=2.*

10. **Localization: skeleton-first, AST/grep-structured search, and (offline) a small embedding retriever if the budget allows.** Agentless file recall: prompting over repo skeleton 78.7, +embedding 81.7, skeleton cheaper than full files (58.3 vs 53.7 at 7× lower cost); CORTEXA fine-tuned embedder recall 72 vs BM25 41; AutoCodeRover's structural search APIs. For a small model, cutting localization tokens is also what frees budget for reproduce/test steps. *Expected: +3–6 and a large token saving.*

11. **If any RL is possible, do it after SFT with a strong prior and sparse execution reward plus shaped behavioural terms (loop penalty, length penalty), using DAPO-style tricks (clip-high, no KL, filter truncated rollouts, dynamic sampling).** DeepSWE 23 → 42 in 200 steps at 32B; SkyRL 14B 18 → 21.6; SWE-Protégé 7B SFT→RL +1.2 to +6.2 and steps 60 → 20; Nebius 72B 20 (RFT) → 39. Kimi-Dev shows a localize/repair/test-gen prior makes RL/SFT ~30× more token-efficient. Below 14B expect RL to buy behaviour (fewer loops, shorter runs) more than raw resolve rate. *Expected: +2–6 at 4–12B; +5–15 at 27–31B.* If no execution infra, SWE-RL's diff-similarity reward is a viable fallback (worked at 70B; UNVERIFIED at small scale).

12. **Plan for a large Verified → hidden-repo drop and evaluate accordingly.** Frontier systems lose 35–45% relative from Verified to SWE-bench Pro; the four public training repos are contaminated for any modern base; git-hacking alone inflates by ~5 (SWE-Lego). Evaluate on SWE-rebench monthly splits / SWE-bench Live / a held-out training repo with git history stripped; strip future commits and reflog in training envs. *Expected: prevents selecting a configuration that only "works" in-distribution.*

13. **Do not self-train narrowly on our own repos.** SWE-Gym's on-policy additions from 11 repos dropped Lite 15.3 → 8.7; specialization gains exist only on the specialized repo (SWE-smith SymPy +7.6/+9.1). Use our repos for environments and reward, external pools for diversity. *Expected: avoids −3 to −7 and generalization collapse.*

14. **Give the model a short planning/thinking step before acting (Gemma 4 thinking mode) but cap it; it mainly keeps small models alive to the edit.** Planning +11.6 for Nemotron-3 30B on Verified (cost up), −2.0 for 550B (cost −30%); DeepSWE learned ~2k thinking tokens for localization vs 100–200 for simple steps; RL in non-thinking mode gave limited gains. *Expected: +3–10 for ≤31B, with token cost to manage.*

15. **Issue-text and demonstration conditioning:** include one compact in-context demonstration trajectory (SWE-agent −1.7 without) and, when generating synthetic training tasks, write LM-style natural issue texts rather than templated ones (31% more action diversity, 3× more reproduction attempts, SWE-smith). *Expected: +1–3.*

### Baseline expectations for Gemma 4 (to calibrate goals)
Gemma 4 tech report (arXiv:2607.02770, Table 5, thinking mode): 31B LiveCodeBench v6 80.0, Terminal-Bench-Hard 36.0, τ²-retail 86.4; 26B-A4B 77.1 / 14.0 / 85.5; 12B 72.0 / 18.0 / 77.6; E4B (4.5B effective) 52.0 / 8.0 / 67.1; E2B 44.0 / 3.0 / 34.6. No SWE-bench Verified figure is published; third parties list ~54–63% for 31B under full scaffolds (UNVERIFIED) and 41.6% on fresh SWE-rebench tasks (UNVERIFIED). Terminal-Bench-Hard (3–36) is the most honest proxy for untuned agentic ability: it says E2B/E4B are near zero as agents out of the box, 12B/26B-A4B weak, 31B moderate. With the literature's small-model curves (SWE-Gym/R2E-Gym 7B 2 → 19, 14B 4 → 27; SWE-Lego 8B 42 with 18k traj and 128k context), a realistic post-training target under tight budgets is roughly +10–20 absolute over the untuned base per size, most of it from items 1–4 and 6–8.

---

## Source index (primary)
- SWE-bench: arXiv:2310.06770 · Verified: openai.com/index/introducing-swe-bench-verified · swebench.com (Verified/Bash-only pages) · SWE-Bench+: arXiv:2410.06992 · SWE-ABS: arXiv:2603.00520 · SWE-bench Live: arXiv:2505.23419 · SWE-rebench: arXiv:2505.20411, HF nebius/SWE-rebench-leaderboard · SWE-rebench V2: arXiv:2602.23866 · SWE-bench Pro: arXiv:2509.16941 · Pro Verified: arXiv:2609.08149 · Multi-SWE-bench: arXiv:2504.02605 · SWE-PolyBench: arXiv:2504.08703 · Multimodal: arXiv:2410.03859 · SWE-bench-java: arXiv:2408.14354 · Terminal-Bench: arXiv:2601.11868 · Leaderboard aggregators: llm-stats.com/benchmarks/swe-bench-verified, leaderboard.steel.dev/leaderboards/swe-bench-verified · Dissecting leaderboards: arXiv:2506.17208.
- Scaffolds: SWE-agent arXiv:2405.15793 · mini-SWE-agent github.com/SWE-agent/mini-swe-agent · Agentless arXiv:2407.01489 · AutoCodeRover arXiv:2404.05427 · OpenHands arXiv:2407.16741 · SWE-Search arXiv:2410.20285 · DARS arXiv:2503.14269 · SWE-Debate arXiv:2507.23348 · Trae Agent arXiv:2507.23370 · Nemotron-CORTEXA research.nvidia.com/labs/adlr/cortexa · Anthropic anthropic.com/engineering/swe-bench-sonnet · GPT-5 system card arXiv:2601.03267 · Confucius Code Agent arXiv:2512.10398 · Harness design study arXiv:2609.20804 · Harness survey arXiv:2606.20683 · Coherence Collapse arXiv:2603.24631 · Beyond Resolution Rates arXiv:2604.02547 · AutoCompact arXiv:2610.02163 · CliffCompaction arXiv:2609.26779 · CompactionRL arXiv:2607.05378 · Slipstream arXiv:2605.08580.
- Training: SWE-Gym arXiv:2412.21139 · SWE-smith arXiv:2504.21798 · SWE-RL arXiv:2502.18449 · R2E-Gym arXiv:2504.07164 · SWE-Fixer arXiv:2501.05040 · Lingma SWE-GPT arXiv:2411.00622 · SWE-Dev arXiv:2506.07636 · Skywork-SWE arXiv:2506.19290 · DeepSWE together.ai/blog/deepswe · Nebius RL arXiv:2508.03501 · Kimi-Dev arXiv:2509.23045 · SWE-Swiss aclanthology.org/2026.findings-acl.790 · Devstral arXiv:2509.25193, mistral.ai/news/devstral-2-vibe-cli · OpenHands LM openhands.dev blog · Seed-Coder arXiv:2506.03524 · CWM arXiv:2510.02387 · Qwen3-Coder-Next arXiv:2603.00729 · SWE-Lego arXiv:2601.01426 · Scale-SWE arXiv:2602.09892 · SWE-Master arXiv:2602.03411 · SWE-ZERO/HERO arXiv:2604.01496 · Open-SWE-Traces arXiv:2606.16038 · SWE-Protégé arXiv:2602.22124 · SWE-Prime arXiv:2608.27449 · STITCH arXiv:2604.00824 · FLARE arXiv:2609.23808 · TQS arXiv:2610.13152 · LoRA curation arXiv:2607.17205 · SWE-Playground arXiv:2512.12216 · SWE-Bench++ arXiv:2512.17419 · SkyRL-Agent arXiv:2511.16108 · Agent Lightning arXiv:2508.03680 · OctoThinker arXiv:2506.20512 · SWE-Tester arXiv:2601.13713 · TestPrune arXiv:2510.18270 · Thinking Longer Not Larger arXiv:2503.23803.
- Test-time: SWE-Replay arXiv:2601.22129 · Fail-Fast Restart-Smart arXiv:2608.03222 · Scaling TTC for Agentic Coding arXiv:2604.16529 · Risa arXiv:2608.22191 · SWE-TRACE arXiv:2604.14820 · SWE-Shepherd arXiv:2604.10493 · PRM course-correction arXiv:2509.02360.
- Gemma 4 technical report: arXiv:2607.02770.
