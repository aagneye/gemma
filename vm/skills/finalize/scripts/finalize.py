#!/usr/bin/env python3
"""finalize.py - patch hygiene before submit_patch (stdlib only). Run from /workspace via run_skill_script.

Usage: finalize.py [--delete path1,path2] [--keep path1,path2]
  * reverts edits to protected files that the grader resets anyway (tests/, test_*.py, conftest.py, pytest.ini,
    pyproject.toml, setup.cfg, tox.ini, setup.py) so they do not waste the patch or conflict with the hidden tests;
  * deletes untracked scratch files (reproduce*/repro*/test_*/debug*/check*/verify*/tmp*/*.log in the repo root and
    anything listed in --delete) because submit_patch includes every untracked file; keeps files in --keep;
  * byte-compiles every modified/added .py file and reports syntax errors;
  * prints `git status --short`, `git diff --stat` and the head of the diff.
Exit code 0 always; read the report and fix anything marked PROBLEM before calling submit_patch.
"""
import argparse, os, re, subprocess, py_compile

PROTECTED = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|(^|/)pytest\.ini$|(^|/)pyproject\.toml$|(^|/)setup\.cfg$|(^|/)tox\.ini$|(^|/)setup\.py$|(^|/)\.pytest\.ini$")
SCRATCH = re.compile(r"^(reproduce|repro|test_|tests_|debug|check|verify|demo|tmp|scratch|minimal|final_test|edge_case|comprehensive|poc|example_)[\w.-]*\.(py|sh|txt|json|md)$|\.log$|^output[\w.-]*\.txt$", re.I)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd="/workspace").stdout


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--delete", default=""); ap.add_argument("--keep", default="")
    a, _ignored = ap.parse_known_args(); os.chdir("/workspace")
    keep = {p.strip() for p in a.keep.split(",") if p.strip()}; dele = {p.strip() for p in a.delete.split(",") if p.strip()}
    report = []; problems = 0
    status = sh("git status --short --untracked-files=all")
    modified = [l[3:] for l in status.splitlines() if l[:2].strip() in ("M", "A", "D", "AM", "MM", "R")]
    untracked = [l[3:] for l in status.splitlines() if l.startswith("??")]
    # 1. protected files
    reverted = [f for f in modified if PROTECTED.search(f) and f not in keep]
    for f in reverted: sh(f"git checkout -- '{f}' 2>/dev/null")
    if reverted: report.append("reverted protected files (grader resets them anyway): " + ", ".join(reverted))
    # 2. scratch files
    removed = []
    for f in untracked:
        base = os.path.basename(f); top = "/" not in f
        if f in keep: continue
        if f in dele or (top and SCRATCH.match(base)) or PROTECTED.search(f) and base.startswith("test_"):
            try: os.remove(f); removed.append(f)
            except OSError: pass
    if removed: report.append("deleted scratch files: " + ", ".join(removed))
    left = [f for f in untracked if f not in removed]
    if left:
        report.append("untracked files that WILL be included in the patch (delete them if they are scratch): " + ", ".join(left))
    # 3. syntax check
    status = sh("git status --short --untracked-files=all")
    changed_py = [l[3:] for l in status.splitlines() if l[3:].endswith(".py") and not l.startswith(" D")]
    bad = []
    for f in changed_py:
        try: py_compile.compile(f, doraise=True)
        except Exception as e: bad.append(f"{f}: {str(e).splitlines()[0][:160]}")
    if bad: problems += len(bad); report.append("PROBLEM syntax errors:\n  " + "\n  ".join(bad))
    else: report.append(f"syntax OK for {len(changed_py)} changed .py file(s)")
    # 4. diff
    stat = sh("git diff --stat"); diff = sh("git diff")
    if not stat.strip() and not left:
        problems += 1; report.append("PROBLEM: no source changes - the patch would be empty")
    report.append("git diff --stat:\n" + (stat.strip() or "(empty)"))
    report.append("diff head:\n" + diff[:2200] + ("\n...[truncated]" if len(diff) > 2200 else ""))
    report.append("READY to submit_patch" if not problems else f"{problems} PROBLEM(s) above - fix, then run finalize again")
    print("\n".join(report)[:4500])


if __name__ == "__main__":
    main()
