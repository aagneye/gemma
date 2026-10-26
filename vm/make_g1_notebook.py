#!/usr/bin/env python3
"""Generate the G1 Kaggle notebook (adapter load + effect test on the scorer's own stack).

It serves the bundle's model WITH its LoRA adapter exactly as the scorer does (pinned image, wheelhouse install,
`VllmServer` + `discover_adapters`), sends N_PROBE harness-style prompts at temperature 0 to the base alias and to the
adapter alias, reports how many outputs differ, the tool-call parse rate and the decode tok/s of both, then runs
N_TASKS full tasks through the harness Evaluator (subprocess sandbox) with the adapter bundle.

  python make_g1_notebook.py <out_dir> <owner/slug> "<title>" --bundle submissions/e4b_v5_smoke \
      --adapter-dataset aagneye/gemma4-e4b-smoke-adapter [--order-csv results/kaggle_soundness.csv] [--n-probe 20] [--n-tasks 3]
  python make_g1_notebook.py --prepare-adapter-dataset submissions/e4b_v5_smoke aagneye/gemma4-e4b-smoke-adapter <dir>
      # copies adapters/main_lora/* + dataset-metadata.json into <dir>; then: kaggle datasets create -p <dir>
Adapter weights cannot be embedded as notebook text, so they travel as a private Kaggle dataset (attached through
kernel-metadata.json dataset_sources) and are copied into agent/adapters/main_lora/ inside the kernel.
Kernel outputs (/kaggle/working/eval): g1_probe.json (per-prompt records + summary), results.csv + patches.json (full tasks).
"""
import argparse, csv, hashlib, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_kaggle_eval import ENV_AND_WHEELS   # pinned env + wheelhouse install + task loading (shared with the eval notebooks)

