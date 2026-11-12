#!/usr/bin/env python3
"""Local copy of the competition scorer: Phase 1 (agent) + Phase 2 (pytest verification), resolution = resolved / tasks.
EvalConfig mirrors the official "Getting Started" notebook / scripts/inference.py (events compaction 15/2/14336/5,
context cache 2048/1800/10, submission limits, adapter manifest, graph dirs).

--sandbox subprocess (default) is what Kaggle's own notebook runs and what our Kaggle-environment evals use; it agrees
with Kaggle on task soundness (see vm/README.md). --sandbox docker is the old per-repo-image grader (not trustworthy).

The model is served separately by vm/serve_vllm.sh; this script routes the submission's declared model and adapters
to that endpoint. Only the TIME budget is scaled (--time; T4s decode slower than the scorer's L4s); tool-call / turn /
command budgets come from the submission's eval_config.yaml unchanged. With REPLICA_TIME_SCALE=k (the clock patch,
patch_replica_clock.py) the per-request model timeout is scaled by k as well (scale_request_timeout below).

  LOCAL_INFERENCE_URL=http://127.0.0.1:8000/v1 python local_score.py --root data/comp --submission submissions/pub022 \
      --results results/local/pub022 --time 24 --concurrency 4 --order-csv results/kaggle_soundness.csv --first 50
"""
import argparse, asyncio, csv, json, os, time
from pathlib import Path


def ordered_sound(path):
    """Kaggle-sound tasks, round-robin by repo (same order as the Kaggle-environment notebooks)."""
    rows = list(csv.DictReader(open(path))); by = {}
    for r in rows:
        if r.get("sound") == "True": by.setdefault(r["instance_id"].split("_")[0], []).append(r["instance_id"])
    qs, out = list(by.values()), []
    while any(qs):
        for q in qs:
            if q: out.append(q.pop(0))
    return out


def scale_request_timeout():
    """Replica only; a no-op at REPLICA_TIME_SCALE=1 (Kaggle's own speed).

    litellm gives every model request 600 s, then the harness's num_retries=5 sends it again. On Kaggle that limit is
    never reached: an 8-minute task cannot wait 600 s for one reply. On the T4s, which decode about 9x slower, a reply
    over ~2,600 tokens was cut and re-sent until the task's time ran out (research/STATE.md, Nov 12). Scale the limit
    like the task clock so that it stands for Kaggle's 600 s. Returns the new limit in seconds, or None."""
    scale = float(os.environ.get("REPLICA_TIME_SCALE", "1") or 1)
    if scale == 1:
        return None
    from google.adk.models import lite_llm      # LiteLlm imports litellm lazily; patch the client method it calls
    orig, limit = lite_llm.LiteLLMClient.acompletion, 600 * scale

    async def acompletion(self, model, messages, tools, **kw):
        if kw.get("timeout") is None:
            kw["timeout"] = limit
        return await orig(self, model, messages, tools, **kw)

    lite_llm.LiteLLMClient.acompletion = acompletion
    return limit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True); ap.add_argument("--image", default="swebench-sandbox:latest")
    ap.add_argument("--sandbox", choices=["subprocess", "docker"], default="subprocess")
    ap.add_argument("--submission", required=True); ap.add_argument("--results", required=True)
    ap.add_argument("--time", type=float, required=True, help="max_time_minutes used locally (scaled)")
    ap.add_argument("--concurrency", type=int, default=3); ap.add_argument("--task-ids", nargs="*", default=None)
    ap.add_argument("--order-csv"); ap.add_argument("--first", type=int, default=0)
    a = ap.parse_args()
    ids = a.task_ids or (ordered_sound(a.order_csv) if a.order_csv else None)
    if ids and a.first: ids = ids[:a.first]
    os.environ.setdefault("LOCAL_INFERENCE_URL", "http://127.0.0.1:8000/v1")
    import yaml
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.apps._configs import EventsCompactionConfig
    from adk_submission import discover_adapters
    from swegemma.cli import _build_cli_model_registry
    from swegemma.config import EvalConfig, build_submission_limits
    from swegemma.evaluate import Evaluator
    limit = scale_request_timeout()
    if limit:
        print(f"replica: model request timeout {limit:.0f} s (600 s x REPLICA_TIME_SCALE)", flush=True)

    root, sub = Path(a.root), Path(a.submission)
    ev = yaml.safe_load(open(sub / "eval_config.yaml"))["evaluation"]
    limits, gen = build_submission_limits()
    kw = dict(image=a.image) if a.sandbox == "docker" else {}
    cfg = EvalConfig(
        tasks_path=root / "tasks.jsonl", snapshots_dir=root / "snapshots", results_dir=Path(a.results),
        submission_dir=sub, models=_build_cli_model_registry(sub), sandbox=a.sandbox,
        wheels_dir=root / "wheels", graph_dir=str(root / "graphs"), embeddings_dir=str(root / "embeddings"),
        timeout_seconds=int(ev["timeout_seconds"]), verification_timeout_seconds=300,
        max_time_minutes=a.time, max_tool_calls=int(ev["max_tool_calls"]), max_turns=int(ev["max_turns"]),
        limits=limits, generation_constraints=gen, adapter_manifest=discover_adapters(str(sub)),
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5),
        task_ids=ids, concurrency=a.concurrency, display_mode="quiet", **kw)
    t0 = time.time()
    res = asyncio.run(Evaluator(cfg).run())
    print(json.dumps({"submission": str(sub), "resolved": res.resolved, "total": res.total,
                      "resolution_rate": round(res.resolution_rate, 4), "minutes": round((time.time() - t0) / 60, 1)}))


if __name__ == "__main__":
    main()
