#!/usr/bin/env python3
"""Generate a Kaggle 4xL4 notebook that measures how much slower the 31B generates with a LoRA adapter, served exactly
like the scorer (adk_submission VllmServer from the competition wheelhouse, as make_kaggle_eval.py agent mode).
A speed measurement only: no agent runs, no tasks (user approvals 2026-11-10 and 2026-11-11: one short check before an
adapter bundle takes a daily slot; Kaggle GPUs are otherwise never used for tests).

  python make_kaggle_speed.py <out_dir> <owner/slug> "<Title>" --bundle submissions/budgetfit_v5_lora1 \
      --adapter-dataset aagneye/gemma4-31b-lora1-adapter
  kaggle kernels push -p <out_dir> --accelerator NvidiaL4 -t 5400
Two servers, one after the other, as the scorer would start them:
  1. the bundle without its adapter -> LoRA off (how Budget-Fit is served): arm `base_plain`;
  2. the bundle with its adapter    -> LoRA on: arms `adapter` and, for reference, `base_on_lora_server`.
Every request forces the same number of output tokens (ignore_eos) and starts with a unique tag (no prefix-cache hits).
The bundle's text files are embedded; the adapter weights come from the attached private dataset.
Output: /kaggle/working/eval/speed.json with slowdown_<case>_c<requests> = adapter seconds / base_plain seconds.
"""
import argparse, hashlib, json, re
from pathlib import Path
from make_kaggle_eval import ENV_AND_WHEELS

