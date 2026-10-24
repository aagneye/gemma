# 01 — Competition Harness & Constraints Dossier
**Competition:** Google — The Gemma 4 Developer Agent Competition (Kaggle, comp id 149921) + Paper Track (comp id 163111)
**Compiled:** 2026-10-16 from web research only (Kaggle pages are JS-rendered; most official text is reconstructed from community mirrors). Everything not marked OFFICIAL is secondhand. Items marked **UNVERIFIED** conflict between sources or rest on a single secondhand source. Items marked **MUST-VERIFY** must be checked against the real `HARNESS_README.md` and wheelhouse source once the ~21 GB dataset is downloaded.

Source legend (short tags used inline):
- **[K-OV]** Kaggle overview https://www.kaggle.com/competitions/gemma-4-developer-agent
- **[K-RULES]** https://www.kaggle.com/competitions/gemma-4-developer-agent/rules
- **[K-DATA]** https://www.kaggle.com/competitions/gemma-4-developer-agent/data
- **[K-LB]** https://www.kaggle.com/competitions/gemma-4-developer-agent/leaderboard
- **[K-PAPER]** https://www.kaggle.com/competitions/gemma-4-developer-agent-paper
- **[K-DISC n]** Kaggle discussion thread id n (content secondhand via emiliodavola playbook / LogosTopos docs; threads could not be fetched directly)
- **[HARNESS-MIRROR]** rishaviitd's `context/harness.md`, a close paraphrase of HARNESS_README: https://raw.githubusercontent.com/rishaviitd/kaggle.gemma.coding.agent/main/context/harness.md
- **[DATA-MIRROR]** rishaviitd `context/data.md`: https://raw.githubusercontent.com/rishaviitd/kaggle.gemma.coding.agent/main/context/data.md
- **[EMILIO-PB]** emiliodavola playbook (incl. §10 "official forum findings"): https://raw.githubusercontent.com/emiliodavola/kaggle-gemma-agent/main/docs/competitive-options-playbook.md and PR https://github.com/emiliodavola/kaggle-gemma-agent/pull/56
- **[G4KIT]** https://github.com/damsolanke/gemma4-swe-kit
- **[HAPPY]** https://github.com/happyc0der/gemma-swe-agent and https://raw.githubusercontent.com/happyc0der/gemma-swe-agent/main/docs/harness-fidelity.md
- **[CONT]** https://github.com/HyunsikParker/continuation-suite
- **[LOGOS]** https://github.com/LogosTopos/gemma-4-developer-agent (+ `docs/research/2026-09-28-agent-architecture.md`, `docs/RESEARCH_STATUS.md`, `docs/EXPERIMENT_HANDOFF.md`)
- **[USP787]** https://github.com/usp787/Gemma4_paper_track
- **[HIND]** https://github.com/HindsightWise/gemma-4-developer-agent
- **[HINDAI-PR]** https://github.com/mangeshraut712/Hindai/pull/32
- **[GOSLING]** https://github.com/Gosling-dude/gemma4-developer-agent
- **[MAUK]** https://github.com/Maukthik/gemma4
- **[8KTA]** https://github.com/8kta/kaggle-gemma4
- **[ROOTFIX]** https://github.com/harshithKumar12/root-fix
- **[ENNY]** https://github.com/ennydev-2026/gemma-4-developer-agent
- **[ELAMURG]** https://github.com/elamurg/gemma-4-dev
- **[SAGAR]** https://github.com/sagarml4949/gemma4-swe-agent
- **[RISHAV]** https://github.com/rishaviitd/kaggle.gemma.coding.agent
- **[GRAPHNAV]** https://github.com/satiricalguru/Gemma-graph-nav
- **[YOSH]** https://github.com/yosh95/g4-developer-agent-paper
- **[NS0437]** https://github.com/ns-0437/gemma4-agent-lab and https://github.com/ns-0437/gemma4-developer-agent
- **[MSING]** https://github.com/msingatullin/gemma-4-developer-agent
- **[NYMREL]** https://github.com/nymrel/nymrel-swarm-studio/issues/20
- **[VLLM-RECIPE]** https://github.com/vllm-project/recipes/blob/main/Google/Gemma4.md
- **[HF-CARD]** https://huggingface.co/google/gemma-4-31B-it-qat-w4a16-ct
- **[ADK-CFG]** https://adk.dev/api-reference/agentconfig ; **[ADK-COMPACT]** https://adk.dev/context/compaction/

Repos that were requested but are now inaccessible (HTTP 404 on github.com and api.github.com as of 2026-10-16; probably made private or deleted): `sweeden-ttu/developer-agent`, `tamasmakos/swe-bench-press`. Only search-engine snippets survive for them (see §3).

---

## 1. Official rules and constraints

### 1.1 Base model, quantization, adapters
| Item | Value | Source / status |
|---|---|---|
| Allowed base model | **Only** `gemma-4-31b-it-qat-w4a16-ct`; "You *must* choose this model for every agent and subagent." | OFFICIAL [K-OV] via search snippet; mirrored by [ENNY], [ELAMURG], [HIND] |
| Other Gemma 4 sizes | Not allowed for scoring. Harness `ModelRegistry` has other aliases (12B, E4B, E2B) for **local CLI use only**. Ryan Holbrook posted "New Gemma 4 Models Available: 12B, E4B, and E2B" in the discussion — context suggests local dev, not scoring. **UNVERIFIED** whether that post changed the scoring rule; the most recent repos (Oct) still say 31B only. | [HARNESS-MIRROR]; Kaggle discussion listing via search |
| Quantization | INT4 weights / 16-bit activations, "compressed-tensors" (`-ct`) QAT checkpoint; ~16–18 GB weights (one source says 23.3 GB on disk). Native context 256K; harness serves at 32,768. License on HF card: **Apache 2.0** (not the old Gemma Terms). | [HF-CARD], [VLLM-RECIPE], [EMILIO-PB] |
| Full fine-tune? | **No.** Only PEFT LoRA adapters may be shipped; the base checkpoint is loaded by the scorer. Weights other than `adapter_model.safetensors` are impossible (`.bin/.pt/.pth` rejected). | [HARNESS-MIRROR], [K-OV] |
| LoRA format | `adapters/<name>/adapter_config.json` + `adapter_model.safetensors` (PEFT dir); referenced by `adapter: <name>` on any `LlmAgent` (root or `sub_agents/*.yaml`). Official example: `main_lora` on root coder, `tool_lora` on read-only analyzer AgentTool. `discover_adapters()` registers them with vLLM `--lora-modules`; it expects the **submission root**, not the adapter folder. | OFFICIAL [K-OV] snippet; [HARNESS-MIRROR]; [EMILIO-PB §10.5] |
| Number of adapters | "one or more" [K-OV]; vLLM started with `max_loras = 8` → effectively ≤ 8 adapters. **CONFLICT:** [EMILIO README] says "at most one model, total < 3 GiB" — that refers to one *base* model, not one adapter. | [HARNESS-MIRROR]; [EMILIO-PB] constraint table "Up to 8; rank ≤ 128" |
| LoRA rank limit | vLLM `max_lora_rank = 128`. Size guidance for 31B: r16 ≈110–220 MB, r32 ≈220–450 MB, r64 ≈450–900 MB, r128 ≈0.9–1.8 GB. | [HARNESS-MIRROR] |
| Total size | Unpacked submission **< 3 GiB** (3,221,225,472 bytes incl. `adapters/`); also ≤10,000 files, ≤1,000 YAML files, ≤50 MiB per YAML or skill dir, ≤500 agents, nesting ≤50, ≤1,000 skills, ≤500 loop iterations. | [HARNESS-MIRROR]; 3 GiB also in [EMILIO], [AMonFer], [bbkdevops HF] |
| Allowed file extensions | `.yaml .yml .md .txt .py .json .safetensors` (`swegemma.config.ALLOWED_SUBMISSION_EXTENSIONS`). `.sh` files and **extensionless files (e.g. `.gitkeep`)** cause validation failure. | [HINDAI-PR], [8KTA] ("File has disallowed extension ''"), [LOGOS] |
| Multi-adapter per request | Different adapters per agent are allowed (routing by agent). LoRA KV-cache cost: a rank-64 adapter reportedly shrank usable KV cache to ~7.6k tokens; organizer said vLLM "now sizes LoRA parameters from the submission" so fewer/lower-rank adapters free KV memory. | [K-DISC 744331] via [EMILIO-PB]; [HIND] "~8.8 GB per GPU reserved by default LoRA config" |
| LoRA loading bugs | Adapters were "silently zeroed/wiped" by the patched vLLM until wheelhouse v23 (fix ~2026-09-27/28 per [K-DISC 743964]). Only the **patched wheelhouse vLLM** supports Gemma 4 LoRA; PyPI vLLM fails "does not support LoRA yet". | [EMILIO-PB §10.2, §10.5], [LOGOS], [GOSLING] |
| LoRA throughput cost | Decode slowdown 8–9 % at r8–16, 16 % at r32, 21 % at r64 (local measurement on scorer-like stack). | [USP787] |

