# 06 — Facts verified against the REAL HARNESS_README.md and swegemma 0.2.11 source (2026-10-17)

Sources: `data/HARNESS_README.md` (692 lines, downloaded from the competition with the aagneye account) and the installed wheel
`swegemma-0.2.11` (`harness/agent_runner.py`, `tools/base.py`, `tools/workspace.py`) on the VM. These supersede the community
reconstructions in 01_competition_harness.md where they differ.

## Answers to the open questions from LITERATURE_REVIEW.md III.4

1. **Adapters** (README 3.4): PEFT dirs under `adapters/<name>/`, names `[A-Za-z0-9][A-Za-z0-9._-]*`; `adapter: <name>` on any LlmAgent; scorer sets
   `enable_lora = bool(adapters)`, `max_loras = len(adapters)`, `max_lora_rank = max(detected ranks)` (default 128), registered via `--lora-modules`;
   `resolve_swegemma_adapter` routes each agent to `openai/<adapter_name>`. Rank <= 128; total unpacked submission < 3 GiB.
2. **`search_similar_code`** (README 6.3): offline, no neural query encoder. The query is resolved against node keys/suffixes in the graph and the
   `.npz`; "pass a dotted symbol path or short symbol name"; a lexical token-overlap fallback exists for multi-word keyword strings. Cosine is computed
   against the node's own stored embedding. So it is a "more like this" tool seeded by a symbol, not free-text semantic search.
3. **Compaction** (README 7.2): ADK `EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5)` is set on the App for
   scoring, plus `ContextCacheConfig(min_tokens=2048, ttl=1800, cache_intervals=10)`. Intent is explicitly "to prevent long debugging trajectories from overflowing 32,768".
4. **Nudges** (README 5.3): `max_nudges = 3`; counter resets after any turn with a valid tool call; three exact messages (unclosed `<|tool_call>`, MAX_TOKENS/LENGTH, normal stop).
   After `submit_patch()` the loop exits as soon as the turn ends (final text response) -> `submit_patch` must be the last tool action; no post-submit work.
5. **Skill tools / budget**: only 9 registry tools are `@budget_gated`; `submit_patch` and `get_status` are free; skill tool accounting is not documented in the README.
6. **Container setup is excluded from the agent time budget** (README 7.1 TIP); `agent_start_time` starts after container creation + wheel install + snapshot extraction.
7. **Errors**: `ToolErrorPlugin` returns undeclared-tool and runtime exceptions to the model as `{"status":"error","error_type","error"}` instead of aborting (the old "undeclared tool ends the task" bug is fixed in this wheel).

## Exact initial user prompt (swegemma `build_agent_prompt`)
Sections, in order: `You are evaluating a software engineering task for repository {repo}.\n\nProblem Statement:\n{problem}\n`; optional `## Hints:`;
`## Task Budget (Session terminates when any budget is exhausted)` (time minutes, tool calls, max loop iterations); `## Execution Environment Rules` (command timeout,
output limit 5000, file view limit 150 lines, file char limit 10000, offline/no pip); `## Instructions:` items 0-5 (all source under /workspace; analyse; inspect conventions;
verify with targeted tests; call submit_patch only when complete; final action must be a text-only reply); optional `## Code Intelligence Tools` (only if graph+embedding files >100 B
exist and the tools are declared); `## Workspace Layout` (<=200 entries of `find . -maxdepth 3`, pruning docs/docs_src/tests/test_data/examples/benchmarks/assets/imgs/questions/site/g3doc/google3).
The exact text is reproduced in `vm/prepare_data.py` (INSTRUCTIONS, GRAPH_BLOCK, build_user_prompt) so training data matches inference.

## Exact tool result shapes
- run_command ok `{"status":"ok","stdout","stderr","exit_code":0}`; non-zero `{"status":"error","error_type":"CommandError","error_message","details":{stdout,stderr,exit_code}}`; timeout `TimeoutExceeded` (session continues).
- read_file `{"status":"ok","filepath","content"(RAW lines, no line numbers),"start_line","end_line","total_lines","is_truncated"}`; caps 150 lines / 10,000 chars.
- edit_file `{"status":"ok","filepath","occurrences","strategy":"exact|flexible|regex","diff","is_truncated"}`; errors `FileEditError` (multiple matches without allow_multiple, missing/empty file, empty old_string).
- write_file `{"status":"ok","filepath","size"}`; submit_patch `{"status":"ok","patch_size","files_changed"}`; get_status has tool_calls_used/remaining, time_seconds_remaining, agent_elapsed_seconds, max_turns, command_timeout_seconds.
- `budget_warning` field added to every tool result when `max_tool_calls >= 20` and `remaining <= 10`: "Only X tool call(s) remaining (Y/Z used). Finalize your edits and call submit_patch soon."
- graph tools: `get_code_neighbors` `{"status":"ok","node","neighbors":[...],"count","is_truncated"}` (4-tier name resolution: exact, suffix, case-insensitive, substring); `get_code_subgraph` `{"status","nodes","edges":[{"from","to","type"}],"node_count","edge_count","is_truncated"}`.

## Verification (Container B)
Protected files stripped from the agent patch before the test patch is applied: `test_*.py`, `*_test.py`, any `.py` under tests/test/testing, conftest.py, pytest.ini, pyproject.toml, tox.ini, setup.cfg, .pytest.ini, sitecustomize/usercustomize, `_swegemma_stubs.py`, `*.pth`.
Four-pass patch apply; resolved iff pytest exit 0 and JUnit shows every required node passed (no skips). Verification timeout fixed at 300 s on the scorer.
Gotchas confirmed by the README: scratch files created under /workspace appear in the patch (use /tmp or delete); do not touch pytest.ini/conftest.py; keep edits small to avoid `<|tool_call>` truncation (README suggests thinking_budget 4096 with max_output_tokens 16384).

## Still unverified
Skill-script budget accounting; `references/` vs `resources/` naming; sub-agent `skills:`; whether the scorer's thinking default is on when `thinking_config` is omitted (README suggests `thinking_budget` 4096).