G1 = r'''
# ---------------------------------------------------------------- bundle + adapter -------------------------------
AGENT_DIR = WORK / 'agent'; shutil.rmtree(AGENT_DIR, ignore_errors=True)
for rel, text in FILES.items():
    p = AGENT_DIR / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')
assert hashlib.sha256(json.dumps(FILES, sort_keys=True).encode()).hexdigest()[:16] == BUNDLE_HASH
cands = [Path(p) for p in glob.glob('/kaggle/input/**/adapter_config.json', recursive=True) if 'wheelhouse' not in p]
slug = ADAPTER_DATASET.split('/')[-1]
pick = [c for c in cands if slug in str(c)] or cands
assert pick, f'no adapter_config.json found under /kaggle/input (dataset {ADAPTER_DATASET} attached?)'
adir = pick[0].parent; dst = AGENT_DIR / 'adapters' / 'main_lora'; dst.mkdir(parents=True, exist_ok=True)
for f in adir.iterdir():
    if f.is_file() and f.suffix in ('.json', '.safetensors'): shutil.copyfile(f, dst / f.name)
print('adapter files:', sorted(p.name for p in dst.iterdir()), 'from', adir, flush=True)
import litellm, torch, yaml, urllib.request, statistics
from adk_submission import VllmConfig, VllmServer, discover_adapters, validate_directory
from adk_submission.discovery import discover_declared_models
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS, EvalConfig, build_submission_limits
from swegemma.evaluate import Evaluator
from swegemma.harness.agent_runner import build_agent_prompt
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
litellm.drop_params = True
limits, gen = build_submission_limits()
validate_directory(AGENT_DIR, limits=limits)
declared = discover_declared_models(AGENT_DIR); assert len(declared) == 1, declared; model = next(iter(declared))
MODEL_PATH = Path(f'/kaggle/input/models/google/gemma-4/other/{model}/2')
if not MODEL_PATH.exists():
    MODEL_PATH = Path(sorted(glob.glob(f'/kaggle/input/**/{model}/**/config.json', recursive=True))[0]).parent
adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
amap = getattr(adapters, 'adapters', None) or {}
assert 'main_lora' in amap, f'adapter not discovered: {list(amap)}'
ranks = [r for i in amap.values() if (r := getattr(i, 'rank', None))]
ngpu = torch.cuda.device_count(); tp = 4 if ngpu >= 4 else (2 if ngpu >= 2 else 1)
print(f'model {model} at {MODEL_PATH}; gpus {ngpu} ({torch.cuda.get_device_name(0) if ngpu else "none"}); tp {tp}; adapters {dict((k, getattr(v, "rank", None)) for k, v in amap.items())}', flush=True)
extra = ('--hf-overrides', '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}') if model == 'gemma-4-12b-it-qat-w4a16-ct' else ()
t_start = time.time()
server = VllmServer(VllmConfig(model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4', reasoning_parser='gemma4',
                               max_model_len=32768, dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto',
                               gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=True,
                               max_loras=max(1, len(amap)), max_lora_rank=max(ranks) if ranks else 128,
                               scheduler_reserve_full_isl=False, tensor_parallel_size=tp, startup_timeout=60 * 20, extra_args=extra),
                    adapter_manifest=adapters)
server.start(); print(f'vLLM up in {(time.time() - t_start) / 60:.1f} min; cmd tail: {" ".join(server.build_cmd()[-12:])}', flush=True)
models = server.create_model_registry(aliases=[model], model_prefix='openai/', api_key='EMPTY')
print('registry aliases:', models.list_available(), flush=True)
base_url = server.base_url.rstrip('/')
if not base_url.endswith('/v1'): base_url += '/v1'
served = [m['id'] for m in json.load(urllib.request.urlopen(base_url + '/models'))['data']]
adapter_id = 'main_lora'; base_id = next(m for m in served if m != adapter_id and m not in amap)
print('served models:', served, '| base:', base_id, '| adapter:', adapter_id, flush=True)

# ---------------------------------------------------------------- G1 probe: 20 prompts, T=0, base vs adapter -----
from types import SimpleNamespace
from openai import OpenAI
client = OpenAI(base_url=base_url, api_key='EMPTY', timeout=600)
ecf = next((c for n in ('eval_config.yaml', 'eval_config.yml') if (c := AGENT_DIR / n).is_file()), None)
raw = (yaml.safe_load(ecf.read_text()) or {}) if ecf else {}; ev = raw.get('evaluation', raw)
turns = ev.get('max_turns', ev.get('max_llm_calls'))
sampling = {}
for p in sorted(AGENT_DIR.rglob('*.yaml')):
    d = yaml.safe_load(p.read_text()) or {}
    if isinstance(d, dict) and 'temperature' in d: sampling = d; break
sys_prompt = next((FILES[k] for k in ('prompts/system.md',) if k in FILES), None) or next(FILES[k] for k in sorted(FILES) if k.startswith('prompts/'))
pcfg = SimpleNamespace(budget=SimpleNamespace(time_minutes=float(ev.get('max_time_minutes', 60.0)), tool_calls=int(ev.get('max_tool_calls', 100)),
                                              turns=int(turns) if turns is not None else None, cost_usd=None),
                       harness=SimpleNamespace(command_timeout_seconds=int(ev.get('timeout_seconds', 300)), max_stdout_chars=5000, max_file_lines=150, max_file_chars=10000),
                       graph_dir=None, embeddings_dir=None, enable_sandbox_testing=True)
PRUNED = ('docs', 'docs_src', 'tests', 'test_data', 'examples', 'benchmarks', 'assets', 'imgs', 'questions', 'site', 'g3doc', 'google3')

def workspace_tree(task):
    """Approximate the harness's `find . -mindepth 1 -maxdepth 3 … | sort -n -k1 | head -200 | sort` on the snapshot
    (a .tgz archive or an extracted directory) without starting a sandbox."""
    import tarfile
    names = []
    tgz = next((Path(p) for p in glob.glob(str(DATA_DIR / 'snapshots' / f'{task.instance_id}*.t*gz'))), None)
    if tgz is not None:
        try:
            with tarfile.open(tgz) as tf: names = [m.name for m in tf.getmembers()]
        except Exception as e:
            print('tree: cannot read', tgz, repr(e)[:100]); return ''
    else:
        root = next((Path(p) for p in glob.glob(str(DATA_DIR / 'snapshots' / f'{task.instance_id}*')) if Path(p).is_dir()), None)
        if root is None: return ''
        for dp, dns, fns in os.walk(root):
            rel = Path(dp).relative_to(root)
            names += [str(rel / d) for d in dns] + [str(rel / f) for f in fns]
    parts = [tuple(x for x in n.replace(os.sep, '/').strip('/').split('/') if x and x != '.') for n in names]
    parts = [p for p in parts if p]
    if parts and len({p[0] for p in parts}) == 1 and all(len(p) > 1 for p in parts if len(p) > 0) and sum(1 for p in parts if len(p) == 1) <= 1:
        parts = [p[1:] for p in parts if len(p) > 1]            # archives carry one top-level dir (e.g. workspace/)
    keep = []
    for p in parts:
        if not p or len(p) > 3 or p[0] in PRUNED: continue
        if any(x.startswith('.') or x == '__pycache__' or x.endswith('.egg-info') or x.endswith('.pyc') for x in p): continue
        keep.append((len(p), './' + '/'.join(p)))
    keep = sorted(set(keep))[:200]
    return '\n'.join(sorted(p for _, p in keep))

def tool_calls_of(msg):
    return [{'name': tc.function.name, 'arguments': tc.function.arguments} for tc in (getattr(msg, 'tool_calls', None) or [])]

# what the harness adds per request (adk_submission.resolvers.generation.apply_thinking_config_to_model)
tb = int(((sampling.get('thinking_config') or {}).get('thinking_budget')) or 0)
EXTRA_BODY = {'chat_template_kwargs': {'enable_thinking': tb > 0}}
if tb > 0: EXTRA_BODY['thinking_token_budget'] = tb
print('probe extra_body:', EXTRA_BODY, '| max_tokens', PROBE_MAX_TOKENS, flush=True)

def probe(mid, msgs):
    t0 = time.time()
    try:
        r = client.chat.completions.create(model=mid, messages=msgs, tools=TOOLS, temperature=0.0, top_p=1.0, max_tokens=PROBE_MAX_TOKENS, seed=0, extra_body=EXTRA_BODY)
    except Exception as e:
        return {'model': mid, 'error': repr(e)[:300], 'elapsed': round(time.time() - t0, 2)}
    el = time.time() - t0; m = r.choices[0].message; u = r.usage
    return {'model': mid, 'elapsed': round(el, 2), 'prompt_tokens': getattr(u, 'prompt_tokens', None), 'completion_tokens': getattr(u, 'completion_tokens', None),
            'tok_s': round((getattr(u, 'completion_tokens', 0) or 0) / max(el, 1e-6), 2), 'finish': r.choices[0].finish_reason,
            'content': (m.content or '')[:2000], 'reasoning': (getattr(m, 'reasoning_content', None) or getattr(m, 'reasoning', None) or '')[:2000],
            'tool_calls': tool_calls_of(m)}

records = []
probe_tasks = order[:N_PROBE]
for i, task in enumerate(probe_tasks, start=1):
    user = build_agent_prompt(task, pcfg, workspace_tree=workspace_tree(task), declared_tools=TOOL_NAMES)
    msgs = [{'role': 'system', 'content': sys_prompt}, {'role': 'user', 'content': user}]
    rec = {'instance_id': task.instance_id, 'base': probe(base_id, msgs), 'adapter': probe(adapter_id, msgs)}
    b, a = rec['base'], rec['adapter']
    same = (b.get('tool_calls') == a.get('tool_calls')) and ((b.get('content') or '').strip() == (a.get('content') or '').strip())
    rec['differs'] = not same
    records.append(rec)
    print(f"[{i}/{len(probe_tasks)}] {task.instance_id}: base {[t['name'] for t in b.get('tool_calls', [])]} {b.get('tok_s')} tok/s | "
          f"adapter {[t['name'] for t in a.get('tool_calls', [])]} {a.get('tok_s')} tok/s | differs={rec['differs']}", flush=True)
    json.dump(records, open(OUT / 'g1_probe.json', 'w'), indent=1)

def summarise(key):
    rs = [r[key] for r in records if 'error' not in r[key]]
    return {'n': len(rs), 'errors': sum(1 for r in records if 'error' in r[key]),
            'parse_rate': round(sum(1 for r in rs if r['tool_calls']) / max(1, len(rs)), 3),
            'reasoning_rate': round(sum(1 for r in rs if r['reasoning']) / max(1, len(rs)), 3),
            'tok_s_median': round(statistics.median([r['tok_s'] for r in rs]), 2) if rs else None,
            'completion_tokens_median': statistics.median([r['completion_tokens'] or 0 for r in rs]) if rs else None,
            'elapsed_median': round(statistics.median([r['elapsed'] for r in rs]), 2) if rs else None,
            'finish': dict(collections.Counter(r['finish'] for r in rs))}
import collections
summary = {'model': model, 'adapter_rank': ranks, 'n_probe': len(records), 'n_differ': sum(1 for r in records if r['differs']),
           'base': summarise('base'), 'adapter': summarise('adapter'), 'vllm_cmd_tail': server.build_cmd()[-14:], 'bundle': BUNDLE_HASH}
json.dump({'summary': summary, 'records': records}, open(OUT / 'g1_probe.json', 'w'), indent=1)
print('G1 SUMMARY', json.dumps(summary), flush=True)
print(f"G1 VERDICT: differ {summary['n_differ']}/{summary['n_probe']} (gate >= 15/20) | parse base {summary['base']['parse_rate']} adapter {summary['adapter']['parse_rate']} (gate: all parse) | "
      f"tok/s base {summary['base']['tok_s_median']} adapter {summary['adapter']['tok_s_median']}", flush=True)

# ---------------------------------------------------------------- N_TASKS full tasks with the adapter bundle -----
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
for idx, task in enumerate(order[:N_TASKS], start=1):
    try:
        r = run_sync(evaluator.evaluate_task, task=task, task_index=idx, total_tasks=N_TASKS)
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
summary['full_tasks'] = {'resolved': sum(1 for x in rows if x[2]), 'n': len(rows), 'hours': round((time.time() - t0) / 3600, 2), 'rows': rows}
json.dump(summary, open(OUT / 'g1_summary.json', 'w'), indent=1)
print(f"DONE G1: differ {summary['n_differ']}/{summary['n_probe']}, full tasks {summary['full_tasks']['resolved']}/{len(rows)} in {summary['full_tasks']['hours']} h; bundle {BUNDLE_HASH}", flush=True)
'''


