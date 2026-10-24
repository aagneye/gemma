---
name: locate
description: Deterministic issue-to-code localisation. Run scripts/locate.py once at the start of a task to get the most likely source files, matching lines and symbols for the reported issue, instead of exploring with many grep/ls/read calls.
---

# locate

Run this FIRST, before reading files:

    run_skill_script(skill_name="locate", file_path="scripts/locate.py", args={"text": "<paste the problem statement>"})

Optional keys in `args`: `"terms": "name1,name2"` to add identifiers you already suspect, `"top": "8"` for more files.

It greps every anchor from the issue (paths, dotted names, CamelCase/snake_case identifiers, exception names, quoted
strings, CLI flags) across the repository's tracked Python files, weights rare anchors higher, down-weights tests and
docs, and adds a symbol-name index. Output: TOP FILES with their matching lines, then TOP SYMBOLS as `file:line name`.

Then: `read_file` the top source file around the matching lines (use `start_line`/`end_line`), confirm the cause,
and edit the source file, not the tests. If the list looks wrong, run it again with `terms` set to identifiers you
found while reading. Do not spend more than 2 calls on locate.
