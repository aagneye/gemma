#!/usr/bin/env python3
"""Generate a Kaggle notebook that trains a LoRA with train_qlora.py on Kaggle's 4x L4 (one process, --pipeline 4).
Kaggle GPUs are for TRAINING only (user rule, 2026-11-03): never evaluate or test agents with this notebook.

4x L4 is granted only to a notebook with the competition attached, internet OFF and machine_shape NvidiaL4 (pushed with
--accelerator NvidiaL4), so every input is attached:
  base model  google/gemma-4/transformers/<base>/2 (default gemma-4-31b-it-qat-q4_0-unquantized: bf16 QAT weights, 62 GB,
              loaded in NF4); the scorer applies the adapter to the matching -w4a16-ct model.
  wheels      metric/gemma-4-developer-agent-wheelhouse: transformers 5.13.1, bitsandbytes 0.46.1, safetensors 0.8.0,
              tokenizers 0.22.2. The pinned image already has torch 2.10.0+cu128, peft 0.19.1 and accelerate 1.13.0, but
              transformers 5.0.0 (no Gemma 4) and no bitsandbytes.
  our data    a private dataset <owner>/<slug>, flat (`kaggle datasets create` skips sub-directories): train_qlora.py,
              make_submission.py, train.parquet + stats.json. Tokenize the windows with the SERVING model's chat template
              (prepare_data.py --tokenize --model models/gemma-4-31b-it-qat-w4a16-ct): the unquantized model on Kaggle ships
              an older chat_template.jinja (16,934 bytes vs 18,683).

  python make_kaggle_train.py dataset <dir> aagneye/gemma4-31b-train-smoke --data scratch/k31b/tok_31b_16k_smoke
  kaggle datasets create -p <dir>                 (new data later: kaggle datasets version -p <dir> -m "<msg>")
  python make_kaggle_train.py notebook <out_dir> aagneye/gemma4-31b-lora-smoke --dataset aagneye/gemma4-31b-train-smoke \
      --minutes 95 --train-args "--max-len 16384 --rank 32 --lr 1e-4 --optim adamw --max-steps 20 --grad-accum 1 --log-every 1 --fit-probe"
  kaggle kernels push -p <out_dir> --accelerator NvidiaL4 -t 7200      (-t caps the session; --minutes stops training first)
  kaggle kernels status aagneye/gemma4-31b-lora-smoke;  kaggle kernels output aagneye/gemma4-31b-lora-smoke -p <download_dir>
Outputs (/kaggle/working): report.json (GPUs, versions, fit probe, step records, summary, G0 result), train.log,
run/train_log.jsonl, run/final (PEFT adapter, fp32 master weights), packaged/adapters/main_lora (fp16, make_submission.py G0 checks).
"""
import argparse, json, shlex, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"  # py3.12, as the wheelhouse

