#!/usr/bin/env python3
"""Generate a Kaggle notebook that scores on Kaggle's own hardware and sandbox (the scorer's environment).

  controls (CPU, no GPU quota): verify the gold patch and the empty patch for every public task with the
            harness Evaluator (sandbox='subprocess', like the official getting-started notebook). A task is
            sound in Kaggle's environment iff gold passes and empty fails.
  agent    (GPU L4x4): start vLLM exactly like the official notebook / scorer, run one bundle on public tasks
            in a fixed order until the time budget is spent, write per-task results.

  python make_kaggle_eval.py controls <out_dir> <owner/slug> "<title>"
  python make_kaggle_eval.py agent <out_dir> <owner/slug> "<title>" --bundle submissions/pub022 \
         [--order-csv results/gold_soundness.csv] [--hours 4.0] [--machine NvidiaL4X4]
Outputs (in the kernel's /kaggle/working/eval): results.csv (+ controls_gold/controls_empty or agent_run dirs).
"""
import argparse, csv, json, hashlib
from pathlib import Path

ENV_AND_WHEELS = r'''
import glob, importlib, json, logging, os, shutil, subprocess, sys, time, csv, asyncio, concurrent.futures, re, traceback
from pathlib import Path
for k, v in {'TRANSFORMERS_NO_TF': '1', 'TRANSFORMERS_NO_FLAX': '1', 'TRANSFORMERS_OFFLINE': '1', 'VLLM_NO_USAGE_STATS': '1',
             'VLLM_WORKER_MULTIPROC_METHOD': 'spawn', 'VLLM_ENGINE_READY_TIMEOUT_S': '1200',
             'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS': '1', 'NCCL_DEBUG': 'WARN', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
             'LITELLM_TELEMETRY': 'False', 'LITELLM_LOG': 'WARNING', 'OPENAI_API_KEY': 'EMPTY', 'LOCAL_API_KEY': 'EMPTY',
             'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True', 'OTEL_SDK_DISABLED': 'true', 'OTEL_PYTHON_DISABLED': 'true'}.items():
    os.environ.setdefault(k, v)

def quiet():
    # Library logging floods the notebook's IOPub channel (thousands of sandbox WARNING lines -> CellTimeoutError);
    # progress is reported with print(), so only errors from libraries are kept.
    logging.getLogger().setLevel(logging.ERROR)
    for name in ('LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy', 'litellm', 'httpx', 'httpcore', 'openai', 'urllib3', 'opentelemetry',
                 'swegemma', 'adk_submission', 'adk_eval_core', 'google_adk', 'google', 'vllm'):
        lg = logging.getLogger(name); lg.setLevel(logging.ERROR)
        if 'litellm' in name.lower(): lg.propagate = False; lg.handlers.clear()
quiet()

WHEELHOUSE = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
if not WHEELHOUSE.exists():
    WHEELHOUSE = Path(sorted(glob.glob('/kaggle/input/**/gemma-4-developer-agent-wheelhouse', recursive=True))[0])
for pat in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth', '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    for pth in glob.glob(pat):
        try: os.unlink(pth)
        except OSError: pass
tmp_whl = Path('/tmp/wheelhouse'); tmp_whl.mkdir(parents=True, exist_ok=True)
SKIP_GPU_WHEELS = (MODE == 'controls')
for w in WHEELHOUSE.glob('*.whl'):
    low = w.name.lower()
    if 'cutlass' in low: continue
    if SKIP_GPU_WHEELS and low.startswith(('vllm', 'torch', 'flashinfer', 'xformers', 'triton', 'nvidia')): continue
    t = tmp_whl / (w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name)
    if not t.exists():
        try: os.symlink(w, t)
        except OSError: shutil.copyfile(w, t)
wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))
print(f'installing {len(wheels)} wheels', flush=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels], check=True)
importlib.invalidate_caches(); quiet()

DATA_DIR = Path('/kaggle/input/competitions/gemma-4-developer-agent')
if not (DATA_DIR / 'tasks.jsonl').exists():
    DATA_DIR = Path(sorted(glob.glob('/kaggle/input/**/tasks.jsonl', recursive=True))[0]).parent
WORK = Path('/kaggle/working'); OUT = WORK / 'eval'; OUT.mkdir(parents=True, exist_ok=True)
from swegemma.models import load_tasks
tasks = load_tasks(DATA_DIR / 'tasks.jsonl'); by_id = {t.instance_id: t for t in tasks}
order = [by_id[i] for i in TASK_ORDER if i in by_id] + [t for t in tasks if t.instance_id not in set(TASK_ORDER)]
print(f'{len(tasks)} tasks from {DATA_DIR}', flush=True)

def run_sync(fn, *args, **kwargs):
    call = lambda: fn(*args, **kwargs) if callable(fn) else fn
    try: loop = asyncio.get_running_loop()
    except RuntimeError: loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(call())).result()
    return asyncio.run(call())
'''