SPEED = r"""
import torch, urllib.request
from adk_submission import VllmConfig, VllmServer, discover_adapters
from adk_submission.discovery import discover_declared_models
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
BASE_DIR = WORK / 'agent_base'; AGENT_DIR = WORK / 'agent'
for d in (BASE_DIR, AGENT_DIR):
    shutil.rmtree(d, ignore_errors=True)
    for rel, text in FILES.items():
        p = d / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')
assert hashlib.sha256(json.dumps(FILES, sort_keys=True).encode()).hexdigest()[:16] == BUNDLE_HASH
(BASE_DIR / 'agent.yaml').write_text(re.sub(r'^adapter:.*\n', '', FILES['agent.yaml'], flags=re.M), encoding='utf-8')
# by dataset name: the competition data holds sample adapters too (sample_submission/adapters/{main,tool}_lora)
src = sorted(glob.glob(f'/kaggle/input/**/{ADAPTER_DS}/adapter_model.safetensors', recursive=True)); assert len(src) == 1, src
src = Path(src[0]).parent
dst = AGENT_DIR / 'adapters' / 'main_lora'; dst.mkdir(parents=True, exist_ok=True)
for f in src.iterdir():
    if f.is_file() and f.name.startswith('adapter_'): shutil.copyfile(f, dst / f.name)
declared = discover_declared_models(AGENT_DIR); model = next(iter(declared))
MODEL_PATH = Path(f'/kaggle/input/models/google/gemma-4/other/{model}/2')
if not MODEL_PATH.exists():
    MODEL_PATH = Path(sorted(glob.glob(f'/kaggle/input/**/{model}/**/config.json', recursive=True))[0]).parent
ngpu = torch.cuda.device_count(); tp = 4 if ngpu >= 4 else (2 if ngpu >= 2 else 1)
gpu_name = torch.cuda.get_device_name(0) if ngpu else 'none'
print(f'model {model}; gpus {ngpu} ({gpu_name}); tp {tp}', flush=True)

def start(bundle_dir):
    # the agent-mode server of make_kaggle_eval.py (= the scorer): LoRA on only when the bundle holds adapters
    ads = discover_adapters(str(bundle_dir), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
    amap = getattr(ads, 'adapters', None) or {}
    ranks = [r for i in amap.values() if (r := getattr(i, 'rank', None))]
    t = time.time()
    s = VllmServer(VllmConfig(model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4', reasoning_parser='gemma4',
                              max_model_len=32768, dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto',
                              gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=bool(amap),
                              max_loras=max(1, len(amap)), max_lora_rank=max(ranks) if ranks else 128,
                              scheduler_reserve_full_isl=False, tensor_parallel_size=tp, startup_timeout=60 * 20),
                   adapter_manifest=ads)
    s.start(); up = round((time.time() - t) / 60, 1)
    ids = [m['id'] for m in json.load(urllib.request.urlopen('http://127.0.0.1:8000/v1/models'))['data']]
    print(f'vLLM up in {up} min; lora {bool(amap)} ranks {ranks}; served {ids}', flush=True)
    return s, amap, ranks, ids, up

LONG = ' '.join(['The quick brown fox jumps over the lazy dog while the compiler reports a type error in module seven.'] * 300)
def one(mid, tag, n, long=False):
    text = (f'[{tag}] ' + LONG + ' Summarise the text above in one line.') if long else f'[{tag}] Explain in detail how the Python import system finds and loads a module: sys.path, finders, loaders and caching. Write at least 400 words.'
    body = {'model': mid, 'messages': [{'role': 'user', 'content': text}], 'max_tokens': n, 'temperature': 0, 'ignore_eos': True,
            'chat_template_kwargs': {'enable_thinking': False}}
    req = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    u = json.load(urllib.request.urlopen(req, timeout=900))['usage']; return u['completion_tokens'], u['prompt_tokens']

CASES = (('decode', 1, 500, False), ('decode', 4, 400, False), ('long_prompt', 1, 64, True))
def bench(arm, mid, rounds=2):
    one(mid, f'warm-{arm}', 16); one(mid, f'warm-{arm}-long', 8, True)
    recs = []
    for case, conc, n, long in CASES:
        for r in range(rounds):
            t = time.time()
            with concurrent.futures.ThreadPoolExecutor(conc) as ex:
                res = list(ex.map(lambda i: one(mid, f'{arm}-{case}-{conc}-{r}-{i}', n, long), range(conc)))
            el = time.time() - t; out = sum(x[0] for x in res); inp = sum(x[1] for x in res)
            rec = {'arm': arm, 'case': case, 'concurrency': conc, 'round': r, 'out_tokens': out, 'prompt_tokens': inp,
                   'sec': round(el, 2), 'out_tok_s': round(out / el, 2)}
            recs.append(rec); print(rec, flush=True)
    return recs

report = {'gpu': gpu_name, 'ngpu': ngpu, 'tp': tp, 'model': model, 'bundle': BUNDLE_HASH, 'runs': []}
server, amap, ranks, ids, up = start(BASE_DIR); assert not amap
report['vllm_up_min_plain'] = up
report['runs'] += bench('base_plain', ids[0])
server.stop(); time.sleep(30)
server, amap, ranks, ids, up = start(AGENT_DIR); assert amap, 'no adapter found in the bundle'
report['vllm_up_min_lora'] = up; report['ranks'] = ranks
lora_id = next(i for i in ids if i in amap); base_id = next(i for i in ids if i not in amap)
report['runs'] += bench('adapter', lora_id)
report['runs'] += bench('base_on_lora_server', base_id)
server.stop()
def secs(arm, case, conc): return sum(x['sec'] for x in report['runs'] if x['arm'] == arm and x['case'] == case and x['concurrency'] == conc)
for case, conc, n, long in CASES:
    report[f'slowdown_{case}_c{conc}'] = round(secs('adapter', case, conc) / secs('base_plain', case, conc), 3)
    report[f'lora_server_base_{case}_c{conc}'] = round(secs('base_on_lora_server', case, conc) / secs('base_plain', case, conc), 3)
print({k: v for k, v in report.items() if k.startswith(('slowdown', 'lora_server', 'vllm_up'))}, flush=True)
json.dump(report, open(OUT / 'speed.json', 'w'), indent=1)
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("slug"); ap.add_argument("title")
    ap.add_argument("--bundle", required=True); ap.add_argument("--adapter-dataset", required=True)
    ap.add_argument("--machine", default="NvidiaL4")
    a = ap.parse_args()
    assert a.slug.split("/")[1] == re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-"), "the slug must equal the slugified title"
    pkg = Path(a.bundle)
    files = {p.relative_to(pkg).as_posix(): p.read_text(encoding="utf-8") for p in sorted(pkg.rglob("*"))
             if p.is_file() and not p.relative_to(pkg).as_posix().startswith("adapters/")}
    assert "adapter: main_lora" in files["agent.yaml"], "the bundle must declare its adapter (adapter: main_lora)"
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    model = next(l.split(":", 1)[1].strip() for l in files["agent.yaml"].splitlines() if l.strip().startswith("model:"))
    head = f"MODE = 'speed'\nTASK_ORDER = []\nHOURS = 0\nCONCURRENCY = 1\nimport hashlib\nFILES = {json.dumps(files, indent=1)}\nBUNDLE_HASH = {digest!r}\nADAPTER_DS = {a.adapter_dataset.split('/')[1]!r}\n"
    code = head + ENV_AND_WHEELS + SPEED
    compile(code, "nb", "exec")
    md = f"# {a.title}\n\nGeneration speed of `{model}` with and without the adapter, served like the scorer. No agent runs. Bundle `{digest}`."
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
    print("notebook", out / fn, "bundle", digest, "adapter dataset", a.adapter_dataset)


if __name__ == "__main__":
    main()