### 1.2 Budgets, hardware, serving
| Item | Value | Source / status |
|---|---|---|
| Scorer GPUs | **4 × NVIDIA L4 (24 GB each, 96 GB)**; Kaggle notebook accelerator "GPU L4 x4"; internet disabled. | [HARNESS-MIRROR], [G4KIT], [HIND], [RISHAV], [GOSLING] |
| vLLM settings | vLLM **0.19.1** (patched wheel), `tensor_parallel_size=4`, `gpu_memory_utilization=0.80`, `max_model_len=32768`, `enable_lora=True`, `max_loras=8`, `max_lora_rank=128`, `tool_call_parser=gemma4`, `reasoning_parser=gemma4`; served as OpenAI-compatible `/v1` on :8000 (Transformers fallback exists). | [HARNESS-MIRROR], [8KTA], [HAPPY], [RISHAV] |
| Context window | **32,768 tokens hard** (prompt + thinking + output). Request with prompt_tokens + max_tokens > 32,768 → **HTTP 400**. | [G4KIT], [EMILIO-PB], [MAUK], [ROOTFIX] |
| Effective context / compaction | ADK `EventsCompactionConfig(token_threshold=14,336, overlap_size=2, event_retention_size=5, compaction_interval=5 **or** 15)`. See §2.6 for the conflict over whether compaction ever fires inside a task. | [HARNESS-MIRROR], [HAPPY], [G4KIT], [EMILIO-PB] |
| Output / thinking defaults | `max_output_tokens` 1–32,768 (default **16,384**); `thinking_budget` 0–32,768 (default **4,096**); `thinking_level` MINIMAL/LOW/MEDIUM/HIGH/NONE (advice: omit on vLLM). | [HARNESS-MIRROR] |
| Sampling defaults | vLLM request defaults = model defaults: temperature 1.0, top_p 0.95, top_k 64, `enable_thinking: true`. | [G4KIT], [HF-CARD] |
| Per-task defaults (no eval_config) | **60 min, 100 tool calls, 500 turns, 300 s command timeout**. Env overrides `SWE_MAX_TIME_MINUTES`, `SWE_MAX_TOOL_CALLS`, `SWE_MAX_TURNS`/`SWE_MAX_LOOP_ITERATIONS`, `SWE_TIMEOUT_SECONDS`. Timer starts **after** container setup. | [HARNESS-MIRROR]; [EMILIO-PB] (organizer: "by default there is no limit" — i.e., only these generous defaults) |
| `eval_config.yaml` | Optional; scorer reads **exactly four** keys under `evaluation:`: `timeout_seconds`, `max_tool_calls`, `max_time_minutes`, `max_turns`. Sample ships 300 / 10 / 1 / 50 (i.e., 1 min, 10 calls — do not reuse). | OFFICIAL via [K-DISC 743063]; [HARNESS-MIRROR]; [MAUK] |
| Total wall-clock | **12 hours** for the whole hidden set (~120 tasks), **sequential**, setup included in the 12 h per [LOGOS 743063] but agent timer excludes setup per [HARNESS-MIRROR]. Exceeding 12 h currently **errors the whole submission**; organizers plan to change to "unfinished tasks score 0". Parallel model calls / concurrency are **not supported** on the scorer. | OFFICIAL via [K-DISC 743063, 743964]; [EMILIO-PB §10.3]; [GOSLING]; [MAUK] |
| Verification timeout | Since swegemma 0.2.11 (Oct 12 wheelhouse) verification has its own `verification_timeout_seconds` (default 300, `--verification-timeout-seconds`); earlier, `timeout_seconds` from eval_config also capped the grading pytest run (so a 120 s value could fail grading). | [HAPPY harness-fidelity], [CONT], [GOSLING] |
| Sandbox | Docker image `swebench-sandbox:latest`, Python **3.13**, `network_mode="none"`, **4 GiB RAM** (exit 137 on OOM), **2 vCPU**, cwd `/workspace`, wheels at `/wheels` (read-only, 124 wheels), `TEST_TMPDIR=/tmp`. Containers are warm-pooled; `/workspace`, `/tmp`, `/var/tmp` wiped between phases. | [HARNESS-MIRROR], [DATA-MIRROR], [GOSLING], [HAPPY] |
| Internet | None in sandbox; no pip installs, no servers, no background processes. | [HARNESS-MIRROR], [EMILIO-PB] |
| Measured scorer throughput | ~25.5 tok/s decode on 4×L4; per-call cost ≈ 0.6 s + completion_tokens/25.5 [G4KIT]. Host trial: 35–58 s per tool call end-to-end [EMILIO-PB §10.9]. Base decode 28.4 tok/s vs 22.5 with r64 LoRA [USP787]. Thinking consumes 65–71 % of agent time [USP787]. |

### 1.3 Submission format and cadence
- `submission.zip` with `agent.yaml` **at the archive root** (also accepted: `agent.yml`, `root_agent.yaml`, `root_agent.yml`; zero → `MissingRootConfigError`, >1 → `MultipleRootConfigsError`). Nesting under a folder breaks it. [HARNESS-MIRROR], [ENNY], [ROOTFIX]
- **1 submission per day; up to 2 final submissions**; team size ≤ 5; mergers allowed until 2026-11-25. [K-RULES] via search snippet; [EMILIO-PB]
- Scoring output is a `submission.parquet` with `id` (= `instance_id`) and `prediction` = unified git diff vs `base_commit` or the literal **`NO_PATCH`**. (Produced by the harness, not by you.) [K-DATA] via search; [DATA-MIRROR]
- Scored metric: **Resolution Rate** = resolved / total, 0.0–1.0; resolved = `pytest` exit 0 **and** JUnit XML with ≥1 pass, 0 fail/err, all required nodes passing (no skips). [HARNESS-MIRROR]
- Public LB uses ~50 % of the hidden set [K-LB snippet]; community infers **58 public tasks** (scores move in 1/58 ≈ 0.017 steps) — **UNVERIFIED** but consistent across [HAPPY], [YOSH], [USP787], [GOSLING].
- Scoring queue: submissions reported running 15–46 h with a 6-min cap; pinned organizer post "Update on 'Kaggle Error' Submissions & Queue Delays" (Dustin, 54 comments) exists — body not retrieved. Sep-30 errors were a GPU outage [K-DISC 744807]. **UNVERIFIED** whether queue time counts toward anything (it does not count toward the 12 h per harness design).

