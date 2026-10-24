# Repository-level code retrieval, fault localization, and code-graph navigation for small LLM coding agents

Literature review for the Kaggle "Google - The Gemma 4 Developer Agent Competition". Written 2026-10-16; covers work through October 2026.

Competition setting (fixed, not ours to change): the agent gets normal file/bash tools **plus** a NetworkX AST call/dependency graph of the repo (nodes = modules/classes/functions with full source text; directed multigraph with typed edges such as `calls`), a fixed 256-d embedding per graph node, and three tools: `get_code_neighbors`, `get_code_subgraph`, `search_similar_code`. The model is Gemma 4 (4B-31B) with a limited tool-call budget, and the task is to localize and fix GitHub issues in Python repos. We cannot re-embed the hidden test repos, so the question is how to *use* a fixed function-level embedding index plus a graph well.

Method note: ~50 web searches/fetches (arXiv abstract/HTML pages, GitHub READMEs, vendor blogs). Numbers taken from a paper's own tables are cited by arXiv ID; numbers taken only from search snippets or secondary summaries are flagged **UNVERIFIED**. Where versions of a paper disagree I say so.

---

## A. Fault localization for issue resolution

### A.1 Why localization is the bottleneck

The original SWE-bench paper (Jimenez et al., arXiv:2310.06770, ICLR 2024) already established the shape of the problem. It used BM25 file retrieval because dense retrieval with very long NL queries and code keys was judged a poor fit; with a 27k-token budget BM25 returned a superset of the gold ("oracle", i.e. files touched by the reference patch) files in only ~40% of instances and *none* of them in almost half. Claude 2 dropped from 4.8% resolved (oracle files) to 1.96% (BM25), and giving BM25 a larger budget raised recall but *lowered* resolution because models could not localize inside the extra context. Two durable lessons: (i) resolution is upper-bounded by whether the edited location is in context, and (ii) more context is not free, especially for weaker models.

Agentless (Xia et al., arXiv:2407.01489, FSE 2025) made this quantitative for a modern pipeline. On SWE-bench Lite with GPT-4o its final patches hit the correct file 69.7% of the time, the correct function 52.0% and the correct line 35.3%, and the paper says these correlate heavily with solve rate (32.0% Lite, 38.8% Verified). Its localization ablation (Table 2, "contains ground truth") is the most useful public breakdown of where recall is lost:

| Stage | Method | Contains GT | Avg LoC | Avg $ |
|---|---|---|---|---|
| File | LLM on repo tree | 78.67% | 3,221 | 0.02 |
| File | Embedding only (no folder filtering) | 67.67% | 3,388 | 0.05 |
| File | Embedding + LLM-filtered folders | 70.33% | 3,622 | 0.04 |
| File | **Combined (LLM + embedding)** | **81.67%** | 3,424 | 0.06 |
| Element | Full file | 53.67% | 778 | 0.15 |
| Element | **Skeleton format** | **58.33%** | 698 | 0.02 |
| Edit loc | Greedy single sample | 50.67% | 189 | 0.06 |
| Edit loc | **4 samples merged** | **56.33%** | 342 | 0.07 |

Three take-aways for us: embedding retrieval alone is clearly worse than an LLM reading the repository tree (67.7 vs 78.7 file recall) but the union adds ~3 points; a *skeleton* (signatures + docstrings, no bodies) beats full files for picking elements while being cheaper; and merging several samples of edit locations buys ~6 points of recall. Agentless' embedding setup is text-embedding-3-small over 512-token chunks via LlamaIndex, with the LLM first naming irrelevant folders to exclude (github.com/OpenAutoCoder/Agentless).

LocAgent's Table 8 (arXiv:2503.09089) closes the loop: swapping Agentless' own localizer (function Acc@5 58.4%) for LocAgent (73.4%) raised Agentless' Pass@1 only from 26.3% to 27.9% but Pass@10 from 33.6% to 37.6%. CoSIL (arXiv:2503.22424) reports 14-30% relative resolve-rate gains on Lite and 2-12% on Verified when plugged into Agentless; OrcaLoca (arXiv:2502.00350) reports +6.33 pp (34.67% to 41.00%) with Agentless' repair stage and 40 patch samples; ToolTrain (arXiv:2508.03012) shows a 7B localizer feeding a 7B patcher resolves 14.0% vs 7.6% with Agentless localization. The pattern is consistent: better localization gives modest Pass@1 gains and larger Pass@k gains, i.e. it widens the funnel rather than fixing the editor. A cautionary 2026 placebo-controlled study (Jha, arXiv:2609.00854) found that *spectrum-based* localization + infilling lost to blind whole-solution resampling for 24-32B models on function-level benchmarks; that is a different setting (single functions with failing tests), but it is a reminder that localization is only worth its budget when the alternative (regenerate the whole thing) is not available, which is the case for repository-scale issues.

### A.2 Agentless-style hierarchical localization

Pipeline: repository tree (no code) -> LLM ranks top-N files, in parallel embedding retrieval over chunks after folder filtering, intersect/union -> skeleton of each suspicious file -> LLM selects classes/functions -> full code of those elements -> LLM emits edit locations, sampled 4x and merged. Cost per issue ~$0.70 and ~78k tokens with GPT-4o on Lite (arXiv:2407.01489). The structure is exactly what we want for a small model: every step consumes a compact representation and emits a short list.

### A.3 LocAgent (Chen et al., arXiv:2503.09089, ACL 2025) - the most directly relevant work

**Graph.** Python-only, built from the `ast` module in seconds. Nodes: directory, file, class, function (function is the finest granularity and the retrieval document). Edges: `contain` (a tree over everything), `import` (file -> class/function), `invoke` (function/class -> function/class; instantiating a class counts), `inherit` (class -> class). This is essentially the competition graph schema.

**Index.** A four-level sparse hierarchical index consulted top-down: (1) fully-qualified entity IDs like `src/utils.py:MathUtils.calculate_sum`; (2) short-name -> all matching nodes; (3) BM25 over entity IDs for fuzzy keyword matches; (4) inverted index from code chunks to entities (catches global variables). No dense embeddings at all.

