#!/usr/bin/env python3
"""Select SWE-rebench tasks that look like the hidden set and run in our replica without installing anything.

The scorer's subprocess sandbox installs nothing, so every hidden task must validate with the Kaggle image's packages.
A candidate therefore needs every package of its frozen environment to be present in scorer-host-venv (Python
3.12.13 + the Kaggle freeze); development tools are ignored. Further filters: not a competition repo, no web framework,
flat layout (no src/), gold patch of 1-3 .py source files (docs allowed, nothing compiled) with no async code,
1-20 FAIL_TO_PASS tests, issue and test llm_score <= 2 (0 best), PR from 2019 on. Newest first, --per-repo cap.
Instance ids become <short>_<pr> (our scripts split ids on "_").

  scorer-host-venv/bin/python rebench_select.py --data datasets/swe-rebench --out datasets/swe-rebench/candidates.jsonl
Run with scorer-host-venv's python: the installed-package check reads that interpreter's distributions.
"""
import argparse, collections, glob, importlib.metadata as md, json, re
import pyarrow.parquet as pq

COMPETITION = {"fastapi/fastapi", "tiangolo/fastapi", "textualize/rich", "willmcgugan/rich", "psf/requests",
               "kennethreitz/requests", "encode/httpx"}
WEB = {"django", "flask", "fastapi", "starlette", "aiohttp", "tornado", "sanic", "quart", "falcon", "pyramid", "bottle",
       "litestar", "werkzeug", "cherrypy", "aiohttp-jinja2", "channels", "uvicorn", "gunicorn", "hypercorn"}
DEV = {"pip", "setuptools", "wheel", "build", "twine", "tox", "nox", "pre-commit", "virtualenv", "coverage", "pytest-cov",
       "codecov", "coveralls", "flake8", "pyflakes", "pycodestyle", "pydocstyle", "black", "isort", "mypy", "mypy-extensions",
       "pylint", "astroid", "ruff", "bandit", "check-manifest", "sphinx", "sphinx-rtd-theme", "readme-renderer",
       "setuptools-scm", "versioneer", "bump2version", "bumpversion", "pytest-runner", "pip-tools", "distlib", "filelock",
       "platformdirs", "identify", "nodeenv", "cfgv", "docutils", "alabaster", "babel", "imagesize", "snowballstemmer",
       "pyproject-api", "cachetools", "chardet", "tomli", "exceptiongroup", "importlib-metadata", "zipp",
       "typing-extensions", "backports-tarfile", "pkginfo", "rfc3986", "keyring", "jaraco-classes", "jaraco-context",
       "jaraco-functools", "more-itertools", "nh3", "requests-toolbelt", "secretstorage", "jeepney", "pywin32-ctypes"}


DEV_PREFIX = ("types-", "flake8", "sphinx", "mkdocs", "pytest-cov", "pytest-xdist", "pytest-timeout", "pytest-benchmark",
              "pytest-randomly", "pytest-sugar", "pytest-rerunfailures", "pytest-runner", "pre-commit", "pep8", "pylint",
              "mypy", "coverage", "codecov", "docformatter", "pyupgrade", "towncrier", "autoflake", "autopep8", "yapf")
DEV |= {"execnet", "mccabe", "pdoc", "pdoc3", "covdefaults", "typed-ast", "ruamel-yaml-clib", "py-cpuinfo",
        "pathspec", "tomlkit", "colorama", "termcolor", "setuptools-rust", "editables", "hatchling",
        "hatch-vcs", "flit-core", "poetry-core", "pdm-backend", "scikit-build", "jinja2-cli", "invoke", "gitpython", "gitdb", "smmap",
        "py", "pytest-asyncio", "pytest-env", "pytest-doctestplus", "pytest-remotedata", "numpydoc"}   # unused by most test runs; soundness decides
COMPILED = (".pyx", ".pxd", ".c", ".h", ".cpp", ".cc", ".rs", ".go", ".f90")


def is_dev(name):
    return name in DEV or name.startswith(DEV_PREFIX)


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower().strip()


def req_names(text):
    out = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        m = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if m:
            out.add(norm(m.group(1)))
    return out


def patch_files(patch):
    return re.findall(r"^diff --git a/(\S+) b/", patch or "", re.M)


