# Research sprint ledger (Workstream 1, started 2026-10-25)

Progress log of the research sprint session. One line per source read or skipped, one block per deliverable.
Repos were cloned read-only into the session scratchpad (never into the project); nothing from them was executed.

## Deliverables
| File | Status | Notes |
|---|---|---|
| research/raw/09a_bucket_ceilings.md | written 10-25 | 6 runs joined; E4B/v5 kernel outputs downloaded to VM /tmp and copied locally |
| research/raw/09_swe_prompt_corpus.md | pending | |
| research/raw/10_kits_and_loops.md | pending | |
| research/raw/11_ttc_and_data_recipes.md | pending | |
| research/FT_DATA_SPEC.md | pending | |
| research/INSTRUCTION_DESIGN.md | pending | |
| vm/prompts/e2_demo.md, e1_solver.md, e1_verifier.md, e4b_short.md | pending | drafts only; no bundle built |

## Day 0 (own traces)
- READ: VM `scratch/kev_{pub022,v3t2k,v4single,v4phased}_out/eval/{results.csv,trace_analysis.csv,agent_run/traces}` (copied).
- READ: Kaggle kernel logs + outputs `gemma4-kaggle-eval-v5single`, `gemma4-kaggle-eval-e4b-v3t2k` via `kev_status.py` (downloaded to VM `/tmp/rs_v5`, `/tmp/rs_e4b`; no project dir touched).
- RE-ANALYSED all six with `vm/analyze_traces.py` @ 7ce7a2d (another session's new columns) in a local Python 3.12 (uv), outputs in the scratchpad.
- SKIPPED: `scratch/kev_controls_out` (gold/empty controls; not agent runs).

## Day 1 (SWE prompt corpus) — clones at these commits
- mini-swe-agent 04d809ce (config/benchmarks/swebench.yaml, config/default.yaml, config/mini.yaml; `config/extra/` no longer exists)
- SWE-agent 3ea751c0 (config/default.yaml = anthropic_filemap, config/sweagent_0_7/07.yaml, tools/edit_anthropic/config.yaml, tools/windowed_edit_linting, trajectories/demonstrations/function_calling_simple.traj; the marshmallow demo referenced by 07.yaml is not in the shallow clone)
- OpenHands: current main b185939d is the app monorepo (no agent prompts); prompts taken from OpenHands 0.30.1 (0e67deee) `openhands/agenthub/codeact_agent/prompts/system_prompt.j2` + `evaluation/benchmarks/swe_bench/run_infer.py`, and OpenHands/software-agent-sdk d2ee0cde `openhands-sdk/openhands/sdk/context/prompts/sections/static.py`
- Aider 5dc9490b (aider/coders/editblock_prompts.py)
- Anthropic engineering post "Raising the bar on SWE-bench Verified with Claude 3.5 Sonnet" (WebFetch, prompt text partly quoted by the page)

## Day 2 (kits and loops)
- Agentless 5ce5888b (agentless/fl/FL.py, agentless/repair/repair.py)
- auto-code-rover 585d3e63 (app/agents/agent_search.py, agent_write_patch.py)
- moatless-tools 011ead57 (moatless/actions/string_replace.py)
- trae-agent e839e559 (trae_agent/prompt/agent_prompt.py)
- refact 27f86def (refact-agent/engine/crates/refact-yaml-configs/src/defaults/modes/{agent,oss_weak_agent,debug}.yaml)
- on disk: third_party/superpowers @ bb92a777 (systematic-debugging, verification-before-completion, test-driven-development), .claude/skills (ECC @ 90606c83)
- Ralph loop, long-running-agent harness post, claude-flow, Agent SDK examples: delegated to a read-only subagent (report in scratchpad reports/day2_loops.md)

## Day 3 (papers) — delegated extraction (scratchpad reports/day3_papers.md), verified against raw/03 and raw/05 summaries
