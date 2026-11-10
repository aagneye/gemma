#!/usr/bin/env python3
"""Generate a Kaggle 4xL4 notebook that measures the 31B's generation speed with and without a LoRA adapter, served
exactly like the scorer (adk_submission VllmServer from the competition wheelhouse, as make_kaggle_eval.py agent mode).
A speed measurement only: no agent runs, no tasks (user approval 2026-11-10: one short check before an adapter bundle
takes a daily slot; Kaggle GPUs are otherwise never used for tests).

  python make_kaggle_speed.py <out_dir> <owner/slug> "<title>" --bundle submissions/budgetfit_v5_lora1 \
      --adapter-dataset aagneye/gemma4-31b-lora1-adapter
  kaggle kernels push -p <out_dir> --accelerator NvidiaL4 -t 5400
The bundle's text files are embedded; its adapter weights come from the attached private dataset (they are binary and
too large for the notebook). Output: /kaggle/working/eval/speed.json (tokens/s for base and adapter at 1 and 4
concurrent requests, and a long-prompt case per model).
"""
import argparse, hashlib, json
from pathlib import Path
from make_kaggle_eval import ENV_AND_WHEELS

SPEED = r"""
AGENT_DIR = WORK / 'agent'; shutil.rmtree(AGENT_DIR, ignore_errors=True)
for rel, text in FILES.items():
    p = AGENT_DIR / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')
src = Path(sorted(glob.glob('/kaggle/input/**/adapter_model.safetensors', recursive=True))[0]).parent
dst = AGENT_DIR / 'adapters' / 'main_lora'; dst.mkdir(parents=True, exist_ok=True)
for f in src.iterdir():
    if f.is_file(): shutil.copyfile(f, dst / f.name)
import torch, urllib.request
from adk_submission import VllmConfig, VllmServer, discover_adapters
from adk_submission.discovery import discover_declared_models
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
declared = discover_declared_models(AGENT_DIR); model = next(iter(declared))
MODEL_PATH = Path(f'/kaggle/input/models/google/gemma-4/other/{model}/2')
if not MODEL_PATH.exists():
    MODEL_PATH = Path(sorted(glob.glob(f'/kaggle/input/**/{model}/**/config.json', recursive=True))[0]).parent
adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
amap = getattr(adapters, 'adapters', None) or {}; assert amap, 'no adapter found in the bundle'
ranks = [r for i in amap.values() if (r := getattr(i, 'rank', None))]
ngpu = torch.cuda.device_count(); tp = 4 if ngpu >= 4 else (2 if ngpu >= 2 else 1)
gpu_name = torch.cuda.get_device_name(0) if ngpu else 'none'
print(f'model {model}; gpus {ngpu} ({gpu_name}); tp {tp}; adapters {list(amap)} ranks {ranks}', flush=True)
t_start = time.time()
server = VllmServer(VllmConfig(model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4', reasoning_parser='gemma4',
                               max_model_len=32768, dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto',
                               gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=True,
                               max_loras=max(1, len(amap)), max_lora_rank=max(ranks) if ranks else 128,
                               scheduler_reserve_full_isl=False, tensor_parallel_size=tp, startup_timeout=60 * 20),
                    adapter_manifest=adapters)
server.start(); up_min = round((time.time() - t_start) / 60, 1); print(f'vLLM up in {up_min} min', flush=True)
ids = [m['id'] for m in json.load(urllib.request.urlopen('http://127.0.0.1:8000/v1/models'))['data']]
lora_id = next(i for i in ids if i in amap); base_id = next(i for i in ids if i not in amap)
LONG = ' '.join(['The quick brown fox jumps over the lazy dog while the compiler reports a type error in module seven.'] * 300)
def one(mid, i, n, long=False):
    text = (LONG + f' ({i}) Summarise the text above in one line.') if long else f'({i}) Explain in detail how the Python import system finds and loads a module: sys.path, finders, loaders and caching. Write at least 400 words.'
    body = {'model': mid, 'messages': [{'role': 'user', 'content': text}], 'max_tokens': n, 'temperature': 0,
            'chat_template_kwargs': {'enable_thinking': False}}
    req = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    u = json.load(urllib.request.urlopen(req, timeout=900))['usage']; return u['completion_tokens'], u['prompt_tokens']
report = {'gpu': gpu_name, 'tp': tp, 'vllm_up_min': up_min, 'base_id': base_id, 'lora_id': lora_id, 'ranks': ranks, 'runs': []}
for case, conc, n, long in (('decode', 1, 500, False), ('decode', 4, 400, False), ('long_prompt', 1, 100, True)):
    for mid in (base_id, lora_id, base_id, lora_id):
        t = time.time()
        with concurrent.futures.ThreadPoolExecutor(conc) as ex: res = list(ex.map(lambda i: one(mid, i, n, long), range(conc)))
        el = time.time() - t; out = sum(r[0] for r in res); inp = sum(r[1] for r in res)
        rec = {'case': case, 'model': 'adapter' if mid == lora_id else 'base', 'concurrency': conc, 'out_tokens': out, 'prompt_tokens': inp,
               'sec': round(el, 2), 'out_tok_s': round(out / el, 2)}
        report['runs'].append(rec); print(rec, flush=True)
for case, conc in (('decode', 1), ('decode', 4), ('long_prompt', 1)):
    sec = {m: sum(r['sec'] for r in report['runs'] if r['case'] == case and r['concurrency'] == conc and r['model'] == m) for m in ('base', 'adapter')}
    report[f'slowdown_{case}_c{conc}'] = round(sec['adapter'] / sec['base'], 3)
print({k: v for k, v in report.items() if k.startswith('slowdown')}, flush=True)
json.dump(report, open(OUT / 'speed.json', 'w'), indent=1)
server.stop()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("slug"); ap.add_argument("title")
    ap.add_argument("--bundle", required=True); ap.add_argument("--adapter-dataset", required=True)
    ap.add_argument("--machine", default="NvidiaL4")
    a = ap.parse_args()
    pkg = Path(a.bundle)
    files = {p.relative_to(pkg).as_posix(): p.read_text(encoding="utf-8") for p in sorted(pkg.rglob("*"))
             if p.is_file() and not p.relative_to(pkg).as_posix().startswith("adapters/")}
    assert "adapter: main_lora" in files["agent.yaml"], "the bundle must declare its adapter (adapter: main_lora)"
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    model = next(l.split(":", 1)[1].strip() for l in files["agent.yaml"].splitlines() if l.strip().startswith("model:"))
    head = f"MODE = 'speed'\nTASK_ORDER = []\nHOURS = 0\nCONCURRENCY = 1\nimport hashlib\nFILES = {json.dumps(files, indent=1)}\nBUNDLE_HASH = {digest!r}\n"
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