def is_test_path(p):
    base = p.rsplit("/", 1)[-1]
    return base.startswith("test_") or base.endswith("_test.py") or "/tests/" in "/" + p or "/test/" in "/" + p or base == "conftest.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--per-repo", type=int, default=12); ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--max-llm-score", type=int, default=2, help="max issue_text_score and test_score (0 best, 3 worst)")
    ap.add_argument("--max-f2p", type=int, default=20); ap.add_argument("--max-src-files", type=int, default=3)
    a = ap.parse_args()
    installed = {norm(d.metadata["Name"]) for d in md.distributions() if d.metadata["Name"]}
    rows, seen = [], set()
    for f in sorted(glob.glob(f"{a.data}/*.parquet")):
        for r in pq.read_table(f).to_pylist():
            if r["instance_id"] not in seen:
                seen.add(r["instance_id"]); rows.append(r)
    stage = collections.Counter(); stage["all"] = len(rows); missing_top = collections.Counter(); keep = []
    for r in rows:
        repo = r["repo"]; meta = r.get("meta") or {}; ls = meta.get("llm_score") or {}
        if repo.lower() in COMPETITION: stage["x_competition"] += 1; continue
        if str(r.get("created_at") or "") < a.since: stage["x_old"] += 1; continue
        f2p = list(r.get("FAIL_TO_PASS") or [])
        if not 1 <= len(f2p) <= a.max_f2p: stage["x_f2p"] += 1; continue
        if not meta.get("has_test_patch", True): stage["x_no_test_patch"] += 1; continue
        issue, tests = ls.get("issue_text_score"), ls.get("test_score")
        if issue is None or tests is None or not (0 <= issue <= a.max_llm_score and 0 <= tests <= a.max_llm_score): stage["x_llm_score"] += 1; continue
        allp = patch_files(r["patch"]); files = [p for p in allp if p.endswith(".py") and not is_test_path(p)]
        if any(p.endswith(COMPILED) for p in allp): stage["x_compiled"] += 1; continue
        if not 1 <= len(files) <= a.max_src_files or any(p.endswith(".py") and is_test_path(p) for p in allp):
            stage["x_patch_files"] += 1; continue
        if any(p.startswith("src/") for p in files + patch_files(r["test_patch"])): stage["x_src_layout"] += 1; continue
        if re.search(r"^[-+ ].*\b(async def|await )", r["patch"], re.M): stage["x_async"] += 1; continue
        reqs = req_names(r.get("requirements"))
        if reqs & WEB: stage["x_web"] += 1; continue
        name = norm(repo.split("/")[-1])
        own = {name, name.replace("python-", ""), name.replace("py", "", 1)}
        missing = sorted(n for n in reqs - installed - own if not is_dev(n))
        if missing:
            stage["x_missing_pkgs"] += 1; missing_top.update(missing); continue
        stage["kept"] += 1; keep.append(r)
    keep.sort(key=lambda r: str(r["created_at"]), reverse=True)   # newest first, cap per repo
    per, final, shorts = collections.Counter(), [], {}
    for r in keep:
        if per[r["repo"]] >= a.per_repo: continue
        per[r["repo"]] += 1
        owner, name = r["repo"].split("/", 1)
        short = re.sub(r"[^a-z0-9]", "", name.lower()) or "repo"
        if shorts.setdefault(short, r["repo"]) != r["repo"]:
            short = short + re.sub(r"[^a-z0-9]", "", owner.lower())[:8]
            shorts.setdefault(short, r["repo"])
        pr = r["instance_id"].rsplit("-", 1)[-1]
        ls = (r.get("meta") or {}).get("llm_score") or {}
        final.append({"instance_id": f"{short}_{pr}", "rebench_id": r["instance_id"], "repo": r["repo"],
                      "base_commit": r["base_commit"], "environment_setup_commit": r.get("environment_setup_commit") or "",
                      "created_at": str(r["created_at"]), "problem_statement": r["problem_statement"], "hints_text": "",
                      "patch": r["patch"], "test_patch": r["test_patch"], "FAIL_TO_PASS": list(r["FAIL_TO_PASS"] or []),
                      "PASS_TO_PASS": list(r["PASS_TO_PASS"] or []), "difficulty": ls.get("difficulty_score"),
                      "issue_score": ls.get("issue_text_score"), "test_score": ls.get("test_score"),
                      "python": str((r.get("install_config") or {}).get("python")), "license": r.get("license_name")})
    with open(a.out, "w") as f:
        for c in final: f.write(json.dumps(c) + "\n")
    print("stages:", dict(stage))
    print(f"kept {len(keep)} -> {len(final)} candidates from {len(per)} repos (cap {a.per_repo}/repo) -> {a.out}")
    print("difficulty:", dict(collections.Counter(c["difficulty"] for c in final)))
    print("most common missing packages:", missing_top.most_common(25))


if __name__ == "__main__":
    main()
