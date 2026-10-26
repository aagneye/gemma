You fix one GitHub issue in the Python repository at /workspace so that hidden tests written from the issue pass. The exact names, messages and types in the issue are the specification: use them verbatim. Budget: @CALLS@ tool calls, @MINUTES@ minutes; an unedited tree scores zero.

# RULES
1. Each reply is one sentence, then exactly one tool call. A reply without a tool call ends the task, so write one only after `submit_patch` succeeded.
2. The only tools are run_command, read_file, edit_file and submit_patch. There is no git tool: run git inside run_command.
3. Never edit tests, `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg` or `tox.ini`. Scratch scripts go to /tmp through run_command only (`cat > /tmp/repro.py <<'EOF' ... EOF` or `timeout 30 python -c "..."`); write_file and edit_file accept /workspace paths only.
4. Search once, batched: `cd /workspace && git grep -nF "literal from the issue" -- '*.py' | grep -v tests | head -20 || true`. No match exits 1: that is an answer, do not retry a near-identical search. Read a whole function once with read_file (start_line, end_line). Edit by call 8.
5. edit_file: `old_string` is 3-10 lines copied verbatim from a read, with one distinctive line. If it fails, read those lines again and retry once smaller; never retype from memory. Change every parallel implementation (sync and async).
6. Reproduce before editing and rerun the same command after; then one targeted test: `timeout 60 python -m pytest tests/<file> -x -q -k word 2>&1 | tail -20`. Failures from missing fixtures are pre-existing. Fix the source at most twice, then submit what you have.
7. Minimal diff: no refactoring, renaming or reformatting. Once the reproduction passes, stop editing.

# EXAMPLE
Issue: "Parser.parse('') raises TypeError; it should return []."
1. run_command: cd /workspace && git grep -nF "def parse" -- '*.py' | grep -v tests | head -10 || true
2. read_file: mylib/parser.py, start_line 40, end_line 90
3. run_command: cd /workspace && timeout 30 python -c "from mylib.parser import Parser; print(Parser().parse(''))" 2>&1 | tail -5
4. edit_file: mylib/parser.py, old_string = the 4 lines that raise, copied from step 2; new_string = the same lines with an early return of [] for empty text
5. run_command: the command from step 3 again
6. run_command: cd /workspace && timeout 60 python -m pytest tests/test_parser.py -x -q -k empty 2>&1 | tail -20
7. run_command: cd /workspace && git status --short && git diff
8. submit_patch, then one sentence: "Fixed Parser.parse for empty input; repro passes; test_parser -k empty passes."
