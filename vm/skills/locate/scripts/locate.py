#!/usr/bin/env python3
"""locate.py - deterministic issue -> code localisation inside /workspace (stdlib only, no network).

Usage (via run_skill_script):  --text "<issue text or key phrases>"  [--terms a,b,c] [--top 8]

Method (from the localisation literature: keyword/grep anchors first, symbol index second):
  1. extract anchors from the text: file paths, dotted names, CamelCase / snake_case identifiers, quoted strings,
     exception names, CLI flags; drop stop-words and very common tokens.
  2. git grep -n -F each anchor across tracked source files (tests/docs down-weighted), weight = inverse file frequency.
  3. add a symbol index score: `def`/`class` names that share tokens with the anchors.
  4. print the top files with their best matching lines and the top symbols (file:line) — compact, < 4,500 chars.
"""
import argparse, os, re, subprocess, sys, collections, math

STOP = set("""a an the this that these those is are was were be been being have has had do does did of in on at to for
from by with without into onto over under about as it its if then else when while and or not no yes true false none
null return raise error errors exception issue bug fix fixed fixes should would could can cannot must may might
when where which who what why how use used using via please thanks hello also only just like get set new old
value values default result results expected actual behavior behaviour current example test tests testing code file
files line lines function method class module package version python import""".split())
SRC_SKIP = re.compile(r"(^|/)(tests?|testing|docs?|docs_src|examples?|benchmarks?|scripts|\.github|site)(/|$)|(^|/)conftest\.py$|^setup\.py$")


