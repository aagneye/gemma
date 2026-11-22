#!/usr/bin/env bash
# E4B side track (user, Nov 22; research/PLAN_E4B.md): build the small-model bundles, each one change from its parent.
#   bash e4b_build.sh                               the base e4b_bf5 and the thinking ladder e4b_bf5_t1k, _t256, _t0
#   bash e4b_build.sh one <name> <parent> <thinking>   one bundle; <parent> = budgetfit_v5 or budgetfit_e1r1
# Every bundle = the parent's files with (1) the model line set to the E4B, (2) the three graph tools taken off the
# tool list and the prompt line about them removed, (3) the thinking budget. (2) is the six-tool profile of the public
# E4B runs (4, 5, 4 of 58). It also keeps the E4B away from get_code_subgraph, the one tool with a list argument:
# vLLM 0.19.1's gemma4 parser hangs on some list items (vm/README.md) and only the 31B was checked for that.
# thinking 0 switches thinking off in the harness (adk_submission/resolvers/generation.py: enable_thinking false).
# Each bundle is validated (make_submission.py --validate), compiled (build_v4.check) and diffed against its parent.
# A bundle that is already there is rebuilt only with FORCE=1 (a running arm reads its bundle folder).
set -eu
R=/mnt/biohub/kdata/gemma4; cd $R; V=~/gemma4_vm; S=submissions; M=gemma-4-e4b-it-qat-w4a16-ct
SIX="tools=['run_command', 'read_file', 'edit_file', 'write_file', 'get_status', 'submit_patch']"
mkdir -p tmp

one() {   # one <name> <parent> <thinking>
  local name=$1 parent=$2 think=$3 out=$S/$1 v c
  case "$name" in e4b_*) ;; *) echo "the name $name does not start with e4b_"; exit 1;; esac
  [ -s $S/$parent/agent.yaml ] || { echo "missing parent $S/$parent"; exit 1; }
  if [ -e $out ] && [ -z "${FORCE:-}" ]; then echo "$name: already built (FORCE=1 rebuilds it)"; return 0; fi
  $R/harness-venv/bin/python $V/make_submission.py --bundle $S/$parent --model $M --out $out > /dev/null
  python3 - $out $think <<'PY'
import re, sys
from pathlib import Path
d, think = Path(sys.argv[1]), sys.argv[2]
a = d / "agent.yaml"; t = a.read_bytes()
for tool in (b"get_code_neighbors", b"search_similar_code", b"get_code_subgraph"):
    line = b"  - " + tool + b"\n"; assert t.count(line) == 1, (tool, t.count(line)); t = t.replace(line, b"")
a.write_bytes(t)
p = d / "prompts" / "system.md"; s = p.read_bytes()
line = ("- Do not use `search_similar_code`, `get_code_neighbors` or `get_code_subgraph`: they only accept exact "
        "fully-qualified ids and usually return nothing.\n").encode()
assert s.count(line) == 1, s.count(line); p.write_bytes(s.replace(line, b""))
c = d / "configs" / "sampling.yaml"
y, n = re.subn(rb"(?m)^(  thinking_budget: )\d+$", rb"\g<1>" + think.encode(), c.read_bytes()); assert n == 1, n
c.write_bytes(y)
PY
  rm -f $out.zip          # make_submission.py zipped the files as they were before these edits; e4b_ship.sh zips at ship time
  v=$($R/harness-venv/bin/python $V/make_submission.py --validate $out 2>&1 | tail -1 | cut -c1-120)
  c=$(cd $V && $R/scorer-host-venv/bin/python -c "import build_v4; from pathlib import Path; build_v4.check(Path('$R/$out'), '$M')" 2>&1 | tail -1 | cut -c1-200)
  echo "$name <- $parent, thinking $think | $v | $c"
  echo "$v" | grep -q "^VALID" || { echo "NOT VALID: $name"; exit 1; }
  echo "$c" | grep -qF "$SIX" || { echo "NOT COMPILED with the six tools: $name"; exit 1; }
  grep -q "^model: $M$" $out/agent.yaml || { echo "WRONG model line: $name"; exit 1; }
  grep -q "^  thinking_budget: $think$" $out/configs/sampling.yaml || { echo "WRONG thinking budget: $name"; exit 1; }
  diff -r $S/$parent $out > tmp/e4b_build_$name.diff || true
  echo "  against $parent: $(grep -c '^<' tmp/e4b_build_$name.diff) lines out, $(grep -c '^>' tmp/e4b_build_$name.diff) lines in (tmp/e4b_build_$name.diff)"
}

case "${1:-ladder}" in
  ladder)
    one e4b_bf5 budgetfit_v5 4096; one e4b_bf5_t1k budgetfit_v5 1024; one e4b_bf5_t256 budgetfit_v5 256; one e4b_bf5_t0 budgetfit_v5 0
    for x in t1k t256 t0; do echo "e4b_bf5 against e4b_bf5_$x:"; diff -r $S/e4b_bf5 $S/e4b_bf5_$x | grep '^[<>]' || true; done;;
  one) one $2 $3 $4;;
  *) echo "usage: e4b_build.sh [ladder | one <name> <parent> <thinking>]"; exit 1;;
esac
