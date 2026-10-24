# Kaggle discussion threads — captured 2026-10-16 (verbatim-faithful notes)

## 742807 "Clarification on distillation from external LLMs" (47 votes)
- Kaggle staff (Ashley Oldacre): distillation from external LLMs is ALLOWED "as long as you are using those models in accordance with their model license terms, and the output ... doesn't conflict with the license requirement of the rules". => check teacher ToS; open-weight teachers (DeepSeek V4, Qwen3.6, GLM 5.3, Kimi) are safest for the Apache-2.0 winner release.
- Community: Justin Scott's "Ghostwriter" KD tool for Gemma 4 exists.

## 746250 Ayush Thakur "Gemma 4 agent experiments: sampling, thinking, time limits, tool ablations" (29 votes) — gemma-4-31b-it-qat-w4a16-ct, 129 local tasks, single runs
Sampling/thinking (60 min cap, 50 tool calls, 80 turns):
| run | change | resolved/129 |
| E9 | T=0.2, top-p .95, thinking 4096, summaries on | 48 (37.2%) |
| E10 | T=0.0 | 47 |
| E11 | T=0.4 | 51 (39.5%) |
| E12 | T=1.0 | 51 (39.5%) |
| E13/E14 | top-p .8 / 1.0 | 48 / 48 |
| E15 | thinking 2048 | 50 |
| E16 | thinking 6144 | 48 |
| **E17** | **thinking disabled** | **23 (17.8%)** |
| E18 | thought summaries disabled (thinking 4096) | 35 (27.1%) |
| E19 | summaries off, thinking 2048 | 34 |
=> Thinking ON + thought summaries ON is worth ~+20 points. Temperature 0.4–1.0 fine. Retained: T=1.0, top-p 0.95, thinking budget 4096.
Active time cap (E12 config): 6 min -> 37 (28.7%, 61 timeouts); 10 min -> 46 (35.7%); 15 min -> 54 (41.9%); 20 min -> 49; 60 min -> 51. Tasks that fail at short caps mostly fail at long caps too.
Graph tools (E32 vs E30 control): 50 vs 55 resolved; tools used on 21/129 tasks; **all 21 search_similar_code calls returned EMPTY results**; 7/10 neighbor calls non-empty; subgraph never used; no graph call returned a gold file path before the first edit. => the model doesn't know how to use the graph tools zero-shot (and/or the search tool was mis-queried / broken in that harness build). This is an OPPORTUNITY, not a verdict.
Analyzer subagent: 50 -> 51 (noise). Tool budget 50 -> 25 calls: 50 -> 36 resolved (-14), median runtime -29%.
Run-to-run noise: same config E30 55 vs repeat E34 48 (±7 tasks on 129!).
Kaggle 4xL4 calibration (TP=4, sequential agent, thinking on): 900.8 s per 1M tokens, 1,110 tok/s, 8.68 s per model call. Full 120-task projection 11.03 h. **Operational rule: 5.5 min/task on Kaggle (120 x 5.5 = 11 h + ~1 h setup).** Successful trajectories ≈ 40–50 LLM+tool calls, 300–350k tokens (input+thinking+output).
Follow-up thread 747857: system prompt vs none; command timeouts no impact.
Comment (Hitarth Jain): lexical localization study over 129 tasks — first identifier-grep hit correct 30%; grep+BM25 fusion top-5 61%, top-10 74%; **35/128 issues contain NO code identifier at all** (just "Fixes #NNNN"-style merged-PR titles + link). Notebook: kaggle.com/code/hitarthjain0/gemma-4-agent-can-grep-find-the-bug
Comment (Oleksii Zhukov): on 4xL4 with thinking OFF ≈ 3.8 s/model call; a 4.5-min cap took ~10 h for a scored run (≈0.5 min/task setup+verification overhead on top of the cap). Exceeding 12 h errors the WHOLE submission.
Author's conclusion: "The gains will come from post training. Data curation and fine tuning should be center of research."

