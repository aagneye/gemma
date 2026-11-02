# Prompt review log (the user reviews every instruction draft before it runs)

| Date (UTC) | Draft | Reviewer verdict | Notes |
|---|---|---|---|
| 2026-10-31 | `vm/prompts/system_v6_gates.md` (G0: event-gated feedback loop, 5 invariants, 5-line STATE, 6 gates, budget override; 957 words, 13 must/never sentences, no count rules) | approved for the VM test | runs as bundle `v6_gates` against the `v5_1_vm` baseline on the 50 Kaggle-sound tasks |
| 2026-11-02 | `vm/prompts/system_v6_1.md` (v6 with invariant 2 rewritten in both places: no `/tmp/repro.py` example, `/tmp` named as refused, every check inline with `python -c`; 958 words) | approved for the VM test | targets the 11 `write_file("/tmp/...")` path-traversal refusals in `v6_gates_vm`; runs as bundle `v6_1` against v6 |
| 2026-11-02 | `vm/prompts/system_v7.md` (v6.1 + pytest wrapper `timeout 120`, graph tools forbidden in TOOL FACTS, general documentation-example rule instead of the fastapi `docs_src/` hint, timeout sentence reworded; 1,007 words) with `vm/specs/v7.json` (`timeout_seconds` 240, 9 tools declared) | drafted, awaiting review | the proven public settings on top of v6.1; runs as bundle `v7` against `v6_1` (scale 9) after round 3; built and compiled, nothing run |
