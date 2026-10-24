---
name: finalize
description: Patch hygiene before submit_patch. Run scripts/finalize.py after your fix is verified; it reverts edits to test and config files, deletes scratch files, byte-compiles changed Python files and prints the final diff summary.
---

# finalize

Run this ONCE after your targeted test passes and BEFORE `submit_patch`:

    run_skill_script(skill_name="finalize", file_path="scripts/finalize.py")

Options: `args={"delete": "a.py,b.py"}` to remove extra untracked files you created,
`args={"keep": "pkg/new_module.py"}` to keep a new source file that is part of the fix.

What it does: reverts changes to `tests/`, `test_*.py`, `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg`,
`tox.ini`, `setup.py` (the grader strips them anyway and they can conflict with the hidden tests); deletes untracked
scratch files in the repo root (`reproduce*.py`, `test_*.py`, `debug*.py`, `check*.py`, `*.log`, ...); compiles every
changed `.py` file; prints `git status`, `git diff --stat` and the head of the diff.

If the report says PROBLEM (syntax error, empty patch, leftover scratch files), fix it and run finalize again.
If it says READY, call `submit_patch` and then reply with a one-paragraph summary to end the session.
