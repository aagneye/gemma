# research/

Literature review and competition intelligence for the Kaggle "Google - The Gemma 4 Developer Agent Competition" (compiled 2026-10-16).

- `LITERATURE_REVIEW.md` — START HERE. Part I: the competition as it really is (official constraints, leaderboard/forum intelligence, data). Part II: the field (Gemma 4, SWE agents, localisation/code graphs, training recipes). Part III: thesis, 12 ranked design decisions, paper-track plan, open questions.
- `GPU_PLAN.md` — what to run on the T4 vs the H100 vs Kaggle L4x4, compute budget, week-by-week timeline to Dec 2, kill criteria.
- `raw/` — source dossiers with per-claim citations:
  - `00_kaggle_overview_verbatim.md`, `00b_kaggle_discussion_notes.md`, `00c_getting_started_notebook_facts.md` — captured from Kaggle in a logged-in browser.
  - `01_competition_harness.md` — HARNESS_README reconstruction + community repos.
  - `02_gemma4_model.md` — Gemma 4 technical report / ecosystem.
  - `03_swe_agent_literature.md` — SWE-bench agents, training, test-time compute.
  - `04_code_graph_retrieval.md` — localisation, code graphs, embeddings.
  - `05_training_recipes_and_data.md` — datasets, LoRA/RL recipes, hardware.