CONTROLS = r'''
from adk_eval_core.tracing import SessionTrace
from adk_submission import ModelRegistry
from swegemma.config import EvalConfig
from swegemma.evaluate import Evaluator
stub = WORK / 'stub'; shutil.rmtree(stub, ignore_errors=True); shutil.copytree(DATA_DIR / 'sample_submission', stub)
gold = {t.instance_id: t.patch for t in tasks}
rows = {}
for mode in ('gold', 'empty'):
    rd = OUT / f'controls_{mode}'; rd.mkdir(parents=True, exist_ok=True)
    cfg = EvalConfig(tasks_path=DATA_DIR / 'tasks.jsonl', snapshots_dir=DATA_DIR / 'snapshots', results_dir=rd,
                     submission_dir=stub, models=ModelRegistry(), sandbox='subprocess', wheels_dir=DATA_DIR / 'wheels',
                     verification_timeout_seconds=300, task_ids=[t.instance_id for t in order], concurrency=CONCURRENCY,
                     graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'))
    class ControlEvaluator(Evaluator):
        async def _run_agent_sandbox(self, task, *args, **kw):
            return (gold[task.instance_id] if mode == 'gold' else ''), None, SessionTrace()
    t0 = time.time()
    try:
        res = run_sync(ControlEvaluator(cfg).run)
        print(f'{mode}: resolved {res.resolved}/{res.total} in {(time.time() - t0) / 60:.1f} min', flush=True)
    except Exception:
        traceback.print_exc()
    for f in rd.rglob('task_results.jsonl'):
        for line in open(f):
            r = json.loads(line); iid = r.get('instance_id') or r.get('id')
            rows.setdefault(iid, {})[mode] = r.get('resolved')
            rows[iid][mode + '_exit'] = r.get('test_exit_code'); rows[iid][mode + '_err'] = (r.get('error') or '')[:160].replace(chr(10), ' ')
with open(OUT / 'results.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['instance_id', 'repo', 'gold_pass', 'empty_pass', 'sound', 'gold_exit', 'empty_exit', 'gold_err', 'empty_err'])
    for iid in sorted(rows):
        r = rows[iid]; g, e = bool(r.get('gold')), bool(r.get('empty'))
        w.writerow([iid, iid.split('_')[0], g, e, g and not e, r.get('gold_exit'), r.get('empty_exit'), r.get('gold_err'), r.get('empty_err')])
import collections
sound = [iid for iid, r in rows.items() if r.get('gold') and not r.get('empty')]
print('SOUND', len(sound), '/', len(rows), dict(collections.Counter(i.split('_')[0] for i in sound)), flush=True)
'''