**Tools (three, all read-only).**
- `SearchEntity(keywords)` returns matches at three detail levels: full code when <=3 hits, a module skeleton "preview" for large files, and IDs only ("fold") when >3 hits.
- `TraverseGraph(start_ids, direction, hops, entity_types, relation_types)` runs a type-aware BFS and returns the subgraph as an indented tree with full IDs and explicit (including reversed) relation labels.
- `RetrieveEntity(ids)` returns file, line range and code.

**Results (SWE-bench Lite, 274 instances).** File Acc@5 / Module Acc@10 / Function Acc@10: Claude-3.5 94.2 / 87.6 / 77.4; fine-tuned Qwen2.5-Coder-32B 92.7 / 87.2 / 77.0; fine-tuned Qwen2.5-Coder-7B 88.3 / 82.9 / 71.5; Agentless (Claude-3.5) 79.6 / 69.0 / 58.8; CodeRankEmbed embedding retrieval 84.7 / 78.8 / 58.8; BM25 61.7 / 52.9 / 36.9. The fine-tuned 32B essentially matches Claude-3.5 and the fine-tuned **7B closes roughly 80% of the gap** between raw retrieval and the frontier model at function level. Cost: $0.66/instance (Claude, 7 rounds), $0.09 (32B, 9 rounds), $0.05 (7B, 6 rounds). On the harder, less lexically-hinted Loc-Bench (560 issues created after Oct 2024: 242 bugs, 150 features, 29 security, 139 performance), the 7B still reached file Acc@5 78.6 and function Acc@10 51.4 vs 59.3 for Claude-3.5.

**Ablation (7B, file Acc@5 / module Acc@10 / function Acc@10).** Full 88.3/82.9/71.5; without `TraverseGraph` 86.1/78.5/66.1; only `contain` edges 86.5/79.6/66.4; hops fixed to 1 86.9/80.3/66.8; without `RetrieveEntity` 87.6/81.4/69.3; **without `SearchEntity` 69.0/61.3/53.3**; without BM25 index 75.2/69.0/60.2. Translation: keyword/entity search is the load-bearing tool; graph traversal adds ~5 points at function level; being able to traverse >1 hop and over non-containment edges matters.

**Output format.** On 37 hard instances, the indented tree format beat JSON, row/edge lists, "incident" lists and Graphviz DOT; JSON and tree were the two best.

**Training.** 433 successful Claude-3.5 trajectories on SWE-bench-train, filtered to correct localization, then 335 self-sampled trajectories from the first fine-tuned 32B; LoRA, 5 epochs, lr 2e-4, 128k context. (Appendix C says 768 total, 447 from Claude; the two counts disagree.) The 7B was distilled from the combined set. Two runs are made and merged by mean reciprocal rank.

### A.4 OrcaLoca (Yu et al., arXiv:2502.00350, ICML 2025)

AutoCodeRover-style search API (`search_file_contents` returning a skeleton for files >200 lines, `search_class`, `search_method_in_class`, `search_callable`, `search_source_code`, each with optional `file_path`) wrapped in three controls: (1) a heap-based **action scheduler** (new actions priority 1, decomposed sub-actions priority 2, repeats bump priority, UID de-duplication); (2) **action decomposition with relevance scoring** - when a search hits a class or large file a sub-agent scores its members and the top k (3 for classes, 2 for files) become new actions; (3) **distance-aware context pruning** - every search result is scored by average shortest-path distance (min of forward and reverse) in a code graph with containment and call edges to the current suspected locations, and only the top 12 context entries are kept, re-evaluated each step. Claude-3.5-Sonnet, temperature 0.1. SWE-bench Lite: 65.33% function match, 83.33% file match vs OpenHands 63.67/81.67, Moatless 59.33/79.33, Agentless-1.5 58.67/78.67. Search cost ~$0.87/instance. Ablation on 93 "common" instances: full 76.3% function match; no scheduling 73.1; no decomposition 72.0; no pruning 72.0. The distance-based pruning is directly reproducible with the competition's NetworkX graph.

### A.5 CoSIL (Jiang et al., arXiv:2503.22424; ASE 2025)

Training-free. Phase 1 (file level): LLM preselects files from the issue, then gets the repo tree + a *module call graph* built on demand from the preselected files' imports and reranks. Phase 2 (function level): an iterative search agent (tools: class lookup, class-method lookup, static-function lookup, exit) walks a *function call graph* expanded one hop at a time around accepted nodes; a **pruner** LLM call decides per node whether it is relevant (accepted -> neighbors become visible, rejected -> branch cut). Max 10 iterations. A "reflective alignment" call re-formats the final answer to avoid malformed paths. With Qwen2.5-Coder-32B on Lite: file Top-1/3/5 = 0.613/0.780/0.837, function 0.433/0.547/0.580 vs Agentless-FL 0.583/0.730/0.773 and 0.247/0.397/0.427; on Verified function Top-5 0.650 vs 0.484. Cost ~$0.02/instance on DeepSeek-v3 (~70k tokens), ~$0.32-0.34 on GPT-4o. Relevant insight: the accept/reject pruner is a cheap binary judgement a small model can make, and the frontier of visible nodes grows only along accepted paths - a budgeted beam search over the call graph.

### A.6 Other localizers worth knowing

