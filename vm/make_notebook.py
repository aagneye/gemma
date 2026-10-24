import json, sys, hashlib
from pathlib import Path
pkg = Path(sys.argv[1]); out = Path(sys.argv[2]); slug = sys.argv[3]; title = sys.argv[4]
files = {}
for p in sorted(pkg.rglob("*")):
    if p.is_file(): files[p.relative_to(pkg).as_posix()] = p.read_text(encoding="utf-8")
assert "agent.yaml" in files and all(not k.endswith((".sh", ".gitkeep")) for k in files)
digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
md = f"# {title}\n\nWrites the agent bundle (single LlmAgent, 6 core tools, gemma-4-12b-it-qat-w4a16-ct, thinking ON, no LoRA) and packages it as `submission.zip`.\nBundle hash: `{digest}`. The finished agent is evaluated by the competition harness; no GPU is needed to assemble it."
code = f'''import json, os, zipfile, hashlib
from pathlib import Path

FILES = {json.dumps(files, indent=1)}

WORK = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path.cwd()
BUNDLE = WORK / "submission_bundle"; ZIP = WORK / "submission.zip"
import shutil; shutil.rmtree(BUNDLE, ignore_errors=True)
for rel, text in FILES.items():
    p = BUNDLE / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")
assert hashlib.sha256(json.dumps(FILES, sort_keys=True).encode()).hexdigest()[:16] == "{digest}"
ZIP.unlink(missing_ok=True)
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(BUNDLE.rglob("*")):
        if p.is_file(): z.write(p, p.relative_to(BUNDLE).as_posix())
with zipfile.ZipFile(ZIP) as z: names = z.namelist()
assert "agent.yaml" in names
print("Created", ZIP, os.path.getsize(ZIP), "bytes"); print(chr(10).join(names))
print(open(BUNDLE / "agent.yaml").read()); print(open(BUNDLE / "eval_config.yaml").read())
'''
nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": md.splitlines(True)},
                {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": code.splitlines(True)}],
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
out.mkdir(parents=True, exist_ok=True)
fn = slug.split("/")[1] + ".ipynb"
json.dump(nb, open(out / fn, "w"), indent=1)
meta = {"id": slug, "title": title, "code_file": fn, "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": False, "enable_tpu": False, "enable_internet": False, "dataset_sources": [], "kernel_sources": [],
        "competition_sources": ["gemma-4-developer-agent"], "model_sources": []}
json.dump(meta, open(out / "kernel-metadata.json", "w"), indent=2)
print("notebook", out / fn, "hash", digest, "files", list(files))
