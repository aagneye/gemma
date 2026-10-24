"""Download competition files by prefix into data/competition, skipping files already present with the right size.
Usage: python scripts/kaggle_fetch.py <list.json> <dest_root> [--include PREFIX ...] [--exclude PREFIX ...] [--workers N]
"""
import json, os, sys, time, argparse, shutil, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from kaggle.api.kaggle_api_extended import KaggleApi

ap = argparse.ArgumentParser()
ap.add_argument("listfile"); ap.add_argument("dest")
ap.add_argument("--include", nargs="*", default=[]); ap.add_argument("--exclude", nargs="*", default=[])
ap.add_argument("--workers", type=int, default=4); ap.add_argument("--competition", default="gemma-4-developer-agent")
a = ap.parse_args()
files = json.load(open(a.listfile))
sel = [(n, s) for n, s in files if (not a.include or any(n.startswith(p) for p in a.include)) and not any(n.startswith(p) for p in a.exclude)]
api = KaggleApi(); api.authenticate()

def fetch(name, size):
    target = os.path.join(a.dest, *name.split("/"))
    if os.path.exists(target) and (size == 0 or os.path.getsize(target) == size):
        return name, "skip"
    os.makedirs(os.path.dirname(target), exist_ok=True)
    for attempt in range(4):
        tmp = tempfile.mkdtemp(prefix="kg_", dir=a.dest)
        try:
            api.competition_download_file(a.competition, name, path=tmp, force=True, quiet=True)
            got = [os.path.join(tmp, f) for f in os.listdir(tmp)]
            if len(got) != 1: raise RuntimeError(f"unexpected files {got}")
            if size and os.path.getsize(got[0]) != size: raise RuntimeError(f"size mismatch {os.path.getsize(got[0])} != {size}")
            shutil.move(got[0], target); shutil.rmtree(tmp, ignore_errors=True)
            return name, "ok"
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True); err = e; time.sleep(3 * (attempt + 1))
    return name, f"FAIL {err}"

t0 = time.time(); done = 0; fails = []
with ThreadPoolExecutor(a.workers) as ex:
    futs = [ex.submit(fetch, n, s) for n, s in sel]
    for f in as_completed(futs):
        n, st = f.result(); done += 1
        if st.startswith("FAIL"): fails.append((n, st))
        if done % 10 == 0 or st.startswith("FAIL"): print(f"[{done}/{len(sel)}] {n} {st} ({time.time()-t0:.0f}s)", flush=True)
print(f"done {done}/{len(sel)} in {time.time()-t0:.0f}s, failures: {len(fails)}")
for n, st in fails: print("  ", n, st)
