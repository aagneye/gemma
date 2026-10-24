# Official "Getting Started - Gemma 4 Developer Agent" notebook (Ryan Holbrook, v3, 2026-10-12) — scorer-equivalent config
Source: https://www.kaggle.com/code/ryanholbrook/getting-started-gemma-4-developer-agent (1488 upvotes, 15.9k views)

## Environment
- Wheelhouse dataset: /kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse (41 wheels, cu128). Python 3.12 on the host (agent/harness side); sandbox container is python 3.13.
- Model weights path: /kaggle/input/models/google/gemma-4/other/<model>/2  (Kaggle model "Gemma 4 · gemma-4 · V2", variant "other").
- Env: TRANSFORMERS_OFFLINE=1, VLLM_ENGINE_READY_TIMEOUT_S=1200, LiteLLM routing (openai/ prefix), OTEL disabled.

## Graph API (swegemma.graph)
- sg.get_graph(repo_name, graph_dir, embeddings_dir, base_commit) -> networkx graph. fastapi example: **4263 nodes, 2430 edges** (sparser than nodes! many isolated nodes; includes docs_src tutorial modules like custom_request_and_route.tutorial002_py310...).
- sg.get_neighbor(node, graph, max_neighbors) -> list of neighbor ids, printed with repo prefix "fastapi/fastapi;fastapi.exceptions.HTTPException".
- sg.get_similar_nodes(node=..., repo_name, k, graph, graph_dir, embeddings_dir, base_commit) -> [{node_name, similarity}]. **Example similarities: 1.0000, 0.9996, 0.9993, 0.9991, 0.9991 for semantically unrelated nodes (a tutorial route handler vs APIRouter.__init__ vs FastAPI.setup)** => the 256-d embeddings are highly anisotropic / near-collapsed; raw cosine has almost no discriminative power. search_similar_code(query: str) embeds a free-text query — with what encoder? (unknown offline; Ayush's runs returned EMPTY for all 21 queries). ACTION: inspect embeddings once downloaded; test mean-centering/whitening; test whether query strings must match node ids.
- sg.get_induced_subgraph(graph, nodes).

## vLLM server (adk_submission.VllmConfig) — scorer uses the same
- tool_call_parser='gemma4', reasoning_parser='gemma4', max_model_len=32768, dtype=bfloat16, gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=bool(adapters), max_loras=len(adapters), **max_lora_rank = max detected adapter rank (default 128)**, scheduler_reserve_full_isl=False, tensor_parallel_size=4 on L4x4, startup_timeout 20 min, extra_args per model (12B needs --hf-overrides Gemma4ForCausalLM/gemma4).
- Adapter names must match [A-Za-z0-9][A-Za-z0-9._-]*; registered as LiteLLM models openai/<adapter_name> via server.create_model_registry(aliases=[model], model_prefix='openai/').
- discover_declared_models(AGENT_DIR) must return exactly 1 model.

## Evaluator (swegemma.evaluate.Evaluator / EvalConfig) — defaults read from eval_config.yaml (section `evaluation:`)
- timeout_seconds (per command) default 300; verification_timeout_seconds 300; **max_tool_calls default 100; max_time_minutes default 60.0; max_turns / max_llm_calls optional**.
- sandbox='subprocess' in Kaggle notebooks (docker in scorer per HARNESS_README).
- ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10).
- **EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5)** => ADK compacts the event history (LLM-summarised) every 15 events once >14k tokens, keeping last 5 events. This is the "context compaction" that limits long trajectories; it means state must be re-derivable from the workspace (files, notes) not from chat history.
- Tool budget errors returned to the model as {'status':'error','error_type':'BudgetExceeded',...}. Time-out => "agent timed out"; if no submit_patch and no working-tree changes => NO_PATCH. Working-tree modifications are captured even without submit_patch ("completed without explicit submit_patch call and no working tree modifications").
- Trajectory shows the 12B model reasoning (💭 thought summaries) + tool calls; read_file returns {'status':'ok','filepath','content'} JSON; one 12B call ≈ 1.5–3 s on 4xL4 for short contexts, ~18 s for a 4k-char thought.
- Observed sample system prompt: "You are an expert autonomous software engineer assigned to resolve an issue in a repository efficiently and decisively." Task prompt: "You are evaluating a software engineering task for repository <repo>."

## Packaging
- validate_directory(AGENT_DIR, limits=build_submission_limits()); no symlinks; **MAX_SUBMISSION_SIZE_BYTES = 3 GiB**; ALLOWED_SUBMISSION_EXTENSIONS whitelist (yaml/md/json/safetensors/py/sh ... exact list in swegemma.config); ALLOWED_ADAPTER_EXTENSIONS.
- 3 GiB cap: a rank-128 LoRA on all linear layers of 31B is ~1–2 GB in bf16 => at most one or two big adapters for 31B; the 12B allows several.