### 1.4 Prizes, deadlines, team, licensing
| Item | Value | Source |
|---|---|---|
| Main track prizes | **$65,000**: 1st $37k, 2nd $18k, 3rd $10k | [ENNY], [NYMREL], [HIND] (official page snippet confirms $100k total) |
| Paper track prizes | **$35,000**: Overall Best Paper $15k, Best New Resource (dataset/tool/library) $10k, Best New Application (new use of code graphs and/or embeddings) $10k. **CONFLICT:** an X post summarised as "$15,000 to the paper track" — treat as the best-paper line only. | [USP787], [MSING], [NYMREL]; X post via search (UNVERIFIED) |
| Start | 2026-09-23 | [ENNY], [HAPPY] |
| Paper deadline | **2026-11-12 23:59 UTC** | [K-PAPER] snippet, [USP787] |
| Entry / team-merger deadline | **2026-11-25**. **CONFLICT:** a Google Gemma X post said "Entry Deadline: Nov 2"; Kaggle timeline says Nov 25 — trust Kaggle. [MSING] wrongly lists Nov 25 as "submission deadline". | [K-OV] snippet, [ENNY], [NYMREL] |
| Final submission | **2026-12-02 23:59 UTC** | [ENNY], [HIND], [NYMREL], [EMILIO] |
| Team size | max 5 | [K-RULES] snippet |
| Winner licence | "Open Source Apache 2.0" heading; winners must license the winning submission **and the source code used to generate it** under an OSI-approved licence that does not limit commercial use; exception for incompatible-licence inputs/pretrained models. Winners deliver training code, inference code, documentation (+ tax forms). Kaggle Foundational Rules override conflicts. | [K-RULES] snippet; [ELAMURG] (secondhand) |
| Distillation / external models | Allowed if the external model's licence permits it and nothing conflicts with the rules (Ashley Oldacre, institutional reply). Earlier (9/28) only "Gemma-generated data" was clearly allowed. | [K-DISC 742807] via [EMILIO-PB]; [K-DISC 743964] via [LOGOS] |
| Data use | Competition data may be used for research but **not redistributed** to non-participants. | [USP787], [YOSH] |

### 1.5 Paper Track specifics [K-PAPER], [USP787]
- Format: Kaggle **Writeup ≤ 3,000 words** (title, subtitle, abstract, intro, research description, related work/citations; optional public notebook or arXiv-ready PDF). Must be unpublished (arXiv preprints OK), non-archival, "related research of any kind" accepted. Up to **5 submissions/day**, max **two writeups per team**, team ≤ 5. Must join the paper competition; joining main track not required but encouraged.
- Judging: five equally weighted criteria, each 0–5, averaged: **Novelty, Quality (generality beyond the competition), Relevance (impact on SWE & agentic learning), Verifiability, Clarity**. **CONFLICT:** [MSING] lists "Innovation, Technical Depth, Generalizability, Empirical Validation, Clarity"; the official snippet confirms "Novelty" and "Quality", so [USP787]'s list is the one to trust.
- Text written mostly by an LLM "will score poorly"; coding assistants fine.
- Each writeup can win at most one award; ties → earlier entry. Winning papers highlighted at a Google-hosted event (e.g., NeurIPS expo workshop).
- Winners must OSI-license submission and provide code + docs.

---

## 2. HARNESS_README reconstruction (swegemma / adk-submission / adk-eval-core)

Primary source: [HARNESS-MIRROR] (close paraphrase of the official README, incl. file/line references), cross-checked with [HAPPY harness-fidelity] (diffed against the actual wheel source), [G4KIT], [CONT], [LOGOS]. Versions seen: wheelhouse dataset `metric/gemma-4-developer-agent-wheelhouse` (~827 MB, ~41 wheels, 4 pure-Python). **swegemma 0.2.7 → 0.2.10 (Oct 8) → 0.2.11 (Oct 12)**; **adk_submission 0.2.11 → 0.2.12 → 0.2.13 (Oct 8)**; **adk_eval_core 0.1.0**; **google-adk 1.36.1**; **vllm 0.19.1** (patched); **transformers 5.6.2** used for template rendering by [CONT]. [HAPPY], [CONT], [8KTA]

### 2.1 Library roles [HARNESS-MIRROR]
- **adk-submission** — compiles the declarative submission directory into a Google ADK agent tree **without importing competitor Python**; resolves names against closed registries (`ToolRegistry`, `ModelRegistry`, `SkillRegistry`, `CallbackRegistry`); manages local vLLM/Transformers servers; key functions `validate_directory`, `discover_declared_models`, `validate_single_declared_model`, `compile_submission`, `discover_adapters`. Thinking config lives in `resolvers/generation.py`; tools in `resolvers/tools.py` [LOGOS].
- **adk-eval-core** — base task/result models, sandbox backends (`DockerContainer`, `SubprocessSandbox`), 3-tier file editing, token/cost tracking, ADK plugins (`ModelRetryPlugin`), ATIF v1.7 trajectory tracing.
- **swegemma** — the SWE-bench-style harness: two-container lifecycle, binds the 9 tools, builds the prompt and nudges (`swegemma/harness/agent_runner.py`), extracts diffs, runs pytest with JUnit verification; CLI `swegemma eval`.

### 2.2 Two-container sandbox lifecycle [HARNESS-MIRROR], [HIND], [ROOTFIX]
**Phase 1 — Container A (agent):**
1. Start sandbox, stage wheels at `/wheels`.
2. Extract snapshot at `base_commit` (forward history removed).
3. Append to `/workspace/.git/info/exclude`: `__pycache__/ *.pyc .pytest_cache/ *.egg-info/ build/ dist/ .coverage`.
4. `pip install --no-index --find-links=/wheels --no-build-isolation --no-deps -e /workspace` (failures ignored).
5. Install cached test deps; run `/sandbox/setup.py --fast-path <repo>`.
6. Write `/workspace/pytest.ini`, prepend hermetic hook to `/workspace/conftest.py`.
7. `git add -A && git commit -m "baseline" --allow-empty -q` → commit `_swegemma_baseline`. (Harness files are in the baseline, so edits to them appear in the diff.)
8. Agent loop runs until `submit_patch()` + final text, timeout, budget exhaustion, or >3 consecutive nudges.

**Phase 2 — Container B (verification):** fresh container, repeat setup at commit `eval_baseline`; **four-pass apply** (`git apply --unsafe-paths -p1` → `-3` → whitespace-ignoring → `--recount`; symlink-normalised `-p1`; prefixless `-p0`; GNU `patch` with dry run) else "Failed to apply agent patch"; **reset protected paths** (`conftest.py`, `pytest.ini`, `pyproject.toml`, `tox.ini`, `setup.cfg`, `.pytest.ini`, `sitecustomize.py`, `usercustomize.py`, `_swegemma_stubs.py`, `*.pth`, and test files) to `eval_baseline`; apply `test_patch`; run `PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest --junitxml ... -p no:anyio -o timeout=0 -o python_classes="Test* *Test"`. [HIND] adds the reset is effectively `git checkout HEAD -- tests/ conftest.py pytest.ini setup.cfg pyproject.toml && git clean -f`.

Subprocess backend (local only): temp dir with `workspace/ tmp/ wheels/ venv/`, path rewriting, kills process group on timeout; **not filesystem isolation** [NS0437]; skill scripts saw an empty dir under it in one report [GOSLING].