AGENT = r'''
AGENT_DIR = WORK / 'agent'; shutil.rmtree(AGENT_DIR, ignore_errors=True)
for rel, text in FILES.items():
    p = AGENT_DIR / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')
assert hashlib.sha256(json.dumps(FILES, sort_keys=True).encode()).hexdigest()[:16] == BUNDLE_HASH
import litellm, torch, yaml
from adk_submission import VllmConfig, VllmServer, discover_adapters
from adk_submission.discovery import discover_declared_models
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS, EvalConfig, build_submission_limits
from swegemma.evaluate import Evaluator
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
litellm.drop_params = True
declared = discover_declared_models(AGENT_DIR); assert len(declared) == 1, declared; model = next(iter(declared))
MODEL_PATH = Path(f'/kaggle/input/models/google/gemma-4/other/{model}/2')
if not MODEL_PATH.exists():
    MODEL_PATH = Path(sorted(glob.glob(f'/kaggle/input/**/{model}/**/config.json', recursive=True))[0]).parent
adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
amap = getattr(adapters, 'adapters', None) or {}
ranks = [r for i in amap.values() if (r := getattr(i, 'rank', None))]
ngpu = torch.cuda.device_count(); tp = 4 if ngpu >= 4 else (2 if ngpu >= 2 else 1)
print(f'model {model} at {MODEL_PATH}; gpus {ngpu} ({torch.cuda.get_device_name(0) if ngpu else "none"}); tp {tp}; adapters {list(amap)}', flush=True)
extra = ('--hf-overrides', '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}') if model == 'gemma-4-12b-it-qat-w4a16-ct' else ()
t_start = time.time()
server = VllmServer(VllmConfig(model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4', reasoning_parser='gemma4',
                               max_model_len=32768, dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto',
                               gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=bool(amap),
                               max_loras=max(1, len(amap)), max_lora_rank=max(ranks) if ranks else 128,
                               scheduler_reserve_full_isl=False, tensor_parallel_size=tp, startup_timeout=60 * 20, extra_args=extra),
                    adapter_manifest=adapters)
server.start(); print(f'vLLM up in {(time.time() - t_start) / 60:.1f} min', flush=True)
models = server.create_model_registry(aliases=[model], model_prefix='openai/', api_key='EMPTY')
ecf = next((c for n in ('eval_config.yaml', 'eval_config.yml') if (c := AGENT_DIR / n).is_file()), None)
raw = (yaml.safe_load(ecf.read_text()) or {}) if ecf else {}; ev = raw.get('evaluation', raw)
turns = ev.get('max_turns', ev.get('max_llm_calls'))
limits, gen = build_submission_limits()
cfg = EvalConfig(tasks_path=DATA_DIR / 'tasks.jsonl', snapshots_dir=DATA_DIR / 'snapshots', results_dir=OUT / 'agent_run',
                 submission_dir=AGENT_DIR, models=models, sandbox='subprocess',
                 timeout_seconds=int(ev.get('timeout_seconds', 300)), verification_timeout_seconds=int(ev.get('verification_timeout_seconds', 300)),
                 max_time_minutes=float(ev.get('max_time_minutes', 60.0)), max_tool_calls=int(ev.get('max_tool_calls', 100)),
                 max_turns=int(turns) if turns is not None else None, limits=limits, generation_constraints=gen, adapter_manifest=adapters,
                 context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
                 events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5),
                 graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'), wheels_dir=DATA_DIR / 'wheels', verbose=False)
evaluator = Evaluator(cfg)
cols = ['instance_id', 'repo', 'resolved', 'exit_code', 'patch_chars', 'tool_calls', 'duration_s', 'error']
rows, patches = [], {}
t0 = time.time()
for idx, task in enumerate(order, start=1):
    if time.time() - t0 > HOURS * 3600:
        print(f'time budget {HOURS} h spent after {idx - 1} tasks', flush=True); break
    try:
        r = run_sync(evaluator.evaluate_task, task=task, task_index=idx, total_tasks=len(order))
        patch = (r.agent_patch or '').strip(); patches[task.instance_id] = patch
        row = [task.instance_id, task.repo, bool(r.resolved), r.test_exit_code, len(patch), r.tool_calls, round(r.duration_seconds, 1), (getattr(r, 'error', None) or '')[:160]]
    except Exception as e:
        traceback.print_exc(); row = [task.instance_id, task.repo, False, None, 0, None, None, repr(e)[:160]]
    rows.append(row)
    print(f'[{idx}] {row[0]} resolved={row[2]} calls={row[5]} dur={row[6]}s patch={row[4]} | total {sum(1 for x in rows if x[2])}/{len(rows)}', flush=True)
    with open(OUT / 'results.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    json.dump(patches, open(OUT / 'patches.json', 'w'))
server.stop()
print(f'DONE resolved {sum(1 for x in rows if x[2])}/{len(rows)} in {(time.time() - t0) / 3600:.2f} h; bundle {BUNDLE_HASH}', flush=True)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["controls", "agent"]); ap.add_argument("out"); ap.add_argument("slug"); ap.add_argument("title")
    ap.add_argument("--bundle"); ap.add_argument("--order-csv"); ap.add_argument("--hours", type=float, default=4.0)
    ap.add_argument("--concurrency", type=int, default=4); ap.add_argument("--machine", default="NvidiaL4")   # "GPU L4 x4" (unknown ids silently fall back to T4 x2)
    a = ap.parse_args()
    order = []
    if a.order_csv:   # sound tasks first, round-robin across repos so a time cut still covers every repo; unsound last
        rows = list(csv.DictReader(open(a.order_csv)))
        by_repo = {}
        for r in rows:
            if r.get("sound") == "True": by_repo.setdefault(r["instance_id"].split("_")[0], []).append(r["instance_id"])
        queues = list(by_repo.values())
        while any(queues):
            for q in queues:
                if q: order.append(q.pop(0))
        order += [r["instance_id"] for r in rows if r["instance_id"] not in set(order)]
    head = f"MODE = {a.mode!r}\nTASK_ORDER = {json.dumps(order)}\nHOURS = {a.hours}\nCONCURRENCY = {a.concurrency}\n"
    meta_models, files, digest = [], {}, ""
    if a.mode == "agent":
        pkg = Path(a.bundle)
        for p in sorted(pkg.rglob("*")):
            if p.is_file(): files[p.relative_to(pkg).as_posix()] = p.read_text(encoding="utf-8")
        assert "agent.yaml" in files
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
        # the root may be a workflow agent (SequentialAgent) whose model lives in sub_agents/*.yaml
        model = next(l.split(":", 1)[1].strip() for k in sorted(files, key=lambda k: k != "agent.yaml") if k.endswith((".yaml", ".yml"))
                     for l in files[k].splitlines() if l.strip().startswith("model:"))
        meta_models = [f"google/gemma-4/Other/{model}/2"]
        head += f"import hashlib\nFILES = {json.dumps(files, indent=1)}\nBUNDLE_HASH = {digest!r}\n"
    code = head + ENV_AND_WHEELS + (CONTROLS if a.mode == "controls" else AGENT)
    compile(code, "nb", "exec")
    md = (f"# {a.title}\n\nScores on Kaggle's own environment with the harness Evaluator (subprocess sandbox). Mode `{a.mode}`"
          + (f", bundle hash `{digest}`, time budget {a.hours} h." if a.mode == "agent" else ": gold vs empty patch on every public task."))
    nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": md.splitlines(True)},
                    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": code.splitlines(True)}],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fn = a.slug.split("/")[1] + ".ipynb"; json.dump(nb, open(out / fn, "w"), indent=1)
    meta = {"id": a.slug, "title": a.title, "code_file": fn, "language": "python", "kernel_type": "notebook", "is_private": True,
            "enable_gpu": a.mode == "agent", "enable_tpu": False, "enable_internet": False,
            "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"], "kernel_sources": [],
            "competition_sources": ["gemma-4-developer-agent"], "model_sources": meta_models}
    # the wheelhouse is cp312: pin the image the official getting-started notebook runs on (the default image is py3.13)
    meta["docker_image"] = "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"
    if a.mode == "agent": meta["machine_shape"] = a.machine
    json.dump(meta, open(out / "kernel-metadata.json", "w"), indent=2)
    print("notebook", out / fn, "mode", a.mode, "tasks ordered", len(order), "bundle", digest or "-")


if __name__ == "__main__":
    main()