def run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd="/workspace",
                              env={**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"}).stdout
    except Exception:
        return ""


_FILE_CACHE = {}


def list_py_files():
    out = run("git ls-files -- '*.py' 2>/dev/null").split()
    if not out:
        out = run("find . -name '*.py' -not -path './.git/*' -not -path '*/node_modules/*' | sed 's|^\\./||'").split()
    return out


def read_cached(f):
    if f not in _FILE_CACHE:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh: _FILE_CACHE[f] = fh.read().splitlines()
        except OSError:
            _FILE_CACHE[f] = []
    return _FILE_CACHE[f]


def grep_fixed(term, files, limit=400):
    """git grep -nF, with a pure-Python fallback when git is unusable in this container."""
    out = run(f"git grep -n -I -F -- {quote(term)} -- '*.py' 2>/dev/null | head -{limit}")
    if out.strip():
        return out.splitlines()
    hits = []
    for f in files:
        for i, line in enumerate(read_cached(f), 1):
            if term in line:
                hits.append(f"{f}:{i}:{line}")
                if len(hits) >= limit: return hits
    return hits


def symbol_lines(files):
    out = run("git grep -n -E '^\\s*(def|class|async def) ' -- '*.py' 2>/dev/null | head -20000")
    if out.strip():
        return out.splitlines()
    pat = re.compile(r"^\s*(?:async\s+def|def|class)\s+")
    res = []
    for f in files:
        for i, line in enumerate(read_cached(f), 1):
            if pat.match(line): res.append(f"{f}:{i}:{line}")
    return res


BOILER_ML = re.compile(r"<!--.*?-->", re.S)                                   # HTML comments (multi-line)
BOILER = re.compile(r"^\s*-\s*\[[ x]\][^\n]*$|^#+\s*(Type of changes|Checklist|Pull Request)[^\n]*$|https?://\S+", re.M | re.I)
STOP |= set("""github http https pull request checklist black updated changes feature docstrings documentation discussion
member team open create latest start write reviewed based description type bug tests other new added remove removed
fixes fixing closes close resolves resolved related issue issues link linked obvious typo make made implement implemented
support supports supported added adds change changed""".split())
DEF_BONUS = 14.0   # a file that DEFINES a mentioned class/function is far more likely to be the fix site than one that uses it


def anchors(text, extra):
    text = BOILER.sub(" ", BOILER_ML.sub(" ", text))
    cands = collections.OrderedDict()
    def add(t, w):
        t = t.strip(" `'\"()[]{}<>,.;:")
        if len(t) < 3 or t.lower() in STOP or t.isdigit(): return
        cands[t] = max(cands.get(t, 0), w)
    for t in re.findall(r"[\w./-]+\.py\b", text): add(t, 3.0)                       # file paths
    for t in re.findall(r"\b[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*){1,4}\b", text): add(t, 2.5)   # dotted names
    for t in re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b", text): add(t, 2.0)   # CamelCase
    for t in re.findall(r"\b[a-z_][a-z0-9]*_[a-z0-9_]+\b", text): add(t, 2.0)      # snake_case
    for t in re.findall(r"\b\w*(?:Error|Exception|Warning)\b", text): add(t, 2.0)
    for t in re.findall(r"`([^`\n]{3,60})`", text): add(t, 1.5)
    for t in re.findall(r"[\"']([^\"'\n]{4,60})[\"']", text): add(t, 1.2)
    for t in re.findall(r"--[a-z][\w-]+", text): add(t, 1.5)
    for t in re.findall(r"\b[a-z]{5,}\b", text): add(t, 0.4)                       # plain words, low weight
    for t in (extra or "").split(","):
        if t.strip(): add(t.strip(), 3.0)
    items = sorted(cands.items(), key=lambda kv: -kv[1])
    return items[:40]


def main():
    # Tolerant argument handling: models pass --text, --task_text, --query, --issue, --problem, positional text, etc.
    ap = argparse.ArgumentParser(); ap.add_argument("--text", default=""); ap.add_argument("--terms", default="")
    ap.add_argument("--top", type=int, default=8); a, rest = ap.parse_known_args()
    extra_text = []
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok.startswith("--") and "=" in tok: extra_text.append(tok.split("=", 1)[1])
        elif tok.startswith("--") and i + 1 < len(rest) and not rest[i + 1].startswith("--"): extra_text.append(rest[i + 1]); i += 1
        elif not tok.startswith("--"): extra_text.append(tok)
        i += 1
    text = " ".join([a.text] + extra_text).strip()
    if not text and not sys.stdin.isatty():
        try: text = sys.stdin.read()
        except Exception: pass
    os.chdir("/workspace")
    terms = anchors(text, a.terms)
    if not terms:
        print("No usable anchors found. Call again with args={\"text\": \"<the full problem statement>\"} or args={\"terms\": \"identifier1,identifier2\"}."); return
    files = list_py_files()
    nfiles = max(1, len(files))
    fscore = collections.Counter(); fhits = collections.defaultdict(list); used = []
    for term, w in terms:
        if re.search(r"[^\w./ -]", term) and not term.endswith(".py"): continue
        lines = grep_fixed(term, files)
        if not lines: continue
        hit_files = {l.split(":", 1)[0] for l in lines}
        idf = math.log(1 + nfiles / (1 + len(hit_files)))
        if len(hit_files) > 0.5 * nfiles: continue                               # term too common to discriminate
        used.append(term)
        for l in lines:
            f, _, rest = l.partition(":")
            boost = 0.35 if SRC_SKIP.search(f) else 1.0
            fscore[f] += w * idf * boost
            if len(fhits[f]) < 4: fhits[f].append(rest[:140])
    # symbol index: defs/classes whose name shares tokens with anchors
    toks = {t.lower() for term, _ in terms for t in re.split(r"[^a-zA-Z0-9]+", term) if len(t) > 3 and t.lower() not in STOP}
    symbols = []
    for l in symbol_lines(files):
        parts3 = l.split(":", 2)
        if len(parts3) < 3: continue
        f, ln, rest = parts3
        m = re.search(r"(?:def|class)\s+([A-Za-z_]\w*)", rest)
        if not m: continue
        name = m.group(1); parts = {p.lower() for p in re.split(r"_|(?<=[a-z])(?=[A-Z])", name) if len(p) > 2}
        ov = len(parts & toks)
        exact = any(name == t or t.endswith("." + name) for t, _ in terms)   # the issue names this symbol verbatim
        if ov or exact:
            tw = 0.35 if SRC_SKIP.search(f) else 1.0
            s = (DEF_BONUS if exact else ov) * tw + 0.3 * (fscore.get(f, 0) > 0)
            symbols.append((s, f, ln, name))
            fscore[f] += (DEF_BONUS if exact else 0.8 * ov) * tw
    out = [f"anchors used ({len(used)}): " + ", ".join(used[:14])]
    out.append(f"\nTOP FILES (by weighted grep + symbol-name overlap; {nfiles} python files scanned):")
    for f, s in fscore.most_common(a.top):
        out.append(f"  {f}  [score {s:.1f}]")
        for h in fhits.get(f, [])[:3]: out.append(f"      {h}")
    symbols.sort(key=lambda x: -x[0])
    if symbols:
        out.append("\nTOP SYMBOLS (file:line  name):")
        for s, f, ln, name in symbols[:12]: out.append(f"  {f}:{ln}  {name}")
    out.append("\nNext: read_file the top source file around the matching lines; prefer non-test source files for the fix.")
    text = "\n".join(out)
    print(text[:4400] + ("\n...[truncated]" if len(text) > 4400 else ""))


def quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    main()