### 2.3 Patch capture, fallback, NO_PATCH [HARNESS-MIRROR], [HAPPY], [CONT]
- `submit_patch()` runs `git add -N .` then `git diff --binary _swegemma_baseline` (fallback `HEAD`), stores the patch, sets `patch_submitted`, returns `patch_size`, `files_changed`. Repeatable (last one wins — **MUST-VERIFY**).
- If the agent never calls `submit_patch()`, the harness runs the same capture on the **working tree before teardown**; a non-empty patch is still scored. Untracked files (incl. scratch files under `/workspace`) are included by `git add -N .` → **26 of 46 host-trial patches contained scratch files** [EMILIO-PB §10.9]. `write_file("/tmp/x")` is rewritten to `/workspace/tmp/x` and ends up in the patch [MAUK] — use `run_command` with real `/tmp` for scratch.
- **`NO_PATCH`** = the `prediction` written when the captured diff is empty [K-DATA]; the term does not appear in harness code per [HAPPY] — the mapping "empty diff → NO_PATCH" is **UNVERIFIED** but the only consistent reading.
- Known loss modes: (a) `ContextWindowExceededError`/generic exceptions in `agent_runner.py` **bypassed the working-tree fallback** → empty patch even after edits, and could discard an earlier `submit_patch` [HIND], [G4KIT] (~1 task in 12 locally; 3–4 of 70 per run [USP787]); swegemma 0.2.10 "catches generic exceptions before the working-tree fallback" [CONT] / [K-DISC 744692]. (b) A well-formed call to an **undeclared tool name** raised in ADK and ended the task with no patch [K-DISC 745028]; 0.2.10 returns the error to the model instead [CONT]. **MUST-VERIFY** both fixes are in the wheelhouse the scorer runs.

### 2.4 Exact tool list and signatures (`swegemma.tools`) [HARNESS-MIRROR]
All budget-gated tools return one level of JSON: `{"status":"ok", ...}` or `{"status":"error","error_type","error_message","details"}` (`ensure_ascii=False`). When `tool_calls >= 20` and ≤10 remain, a `budget_warning` field is added. Before the 2026-09-30 wheelhouse, results were double-encoded (`{"result": "<json string>"}`) which broke `edit_file` quoting [G4KIT], [K-DISC 744272].

| # | Tool | Signature | Notes / limits |
|---|---|---|---|
| 1 | `run_command` | `(command: str) -> str` | `/bin/bash -c` in `/workspace`; counts as a call; timeout `min(300, max(5, remaining_seconds))`; `TimeoutExceeded` does not end the session; stdout and stderr each capped at **5,000 chars**; non-zero exit → `CommandError`. |
| 2 | `submit_patch` | `() -> str` | **Free** (not counted). See §2.3. |
| 3 | `get_status` | `() -> str` | **Free.** Returns calls used/remaining, patch status, time remaining/elapsed, `max_turns`, `command_timeout_seconds`. |
| 4 | `read_file` | `(filepath: str, start_line: int\|None=None, end_line: int\|None=None) -> str` | 1-indexed inclusive; cap **150 lines / 10,000 chars**, `is_truncated`, `total_lines`. Line numbers must be integers (ADK serialises optional ints as `any_of [INTEGER, NULL]`; a 12B proxy sent strings and failed — scorer stack OK) [HAPPY]. |
| 5 | `edit_file` | `(filepath: str, old_string: str, new_string: str, allow_multiple: bool=False) -> str` | Three match tiers: exact → flexible (per-line whitespace-insensitive, re-indents) → regex (token-based). `FileEditError` if file missing/empty, `old_string` empty, or multiple matches without `allow_multiple`. Returned diff capped 5,000 chars. |
| 6 | `write_file` | `(filepath: str, content: str) -> str` | Create/overwrite, `mkdir -p` parents, returns `size`. |
| 7 | `get_code_neighbors` | `(node: str, edge_type: str\|None=None, max_neighbors: int=50) -> str` | In+out neighbours; resolution tiers: exact → `.`/`/` suffix → case-insensitive → substring. Example edge types `CALLS`, `DEFINED_IN`, `IMPORTS` (but released graphs contain only `calls` — see §4). Alphabetical, truncated at 50, no edge direction shown [USP787]. |
| 8 | `search_similar_code` | `(query: str, k: int=10) -> str` | Cosine over `.npz` embeddings. **No live embedder offline → query must be a symbol name (node id) or node source, not free text.** >400 free-text calls returned nothing in [USP787]'s runs; output uncapped (one node ≈130k chars) — host said a cap would be added. |
| 9 | `get_code_subgraph` | `(nodes: list[str]) -> str` | Induced subgraph, `node_count`, `edge_count`. |

Path handling for 4–6: paths resolve under `/workspace`; leading `/` or `/workspace/` stripped; any `..` → `ValidationError` ("Path traversal detected").

Graph tools require `data/graphs/<repo>.json` and `data/embeddings/<repo>.npz`; the prompt's "Code Intelligence Tools" paragraph is injected **only when both files exceed 100 bytes**, regardless of `agent.yaml` [HAPPY], [8KTA].

**Skill tools (not in `ToolRegistry`):** declaring `run_skill_script` / `load_skill_resource` under `tools:` → `ToolNotFoundError` at compile ("nine tools plus `agent_tool`") [HINDAI-PR]. They are exposed automatically by ADK's `SkillToolset` when a `skills:` entry exists; the toolset also adds `list_skills` and `load_skill` and **cannot be hidden or renamed** from YAML [HAPPY], [LOGOS]. Official data page: "Scripts run through `run_skill_script` execute in the competition's persistent Docker container"; "Agents read domain knowledge files through `load_skill_resource`" [K-DATA snippet]. A list-valued `file_path` argument to `run_skill_script` raised and ended the task (pre-0.2.10) [CONT], [EMILIO-PB]. **MUST-VERIFY** exact SkillToolset signatures and whether skill-script runs count against `max_tool_calls`.

