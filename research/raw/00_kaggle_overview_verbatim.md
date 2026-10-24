# Kaggle Overview page (captured verbatim via browser, 2026-10-16)
Source: https://www.kaggle.com/competitions/gemma-4-developer-agent/overview

## Key numbers
- Start: Sept 23, 2026. Paper deadline: Nov 12, 2026. Entry/merger deadline: Nov 25, 2026. Final submission: Dec 2, 2026 (11:59 PM UTC).
- Prizes: main $65k (37k/18k/10k); paper track $35k.
- Participation at capture: 11,119 entrants, 3,245 participants, 2,942 teams, 15,075 submissions.
- Authors (citation): Elan Markowitz, Bryan Perozzi, Benedek Rozemberczki, Glenn Cameron, Hadi Hemmati, Yuchen Li, Michael Galkin, Majid Farhadi, Ryan Holbrook, Ashley Oldacre. (Perozzi/Galkin/Rozemberczki = Google graph-ML group -> code graphs are the organizers' research interest; paper track emphasises graphs.)

## Evaluation
- submission.zip with agent.yaml at root; configs/sampling.yaml (!include), prompts/*.md, sub_agents/*.yaml, adapters/<name>/{adapter_config.json, adapter_model.safetensors}, skills/<name>/{SKILL.md, scripts/, resources/}.
- Google ADK Agent Config spec with restrictions; compiled into ADK agents.
- PASS/FAIL per issue like SWE-bench; score = % of patched repos passing validation tests.
- **12 hours total to submit patches for ALL tasks, inclusive of sandbox setup, excluding validation.** Optional per-task time limits in eval_config.yaml.

## Model rules
- ONLY these variants: gemma-4-31b-it-qat-w4a16-ct, gemma-4-12b-it-qat-w4a16-ct, gemma-4-e4b-it-qat-w4a16-ct, gemma-4-e2b-it-qat-w4a16-ct. (26B-A4B MoE NOT allowed. All are QAT int4-weight / 16-bit-activation checkpoints, "-ct" suffix.)
- Every agent/subagent must use the same base model. Different LoRA adapters per agent allowed (PEFT format, safetensors). adapter: <name> on any LlmAgent.

## Tool/prompt/skill rules
- !include relative paths; no path traversal; only harness tools or custom subagents via agent_tool.
- Skills: dir with SKILL.md (YAML frontmatter name:). run_skill_script runs in the persistent Docker container, shares FS with run_command, debits central budget. load_skill_resource reads resource files.

## Predefined tools
- run_command(command) -> /bin/bash -c in /workspace
- submit_patch() -> git add -N . ; git diff HEAD
- get_status() -> live budget consumption + patch status
- read_file(filepath, start_line=None, end_line=None) 1-indexed inclusive
- edit_file(filepath, old_string, new_string, allow_multiple=False) existing non-empty file
- write_file(filepath, content) mkdir -p
- get_code_neighbors(node, edge_type=None, max_neighbors=50) incoming+outgoing neighbors
- search_similar_code(query, k=10) cosine over precomputed embeddings
- get_code_subgraph(nodes: list[str]) induced subgraph

## Accelerators
- Kaggle L4x4 machines (96 GB total GPU memory) for this competition; 2x quota rate; internet disabled; restricted to notebooks attached to this competition. Scoring presumably on same L4x4.

## Paper track topics
- PEFT/RL for SWE agents; code-graph generation/parsing/embedding; new tasks/benchmarks on code structure/graphs; LLM reasoning over large graphs. Using the released graph+embedding dataset "highly encouraged".

# Rules page (captured 2026-10-16) — key points
Source: https://www.kaggle.com/competitions/gemma-4-developer-agent/rules
- Team size max 5. Mergers allowed until merger deadline, subject to submission-count cap.
- **1 submission per day.** Up to **2 final submissions** for judging. (=> local eval is everything; the leaderboard is a slow, noisy signal.)
- Winner license: Open Source Apache 2.0 for submission + source code (training + inference code + docs reproducible). Data: Apache 2.0, commercial use OK.
- External data & models allowed unless prohibited, under a "Reasonableness Standard" (publicly accessible, minimal cost; e.g. a small LLM subscription like Gemini Advanced is explicitly OK; a dataset license costing more than a prize is not). => frontier-model teacher trajectories (Gemini / Claude / GPT) are legal external tools; keep cost modest and document.
- No private code sharing outside team; public sharing must be on the Kaggle forum/notebooks (OSI license).
- Open-source code used must be OSI-approved with no commercial restriction.
- No hand-labeling of test data.
- Public LB = public test split; Private LB decides. Ties -> earlier submission wins.
- Hidden test: ~120 tasks from PRIVATE repos, evenly split public/private (~60/60) => each task ~1.67 points on each LB; high variance.

# Public leaderboard snapshot (2026-10-16, ~50% of test ≈ 60 tasks)
- #1-2: 0.24 (Yurnero, Yike Xu). #3-27: 0.22 (25 teams tied). #28-49: 0.20. 2,943 teams total.
- Interpretation: 0.22 ≈ 13/60 tasks and is almost certainly a shared public notebook/baseline; 0.24 = +1 task. Top is NOT yet differentiated. One task ≈ 0.0167. To win robustly on the private 60 we need a method whose true resolution rate is well above ~0.30, i.e. a step change (better localization + fine-tuned editing + verification), not prompt tweaks.

# Paper Track page (captured 2026-10-16)
Source: https://www.kaggle.com/competitions/gemma-4-developer-agent-paper/overview
- "Featured Hackathon". Start Sept 22, 2026; **final deadline Nov 12, 2026 23:59 UTC**. Participation at capture: 4,831 entrants, **241 participants, 234 teams, 245 submissions** (vs 3,245 participants / 15,075 submissions on the main track).
- Prizes $35k: Overall Best Paper $15k; Best New Resource (dataset/tool/software, e.g. a dataset built from the provided embeddings for evaluating or fine-tuning Gemma 4; a library that clusters code by behaviour; a dashboard to find structurally similar repos) $10k; Best New Application (new use-case of code graphs/embeddings, new eval datasets, applying graphs to other benchmarks) $10k. Three awards to the three highest-scoring submissions.
- Criteria (0–5 each, averaged): Novelty, Quality (generality beyond the competition), Relevance (impact on SWE + agentic learning), Verifiability, Clarity. Judge listed: Elan Markowitz (Google).
- Format: Kaggle Writeup ≤3,000 words (title/subtitle, abstract, intro, methods+experiments, related work) or arXiv-ready PDF via Public Project Link; optional public notebook. Unpublished, non-archival. Participation in main track not required.
- Topics: PEFT/RL for SWE agents; code-graph generation/parsing/embedding; tasks & benchmarks for code structure/graphs; LLM reasoning over large graphs.