- **SWE-Search** (Antoniades et al., arXiv:2410.20285, ICLR 2025) applies MCTS with an LLM value function over Moatless Tools actions (which themselves include semantic search + identifier search); it reports a 23% relative gain across five models but does not isolate localization. Too expensive for our budget except as inspiration for value-guided backtracking.
- **SweRank / SweRank+** (Salesforce, arXiv:2505.07849, arXiv:2512.20482): retrieve-and-rerank with a bi-encoder (SweRankEmbed 0.1B/7B) and a listwise LLM reranker (SweRankLLM, Qwen2.5-Coder-7B-based), trained on SweLoc mined from PRs. Authors state the 7B retriever alone beats LocAgent+Claude-3.5 on function localization; a secondary source gives file Acc@1 83.2% on Lite (**UNVERIFIED**). SweRank+ tables place CodeRankEmbed at 51.8 Acc@5 / 58.8 Acc@10 function level, consistent with LocAgent's numbers.
- **KGCompass** (arXiv:2503.21710): knowledge graph linking issues/PRs to files/classes/functions, narrows to 20 candidate functions and feeds "entity paths" to the repairer; v2 reports 56.0% function-level localization and 58.3% resolved on Lite, and that 89.7% of the bugs it localizes have no explicit location hint (v1 said 69.7% needed multi-hop traversal). Version numbers differ; treat as approximate.
- **GraphLocator** (ByteDance, arXiv:2512.22469, FSE 2026): decomposes an issue into a graph of sub-issues to handle symptom-to-cause distance and one-to-many issues; +19.5% function recall / +11.9% precision on average over Agentless and CoSIL across Lite, LocBench, Multi-SWE-bench Java (relative vs absolute **UNVERIFIED**).
- **SHERLOC** (NVIDIA/TU Darmstadt, arXiv:2606.24820, EMNLP 2026): training-free, ~30B reasoning model + four "LLM-friendly" repository tools + self-recovery; 84.33% Acc@1 on Lite and 81.27% Recall@1 on Verified, +5.95 pp resolve when its diagnosis is fed to repair agents while cutting localization tokens 36.7%. Its thesis - judge localization by *diagnostic actionability* (correct file + wrong diagnosis still misleads) - argues for emitting a short causal hypothesis alongside the location.
- **RepoMem** (arXiv:2510.01003): LocAgent + commit-history memory, 76.5% Acc@5 on Verified (+4.9 over LocAgent); irrelevant for us if the sandbox lacks git history, but it indicates how much lexical/temporal priors help.
- **RPG-Encoder** (Microsoft, arXiv:2602.02084): a learned "repository planning graph" representation; claims 93.7% function Acc@5 on Verified with Claude-4.5-Sonnet, +14.4 over the best baseline. Impressive but requires its own encoder/representation - out of scope for a fixed index.
- **Execution-guided**: IssueExec (arXiv:2607.17286) retrieves candidate tests and uses runtime traces to rank locations, raising Agentless from 96 to 113 resolved on Lite; XAgent (arXiv:2609.09769) diffs failing/passing runs for 72.8% function localization and 62.0% resolve on Lite at ~$1.56/issue. If our sandbox can run tests, call-chain tracing from a failing test is one of the cheapest high-precision seeds available.
- **Neurosymbolic / LogicLoc** (arXiv:2604.16021) warns that SWE-bench-style issues are full of "keyword shortcuts" (file paths, function names); on 25 hint-free logical queries all baselines fall to 0% perfect function match. Practical reading: exploit the shortcuts when present (grep the identifiers in the issue), and only spend graph/embedding budget when they are absent.
- **Cost-Effective Repository Exploration** (arXiv:2608.29675, AgenticDev '26): swapping the explorer model while keeping the interface fixed, cheaper explorers retain 78-94% of reference Hit@3 while cutting tokens 84-95% - evidence that a small model can do the exploration if the interface is good.

### A.7 BM25 vs embedding vs agentic retrieval (summary of ablations)

| Method (SWE-bench Lite, function level unless noted) | Acc@5 | Acc@10 | Source |
|---|---|---|---|
| BM25 over functions | 31.8 | 36.9 | LocAgent Tab.4 |
| CodeRankEmbed (137M dense) | 51.8 | 58.8 | LocAgent Tab.4; SweRank+ |
| Agentless (Claude-3.5) | 58.8 | 58.8 | LocAgent Tab.4 |
| LocAgent 7B fine-tuned | 64.2 | 71.5 | LocAgent Tab.4 |
| LocAgent Claude-3.5 | 73.4 | 77.4 | LocAgent Tab.4 |
| ToolTrain-7B (Recall@5) | 62.4 | - | arXiv:2508.03012 Tab.2 |
| ToolTrain-32B (Recall@5) | 68.6 | - | arXiv:2508.03012 Tab.2 |

Dense function-level retrieval alone lands around 50-60 Acc@5-10, agentic graph search with a tuned 7B around 62-72, frontier agents 73-77. Practical Code RAG at Scale (JetBrains, arXiv:2510.20609) adds that for *code-to-code* queries BM25 with word splitting is both best and ~100x faster than dense encoders, while for *NL-to-code* dense proprietary encoders win; and that 32-64 line chunks beat whole files at small budgets while syntax-aware chunking is no better than line chunking. CORE-Bench (arXiv:2606.11864, EMNLP 2026) and Agent Retrieval Bench (arXiv:2607.24882) both report a sharp drop for embedding models from docstring-to-function search to issue-to-edit retrieval, with Qwen3-Embedding-4B/8B and Aider-style RepoMap each winning different sub-tasks and agents never touching any gold file in 27-35% of logged trajectories.

---

## B. Code graphs for LLMs

| System | Graph schema | Exposure | Reported gain | Cost notes |
|---|---|---|---|---|
| **RepoGraph** (Ouyang et al., arXiv:2410.14684, ICLR 2025) | tree-sitter; *line-level* def/ref nodes; `contain` + `invoke` edges; built-ins and third-party names filtered; avg 1,419 nodes / 26,392 edges | Agentless/RAG: flattened k-hop ego-graph stuffed into localization and repair prompts; SWE-agent/AutoCodeRover: new `search_repograph` action | Lite resolve: Agentless 27.33->29.67, AutoCodeRover 19.0->21.33, SWE-agent 18.33->20.33, RAG 2.67->5.33 (avg +32.8% relative); file/function/line localization for Agentless 68.7/51.0/34.3 -> 74.3/54.0/36.7 | k=1 flattened ~2.3k tokens (29.67%); k=2 flattened 10.5k tokens and *worse than baseline* (26.0%); LLM-summarized k=2 1.2k tokens (28.67%). Cost rose slightly in all four systems |
| **CodexGraph** (Liu et al., arXiv:2408.03910, NAACL 2025) | Neo4j; nodes MODULE/CLASS/METHOD/FUNCTION/FIELD/GLOBAL_VARIABLE; edges CONTAINS/HAS_METHOD/HAS_FIELD/INHERITS/USES; bodies stored as file indexes | Agent writes NL information needs; a second LLM translates to Cypher; iterative | GPT-4o: 22.96% Lite (ties AutoCodeRover), EvoCodeBench 36.0 vs 28.8, CrossCodeEval EM 27.9 vs 21.2 | 102k tokens/instance on Lite vs 76k; **weaker models collapse**: Qwen2-72B 1.95% vs AutoCodeRover 9.34%; removing the translator drops CCE EM 27.9->8.3. Lesson: never make a small model write graph queries |
| **LocAgent** (above) | file/class/function; contain/import/invoke/inherit | three tools, tree-formatted subgraphs | see A.3 | $0.05-0.09 with 7B/32B |
| **ARISE** (UBC, arXiv:2605.03117) | multi-granularity down to statements with intra-procedural def-use edges | three-tier tool API incl. data-flow slicing as a primitive | Qwen2.5-Coder-32B on Lite: +17.0 function Recall@1, +15.0 line Recall@1, Pass@1 17.3->22.0 vs SWE-agent | ablations attribute gains to the data-flow graph, not the tool schema |
| **DualView** (arXiv:2607.01929) / **RepoAtlas** (arXiv:2609.16936) | module-coupling, call, class-hierarchy, PDG views; rendered as images + text | queryable interface returning picture + text | gains on SWE-bench Pro/Verified across agents (numbers **UNVERIFIED**) | needs a vision model; Gemma 4 is multimodal so this is a possible stretch goal |
| **GraphCoder** (arXiv:2406.07003, ASE 2024) | statement-level code context graph (control flow + data/control deps) | coarse-to-fine retrieval for completion, result stuffed in prompt | +6.06 code match / +6.23 identifier match over RAG baselines | completion-only |
| **CoCoMIC** (arXiv:2212.10007) | cross-file context graph fused via joint attention | model-internal (requires training) | n/a | not usable with a frozen model |
| **RepoHyper** (arXiv:2403.06095) | repo semantic graph; search-expand-refine with link prediction | retrieval for completion | author-claimed SOTA on completion | needs a trained link predictor |
| **RepoFuse** (arXiv:2402.14323) | "analogy" + "rationale" (dependency) contexts, rank-truncated | prompt | completion accuracy at bounded prompt size | the rank-truncation idea transfers |
| **CodeRAG** (Li et al., arXiv:2504.10046) | requirement graph + DS-code graph bigraph | agentic retrieval | +40.9 Pass@1 (GPT-4o) on DevEval vs no RAG | generation, not repair |
| **GRACE** (arXiv:2509.05980) | unified file/AST/call/class/data-flow graph; structural + semantic retrieval + graph-aware reranker | prompt with cross-graph edges | +8.19 EM / +7.51 ES over graph-RAG baselines (DeepSeek-V3) | completion |
| **HCGS / Code-Craft** (Cisco, arXiv:2504.08975) | bottom-up LLM summaries over a code graph | retrieval over summaries | up to +82 pp relative top-1 precision on large repos (5 repos, 7,531 functions) | needs offline summarization; contrast with arXiv:2607.09691 which finds NL summaries carry little of the behavioral info needed to *act* (4/45 vs 27/45 resolved) - summaries help find, source code is needed to fix |
| **Codebase-Memory** (arXiv:2603.27277) | tree-sitter KG, 14 MCP structural tools | tools | 83% answer quality vs 92% for file-exploration agent at 10x fewer tokens and 2.1x fewer tool calls; wins on hub detection / caller ranking | tool-level graph access trades a little quality for a lot of budget |
| **Reliable Graph-RAG for Codebases** (arXiv:2601.08773) | deterministic AST graph vs LLM-extracted KG vs vector-only | RAG | AST graph most correct, LLM-KG close but slow and missed 377 files on one repo, vector-only worst with most hallucination | validates the competition's choice of an AST graph |
| **Code Isn't Memory** (arXiv:2606.22417) | structural index inside a fixed harness (Opus 4.7) | index tool | localization acc@5 44.3->84.5, resolve 41.9->50.4 on SWE-PolyBench Verified / SWE-bench Pro, lower $/solve; no loss vs agentic grep | strongest 2026 evidence that a structural index helps even frontier agents |
| **Aider repo-map** (aider.chat/2023/10/22/repomap.html) | tree-sitter tags; file nodes, edges = identifier references; **personalized PageRank (NetworkX)** with restart mass on files/identifiers mentioned in chat | prompt, binary-searched to a token budget (default ~1k, reportedly 1/8 of context clamped 1k-4k, **UNVERIFIED**) | no published benchmark; Agent Retrieval Bench shows RepoMap best on its budgeted coverage metric | essentially free |
| **Sourcegraph SCIP / MCP** (scip-code.org; sourcegraph.com/mcp), CodeGraphContext | precise cross-repo symbol index; go-to-def / find-refs | MCP tools | vendor claims only | our NetworkX graph is a lightweight SCIP equivalent |
| **CodeQL-style call graphs** | precise inter-procedural call graph with virtual dispatch resolution | n/a | n/a | no agent studies found; AST `calls` edges (ours) over-approximate on dynamic dispatch, under-approximate on getattr/decorators |

Cross-cutting findings: (1) every study that tried k=2 or larger flattened neighborhoods for a prompt found diminishing or negative returns (RepoGraph k=2 below baseline; LocAgent found the *option* of multi-hop useful but used it selectively); (2) exposing the graph as a tool the agent calls on demand (LocAgent, Codebase-Memory, ARISE) is cheaper than prompt-stuffing, and the benefit grows with model weakness because it removes the need to hold the whole map; (3) query languages (Cypher) are a trap for small models; fixed-signature tools are not; (4) the deterministic AST graph is the right substrate, and the remaining gap is data-flow (ARISE) and tests-to-code edges (LARGER, arXiv:2605.16352, notes code-test relationships as a key missing link in lexical search).

---

## C. Embedding retrieval for code with a *fixed* function-level index

### C.1 Which embeddings are good (context only - we cannot swap ours)

- **CodeSage** (arXiv:2402.01935) and **CodeXEmbed** (Salesforce, arXiv:2411.12644; 400M-7B) set the 2024 open baselines on CoIR (CodeSage-large-v2 64.18 avg per CodeXEmbed's table).
- **CoRNStack / CodeRankEmbed** (arXiv:2412.01007; 137M) plus the CodeRankLLM reranker: first to evaluate on SWE-bench Lite function localization (gold = functions modified by the patch, 274/300 instances); ~50 Acc@5 / 59 Acc@10. **Nomic Embed Code** is trained on CoRNStack.
- **voyage-code-3** (blog.voyageai.com/2024/12/04/voyage-code-3): +13.8% over OpenAI-v3-large and +16.8% over CodeSage-large across 32 datasets (vendor numbers); Matryoshka-trained so **256-d** vectors are a supported operating point with small loss, and binary 256-d reportedly still beats OpenAI float 3072-d (**UNVERIFIED** vendor claim). This matters for us: a 256-d index is not inherently crippled if it was produced by an MRL-trained model.
- **jina-code-embeddings** 0.5B/1.5B (arXiv:2508.21290; jina.ai blog): MTEB-Code 78.7/78.9, 1.5B matches voyage-code-3 (79.2).
- **Qwen3-Embedding** (arXiv:2506.05176): MTEB-Code 75.4 (0.6B), 80.1 (4B), 80.7 (8B). Agent Retrieval Bench found Qwen3-Embedding-4B best MRR and 8B best Recall@20 for agent context retrieval; CORE-Bench found a lightly SFT'd Qwen3-8B best in the agentic setting.
- **EmbeddingGemma** (arXiv:2509.20354) is the Google family member; plausibly what the competition used (**UNVERIFIED** - not stated in the material I had).

None of this changes our situation: the 256-d vectors are given. What the literature *does* say is that function-granularity chunks are a good unit (SweRank, CoRNStack, LocAgent all use function = document; Practical Code RAG found 32-64-line chunks best at small budgets, which is roughly a function), and that the big losses come from the *query* side.

### C.2 Query formulation from a bug report

- **Raw issue text is a poor query.** BLAgent (arXiv:2605.17965) argues raw bug reports hurt dense retrieval through lexical mismatch with identifiers and narrative noise; it uses "dual-perspective" query transformation (structural: names/paths; behavioral: what goes wrong) plus path-augmented AST chunking and a two-phase agentic rerank, reaching >78% file Top-1 on Lite with open models at 18x lower cost than the strongest baseline.
- **Extract-then-query.** "Reformulate, Retrieve, Localize" (arXiv:2512.07022, BoatSE 2026) has Qwen3-30B extract summary, file paths, identifiers, code snippets, stack traces and error messages from the report and issues several BM25 queries; best reformulation gives 35% better first-file ranking than BM25 on the raw report. Classic IR-based bug-localization work (BLIZZARD, arXiv:1808.00594) found 7-56% Hit@10 gains from report-type-aware reformulation; a 2025 follow-up on semantics-driven query *reduction* (arXiv:2510.04468) finds that removing noise terms matters as much as adding.
- **Hypothesized code (HyDE-style).** I found no paper directly testing HyDE pseudo-code against reformulation for issue localization; the evidence is indirect: function-level indexes are embeddings of *code*, so a query that looks like code (a plausible function signature plus 3-5 lines that would contain the bug, or the exact exception/message string) should land closer in embedding space than prose. Practical Code RAG's finding that code-to-code retrieval behaves very differently from NL-to-code supports generating a code-shaped query when the index is code. Treat as a hypothesis to A/B on the training set.
- **Role-aware summaries** (arXiv:2607.11046) beat file paths by up to 40% Hit@5 at 10-20x smaller footprint and LLM reranking adds up to 42% - but this needs offline summarization of the repo, which we cannot do for the hidden set unless we do it at runtime for a few candidates.

### C.3 Reranking

SweRank's listwise 7B reranker and CoRNStack's CodeRankLLM both show a small LLM listwise reranker over top-20/50 function candidates is a large, cheap win over the bi-encoder ordering; BLAgent and arXiv:2607.11046 show the same with a general LLM given code + issue. For Gemma this is one prompt: issue + 10-20 (ID, signature, first lines) -> ordered IDs. The Agentless skeleton result (58.3% vs 53.7% with full files) suggests reranking over *signatures and docstrings* first, then opening the top few.

### C.4 Using a fixed index well: multi-query, fusion, graph expansion

- **Multi-query + reciprocal rank fusion** (RAG-Fusion, arXiv:2402.03367 - general RAG, not code-specific): issue 3-5 queries (error string, suspected symbol names, a code-shaped hypothesis, the title) and fuse by RRF. LocAgent's observation that two independent runs merged by MRR improve results is the agentic analogue.
- **Seeds -> graph expansion.** FeatLens (arXiv:2609.26480) builds a task-specific seed graph then runs personalized PageRank for "semantic-structural" filtering and reports the best DR@15 among sparse/dense/graph baselines on DevEval/EvoCodeBench; HippoRAG (arXiv:2405.14831) is the canonical seeds + PPR retrieval pattern; an open tool, `codegraph` (github.com/tarunms7/codegraph), implements exactly "tree-sitter + NetworkX + PPR seeded on given files + token budget". A citation-grounded code comprehension system (arXiv:2512.12117) reports 1-hop BFS from 4 seed files found ~11.8 extra relevant neighbors per query and raised completeness to 82%. No paper I found compares PPR to plain 1-hop BFS on a localization benchmark - but PPR is a few lines over our NetworkX graph and degrades gracefully to BFS.

---

## D. Graph-aware retrieval algorithms usable at inference

1. **Seed expansion / k-hop.** LocAgent: `TraverseGraph` with configurable hops, direction and edge-type filter; ablation shows fixing hops=1 costs ~5 points at function level while RepoGraph shows that *dumping* 2 hops into the prompt costs more than it gains. Resolution: expand 2 hops but **rank and truncate**, never dump.
2. **Personalized PageRank from seeds.** Aider (restart mass on mentioned identifiers/files), FeatLens, HippoRAG, codegraph. With the competition graph: `nx.pagerank(G, personalization={seed: score})` where seeds are the union of grep hits, `search_similar_code` hits (weighted by similarity) and test-call-chain hits; then take top-k nodes not already seen. Reverse edges should be included (or run on the undirected view) so that *callers* of a suspicious function are reachable - OrcaLoca explicitly uses min(forward, reverse) distance.
3. **Distance-aware pruning** (OrcaLoca): score every candidate by shortest-path distance to the current hypothesis set, keep top-12. Cheap with NetworkX and prevents context bloat for a 4B model.
4. **Accept/reject frontier search** (CoSIL): expand only through nodes a one-token LLM judgement accepts; max 10 iterations. Natural fit for `get_code_neighbors`.
5. **Call-chain tracing from tests/entry points.** IssueExec/XAgent show tests are high-precision seeds. Statically: find test functions whose name/body mentions issue identifiers (grep), take their `calls` closure 2-3 hops into non-test code, intersect with embedding seeds. Dynamically: run the one failing test with `pytest --tb=long` and map traceback frames to graph nodes.
6. **Mixing lexical grep with graph neighbors.** LARGER (arXiv:2605.16352) formalizes "lexical anchors -> graph anchors -> confidence-filtered neighborhoods inside the agent's existing search loop"; LocAgent's ablation says keyword search is the single most important tool, and LogicLoc says keyword shortcuts are what SWE-bench rewards. Rule: grep first for every identifier, path, exception name and quoted string in the issue; use embeddings only for what grep cannot anchor; use the graph to connect anchors.
7. **Budgeted exploration.** Observed round counts: LocAgent 6-9 tool rounds (7B used 6), Moatless 5, SWE-agent 8-9, OpenHands 13-15, CoSIL <=10 iterations, A^2Agent/RepoNavigator show RL-trained small models improving with more allowed turns. Cost-Effective Repository Exploration shows cheap explorers keep ~80-90% of Hit@3 at 5-16% of tokens. A reasonable target for us is **4-8 tool calls for localization** out of the total budget, with hard caps per tool type.
8. **Presenting subgraphs to a small model.** LocAgent: indented tree with full IDs and explicit relation labels beat JSON, edge lists, incident lists and DOT; "Talk like a Graph" (arXiv:2310.04560) found incident/neighbor-list encodings beat edge-pair lists because related facts sit together, and that LLMs are bad at global graph properties - so never ask the model to reason over a raw edge list; pre-compute degree/centrality and show only ranked, labelled neighbors. Token budgets reported: RepoGraph k=1 flattened ~2.3k tokens, LLM-summarized ~0.7-1.2k; Code Isn't Memory and Codebase-Memory both show ~10x token savings when structure replaces file dumps. Concretely, a neighbor line should be `<- calls  pkg/mod.py:Class.method(sig)  [L120-168]  "first docstring line"`, roughly 25-40 tokens per node, so a 30-node view costs about 1k tokens.

---

## E. Training a small model to localize

- **LocAgent SFT** (arXiv:2503.09089): ~430-450 Claude-3.5 trajectories on SWE-bench-train filtered to correct localization, +335 self-sampled from the fine-tuned 32B; LoRA; the 7B student reaches 88.3 file Acc@5 / 71.5 function Acc@10 on Lite ($0.05/instance).
- **ToolTrain / RepoSearcher** (arXiv:2508.03012): ~28k issue->PR localization examples from 600 repos (SWE-bench-Verified repos excluded); Claude-3.7 generates trajectories for 10k -> 5k kept for rejection-sampled SFT; the remaining 18k used for rule-based RL with **nDCG@k over the predicted function ranking vs gold-patch functions as the reward**; Qwen2.5-Coder-7B reaches 83.1 file / 62.4 function Recall@5 on Verified (beating 32B CoSIL and Agentless) and 32B reaches 88.6 / 68.6 (above Claude-3.7+CoSIL at function level). Tool-call success rate stabilizes >95% during RL for the 7B.
- **RepoNavigator / "One Tool Is Enough"** (arXiv:2512.20957): single jump-to-definition tool, pure RL on Qwen2.5 7B/14B/32B; 7B beats 14B multi-tool baselines; performance scales with allowed tool turns.
- **A^2Agent** (arXiv:2608.29831): per-turn reward for both *discovering* and *committing* gold regions plus action-level advantages; six tools incl. `TraverseGraph` and `SearchEntity`; a **Qwen3-4B** beats baselines up to 8x larger (+1.58 F1 Verified, +8.55 SWE-bench Pro). Directly relevant: a 4B model with graph tools is competitive when trained with dense, action-level reward.
- **CodeScout** (OpenHands, arXiv:2603.17829): GSPO RL on Qwen3 1.7B/4B/14B with only a Unix terminal; 1.7B post-RL beats Qwen3-14B. Evidence that the *recipe* matters more than the tool count - though for a frozen or lightly tuned model, tools substitute for training.
- **SweRank's SweLoc** (arXiv:2505.07849): mines (issue, modified functions) pairs from PRs at scale with hard negatives from the same repo for contrastive retriever/reranker training.
- **SWE-smith** (arXiv:2504.21798, NeurIPS 2025): ~50k synthetic task instances from 128 repos; the toolkit explicitly supports generating *file-localization* tasks; SWE-agent-LM-32B reached 40.2% Verified. **SWE-Fixer** (arXiv:2501.05040): BM25 top-30 (**UNVERIFIED** count) then a fine-tuned Qwen2.5-7B retriever picks files to edit, trained on 110k instances; 24.7% Lite / 32.8% Verified best@1.
- **Deriving labels from gold patches** (standard across LocAgent, CoRNStack, ToolTrain, SweRank): parse the gold diff hunks, map changed line ranges to enclosing functions/classes/files via the AST (our graph already stores line ranges per node), giving file/module/function label sets. Known caveats: hunks in new files or at module level have no function node (LocAgent reports module-level accuracy separately); some fixes touch a caller rather than the function the issue describes, so training a localization reward on *exact* gold functions under-credits valid alternatives - ToolTrain's ranked nDCG and A^2Agent's discover+commit reward both soften this. For a competition, the cheapest high-value use is **evaluation**: compute file/function Acc@k of our localization sub-pipeline on the training set before touching the editor.

---

## F. Synthesis: recommendations and a localization sub-pipeline

### F.1 Twelve actionable recommendations

1. **Grep before you embed.** Extract every file path, dotted name, identifier, exception class, and quoted message from the issue and grep/`SearchEntity`-style match them against node names first. LocAgent's largest ablation drop is losing keyword search (-18 points function Acc@10); LogicLoc shows SWE-bench rewards exactly this. Expected effect: file Acc@5 in the high 70s with 1-2 calls on hinted issues.
2. **Use `search_similar_code` with several code-shaped queries, not the raw issue.** Issue 3-4 queries: (a) the error/exception string, (b) a hypothesized function signature + 3-5 lines of the buggy logic, (c) the title plus key nouns, (d) a test-like call that reproduces the bug; fuse by RRF. Basis: BLAgent, Reformulate-Retrieve-Localize (+35% first-file ranking), RAG-Fusion, Practical Code RAG's NL-vs-code asymmetry. HyDE-style code queries are a hypothesis to validate on the train split.
3. **Treat the three graph tools as read-only navigation, never as a query language.** CodexGraph shows weaker models collapse when they must compose graph queries (Qwen2-72B 1.95%); LocAgent/ARISE/Codebase-Memory show fixed-signature traversal tools work for 7B-class models. Wrap `get_code_neighbors` with sensible defaults (both directions, `calls` + containment edges, 1 hop) so the model only supplies node IDs.
4. **Expand seeds 1 hop with `get_code_neighbors`, 2 hops only via ranking.** RepoGraph k=2 prompt dumps hurt (26.0% vs 29.67%); LocAgent's selective multi-hop helps (+5 points). Compute 2-hop candidates locally with NetworkX and personalized PageRank, show the model only the top 10-15.
5. **Run personalized PageRank over the union of seeds** (grep hits weight 1.0, embedding hits weight = cosine score, test-trace hits weight 1.5) on the undirected or reverse-augmented graph; take top-k unseen nodes as candidates. Basis: Aider, FeatLens, HippoRAG, codegraph. Zero tool calls - it is local computation on the provided graph.
6. **Prune by graph distance, keep ~12 context items.** OrcaLoca's distance-aware pruning (+4.3 points in ablation) and context cap keep a 4B model's window clean. Re-rank the live candidate set each step by average shortest-path distance to the current top hypotheses.
7. **Rerank skeletons before opening bodies.** Present candidates as `ID | signature | docstring line | callers count | callees count` (Agentless skeleton 58.3% vs full-file 53.7%; SweRank/CoRNStack listwise rerank). One Gemma call orders 15-20 candidates; open full source for only the top 3-5.
8. **Trace from tests when possible.** Statically take the `calls` closure from tests whose names/bodies match issue identifiers (IssueExec +17 resolved on Lite when added to Agentless); dynamically, if a reproduction test is written anyway for the fix, map its traceback frames to graph nodes before patching (XAgent 72.8% function localization).
9. **Budget: 4-8 tool calls for localization, then commit.** LocAgent-7B averaged 6 rounds, CoSIL caps at 10, cheap explorers keep 78-94% of Hit@3 at a fraction of tokens (arXiv:2608.29675). Hard-cap: <=3 `search_similar_code`, <=3 `get_code_neighbors`, <=1 `get_code_subgraph`, plus grep. A^2Agent's "find but fail to commit" failure mode argues for forcing an explicit ranked output at the cap.
10. **Emit a diagnosis with the location.** SHERLOC's +5.95 pp from passing *diagnostic findings* to the repair stage, and GraphLocator's symptom-vs-cause framing, suggest the localizer should output `(node_id, why_this_is_the_cause, what_to_change)` triples, and include one caller/one callee each so the editor sees the contract. Source code, not summaries, must go to the editor (arXiv:2607.09691: 4/45 vs 27/45).
11. **Sample and merge location sets.** Agentless gains ~6 points of edit-location recall by merging 4 samples; LocAgent merges two runs by MRR. With a small model and temperature >0, two localization passes merged by RRF are cheap insurance if the budget allows; otherwise merge the grep-, embedding- and graph-derived rankings (three "views") rather than three model runs.
12. **Validate on the training set with gold-patch labels before tuning anything else.** Map gold hunks to graph nodes and measure file Acc@5 / function Acc@10 of the sub-pipeline; the literature's bands (dense-only ~50-59, tuned 7B agents ~62-72, frontier ~73-77 function Acc@10 on Lite) tell you whether a given change is worth it. If fine-tuning is permitted, a few hundred filtered successful trajectories (LocAgent) or a ranked nDCG reward (ToolTrain) are the proven recipes; if not, the same labels still calibrate the prompts and caps.

### F.2 Proposed localization sub-pipeline (small model, tool budget B_loc ~ 6)

```
Stage 0  Parse issue (0 tool calls, 1 short model call or regex)
         -> anchors: paths, dotted names, identifiers, exception names, quoted strings
         -> 3 queries: error-string, code-shaped hypothesis, title+nouns

Stage 1  Lexical seeds (grep / name index, 1-2 calls)
         -> exact node-name matches, path matches, string-literal matches
         -> weight 1.0 each; if >= 3 strong anchors found, skip half of Stage 2

Stage 2  Semantic seeds (search_similar_code x 2-3, fused by RRF)
         -> top-10 nodes per query, weight = fused score

Stage 3  Test seeds (0-1 calls, optional)
         -> tests whose name/body mention anchors; 2-hop `calls` closure into src
         -> weight 1.5 (static) or 2.0 (traceback frames if a repro test was run)

Stage 4  Graph expansion (local NetworkX, 0 tool calls)
         -> personalized PageRank from weighted seeds on reverse-augmented graph
         -> union seeds + top-15 PPR nodes; drop test/vendor/`__init__` noise
         -> distance-aware prune to <= 20 candidates

Stage 5  Skeleton rerank (1 model call)
         -> show ID | signature | docstring line | in/out degree | 1-line why-seeded
         -> model returns ordered top-5 + one-sentence hypothesis each

Stage 6  Verification (1-2 calls: get_code_neighbors on top-1/2, read bodies)
         -> confirm the hypothesis against full source + immediate callers/callees
         -> if top-1 rejected, promote next; at most one re-expansion
         -> output: ranked (file, function, line-range, diagnosis) + 1-hop context pack
```

Expected standing, from the cited bands: with grep + fused embedding seeds alone, ~55-65 function Acc@10 on SWE-bench-Lite-like issues; adding graph expansion, distance pruning and skeleton rerank should move an untuned 7-31B model toward the 65-72 band that LocAgent-7B/ToolTrain-7B occupy; the 4B will sit lower but A^2Agent shows 4B + graph tools is not hopeless. Every stage degrades gracefully: if the embedding index is weak for a repo, lexical and test seeds still feed PPR; if the model cannot rerank well, PPR order is the fallback.

### F.3 Open risks

- The provided `calls` edges are static AST edges: dynamic dispatch, decorators, `getattr`, and framework callbacks (Django signals, pytest fixtures) will be missing or wrong; treat 0-degree nodes with suspicion rather than as dead code.
- Module-level code (constants, top-level statements) and new-file fixes have no function node; keep file-level candidates alive alongside function-level ones (LocAgent reports module-level accuracy separately for this reason).
- Embedding quality of the fixed 256-d index is unknown; measure Acc@k of `search_similar_code` alone on the training set first, so the pipeline's weights for lexical vs semantic seeds are data-driven rather than borrowed.
- Benchmarks reward keyword shortcuts (arXiv:2604.16021); hidden-test issues written after model cut-offs (Loc-Bench style) are harder, and LocAgent-7B lost ~20 points of function accuracy moving from Lite to Loc-Bench - plan for that gap.

---

## Sources (primary)

- SWE-bench: arXiv:2310.06770 - https://arxiv.org/abs/2310.06770
- Agentless: arXiv:2407.01489 - https://arxiv.org/abs/2407.01489 ; https://github.com/OpenAutoCoder/Agentless
- LocAgent: arXiv:2503.09089 - https://arxiv.org/abs/2503.09089 ; https://github.com/gersteinlab/LocAgent
- OrcaLoca: arXiv:2502.00350 - https://arxiv.org/abs/2502.00350 ; https://github.com/fishmingyu/OrcaLoca
- CoSIL: arXiv:2503.22424 - https://arxiv.org/abs/2503.22424
- SWE-Search: arXiv:2410.20285 - https://arxiv.org/abs/2410.20285 ; https://github.com/aorwall/moatless-tree-search
- SweRank: arXiv:2505.07849 ; SweRank+: arXiv:2512.20482
- KGCompass: arXiv:2503.21710
- GraphLocator: arXiv:2512.22469
- SHERLOC: arXiv:2606.24820
- RepoMem: arXiv:2510.01003
- RPG-Encoder: arXiv:2602.02084
- IssueExec: arXiv:2607.17286 ; XAgent: arXiv:2609.09769
- LogicLoc / Neurosymbolic localization: arXiv:2604.16021
- Cost-Effective Repository Exploration: arXiv:2608.29675
- Does Fault Localization Beat a Fresh Attempt: arXiv:2609.00854
- RepoGraph: arXiv:2410.14684 - https://arxiv.org/abs/2410.14684 ; https://github.com/ozyyshr/RepoGraph
- CodexGraph: arXiv:2408.03910 - https://arxiv.org/abs/2408.03910
- ARISE: arXiv:2605.03117 - https://github.com/FARD-Lab/ARISE
- DualView: arXiv:2607.01929 ; RepoAtlas: arXiv:2609.16936
- GraphCoder: arXiv:2406.07003 ; CoCoMIC: arXiv:2212.10007 ; RepoHyper: arXiv:2403.06095 ; RepoFuse: arXiv:2402.14323 ; CodeRAG: arXiv:2504.10046 ; GRACE: arXiv:2509.05980
- Code-Craft / HCGS: arXiv:2504.08975 ; What Context Does a Coding Agent Actually Need: arXiv:2607.09691
- Codebase-Memory: arXiv:2603.27277 ; Reliable Graph-RAG for Codebases: arXiv:2601.08773 ; Code Isn't Memory: arXiv:2606.22417
- LARGER: arXiv:2605.16352 ; FeatLens: arXiv:2609.26480 ; HippoRAG: arXiv:2405.14831 ; RAG-Fusion: arXiv:2402.03367 ; Talk like a Graph: arXiv:2310.04560
- Aider repo-map: https://aider.chat/2023/10/22/repomap.html ; codegraph: https://github.com/tarunms7/codegraph ; SCIP: https://scip-code.org ; Sourcegraph MCP: https://sourcegraph.com/mcp
- Embeddings: CodeSage arXiv:2402.01935 ; CodeXEmbed arXiv:2411.12644 ; CoRNStack arXiv:2412.01007 ; voyage-code-3 https://blog.voyageai.com/2024/12/04/voyage-code-3/ ; jina-code-embeddings arXiv:2508.21290 ; Qwen3-Embedding arXiv:2506.05176 ; EmbeddingGemma arXiv:2509.20354
- Retrieval studies/benchmarks: Practical Code RAG at Scale arXiv:2510.20609 ; CORE-Bench arXiv:2606.11864 ; Agent Retrieval Bench arXiv:2607.24882 ; Retrieval-Oriented Code Representations arXiv:2607.11046 ; BLAgent arXiv:2605.17965 ; Reformulate-Retrieve-Localize arXiv:2512.07022 ; BLIZZARD arXiv:1808.00594 ; query reduction arXiv:2510.04468
- Training: ToolTrain arXiv:2508.03012 ; RepoNavigator arXiv:2512.20957 ; A^2Agent arXiv:2608.29831 ; CodeScout arXiv:2603.17829 ; SWE-smith arXiv:2504.21798 ; SWE-Fixer arXiv:2501.05040
