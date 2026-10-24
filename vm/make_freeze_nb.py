#!/usr/bin/env python3
"""CPU notebook that records the Kaggle scorer host environment (pinned official image + wheelhouse): python version,
pip freeze, and the pytest/plugins the subprocess sandbox inherits.  python make_freeze_nb.py <out_dir> <owner/slug>"""
import json, sys
from pathlib import Path
out, slug = Path(sys.argv[1]), sys.argv[2]
code = r'''
import glob, os, shutil, subprocess, sys
from pathlib import Path
W = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
if not W.exists(): W = Path(sorted(glob.glob('/kaggle/input/**/gemma-4-developer-agent-wheelhouse', recursive=True))[0])
t = Path('/tmp/wh'); t.mkdir(exist_ok=True)
for w in W.glob('*.whl'):
    if 'cutlass' in w.name.lower() or w.name.lower().startswith(('vllm', 'torch', 'flashinfer', 'xformers', 'triton', 'nvidia')): continue
    d = t / (w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name)
    if not d.exists(): os.symlink(w, d)
Path('/kaggle/working/before.txt').write_text(subprocess.run([sys.executable, '-m', 'pip', 'freeze'], capture_output=True, text=True).stdout)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *map(str, t.glob('*.whl'))], check=True)
fr = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], capture_output=True, text=True).stdout
Path('/kaggle/working/freeze.txt').write_text(fr)
Path('/kaggle/working/python.txt').write_text(sys.version + '\n' + '\n'.join(p for p in sys.path if 'site-packages' in p or 'dist-packages' in p))
print(sys.version); print(len(fr.splitlines()), 'packages')
print([l for l in fr.splitlines() if l.lower().startswith(('pytest', 'pluggy', 'anyio', 'hypothesis', 'trio', 'httpx', 'starlette', 'pydantic', 'typing'))])
'''
nb = {"cells": [{"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": code.splitlines(True)}],
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}}, "nbformat": 4, "nbformat_minor": 5}
out.mkdir(parents=True, exist_ok=True); fn = slug.split("/")[1] + ".ipynb"; json.dump(nb, open(out / fn, "w"))
json.dump({"id": slug, "title": slug.split("/")[1], "code_file": fn, "language": "python", "kernel_type": "notebook", "is_private": True,
           "enable_gpu": False, "enable_tpu": False, "enable_internet": False, "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
           "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [], "model_sources": [],
           "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"},
          open(out / "kernel-metadata.json", "w"), indent=2)
print("wrote", out / fn)
