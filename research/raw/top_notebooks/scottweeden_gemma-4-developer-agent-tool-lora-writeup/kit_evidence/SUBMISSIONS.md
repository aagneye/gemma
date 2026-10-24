# Everything built for the Gemma 4 Developer Agent so far (as of 2026-10-22)

Team **Agent G** (scottweeden). Public leaderboard on 2026-10-21: 3,416 teams; top score 0.24, 0.22 reached by 34 teams, median 0.13.

## Leaderboard submissions

| Date | Bundle | Public score | Rank (21 Oct) |
|---|---|---|---|
| 2026-10-07 21:35 | MoE SWE agent: `SequentialAgent(verifier, moe_router + 6 expert AgentTools, swe_coder)`, compiled with adk-submission 0.2.12 / google-adk 1.36.1 | **0.05** | 3,046 / 3,416 |
| 2026-10-22 08:24 | A1 `a1_graph_decision` with `max_time_minutes: 6` (`bundles/a1_graph_decision_6min`) | no score: "Notebook Threw Exception" | — |

The 22 Oct run failed during a platform-wide incident: since about 04:00 UTC on 21 Oct many teams report "Notebook Threw Exception" on zips that are byte-identical to ones that scored days earlier (competition discussion 751339). The bundle passes the static checker and the official compiler path.

## Builds that were not submitted

| Date | Build | Status | Evidence |
|---|---|---|---|
| 2026-10-07 | 30 `evidently-*` notebooks: Evidently tracing of swe-agent runs, LLM input/output validation, polygraph graph-edge checks on fastapi/httpx/rich | Tooling and exploration | Notebooks (backed up, deleted from Kaggle 2026-10-21) |
| 2026-10-08 | `gemma4_lora_prophecy`: LoRA training governed by a TLA+ spec with a prophecy variable (Lamport and Merz, *Prophecy Made Simple*) | **Dry run only**, on a 2-layer stand-in model. Its `tool_acc = 1.0` is not a real result | `adapter_dryrun/metrics.json` |
| 2026-10-09/10 | `gemma4-lora-prophecy-wet-31b`: the same spec, QLoRA on the real 31B QAT checkpoint, SWE-smith trajectories, teacher-forced next-tool accuracy | Ran on 4x L4. The staged adapter was not kept | Kernel source only |
| 2026-10-10 | `prophecy-made-simple-gemmadev` (paper track) | Last run errored | Notebook (backed up) |
| 2026-10-17 | **A1 `a1_graph_decision`**: one coder agent, the 9 harness tools, prompt template A1 with a "GRAPH decision line" | Ran end to end in the real swegemma harness: **18/81 and 17/81** public repo-train tasks on two seeds (0.222 / 0.210) | `evidence/a1_harness_runs.json` |
| 2026-10-17 | `skills_lean`, `skills_multi`: A1 plus ADK skills (`py-locate`, `repro-verify`, `swe-rca`, `test-scout`), the multi variant with a read-only `code_analyzer` sub-agent | Built, **not run** in the harness | `bundles/` |
| ~2026-10-17 | **Tool-use LoRA** (`gemma4_31b_peft_config`): r=16, alpha=32, 410 language-model projections, assistant-only loss on rejection-sampled harness trajectories. Mapping A on one Colab GPU (HF PEFT); mapping B on 8x H100 (Megatron Bridge) | **Lost with the disk**: adapter, `scripts/30_train_lora.py`, the `gen_graph_31b` trajectories and `RALPH_STATE.md`. Only the recipe survived | `recipe/gemma4_31b_peft_recipe.md` |

## The 2026-10-21/22 rebuild

Four private scratch kernels on the competition's own 4x L4 hardware:

1. `scripts/sample.py`: rejection sampling. A1 in the real harness on the repo-train fold, two passes at T=0.7, plus the rich fold at T=0.2. A logging proxy between the agent and vLLM keeps the exact request and response of every model call (4,732 calls).
2. `scripts/eval_bundles.py`: A1 and a graph-first prompt on the rich fold at concurrency 2, closer to the scorer, which runs tasks one at a time.
3. `scripts/train.py`: turn-mode SFT samples from resolved runs only, LoRA training, the recipe's gates, and export in the competition's adapter layout.
4. `scripts/eval_adapter.py`: A1 plus the adapter on the rich fold (pending: the weekly GPU quota ran out on 22 Oct).

| Run | Fold | Concurrency | Resolved | Session timeouts |
|---|---|---|---|---|
| A1, T=0.7, pass 1 | repo-train (81) | 8 | 10 | 57 |
| A1, T=0.7, pass 2 | repo-train (81) | 8 | 12 | 50 |
| A1, T=0.2 | rich (48) | 8 | 13 | 33 |
| A1, T=0.2 | rich (48) | 2 | **14** | 19 |
| graph-first, T=0.2 | rich (48) | 2 | 13 | 14 |

Aggregates are in `evidence/`; no task text, patches or tests are included (competition Rule 2.4).