NB = r'''
import glob, json, os, shutil, subprocess, sys, time
from pathlib import Path
for k, v in {'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_PROGRESS_BARS': '1', 'TQDM_DISABLE': '1',
             'TRANSFORMERS_NO_TF': '1', 'TRANSFORMERS_NO_FLAX': '1', 'TOKENIZERS_PARALLELISM': 'false',
             'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True'}.items():
    os.environ.setdefault(k, v)
T0 = time.time(); WORK = Path('/kaggle/working'); RUN = WORK / 'run'
REPORT = {'dataset': DATASET, 'base_model': BASE_MODEL, 'target_model': TARGET_MODEL, 'train_args': TRAIN_ARGS, 'minutes': MINUTES}
def save(): json.dump(REPORT, open(WORK / 'report.json', 'w'), indent=1)
def out(cmd): return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

# 1. hardware: an unknown machine_shape silently falls back to T4 x2, so stop at once unless the L4s are there
gpus = [l.split(', ') for l in out(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits']).splitlines()]
REPORT['gpus'] = gpus; save(); print('GPUs:', gpus, flush=True)
assert len(gpus) >= PIPELINE and all('L4' in g[0] for g in gpus), f'expected {PIPELINE}x L4, got {gpus}'

# 2. wheels the image lacks, from the competition wheelhouse (internet is off)
WH = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
if not WH.exists():
    WH = Path(sorted(glob.glob('/kaggle/input/**/gemma-4-developer-agent-wheelhouse', recursive=True))[0])
wheels = sorted(str(w) for w in WH.glob('*.whl') if w.name.lower().startswith(('transformers-', 'bitsandbytes-', 'safetensors-', 'tokenizers-')))
assert len(wheels) == 4, wheels
r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', '--disable-pip-version-check', *wheels],
                   capture_output=True, text=True)
print('pip:', r.returncode, r.stderr[-1500:], flush=True); assert r.returncode == 0
VERSIONS = 'import json, torch, transformers, peft, accelerate, bitsandbytes as b; print(json.dumps({m.__name__: m.__version__ for m in (torch, transformers, peft, accelerate, b)}))'
REPORT['versions'] = json.loads(out([sys.executable, '-c', VERSIONS]).splitlines()[-1]); save(); print('versions:', REPORT['versions'], flush=True)

# 3. inputs
MODEL_DIR = Path(sorted(glob.glob(f'/kaggle/input/**/{BASE_MODEL}/**/config.json', recursive=True))[0]).parent
CODE = [Path(p).parent for p in glob.glob('/kaggle/input/**/train_qlora.py', recursive=True) if DATASET.split('/')[1] in p][0]
REPORT['paths'] = {'model': str(MODEL_DIR), 'code_and_data': str(CODE)}; save()
print('model', MODEL_DIR, sorted(p.name for p in MODEL_DIR.iterdir()), '| code+data', CODE, sorted(p.name for p in CODE.iterdir()), flush=True)

# 4. train (a subprocess, so this kernel never holds GPU memory); --deadline-min saves the adapter before the session cap
cmd = [sys.executable, str(CODE / 'train_qlora.py'), '--model', str(MODEL_DIR), '--data', str(CODE), '--out', str(RUN),
       '--pipeline', str(PIPELINE), '--attn', 'qchunk', '--deadline-min', str(MINUTES), *TRAIN_ARGS]
REPORT['cmd'] = cmd; save(); print(' '.join(cmd), flush=True)
t = time.time()
with open(WORK / 'train.log', 'w') as f:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in p.stdout:
        f.write(line); f.flush()
        if '%|' not in line: print(line, end='', flush=True)
    rc = p.wait()
REPORT['train_rc'] = rc; REPORT['train_wall_min'] = round((time.time() - t) / 60, 1)
recs = [json.loads(l) for l in open(RUN / 'train_log.jsonl')] if (RUN / 'train_log.jsonl').exists() else []
REPORT['fit_probe'] = [r['fit_probe'] for r in recs if 'fit_probe' in r]
REPORT['steps'] = [r for r in recs if 'step' in r]
REPORT['summary'] = next((r['summary'] for r in recs if 'summary' in r), None); save()

# 5. packaging checks of make_submission.py (G0: key prefix, plain target_modules list, fp16, finite, <= 3 GiB)
PACKAGE = ("import json, sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; from make_submission import package_adapter; "
           "print('G0_JSON', json.dumps(package_adapter(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], 'base_model.model.model.language_model.layers.', 3072)))")
if (RUN / 'final' / 'adapter_model.safetensors').exists():
    shutil.rmtree(WORK / 'packaged', ignore_errors=True)
    r = subprocess.run([sys.executable, '-c', PACKAGE, str(CODE), str(RUN / 'final'), str(WORK / 'packaged'), TARGET_MODEL], capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-3000:], flush=True)
    REPORT['g0'] = next((json.loads(l.split(' ', 1)[1]) for l in r.stdout.splitlines() if l.startswith('G0_JSON')), {'error': r.stderr[-1500:]})
REPORT['total_min'] = round((time.time() - T0) / 60, 1); save()
print('DONE', json.dumps({k: REPORT.get(k) for k in ('train_rc', 'train_wall_min', 'total_min', 'fit_probe', 'summary', 'g0')}), flush=True)
'''


