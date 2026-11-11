# Reading list (Nov 11, 2026)

Papers behind the instruction program, grouped by the part of the plan each one informs.
Start with the six in bold. Entries marked *(our notes)* are 2026 papers collected by earlier research
(`research/LITERATURE_REVIEW.md`, `research/raw/03_swe_agent_literature.md`); they were not re-read for this list.

## 1. The exam we are solving
- SWE-bench, Jimenez et al. 2023, arXiv:2310.06770 — the task format our harness copies (issue → patch → hidden tests).
- SWE-rebench, Badertdinov et al. 2025, arXiv:2505.20411 — source of our practice tasks; fresh monthly sets; evaluation rules (several runs, report the spread).
- *Investigating Test Overfitting*, arXiv:2511.16858 *(our notes)* — passing tests does not always mean a correct patch.

## 2. Agent design and instructions (the instructions channel)
- **SWE-agent**, Yang et al. 2024, arXiv:2405.15793 — interface design for agents; one-change-at-a-time ablations (their Table 3); failure categories (their Figure 8).
- **Agentless**, Xia et al. 2024, arXiv:2407.01489 — a fixed find → fix → check procedure beats free exploration for weaker models.
- ReAct, Yao et al. 2022, arXiv:2210.03629 — the think → act → observe loop our agent runs.
- OpenHands, Wang et al. 2024, arXiv:2407.16741 — an open agent platform with its prompts and troubleshooting rules.
- **IFEval**, Zhou et al. 2023, arXiv:2311.07911 — measuring instruction-following with checkable rules (the idea behind our rule checks).
- The Prompt Report, Schulhoff et al. 2024, arXiv:2406.06608 — a map of prompting techniques.
- Harness design study, arXiv:2609.20804 *(our notes)* — what transfers between models; a 30B model gained mostly by reaching an edit before its budget ran out.

## 3. Improving instructions from failure feedback (the Claude ↔ Gemma loop)
- **OPRO**, Yang et al. 2023, arXiv:2309.03409 — one LLM proposes and scores prompt changes.
- APE, Zhou et al. 2022, arXiv:2211.01910 — automatic prompt engineering.
- Reflexion, Shinn et al. 2023, arXiv:2303.11366 — learning from written feedback on failures.
- Self-Refine, Madaan et al. 2023, arXiv:2303.17651 — iterative refinement with self-feedback.
- DSPy, Khattab et al. 2023, arXiv:2310.03714, and TextGrad, Yuksekgonul et al. 2024, arXiv:2406.07496 — automatic prompt-improvement pipelines.

## 4. Training on the model's own successes (the adapter channel; paused Nov 11)
- STaR, Zelikman et al. 2022, arXiv:2203.14465, and ReST-EM, Singh et al. 2023, arXiv:2312.06585 — train on your own verified successes.
- **SWE-Gym**, Pan et al. 2024, arXiv:2412.21139 — the closest prior work to our training rounds.
- SWE-smith, Yang et al. 2025, arXiv:2504.21798; R2E-Gym, Jain et al. 2025, arXiv:2504.07164; SWE-RL, Wei et al. 2025, arXiv:2502.18449.
- SWE-Lego, arXiv:2601.01426, and Open-SWE-Traces, arXiv:2606.16038 *(our notes)* — which training runs to keep.
- DPO, arXiv:2305.18290, and KTO, arXiv:2402.01306 — learning from pairs of a failed and a solved run.
- LoRA, arXiv:2106.09685, and QLoRA, arXiv:2305.14314 — the fine-tuning method we use.

## 5. Failure analysis (the run log)
- **Why Do Multi-Agent LLM Systems Fail? (MAST)**, Cemri et al. 2025, arXiv:2503.13657 — building a failure taxonomy from traces.
- Lost in the Middle, Liu et al. 2023, arXiv:2307.03172 — why long contexts lose details (our 32k window).

## What we took from the two papers read on Nov 11
- **SWE-agent:** we cannot add its commands (the competition fixes the tools). We copy its method (inspect behaviour on a dev set, change one thing, measure, stack the winners) and imitate the missing interface pieces with instruction lines: reads with a line range, small edits with a compile check, an example session.
- **SWE-rebench:** we use its validated task set and labels, its validation rule under Kaggle's packages, its fresh monthly sets as a "fresh" test slice, and its evaluation rules (dev vs test separation, repeated runs).