def task_order(order_csv):
    order = []
    if order_csv:   # sound tasks first, round-robin across repos
        rows = list(csv.DictReader(open(order_csv)))
        by_repo = {}
        for r in rows:
            if r.get("sound") == "True": by_repo.setdefault(r["instance_id"].split("_")[0], []).append(r["instance_id"])
        queues = list(by_repo.values())
        while any(queues):
            for q in queues:
                if q: order.append(q.pop(0))
        order += [r["instance_id"] for r in rows if r["instance_id"] not in set(order)]
    return order


def prepare_adapter_dataset(bundle, dataset_id, out):
    src = Path(bundle) / "adapters" / "main_lora"; out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for f in ("adapter_config.json", "adapter_model.safetensors"): shutil.copyfile(src / f, out / f)
    owner, slug = dataset_id.split("/")
    json.dump({"title": slug, "id": dataset_id, "licenses": [{"name": "CC0-1.0"}]}, open(out / "dataset-metadata.json", "w"), indent=1)
    print(f"adapter dataset dir {out}: {[p.name for p in out.iterdir()]}\n  upload with:  kaggle datasets create -p {out}   (or `kaggle datasets version -p {out} -m update` for a new version)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?"); ap.add_argument("slug", nargs="?"); ap.add_argument("title", nargs="?")
    ap.add_argument("--bundle"); ap.add_argument("--adapter-dataset", help="owner/slug of the private Kaggle dataset holding adapters/main_lora/*")
    ap.add_argument("--order-csv"); ap.add_argument("--n-probe", type=int, default=20); ap.add_argument("--n-tasks", type=int, default=3)
    ap.add_argument("--probe-max-tokens", type=int, default=2048); ap.add_argument("--machine", default="NvidiaL4")
    ap.add_argument("--prepare-adapter-dataset", nargs=3, metavar=("BUNDLE", "OWNER/SLUG", "DIR"))
    a = ap.parse_args()
    if a.prepare_adapter_dataset:
        return prepare_adapter_dataset(*a.prepare_adapter_dataset)
    assert a.out and a.slug and a.title and a.bundle and a.adapter_dataset, "need out, slug, title, --bundle and --adapter-dataset"
    pkg = Path(a.bundle); files = {}
    for p in sorted(pkg.rglob("*")):
        if p.is_file() and "adapters" not in p.relative_to(pkg).parts and p.suffix != ".zip":
            files[p.relative_to(pkg).as_posix()] = p.read_text(encoding="utf-8")
    assert "agent.yaml" in files and (pkg / "adapters" / "main_lora" / "adapter_config.json").is_file(), "bundle must carry adapters/main_lora"
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    model = next(l.split(":", 1)[1].strip() for k in sorted(files, key=lambda k: k != "agent.yaml") if k.endswith((".yaml", ".yml"))
                 for l in files[k].splitlines() if l.strip().startswith("model:"))
    tool_names = [l.strip()[2:].strip() for l in files["agent.yaml"].splitlines() if l.strip().startswith("- ")] or \
                 ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch"]
    decls = {t["function"]["name"]: t for t in json.load(open(HERE / "tool_declarations.json", encoding="utf-8"))}
    tools = [decls[n] for n in tool_names if n in decls]
    order = task_order(a.order_csv)
    head = (f"MODE = 'agent'\nTASK_ORDER = {json.dumps(order)}\nHOURS = 4.0\nCONCURRENCY = 1\nN_PROBE = {a.n_probe}\nN_TASKS = {a.n_tasks}\n"
            f"PROBE_MAX_TOKENS = {a.probe_max_tokens}\nADAPTER_DATASET = {a.adapter_dataset!r}\nTOOL_NAMES = {json.dumps(tool_names)}\n"
            f"TOOLS = {json.dumps(tools)}\nimport hashlib\nFILES = {json.dumps(files, indent=1)}\nBUNDLE_HASH = {digest!r}\n")
    code = head + ENV_AND_WHEELS + G1
    compile(code, "nb", "exec")
    md = (f"# {a.title}\n\nG1 adapter gate on the scorer's stack: `{model}` + LoRA `main_lora` from dataset `{a.adapter_dataset}`, bundle hash `{digest}`. "
          f"{a.n_probe} prompts at T=0 (base vs adapter: differ count, tool-call parse rate, decode tok/s), then {a.n_tasks} full tasks.")
    nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": md.splitlines(True)},
                    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": code.splitlines(True)}],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fn = a.slug.split("/")[1] + ".ipynb"; json.dump(nb, open(out / fn, "w"), indent=1)
    meta = {"id": a.slug, "title": a.title, "code_file": fn, "language": "python", "kernel_type": "notebook", "is_private": True,
            "enable_gpu": True, "enable_tpu": False, "enable_internet": False,
            "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse", a.adapter_dataset], "kernel_sources": [],
            "competition_sources": ["gemma-4-developer-agent"], "model_sources": [f"google/gemma-4/Other/{model}/2"],
            "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461",
            "machine_shape": a.machine}
    json.dump(meta, open(out / "kernel-metadata.json", "w"), indent=2)
    print("notebook", out / fn, "| model", model, "| tools", tool_names, "| tasks ordered", len(order), "| bundle", digest, "| adapter dataset", a.adapter_dataset)


if __name__ == "__main__":
    main()
