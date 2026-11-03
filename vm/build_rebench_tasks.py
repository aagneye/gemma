#!/usr/bin/env python3
"""Turn rebench_select.py candidates into a harness task set: snapshots, task records, graph placeholders.

One worker per repo (repos in parallel, a repo's tasks in sequence): one bare mirror clone; per task an official-format
snapshot (the history of base_commit only, via git fast-export into a fresh repo with branches main + export_ref and
user Agent <agent@eval>, packed as a ./-prefixed .tgz, as data/HARNESS_README.md describes), plus placeholder graph and
embedding files (> 100 bytes, valid formats) so the harness adds the same "Code Intelligence Tools" paragraph as on
Kaggle (swegemma/harness/agent_runner.py:418-466). Writes <out>/{tasks.jsonl, snapshots/, graphs/, embeddings/,
wheels/ (empty), build_log.csv}. Run with scorer-host-venv's python (numpy).

  python build_rebench_tasks.py --candidates datasets/swe-rebench/candidates.jsonl --out data/rebench \
      --mirrors datasets/swe-rebench/mirrors --workers 16 [--limit 100]
"""
import argparse, collections, concurrent.futures as cf, csv, json, shutil, subprocess, tempfile, time
from pathlib import Path
import numpy as np

GIT_CONFIG = "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = false\n\tlogallrefupdates = true\n" \
             "[user]\n\temail = agent@eval\n\tname = Agent\n"


def git(*args, cwd=None, timeout=600, stdin=None, stdout=subprocess.PIPE):
    return subprocess.run(["git", *args], cwd=cwd, timeout=timeout, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, check=True)


def placeholders(out, repo, base_commit):
    """Graph + embeddings the harness only checks for existence (> 100 bytes); our prompts forbid the graph tools."""
    short = repo.split("/")[-1]
    node = short.replace("-", "_")
    g = {"directed": True, "multigraph": True, "graph": {"repo_name": f"{short}_{base_commit}"},
         "nodes": [{"name": node, "text": f"# package {node} (graph not built for this practice task)"}], "edges": []}
    (out / "graphs" / f"{short}_{base_commit}.json").write_text(json.dumps(g))
    np.savez_compressed(out / "embeddings" / f"{short}_{base_commit}.npz", **{node: np.full(256, 1 / 16, dtype=np.float32)})


def snapshot(mirror, task, out, tmp_root):
    tmp = Path(tempfile.mkdtemp(dir=tmp_root)); work = tmp / "work"
    try:
        git("init", "-q", "-b", "main", str(work))
        git("update-ref", "refs/heads/export_ref", task["base_commit"], cwd=mirror)
        exp = subprocess.Popen(["git", "fast-export", "--reencode=yes", "--signed-tags=strip", "--tag-of-filtered-object=drop",
                                "refs/heads/export_ref"], cwd=mirror, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        git("fast-import", "--quiet", cwd=work, stdin=exp.stdout, timeout=1800)
        if exp.wait(timeout=60) != 0: raise RuntimeError("fast-export failed")
        git("update-ref", "refs/heads/main", "refs/heads/export_ref", cwd=work)
        git("reset", "-q", "--hard", "main", cwd=work)
        (work / ".git" / "config").write_text(GIT_CONFIG)
        dst = out / "snapshots" / f"{task['instance_id']}.tgz"
        subprocess.run(["tar", "-czf", str(dst), "-C", str(work), "."], check=True, timeout=1800)
        return dst.stat().st_size / 2**20
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_repo(repo, tasks, out, mirrors, max_mb):
    rows, t0 = [], time.time()
    mirror = mirrors / (repo.replace("/", "__") + ".git")
    try:
        if not mirror.exists():
            git("clone", "--mirror", "--quiet", f"https://github.com/{repo}.git", str(mirror), timeout=1800)
        mb = sum(f.stat().st_size for f in mirror.rglob("*") if f.is_file()) / 2**20
        if mb > max_mb:
            return [(t, "too_big", 0, round(mb)) for t in tasks]
    except Exception as e:
        return [(t, f"clone_fail {type(e).__name__}", 0, 0) for t in tasks]
    for t in tasks:
        s = time.time()
        try:
            git("cat-file", "-e", t["base_commit"] + "^{commit}", cwd=mirror, timeout=60)
        except Exception:
            rows.append((t, "commit_missing", 0, 0)); continue
        try:
            size = snapshot(mirror, t, out, out / "tmp")
            placeholders(out, repo, t["base_commit"])
            rows.append((t, "ok", round(time.time() - s, 1), round(size, 1)))
        except Exception as e:
            rows.append((t, f"export_fail {type(e).__name__}", round(time.time() - s, 1), 0))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--mirrors", required=True); ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--max-mirror-mb", type=int, default=1500)
    a = ap.parse_args()
    out, mirrors = Path(a.out), Path(a.mirrors)
    for d in ("snapshots", "graphs", "embeddings", "wheels", "tmp"): (out / d).mkdir(parents=True, exist_ok=True)
    mirrors.mkdir(parents=True, exist_ok=True)
    cands = [json.loads(l) for l in open(a.candidates)]
    if a.limit: cands = cands[:a.limit]
    by_repo = collections.OrderedDict()
    for c in cands: by_repo.setdefault(c["repo"], []).append(c)
    results, t0 = [], time.time()
    with cf.ProcessPoolExecutor(a.workers) as ex:
        futs = {ex.submit(build_repo, r, ts, out, mirrors, a.max_mirror_mb): r for r, ts in by_repo.items()}
        for i, f in enumerate(cf.as_completed(futs), 1):
            results += f.result()
            if i % 25 == 0: print(f"{i}/{len(futs)} repos, {sum(s == 'ok' for _, s, _, _ in results)} tasks built, {(time.time()-t0)/60:.1f} min", flush=True)
    order = {c["instance_id"]: i for i, c in enumerate(cands)}
    results.sort(key=lambda r: order[r[0]["instance_id"]])
    keys = ("instance_id", "repo", "base_commit", "problem_statement", "patch", "test_patch", "hints_text", "created_at",
            "FAIL_TO_PASS", "PASS_TO_PASS", "environment_setup_commit")
    with open(out / "tasks.jsonl", "w") as f:
        for t, status, _, _ in results:
            if status == "ok": f.write(json.dumps({k: t[k] for k in keys}) + "\n")
    with open(out / "build_log.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["instance_id", "repo", "rebench_id", "status", "seconds", "snapshot_mb", "difficulty", "issue_score", "test_score"])
        for t, status, sec, mb in results:
            w.writerow([t["instance_id"], t["repo"], t["rebench_id"], status, sec, mb, t["difficulty"], t["issue_score"], t["test_score"]])
    shutil.rmtree(out / "tmp", ignore_errors=True)
    st = collections.Counter(s.split()[0] for _, s, _, _ in results)
    print(f"done in {(time.time()-t0)/60:.1f} min: {dict(st)} -> {out}/tasks.jsonl")


if __name__ == "__main__":
    main()
