# Gemma 4 Developer Agent: tool-use LoRA kit

Agent bundles, the LoRA recipe, the scripts that rebuilt a tool-use LoRA for `gemma-4-31b-it-qat-w4a16-ct` on the competition's own 4x L4 hardware, and the aggregate evidence from every run. Built for the Kaggle competition **Google - The Gemma 4 Developer Agent** (`gemma-4-developer-agent`).

- **Companion notebook:** `scottweeden/gemma-4-developer-agent-tool-lora-writeup`. It attaches this dataset and the adapter model, explains the results and writes `/kaggle/working/submission.zip`.
- **Adapter model:** `scottweeden/gemma-4-31b-swe-tool-use-lora` (Kaggle Models, Transformers / `main-lora`).

This dataset contains **no competition data**: no task text, snapshots, gold patches, tests, graphs or embeddings (competition Rule 2.4). Only the author's own prompts, YAML, scripts and aggregate results.

## Contents

| Path | What it is | Status |
|---|---|---|
| `bundles/a1_graph_decision_6min/` | **Submitted bundle.** One coder agent, the 9 harness tools, prompt template A1, session cap 6 minutes | Submitted 2026-10-22 |
| `bundles/a1_graph_decision/` | The same agent with the original 8-minute cap | 14/48 on the rich fold at concurrency 2 |
| `bundles/graph_first/` | A1's structure with a graph-first workflow, thinking budget 2048, max output 4096 | 13/48 on the rich fold at concurrency 2 |
| `bundles/skills_lean/`, `bundles/skills_multi/` | A1 plus four ADK skills; the multi variant adds a read-only analyzer `agent_tool` | Pass the static checker; not run in the harness |
| `recipe/gemma4_31b_peft_recipe.md` | The LoRA recipe: convergence contract plus HF PEFT and Megatron Bridge execution mappings | Reference |
| `scripts/sample.py` | Rejection sampling in the real harness with a logging proxy between the agent and vLLM | Ran 3.7 h on 4x L4 |
| `scripts/eval_bundles.py`, `scripts/eval_adapter.py` | Rich-fold evaluation of bundles, and of A1 plus the adapter | The adapter run is pending |
| `scripts/train.py` | Turn-mode SFT samples, QLoRA training, gates, export in the competition's adapter key layout | Ran 6.7 h on 4x L4 |
| `scripts/make_submit_nb.py` | Builds a CPU notebook that writes `submission.zip` from an embedded bundle | Used for the 22 Oct submission |
| `tools/check_submission.py`, `tools/check_kinds.json` | Standard-library static checker for a bundle | Used before every zip |
| `evidence/` | Aggregate results: `a1_harness_runs.json` (A100, 17 Oct), `rebuild_sampling.json`, `rebuild_outcomes.json`, `rebuild_eval_c2.json`, `rebuild_metrics.json` | |
| `history/SUBMISSIONS.md` | Every build and submission to date, with what was lost and what was rebuilt | |
| `docs/transformer_primer.md`, `examples/` | How the LoRA changes Gemma 4 31B; vLLM serving in the scorer's configuration; an ADK multi-agent example | Reference |

## Results in one table (Kaggle 4x L4, vLLM 0.19.1, the competition wheelhouse)

| Run | Fold | Concurrency | Resolved | Session timeouts |
|---|---|---|---|---|
| A1, T=0.7 (sampling, pass 1) | repo-train, 81 | 8 | 10 | 57 |
| A1, T=0.7 (sampling, pass 2) | repo-train, 81 | 8 | 12 | 50 |
| A1, T=0.2 | rich, 48 | 8 | 13 | 33 |
| **A1, T=0.2** | rich, 48 | 2 | **14** | 19 |
| graph-first, T=0.2 | rich, 48 | 2 | 13 | 14 |

What to take from it:
- **Concurrency decides the timeout rate.** On 4x L4 the KV cache holds about 1.4 full-length (32k) sequences. With 8 tasks sharing one vLLM server, most requests queue and two thirds of the tasks run out of time. The scorer runs tasks one at a time.
- **The graph-first prompt is faster but not better.** It uses fewer tool calls (median 21 vs 26) and has 5 fewer timeouts, but 4 more test failures: it gained 1 task and lost 2.
- **The 12-hour budget binds.** The scorer runs about 120 tasks in sequence within 12 hours. A1's measured durations project an 8-minute cap to 12.4 to 14.2 hours, so the submitted bundle caps sessions at 6 minutes (projected 10.7 to 12.0 hours).

## The LoRA

r=16, alpha=32, dropout 0.05 on all 410 language-model projections (q, k, v, o, gate, up, down; the 10 global-attention layers share k and v, so they have no `v_proj`). It was trained on 83 turn-mode samples (484k tokens, 18k supervised) from 14 train-fold tasks that A1 resolved during sampling, for 2 epochs (12 optimizer steps).

| Gate (recipe §5) | Result |
|---|---|
| Fits 16k context on 4x L4 | yes, with query-chunked attention; peak 20.4 GiB on the last GPU; 16.7 ms per token |
| Loss finite and decreasing | 0.168 → 0.108 |
| Adapter changes the logits | max \|Δ logit\| 18.3 |
| Held-out (rich) agreement with the base agent's tool choice | base 0.990, adapter 0.985 (200 decision points) |
| Rich-fold resolve rate, A1 + adapter vs A1 | **pending**: the weekly GPU quota ran out |

## How to use it

1. Attach this dataset (and, for the adapter bundle, the adapter model) to a notebook with the competition data. Internet off is fine.
2. Copy one bundle directory and zip its **contents** so `agent.yaml` sits at the archive root. To use the adapter, add `adapter: main_lora` under `model:` in `agent.yaml` and copy the model's two files into `adapters/main_lora/`. Use it **only with the A1 prompt and tools it was trained on**.
3. Run `tools/check_submission.py <bundle>` and submit the notebook.

## Licence

Apache-2.0 for the author's prompts, YAML and scripts. `skills/swe-rca` is adapted from MIT-licensed material; see its `references/ATTRIBUTION.txt`. Gemma 4 weights are not included; use of the adapter is subject to the Gemma terms of use.
