"""Write the CPU submission notebook of a validated bundle: it rewrites the bundle's files and zips them as submission.zip.

  python make_notebook.py <bundle_dir> <out_dir> <owner/slug> "<Title>" [--adapter-dataset owner/dataset-slug]

Text files are embedded in the notebook. Adapter weights are binary and too large to embed: with --adapter-dataset the
notebook attaches that private Kaggle dataset, copies its files into adapters/main_lora/, and checks each one against
the sha256 of the validated bundle before zipping. The Kaggle slug must equal the slugified title.
"""
import argparse, hashlib, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("pkg"); ap.add_argument("out"); ap.add_argument("slug"); ap.add_argument("title")
ap.add_argument("--adapter-dataset", help="private Kaggle dataset holding the files of the bundle's adapters/main_lora/")
a = ap.parse_args()
pkg = Path(a.pkg); out = Path(a.out); slug = a.slug; title = a.title
assert slug.split("/")[1] == re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"), "the slug must equal the slugified title"
files, adapter_sha = {}, {}
for p in sorted(pkg.rglob("*")):
    if not p.is_file(): continue
    rel = p.relative_to(pkg).as_posix()
    if rel.startswith("adapters/"):
        assert a.adapter_dataset, f"{rel} is binary: pass --adapter-dataset"
        adapter_sha[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    else:
        files[rel] = p.read_text(encoding="utf-8")
assert "agent.yaml" in files and all(not k.endswith((".sh", ".gitkeep")) for k in files)
assert not a.adapter_dataset or adapter_sha, "--adapter-dataset given but the bundle has no adapters/"
# text-only bundles keep their earlier hash; an adapter bundle's hash also covers the adapter files' sha256
digest = hashlib.sha256(json.dumps([files, adapter_sha] if adapter_sha else files, sort_keys=True).encode()).hexdigest()[:16]
model = (re.search(r"^\s*model:\s*(\S+)", files["agent.yaml"], re.M) or [None, "?"])[1]
extra_md = f" Adapter files ({len(adapter_sha)}) come from the private dataset `{a.adapter_dataset}` and are checked by sha256." if adapter_sha else ""
md = (f"# {title}\n\nWrites the agent bundle (model {model}, {len(files) + len(adapter_sha)} files) and packages it as `submission.zip`.{extra_md}\n"
      f"Bundle hash: `{digest}`. The finished agent is evaluated by the competition harness; no GPU is needed to assemble it.")
# an adapter bundle is assembled outside /kaggle/working, so the output holds only submission.zip (not the weights twice)
bundle_dir = 'Path("/tmp/submission_bundle")' if adapter_sha else 'WORK / "submission_bundle"'
code = '''import glob, json, os, shutil, zipfile, hashlib
from pathlib import Path

FILES = ''' + json.dumps(files, indent=1) + '''
ADAPTER_SHA = ''' + json.dumps(adapter_sha, indent=1) + '''

WORK = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path.cwd()
BUNDLE = ''' + bundle_dir + '''; ZIP = WORK / "submission.zip"
shutil.rmtree(BUNDLE, ignore_errors=True)
for rel, text in FILES.items():
    p = BUNDLE / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")
if ADAPTER_SHA:
    # by dataset name: the competition data holds sample adapters too (sample_submission/adapters/{main,tool}_lora)
    src = sorted(glob.glob("/kaggle/input/**/''' + (a.adapter_dataset or "/").split("/")[1] + '''/adapter_model.safetensors", recursive=True))
    assert len(src) == 1, src
    src = Path(src[0]).parent
    for rel, sha in ADAPTER_SHA.items():
        p = BUNDLE / rel; p.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src / Path(rel).name, p)
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha, rel + ": sha256 differs from the validated bundle"
h = json.dumps([FILES, ADAPTER_SHA] if ADAPTER_SHA else FILES, sort_keys=True).encode()
assert hashlib.sha256(h).hexdigest()[:16] == "''' + digest + '''"
ZIP.unlink(missing_ok=True)
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(BUNDLE.rglob("*")):
        if p.is_file(): z.write(p, p.relative_to(BUNDLE).as_posix())
with zipfile.ZipFile(ZIP) as z: names = z.namelist()
assert "agent.yaml" in names and all(rel in names for rel in ADAPTER_SHA)
print("Created", ZIP, os.path.getsize(ZIP), "bytes"); print(chr(10).join(names))
print(open(BUNDLE / "agent.yaml").read()); print(open(BUNDLE / "eval_config.yaml").read())
'''
compile(code, "nb", "exec")
nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": md.splitlines(True)},
                {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": code.splitlines(True)}],
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
out.mkdir(parents=True, exist_ok=True)
fn = slug.split("/")[1] + ".ipynb"
json.dump(nb, open(out / fn, "w"), indent=1)
meta = {"id": slug, "title": title, "code_file": fn, "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": False, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": [a.adapter_dataset] if adapter_sha else [], "kernel_sources": [],
        "competition_sources": ["gemma-4-developer-agent"], "model_sources": []}
json.dump(meta, open(out / "kernel-metadata.json", "w"), indent=2)
print("notebook", out / fn, "hash", digest, "files", list(files), "adapter files", list(adapter_sha))