### 2.5 agent.yaml / ADK Agent Config schema restrictions [HARNESS-MIRROR], [ADK-CFG], [LOGOS]
- No Python entry points. Agent classes: `LlmAgent` (default), `SequentialAgent`, `ParallelAgent`, `LoopAgent` (`max_iterations` default 500, range 1–500). Note the scorer does not support parallel model calls, so `ParallelAgent` is of dubious value [K-DISC 743964].
- `LlmAgent` keys: `name` (required), `model` (required unless default), `adapter`, `description` (≤1,000,000 chars), `instruction` (≤1,000,000 chars; ADK `{var}` templating — **only `{problem_description}` (and `{hints?}`/`{problem_description?}` optional form) are safe; any other `{word}` raises `KeyError` and crashes every task** [MAUK], [GOSLING]), `tools` (names, `agent_tool` refs, or inline agents), `skills` (paths), `sub_agents` (`config_path` or `code`), `output_key`, `include_contents` (`default`|`none`), `disallow_transfer_to_parent`, `disallow_transfer_to_peers`, `generate_content_config`.
- `generate_content_config`: forbidden keys `tools`, `system_instruction`, `http_options`, `safety_settings`, `response_schema`. Allowed: `temperature`, `top_p`, `top_k`, `max_output_tokens` (1–32,768, default 16,384), `seed`, `thinking_config: {thinking_budget (0–32,768, default 4,096), include_thoughts, thinking_level}`. Field names at ADK level per [ADK-CFG]: `agent_class`, `name`, `description`, `model`, `instruction`, `sub_agents[{config_path|code}]`, `tools[{name, args}]`, `include_contents`, `generate_content_config`, `output_key`, `disallow_transfer_to_*`, `input_schema`, `output_schema`, `*_callbacks` (callbacks need a `CallbackRegistry` the harness does **not** provide → effectively unusable [K-DISC 743573] via [LOGOS]).
- `!include`: `.md/.txt` → raw string; `.yaml/.yml` → recursive to depth 10 with cycle detection; absolute paths, NUL bytes, `..`, symlinks escaping root → `PathTraversalError` (so sub-agent prompts must live at paths like `prompts/analyzer.md`, not `../`).
- Sub-agent as tool: `tools: - agent_tool: {config_path: sub_agents/code_analyzer.yaml, skip_summarization: true}` (official sample form) [HINDAI-PR], [ROOTFIX], [EMILIO issue #71]. In google-adk 1.36.1 `AgentTool` accepts a single string arg `request`, spins a **new Runner + InMemorySessionService** per call (parent history **not** copied; parent state copied minus `_adk*` keys, child state merged back), and `skip_summarization=true` makes the tool response final so the parent's loop ends that turn — continuation then depends on swegemma's nudge [LOGOS]. Sub-agent sessions are **never compacted** [G4KIT]. Turn/tool budgets are **shared across the whole agent tree**; a sub-agent adds no budget [8KTA], [EMILIO #71]. Sub-agent `skills:` paths were rejected by the compiler in one report [GOSLING] — **MUST-VERIFY**.
- Model aliases: only `gemma-4-31b-it-qat-w4a16-ct` accepted for scoring; every agent file must declare the same single base model (`validate_single_declared_model`); mismatch → `ParticipantVisibleError` [ROOTFIX].
- Thinking mapping (adk_submission `resolvers/generation.py`): `include_thoughts=false` or `thinking_level=none` → `chat_template_kwargs.enable_thinking=false` (**i.e., `include_thoughts:false` turns reasoning OFF, not merely hides it** [K-DISC 745059], [LOGOS], [MAUK]); `thinking_level` LOW/MEDIUM/HIGH → `reasoning_effort`; `thinking_budget` → vLLM `thinking_token_budget` (hard cap: budget 24 → 22-token thought [G4KIT]). History: 09-25 wheelhouse never forwarded `thinking_budget` [HAPPY], [GOSLING "never enforced"]; 09-27 re-release forwards it, and because the default injects 4,096, **a config that sets neither `include_thoughts` nor `thinking_level` now gets thinking ON** [HAPPY]. With thinking off the 31B still emits an empty thought block [HF-CARD]. `seed` was not sent until a later fix [EMILIO-PB].
- "Skills" here = ADK skills: a directory `skills/<kebab-name>/SKILL.md` (+ `scripts/*.py`, `references/` — [8KTA] says `references/` is correct and HARNESS_README's example tree saying `resources/` is wrong — **MUST-VERIFY**). `SKILL.md` `name` must equal the directory name [GOSLING]. Skills are the **only** sanctioned way to ship custom Python: scripts run inside the sandbox via `run_skill_script`, may wrap deterministic retrieval/edit/verify logic, cannot replace harness tools or install deps [K-DISC 743573] via [LOGOS]. Limits 1,000 skills, 50 MiB each.
- Sample submission structure (official `sample_submission/`): root `agent.yaml` = `LlmAgent` `swe_coder` with the 9 tools + `agent_tool` → `sub_agents/code_analyzer.yaml` (`skip_summarization: true`); `eval_config.yaml`; `configs/sampling.yaml`; `prompts/system.md`, `prompts/analyzer.md`; `adapters/main_lora/`, `adapters/tool_lora/` referenced by `adapter:` on coder / analyzer respectively ("multi-agent delegation, multi-LoRA routing"); `skills/<name>/SKILL.md`. Official sample scores ≈ **0.01** [EMILIO-PB §10.7]; the sample itself was broken for a while and later fixed [K-DISC 743213/743508]. [K-DATA], [HARNESS-MIRROR], [LOGOS]

### 2.6 Harness→agent protocol, compaction, nudges [HARNESS-MIRROR], [HAPPY], [G4KIT], [CONT]
- Session state: `problem_description` always set; `hints` only when non-empty (injected as a separate message, not a template var [ROOTFIX]); app `swegemma_eval`, user `eval_user`.
- Initial user prompt sections, in order: task header + problem statement; hints; budget lines; execution rules (300 s cmd timeout, 5,000-char output, 150 lines / 10,000 chars per `read_file`, offline); standard instructions 0–5; code-intelligence paragraph (conditional); `find . -maxdepth 3` tree capped at 150 lines.
- **Termination:** loop exits once `submit_patch()` has been called **and** the turn ends with a final text response. "The session ends on a text-only reply after submitting" [MAUK].
- **Continue / nudge messages (`max_nudges = 3`, consecutive, reset by any tool call):**
  1. Unclosed `<|tool_call>` tag (hit token limit mid-call): asks to emit the next tool call immediately and split large edits.
  2. finish_reason `MAX_TOKENS`/`LENGTH`: asks for shorter reasoning and an immediate tool call, or `submit_patch` if done.
  3. Normal stop without `submit_patch`: *"Please continue your work using the available tools, or call submit_patch when you have completed and verified your changes."*
  Three consecutive nudges end the session; only edits already on disk count (via fallback capture) [G4KIT]. Malformed calls embedded in prose stay in content and trigger nudge type 2 [G4KIT]. Which agent receives the continue message in multi-agent trees is exactly what [CONT] tests (30 routing cases; under `AgentTool` root the parent receives it, under `SequentialAgent` behaviour differs — see repo).
- **Compaction:** `EventsCompactionConfig(compaction_interval=5 [HARNESS-MIRROR] / 15 [hosts' notebook & HAPPY], overlap_size=2, token_threshold=14,336, event_retention_size=5)`; summary keeps only text parts [G4KIT]; sub-agent sessions never compacted. **CONFLICT on whether it ever fires inside a task:** [HAPPY] and [MAUK]: "ADK compaction runs only between invocations, not within a task — trajectories die at 32k after ~20 full-size tool outputs"; [G4KIT] and [EMILIO-PB]: "main session compacts at 14,336 via ADK" and `swegemma eval` CLI leaves compaction **off** by default while the scorer path applies it. Organizer answer to "14,336 or 32,768?" was "I'll look into it" [K-DISC 744692]. **MUST-VERIFY** by reading `agent_runner.py` and the Kaggle scoring notebook; design for the pessimistic case (no in-task compaction, 32k hard wall) while keeping prompts small enough for a 14k effective window.
- Context caching: `ContextCacheConfig(min_tokens=2,048, ttl_seconds=1,800, cache_intervals=10)`.
- Retries: `ModelRetryPlugin` up to 5 on 429/5xx/connection/timeouts, 2.0 s initial, ×2.0, 60 s cap, ±20 % jitter.
- Tool choice `required`/named treated as `auto`; no streaming [G4KIT]. Gemma tool-call wire format `<|tool_call>call:grep{...}<tool_call|>`; kwarg-style `call:f{k="v"}` parses to `{}`; vLLM 0.19.1 `_parse_gemma4_array` hangs on 74/60,000 random arg strings [G4KIT].
- Thoughts between tool calls were dropped (vLLM ignored `reasoning_content`) — fixed in current wheelhouse, old submissions not rescored [K-DISC 744354].

### 2.7 Local CLI [HARNESS-MIRROR], [8KTA], [HAPPY]
`swegemma eval --tasks tasks.jsonl --snapshots-dir ... --submission-dir ... --results-dir ... [--sandbox docker|subprocess] [--max-tool-calls N] [--max-time-minutes M] [--max-turns T] [--verification-timeout-seconds S] [--concurrency N] [--task-id id | --task-ids ...] [--shard-index k --num-shards M] [--models-yaml path] [--skip-agent-patch] [--display auto]`. The CLI does **not** read `eval_config.yaml` — pass limits explicitly [LOGOS]. No documented `swegemma serve`; the harness starts vLLM itself (`build_cmd()` passes `--max-lora-rank 128`). Results dir: `summary.json`, `task_results.jsonl`, `patches/<id>.patch`, `test_outputs/<id>.log`, `traces/trace_<id>.json` (ATIF), `logs/<id>.log`. `--skip-agent-patch` on all 129 tasks: 19.5 min at concurrency 3; **4 tasks (3.1 %) resolve with an empty patch** ("free credit") [8KTA]. `--models-yaml` lets you route to a local Ollama/MLX proxy without touching `agent.yaml` [8KTA], [G4KIT `g4kit-proxy`].

---

## 3. Community intelligence

### 3.1 Requested repos
**rishaviitd/kaggle.gemma.coding.agent** [RISHAV] — Best reconstruction of the README (`context/harness.md`, `context/data.md`). Local pipeline `task_pipeline.py` (defaults 25 calls / 10 min / 4,096 out tokens), `evaluate.py` (50 calls / 30 min on `fastapi_11194`), Langfuse trace bridge, Kaggle notebook runner on L4×4. Pitfalls: task wheels target py3.13/amd64 (host py3.12 needs `repair_task_wheels.py`); Apple Silicon runs amd64 emulation. No scores published. Its `src/agent.yaml` is not public (404).

**sweeden-ttu/developer-agent** — **inaccessible (404)**. Search snippets: notes repo with sections on evaluation/timeline/prizes/data/model selection; restates "agents can only request tools supplied by the harness or custom subagents; no path traversal outside the submission root". Sister repo `sweeden-ttu/agentic_verification` has a "Claude multi-agent improvement loop for the Gemma 4 LoRA training notebook". No scores.

**emiliodavola/kaggle-gemma-agent** [EMILIO-PB] — Most complete forum digest (§1.2–1.4 above). Submission contract (`pack --check` 6/6): declarative YAML only; **12 skills**; single base model; eval_config within 100 calls / 60 min / 500 turns; no network/pip/MCP/subprocess strings; <3 GiB. Host trial run_03 (46–48 `rich` tasks, 60 min/100 calls): prompt v2 0.714 vs v3 0.438 (confounded); ≤0.542 real; 47 % of failures were process failures (6 × 60-min timeouts, 2 × 100-call exhaustions, 1 no-submit); **tool calls 35–58 s each; time is the bottleneck**; 26/46 patches had scratch files. Leaderboard signals: sample 0.01, "minimum" 0.08–0.12, public ceiling ~0.15 (early Oct).

**happyc0der/gemma-swe-agent** [HAPPY] — Solo, $0 budget, 58-task public board. Kaggle history: 0.00 (sample prompt, 8 min/40 calls) → 0.06 (v4.3, 3.5 min) → **best 0.12** (v5.0n, 4.5 min, 7/58). All scored configs land 4–7/58 (mean 4.9, sd 1.0 = noise floor). Findings: temp 0.2 vs 0.7 no LB difference; low temp → verbatim retry loops (23 identical calls); thinking ON cut loops but 9/16 tasks hit timeout → net worse; **4.5 min/task averaged best**; ADK never compacts within a task → dies at 32k after ~20 tool outputs; T4 QLoRA r16 fits only 3,072-token sequences at 60 s/step → LoRA infeasible on free T4s; sandbox OOM from runaway repro scripts (cap at 4 GB like scorer); a blank score after 54 h (cause unknown). Faithful local eval (31B via llama.cpp on T4×2, 12 tok/s): v5.0n 13/33; 33-task gold-patch check 33/33 pass, empty 0/33.

**damsolanke/gemma4-swe-kit** [G4KIT] — Scorer emulator (`g4kit-proxy`, `g4kit-harness`, `g4kit-scorer-time`, replay/sign tests, OpenHands-trajectory distillation tools, MLX/TPU LoRA trainers). Key measurements: per-call cost 0.6 s + tokens/25.5; thinking budget 256 vs off: 7/12 vs **9/12**, 4.7 vs 4.0 min/task; 3 of 5 losses were sub-agent context overflows; patch loss ~1/12; 31 % of replayed samples malformed when prompts show shell commands as tool names vs 5 % when phrased as prose bound to `run_command`; failed `edit_file` on old harness 22 % double-encoded; re-inserting empty thought blocks +40 % throughput but changed loop behaviour; curated 1,427/3,567 OpenHands trajectories; TPU v5e-8 LoRA 2.0 s per 12k-token window (r16, layers 30–59); adapter logit canary shifted top-5 logprobs ≤3.15 nats with same top-1.

**sagarml4949/gemma4-swe-agent** [SAGAR] — Data pipeline only: mined 1,522 instances from the 4 public repos (rich 475, httpx 425, requests 316, fastapi 306), 2,866 SFT rows, two adapters planned (`tool_lora` localisation, `main_lora` edits); verification output idealised ("Tests passed."); reward not executed; 24 instances (1.6 %) are renames/deletes the tools can't express. No agent scores.

**tamasmakos/swe-bench-press** — **inaccessible (404)**. PR titles via search: "Round two: ADK experiment harness on swegemma and Kaggle 4x L4" (candidates = declarative ADK submissions built from a prompt/agent/skill library, paired test fixed before first run), "context capped at 32,768 tokens as on Kaggle", "Use Kaggle's sampling defaults on OpenRouter", "Skill integration: codegraph and procedure skills"; round one gold run: **113/129 public tasks usable**; baseline arm's 4 graph-tool calls all returned 0 results; `get_code_neighbors` needs fully-qualified dotted names. No final scores retrievable.

**HyunsikParker/continuation-suite** [CONT] — CPU-only test suite for what the "continue" message does in multi-agent trees (stub model, 61 oracles pass; 30 ADK cases ≈6 s each). Documents the Oct 8 wheelhouse behaviour change (undeclared/failed tool call no longer ends the run) and Oct 12 (swegemma 0.2.11: LoRA discovery + separate verification timeout). Notebook survey of 154 public notebooks (Oct 11): 98 write an agent config; **36 declare an AgentTool, 33 of them keep `skip_summarization: true`**; 3 use Sequential/Loop root; 4 set `include_contents: none`. 140 real-model (12B) first-action generations: zero undeclared-tool calls.

### 3.2 Other repos / notebooks / threads found
- **Kaggle notebook "[0.10]: Gemma 4 Developer Agent Submission" (nihilisticneuralnet)** https://www.kaggle.com/code/nihilisticneuralnet/0-10-gemma-4-developer-agent-submission — body not retrievable (JS); listing shows public 0.08, best 0.10 (V2). **UNVERIFIED** config.
- **"GEMMA: EDA, Baseline for a start | LB TOP 1" (romanrozen)** https://www.kaggle.com/code/romanrozen/gemma-eda-baseline-for-a-start-lb-top-1 — best 0.12 (V1). Package per [LOGOS]: coder `swe_coder` (6 tools + `code_analyzer` AgentTool) + analyzer (run/read + 3 graph tools), T=0.2, top_p 0.95, top_k 40, max_output 8,192, thinking_budget 4,096, `include_thoughts:false` (→ thinking off), no eval_config, no LoRA, analyzer report ≤250 words/6 fields. A reproduction by [LOGOS] was pending; another replicator got 0.08.
- **"Gemma 4 Baseline | LB 0.24"** notebook (listing shows 0.18) and "budget-fit v1" (0.15) — titles only via search; **UNVERIFIED**.
- **"Black Cat"** package (author-labelled 0.10): anchor = 9 tools + analyzer (4 tools), 5 min/40 calls/100 turns/120 s; challenger 8 min/100 calls/150 turns/300 s, max_output 8,192 [LOGOS].
- **Leaderboard**: Kaggle LB snippet (date unknown, ≥Oct 2) **top 0.24 (Yurnero, Yike Xu), big cluster at 0.22**; a 2026-10-02 snapshot: top 0.24, many at 0.15; CLIST mirror stale at 0.15. ⇒ 0.24 ≈ 14/58.
- **LogosTopos** [LOGOS] — reverse-engineering notes (line refs into swegemma 0.2.7 / adk_submission 0.2.11 / google-adk 1.36.1); scores v2 0.05, v4 0.06; withdrew earlier claims ("can't submit Python", "eval_config has no effect", "graphs empty"). Organizer statements with IDs (see §1).
- **usp787/Gemma4_paper_track** [USP787] — most rigorous local numbers (70 public tasks, scorer-like stack): thinking-off 19–24/70, thinking-on 25–28/70; **thinking on vs off = 7/58 vs 3/58 on Kaggle**; repeated calls 9 % vs 50 %, malformed 2.2 % vs 24 %; tool-argument rules cut malformed from 21 % → 1.4 %; run-to-run noise ±2.2 tasks (16 always / 40 never / 14 flip); **same zip 25/70 local vs 7/58 hidden**; RFT r64 adapter *hurt* (8/70 vs 23/70); gold patches pass 111/129, 109 tasks sound; context overflow kills 3–4/70 per run. Graph/embedding quality analysis in §4.
- **yosh95/g4-developer-agent-paper** [YOSH] — "spin" (identical-call chains) in 20/55 tasks, longest 74 calls, up to 34.6 % of calls; single agent 12/18 vs delegated 6/18 (p=0.07); doubling budget (5→10 min, 100→200 calls) did not help (11/11/11); failing tasks take median 151 s vs 49 s and 81 % of total time; **local 34.5 % → hidden 6.9 % (~1/5 transfer), "matching an independent team"**.
- **Gosling-dude** [GOSLING] — never ran real model; useful pitfalls (`timeout_seconds` also capped grading pre-0.2.11; `KeyError` on stray `{placeholder}`; skill `name` = dir name; sub-agent skill paths rejected; full-suite pytest eats budget); eval_config 5.0 min / 60 calls / 80 turns / 300 s → 10.9 h worst case for 125 tasks.
- **Maukthik/gemma4** [MAUK] — 4.5 min / 40 calls / 80 turns; "prompt tweaks plateau ~0.10"; default LoRA r8 attention-only, r32 all-layer "reported unstable on W4A16"; `write_file("/tmp/x")` lands in `/workspace/tmp/x`.
- **8kta/kaggle-gemma4** [8KTA] — comparison cohort (19 tasks): v1 2/19; navigator sub-agent 2/19 (invoked once in 19 tasks); **filesystem-only (graph tools removed) 3/19**; `max_output_tokens` 16,384 → `ContextWindowExceededError` (use 8,192 or less); mechanical pre-call checks forbid bare `pytest tests/` and repeated identical calls; QLoRA base must be `gemma-4-31b-it-qat-q4_0-unquantized` to avoid base-weight mismatch; bf16 fails on T4.
- **HindsightWise** [HIND] — public set split fastapi 67 / rich 48 / requests 13 / httpx 1; 0-byte hard-linked graph/embedding files in some downloads (~50 %); no `async def` nodes; py3.13 removed `imp`/`telnetlib` (shims shipped); double-JSON escaping (pre-09-30); LoRA KV starvation; overflow bypasses fallback → always `submit_patch()` right after edits.
- **Hindai PR #32** [HINDAI-PR] — "Notebook Threw Exception" root causes: `.sh` files, skill tool names under `tools:`, analyzer not wired as `agent_tool`, missing thinking config; eval_config 4.5 min / 40 calls / 60 turns / 180 s.
- **ns-0437** [NS0437] — v1–v3 all 0.06; a thinking-ON v4 "runtime exceeded; no score" while CLI showed COMPLETE; "COMPLETE ≠ scored".
- **harshithKumar12/root-fix** [ROOTFIX] — clean example of root `agent.yaml` (coder + `code_explorer` AgentTool `skip_summarization:true`, `include_contents: none` on explorer, 3 skills); notes `!include` blocks `..`; `max_output_tokens: 16384` "half the window" (risky).
- **satiricalguru/Gemma-graph-nav** [GRAPHNAV] — localisation study (122 tasks): BM25 R@5 .280; PageRank+BM25 .293; 31B navigating with official tools .402 (7.8 calls); Agentless-style 31B .444 (2.0 calls); **65/129 issues mention no identifier matching any graph node**; 31B hit the 8-call cap on half the tasks.
- **bbkdevops HF** — 23 KB skill-only package, greedy T=0, thinking 8,192, max_out 16,384; no scores.
- **Broken public tasks** [K-DISC 743973, 742882] — wheelhouse lacks `typing_inspection`, `inline_snapshot`, `dirty_equals`, `ujson/orjson`, `python-multipart`, `pytest-httpbin`; py3.13 `VERIFY_X509_STRICT` breaks ~8 `requests` https tests; some version-gated skips ⇒ public pass-rate not comparable to scorer; gold patches pass only 111/129 [USP787] / 113/129 [tamasmakos].
- **Other discussion IDs with official replies** (bodies unseen): 744354 thoughts dropped (fixed), 744331 LoRA KV (dynamic sizing), 744692 compaction (looking into it), 744794 bug status summary, 743063 budgets, 743213/743508 adapters & sample, 744272 double JSON, 745028 undeclared tool, 744807 Sep-30 GPU outage, 742882 local eval deps, 742911 empty graphs (partial), 742807 distillation (Ashley Oldacre). No official reply: 743973, 743186 (infra for SFT/RL), 745059 (`include_thoughts`), 745774 (repeat loops), 745796 (domain shift).

---

## 4. Training-set facts and generalisation [DATA-MIRROR], [K-DATA], [USP787], [HIND]
- **129 public tasks** in `tasks.jsonl` from `fastapi/fastapi` (67), `Textualize/rich` (48), `psf/requests` (13), `encode/httpx` (1). Fields: `instance_id` (`<repo_short>_<num>`), `repo`, `base_commit` (40-hex), `problem_statement`, `hints_text` (optional), `patch` (gold; absent in hidden set), `test_patch` (hidden at scoring), `created_at`.
- `snapshots/<instance_id>.tgz`: full git repo frozen at `base_commit`, forward history stripped (git log/diff work).
- `graphs/`: 256 NetworkX node-link JSON files (129 task-named hard-linked to 127 commit-named), `directed: true, multigraph: true`; nodes `{id (FQN e.g. fastapi.routing._prepare_response_content), name, text (full source)}`; edges `{source, target, type, key}`; **only edge type released is `calls`**; no `async def` nodes (0/305 in gold-touched files), no module-level nodes; released graphs capture only 14–21 % of runtime call pairs (2 % for httpx) vs 62–69 % for an AST rebuild [USP787].
- `embeddings/`: 256 `.npz` (same hard-link scheme), one **256-dim float32** vector per node id; model undisclosed; collapsed (random-pair cosine 0.78–0.90; 8–19 % of pairs ≥0.99); gold file in top-10 for 35/129 tasks vs 67 for grep; TF-IDF beats them (52 % vs 9 %) [USP787].
- `wheels/` 124 offline wheels at `/wheels`; `docker/` (`Dockerfile.sandbox` py3.13, `Dockerfile.public`, `imp.py`/`telnetlib.py` shims); `sandbox/setup.py`; `sample_submission/`; `HARNESS_README.md`; wheelhouse dataset separate (~827 MB). Total dataset ≈ 21 GB [8KTA] (snapshots 20 GB+).
- **Hidden set:** "~120 tasks, evenly divided between public and private splits, curated from a set of private repositories" with the same graph pipeline and fail-to-pass / pass-to-pass verification plus a "near completion" frontier-model check [K-DATA], [USP787]. Host statement: **no private-repo task touches an async function; ≤1.8 % of private-repo functions are async**, so graphs will not be regenerated [USP787]. **CONFLICT:** [GeorgeRCAdamJohnson] says "129 hidden tasks" (likely confusion with public count).
- **Generalisation implications:** (1) hidden repos are unknown Python projects → anything tuned to fastapi/rich/requests/httpx (skills named `fastapi-nav`, memorised module layouts, repo-specific heuristics) is wasted or harmful; organizers and [MAUK] both warn against overfitting. (2) Measured transfer ratio local→hidden ≈ **1/3.5 to 1/5** (25/70→7/58 [USP787]; 34.5 %→6.9 % [YOSH]), partly because the 31B has likely seen the public repos (no-retrieval localisation score 0.357 [GRAPHNAV]) and partly because public tasks are broken/easier. (3) Public-set noise is ±2–3 tasks per run; the public LB moves in 1/58 steps with sd ≈1 task → single submissions cannot distinguish configs; only paired, multi-seed local evals can. (4) Half of public issues mention no graph symbol → grep/BM25 localisation must be first-class; graph tools are a secondary aid. (5) Private repos may have different test layouts (not `tests/`), different build backends, and may lack the py3.13-shim pain — but the wheelhouse/dep-missing problem may also exist there (unknowable).

---

## 5. Implications for architecture

### 5.1 Hard constraints the design must satisfy
1. **Model:** `gemma-4-31b-it-qat-w4a16-ct` for every agent; behaviour change only via prompts, YAML structure, skills (Python scripts in sandbox), and ≤8 PEFT LoRA adapters (rank ≤128, total <3 GiB, `.safetensors` only). No callbacks, no custom tool registration, no Python entry point.
2. **Budget arithmetic:** 12 h hard for ~120 sequential tasks incl. setup ⇒ per-task `max_time_minutes` must be set in `eval_config.yaml`; community consensus **4.5–5.0 min** (yields 9–10.9 h worst case). Must also set `max_tool_calls` (40–60), `max_turns` (60–80) and `timeout_seconds` (≥180; note pre-0.2.11 it also capped grading). Failure tasks dominate time (81 %) → an explicit early-stop/submit-best-so-far rule is mandatory.
3. **Context:** 32,768 hard; plan for **≤14k effective** and assume no in-task compaction. `max_output_tokens` ≤ 8,192 (16,384 default overflows). Keep system prompt + tree + issue under ~4k; cap tool outputs (they are already 5k chars / 150 lines); avoid `search_similar_code` on big nodes; sub-agents get fresh 32k windows but are never compacted and share the call/turn budget.
4. **Thinking:** `include_thoughts:false` disables thinking entirely. Evidence is split: thinking ON helped [USP787] (7/58 vs 3/58; fewer loops/malformed calls) but costs 65–71 % of time and caused timeouts for [HAPPY]/[G4KIT]. If ON, use a small `thinking_budget` (256–2,048) and a tight time cap; measure.
5. **Tool declaration hygiene:** declare only the 9 registry names + `agent_tool`; never list skill tools under `tools:`; only `{problem_description}`/`{hints?}` placeholders in instructions; skills via `skills:` with `SKILL.md` name == dir name; no `..` in includes; only allowed extensions; no `.gitkeep`.
6. **Patch hygiene:** `submit_patch()` immediately after every meaningful edit (overflow/exception insurance); scratch files via `run_command` in real `/tmp` (never `write_file` to `/tmp`); never touch tests, `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini` (reset anyway); end with a text-only reply after `submit_patch` so the loop terminates instead of burning nudges.
7. **Loop/malformed-call defences:** the dominant failure is identical-call spin and malformed `<|tool_call>` syntax. Prompt rules (never repeat an identical call; never resend a malformed call; tool calls only in the tool channel; arguments as JSON not kwargs; shell commands only inside `run_command`) measurably cut malformed calls 21 %→1.4 %.
8. **Offline sandbox:** 4 GiB / 2 vCPU / no network; runaway repro scripts can OOM (exit 137); 300 s per command; avoid full-suite pytest.
9. **Localisation must not depend on graph tools:** half the issues have no graph-resolvable symbol; embeddings are weak; `search_similar_code` needs node ids. grep/`git grep`/BM25 skill first; graph tools only with a known FQN.
10. **Single-model LoRA realities:** adapters cost KV cache and 8–21 % decode speed; must be trained against the QAT base (`...-q4_0-unquantized` for QLoRA) and validated through the patched wheelhouse vLLM with a logit canary; a poorly trained adapter *reduced* resolution (8/70 vs 23/70). Ship an adapter only if it beats the best prompt-only config in a paired eval.
11. **Legal/cadence:** 1 submission/day (and multi-day queues) ⇒ at most ~45 more LB probes before Dec 2; team ≤5; winners must open-source code + training pipeline under OSI licence; no redistribution of competition data; distillation allowed subject to source-model licence.

### 5.2 Open questions to verify by reading the real HARNESS_README / wheelhouse source
1. Exact current wheelhouse versions on the scorer (swegemma ≥0.2.11? adk_submission 0.2.13?) and whether the Oct 8/12 fixes (undeclared-tool tolerance, exception-safe working-tree fallback, separate verification timeout, LoRA discovery) are live.
2. Does ADK compaction (`token_threshold=14,336`) ever run **within** a task on the scorer path, and is `compaction_interval` 5 or 15? What does the compacted summary contain (text only?) and does it preserve the issue statement?
3. Precise nudge texts and whether a `skip_summarization: true` AgentTool return counts as "turn ended without tool call" (nudge counter) — i.e., how many wasted nudges a sub-agent call costs.
4. Full `SkillToolset` surface: names/signatures of `list_skills`, `load_skill`, `load_skill_resource`, `run_skill_script`; whether skill script invocations count toward `max_tool_calls`; argument types (`file_path` str vs list); whether `scripts/` can import sibling modules and stdlib only; `references/` vs `resources/`; whether sub-agents may declare `skills:`.
5. Does `submit_patch()` overwrite on repeat calls, and is the final scored patch the last submitted one or the teardown working-tree diff if later edits occurred?
6. Exactly when `NO_PATCH` is emitted vs an empty diff; whether a task that errors (timeout/exception) still gets its working-tree diff captured.
7. Whether the 12 h clock includes container setup/warm-up and vLLM start (organizer said setup is included; README says agent timer starts after setup — these may both be true at different levels).
8. `max_turns` semantics (LLM invocations incl. sub-agents? nudges?) and whether `LoopAgent`/`SequentialAgent` roots receive the continue message correctly.
9. Whether `thinking_budget` is now forwarded as `thinking_token_budget` and enforced as a hard cap on the scorer vLLM; default thinking state when `thinking_config` is omitted.
10. Whether per-agent `generate_content_config` (temperature, max_output_tokens) is honoured for sub-agents independently, and whether `seed` is now forwarded.
11. Current LoRA memory behaviour: does the scorer size `max_loras`/`max_lora_rank` from the submission (and thus does a single r16 adapter leave the full ~32k KV)? Measure KV headroom with 1 adapter at r16/r32.
12. Adapter config constraints: allowed `target_modules`, whether `lora_alpha`/`use_rslora`/DoRA are supported by the patched vLLM 0.19.1, and whether `adapter_config.json` must name the exact base model id.
13. Exact prompt skeleton the harness prepends (instructions 0–5, budget lines) so our system prompt does not duplicate or contradict it; whether `hints_text` appears in the hidden set.
14. Graph/embedding presence in hidden repos (are files >100 bytes so the code-intelligence paragraph is injected?) and edge types beyond `calls`.
15. Confirm public LB = 58 tasks and private = ~62, and whether final scoring reruns the two selected submissions on the private half or reuses the single scoring run.