def prepare_dataset(out, dataset_id, data):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for f in ("train_qlora.py", "make_submission.py"): shutil.copyfile(HERE / f, out / f)
    for f in ("train.parquet", "stats.json"): shutil.copyfile(Path(data) / f, out / f)
    json.dump({"title": dataset_id.split("/")[1], "id": dataset_id, "licenses": [{"name": "CC0-1.0"}]}, open(out / "dataset-metadata.json", "w"), indent=1)
    stats = json.load(open(Path(data) / "stats.json"))
    print(f"dataset dir {out}: {sorted(p.name for p in out.iterdir())} | {stats.get('windows')} windows, {stats.get('tokens')} tokens "
          f"(max {stats.get('tokens_max')}), tokenized with {stats.get('model')}\n  upload: kaggle datasets create -p {out}   (update: kaggle datasets version -p {out} -m <msg>)")


def make_notebook(a):
    train_args = shlex.split(a.train_args)
    head = (f"DATASET = {a.dataset!r}\nBASE_MODEL = {a.base!r}\nTARGET_MODEL = {a.target!r}\nPIPELINE = {a.pipeline}\n"
            f"MINUTES = {a.minutes}\nTRAIN_ARGS = {json.dumps(train_args)}\n")
    code = head + NB
    compile(code, "nb", "exec")
    title = a.title or a.slug.split("/")[1].replace("-", " ")     # a title that resolves to the slug
    md = (f"# {title}\n\nLoRA training on Kaggle 4x L4 (training only): `{a.base}` in NF4 split over {a.pipeline} GPUs, query-chunked "
          f"attention, bf16 autocast; data `{a.dataset}`; adapter packaged for `{a.target}`.\n\n`train_qlora.py {' '.join(train_args)}`")
    nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": md.splitlines(True)},
                    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": code.splitlines(True)}],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fn = a.slug.split("/")[1] + ".ipynb"; json.dump(nb, open(out / fn, "w"), indent=1)
    meta = {"id": a.slug, "title": title, "code_file": fn, "language": "python", "kernel_type": "notebook", "is_private": True,
            "enable_gpu": True, "enable_tpu": False, "enable_internet": False,
            "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse", a.dataset], "kernel_sources": [],
            "competition_sources": ["gemma-4-developer-agent"], "model_sources": [f"google/gemma-4/transformers/{a.base}/{a.model_version}"],
            "docker_image": IMAGE, "machine_shape": a.machine}
    json.dump(meta, open(out / "kernel-metadata.json", "w"), indent=2)
    print(f"notebook {out / fn} | {a.base} -> {a.target} | data {a.dataset} | deadline {a.minutes} min | args {train_args}\n"
          f"  push: kaggle kernels push -p {out} --accelerator {a.machine} -t {int(60 * (a.minutes + 25))}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dataset", help="stage the private dataset dir: scripts + one tokenized window set")
    d.add_argument("out"); d.add_argument("dataset_id"); d.add_argument("--data", required=True, help="dir with train.parquet + stats.json")
    n = sub.add_parser("notebook", help="write <out>/<slug>.ipynb + kernel-metadata.json")
    n.add_argument("out"); n.add_argument("slug"); n.add_argument("--title"); n.add_argument("--dataset", required=True)
    n.add_argument("--base", default="gemma-4-31b-it-qat-q4_0-unquantized"); n.add_argument("--model-version", type=int, default=2)
    n.add_argument("--target", default="gemma-4-31b-it-qat-w4a16-ct", help="declared model the adapter is packaged for")
    n.add_argument("--pipeline", type=int, default=4); n.add_argument("--machine", default="NvidiaL4")   # "GPU L4 x4"; unknown ids fall back to T4 x2
    n.add_argument("--minutes", type=float, default=95, help="train_qlora.py --deadline-min (stop and save before the session cap)")
    n.add_argument("--train-args", default="--max-len 16384 --rank 32 --lr 1e-4 --optim adamw --max-steps 20 --grad-accum 1 --log-every 1 --fit-probe")
    a = ap.parse_args()
    if a.cmd == "dataset":
        prepare_dataset(a.out, a.dataset_id, a.data)
    else:
        make_notebook(a)


if __name__ == "__main__":
    main()