## 747168 Ruijie Zhu "Stronger models barely beat Gemma 4 31B in this harness" (19 votes)
- Same YAML (sample prompt, get_code_subgraph removed), swegemma 0.2.7 (2026-09-30 build), events compaction on, **32k context**, 25 min / 50 tool calls, 124/129 tasks made locally scorable (gold passes, empty fails; 5 unfixable).
| model | resolved | median min/task |
| Gemma 4 31B pass 1 | 54/124 (43.5%) | 5.2 |
| Gemma 4 31B pass 2 | 53/123 | 5.2 |
| DeepSeek V4 Pro | 58/124 | 3.5 |
| Qwen3.6-27B | 59/123 | 3.9 |
- 19/123 tasks (15%) flipped between Gemma's two identical passes. Of 60 tasks Gemma failed twice, teachers solve only 10; 48 solved by nobody. Union of all 4 runs: 73/123 (59%).
- Interpretation: ceiling is the harness (32k ctx + compaction, call budget, sparse issue text), not model strength; teachers are faster (3.5–3.9 vs 5.2 min). Speed matters given 5.5 min/task.
- Gotchas: run_command is synchronous and blocks the event loop (run one task per process). **vLLM gemma4 tool-call parser mangles edit_file calls whose old_string contains triple-quote docstrings** (keys like <|"|>,filepath) -> ADK rejects "mandatory input parameters are not present" -> model retries identical call up to 27x; rejected calls don't count toward cap but burn time.
- Comment (Ayush): GPT-4.1/GPT-5 teachers also landed in the same ballpark.

## 747857 Ayush Thakur follow-up: Kaggle runtime calibration, command timeouts, empty-prompt ablation
- Calibration: Kaggle 4xL4 sequential (vLLM 0.19.1, TP=4, 32K ctx) = 900.8 s/M tokens; sequential B40 = 718 s/M => Kaggle is 1.25x slower per token than one B40. Operating pair: 4.5 min local (B40) ≈ 5.5 min Kaggle. 5.5-min scored Kaggle submission completed.
- Full 129 at local caps: 7 min -> 43 (33%); 4.5 min -> 47 (36%); 4 min -> 43. Paired 4.5 vs 4: McNemar p=0.58 (noise). Temp 1.0 sampling noise ≈ ±5–8 tasks per run.
- Local serving: max_num_seqs=128, max_num_batched_tokens=4096.
- Command timeout (per-command) 100/150/250/300 s: only 0.06–0.47% of commands time out; no detectable effect.
- Empty system prompt vs their "finalize.md" prompt: empty uses 15–18% fewer tokens, calls submit_patch more often (70 vs 55 tasks), but 8–11 "test-patch conflicts" vs 2–4. Their prompt includes a "patch hygiene" finalizer that removes test-file changes and validates the workspace patch before submission. => Agents must NOT leave edits to test files that conflict with the hidden test_patch (conflict = automatic fail). Patch hygiene step is worth ~2–8 tasks.
- Median per successful task: ~32 tool calls / 34 LLM calls with prompt; 26/27 without.

## 748051 "Top of the leaderboard is dominated by those who trained LoRA's" (10 votes)
- OP (Sahil Das, 396th): harness engineering plateaus at ~0.17–0.19; same package resubmitted scored 0.17/0.15/0.13/0.15 (LB noise ±0.04).
- htn (12th on LB): "I think none of the top submissions have managed to get any improvements through finetuning :)" => at 2026-10-14 the top is still prompt/harness + luck. Byron Galbraith: public LB distribution is explainable as two binomials around low means, i.e. pure noise; "no one has cracked anything yet".
- Ayush: "this competition is about post training and not harness engineering".
- Kaggle free tier: ~15 h/week of L4x4 (2x quota burn) — insufficient for training; external GPUs are a real edge.

## 744319 "How well do your CV and LB correlate?" (11 votes)
- ISAKA: CV 0.18/0.19/0.23/0.24 -> LB 0.05/0.06/0.12/0.10. 508shuto (38 rich tasks, official verifier): CV 0.21/0.24/0.32/0.29 -> LB 0.10/0.08/0.03/0.05 (anti-correlated!). daoviet: CV 0.2 -> LB <0.12.
- => **Public-repo CV is a poor proxy for the private-repo LB.** Causes (hypotheses): (1) private repos are unfamiliar to the model (no pretraining memorization of fastapi/rich/requests/httpx fixes); (2) private repos may have heavier setup/test infrastructure; (3) 58-task LB -> ±0.06 binomial noise; (4) harness/runtime failures on Kaggle (timeouts, 12 h overrun) that don't appear locally. Strategy implication: optimise for *generalisation and robustness* (clean, deterministic, time-bounded behaviour; no reliance on repo-specific knowledge) and build a held-out CV on *other* repos (e.g. SWE-bench Verified/ SWE-rebench / SWE-smith repos not in the 4) run through the same harness.

## 743140 "What results did you get with representative submissions?"
- Official sample_submission as-is: FAILED for one user (unhandled error) — suspected adapter path (adapter: name -> LiteLLM id openai/<adapter> served by vLLM --lora-modules on scoring side); another user got 0.01. Public notebooks: nursrijan starter kit -> LB 0.05; romanrozen "EDA, Baseline" -> 0.12 (forks got 0.08; scoring time 14.5 h on 4xL4 !); twangygarlic "super basic" -> 0.08.
- swegemma internals: swegemma/models/registry.py resolve_swegemma_adapter / _make_adapter_model rewrites model to openai/<adapter-name>; discover_adapters(); all 9 tools register unconditionally. Pinned: google-adk 1.36.1, adk-submission 0.2.11/0.2.12, swegemma 0.2.7.

## 743506 "Public leaderboard has exactly 58 tasks" — proven from score lattice (scores are floor(100k/58)/100). One task = 0.0172. 0.24 = 14/58; 0.22 = 13/58; 0.20 = 12/58.

## 745998 HOST (Elan Markowitz) "Note on Code Graphs for Async Functions"
- async def functions are MISSING from the code graphs (affects public fastapi/httpx tasks). **None of the private-repo test tasks touch async def functions; async is ≤1.8% of functions in private repos.** => private repos are mostly synchronous Python; graphs there are complete. Also tells us private repos are not web frameworks like fastapi/httpx.

## 748287 HOST (Ryan Holbrook) "New Gemma 4 Models Available: 12B, E4B, E2B" (2026-10-11)
- All four variants scored under identical conditions (same 4xL4, same 12 h, same eval_config). Adapters for small variants: train against the unquantized "Gemma 4" page checkpoints (host answer), i.e. the bf16 -it models; scorer applies adapters on the QAT w4a16 model.
- Host suggestions for small models: more test-time compute, ParallelAgent for concurrent LLM calls (tool calls still sequential), more/larger specialist adapters.
- **ADK 1.36.1 bug: ParallelAgent with tool-using sub-agents is broken** (adk-python issue 7324; fixed in v2 but scorer stays on 1.36). Workaround: keep parallel sub-agents tool-free. Host: "too risky to migrate to ADK v2".
- 12B serving: needs --hf-overrides '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}' (12B config is Gemma4UnifiedForConditionalGeneration / gemma4_unified); plus wheelhouse fix for vision_embedder.* tensors (fixed in latest wheelhouse, v30+). Scorer already patched.
- **Throughput on 4xL4 TP=4 (single sequence): 12B ≈ 67 tok/s vs 31B ≈ 35 tok/s.** Scorer vLLM: 0.19.1, TP=4, bf16 activations, max_model_len 32768, tool_call_parser & reasoning_parser = gemma4. Wheelhouse versions drift: swegemma 0.2.7 -> 0.2.11, adk-submission 0.2.11 -> 0.2.13.
- Even a tool-free repo-search subagent took ~90 s for 3k tokens on 31B => every extra LLM call is expensive.

## 747248 "fastapi tasks can't pass even with the gold patch" (Nur) + HOST reply
- Public harness (swegemma 0.2.7/0.2.11; python:3.13-slim; wheels deduped to highest py3.13 version and unpacked into site-packages once for all tasks; no per-task resolution): typing_inspection wheel missing -> pydantic import fails -> 61/67 fastapi tasks unsolvable locally even with gold. Also bundled release wheels of fastapi/requests/httpx/rich shadow /workspace on sys.path (src-layout requests, httpx) -> gold patch has no effect for some, and 3 requests tasks pass with an EMPTY patch; rich_3468 passes empty regardless.
- Gold-patch pass rate in public harness: fastapi 1/67, rich 39/48, requests 3/13, httpx 0/1 => **43/129 (33%)**. One user's local re-score of own patches at 12% matched their LB.
- **HOST (Ryan Holbrook): "None of the repos in the training tasks are present in the test set... every task in the test set is solvable and validates at 100% with a gold patch."** Host is fixing the training tasks.
- Community fix: notebook "119 of 129 sound: the Gemma 4 grader rebuilt" by busyaprime (kaggle.com/code/busyaprime/119-of-129-sound-the-gemma-4-grader-rebuilt). Other missing test deps: inline-snapshot, dirty-equals, pytest-httpbin. Thread 744370 (Oleksii Zhukov) also covers this.
- => Local CV must (a) use a repaired grader, (b) drop the empty-patch-passing tasks, (c) report per-repo; the 4 public repos are a *biased* dev set (fastapi dominates 67/129 but private repos are different).

## 742882 local harness
- Packages come from Kaggle dataset "Gemma 4 Developer Agent Wheelhouse" (Ryan Holbrook). Official notebook: https://www.kaggle.com/code/ryanholbrook/getting-started-gemma-4-developer-agent (defines scorer's VllmServer config). Docker unavailable in Kaggle notebooks -> --sandbox subprocess there.
