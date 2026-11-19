#!/usr/bin/env python3
"""Real-fix blocks for practice tasks (Nov 19, round-2 plan: the private note).

For each task it turns the gold patch (the fix written by the project's own developers, field `patch` of tasks.jsonl)
into "Replace / With" blocks against the task's snapshot: one block per changed place of every source file (a non-test
.py file), cut to the shortest text that still occurs exactly once in the file. The note relay (takeover_proxy.py)
shows these blocks to the model in practice runs on the VM; they never go into a bundle.

  python3 make_hints.py --pool data/rebench --tasks results/lists/bf5_train_unsolved.txt --out datasets/r2/hints_train.jsonl
  python3 make_hints.py --pool data/rebench2 --soundness results/rebench2_soundness.csv --out datasets/r2/hints_rb2.jsonl
      [--exclude results/lists/dev48.txt] [--limit N]

One JSON line per task: instance_id, repo, pool, issue_key (the first 200 characters of the issue: how the relay
recognises the task), gold_files, blocks [{path, old, new}], changed_lines, small (<= 2 source files, <= 8 blocks,
<= 80 changed lines), other_files (files of the fix that are neither source, test nor documentation),
new_public_names (public functions, classes or parameters the fix adds, the tests use and the issue does not name:
the model cannot know them, so such a fix is a poor teaching example), ok and why.
A task is ok when every block occurs exactly once in the snapshot and applying the blocks gives exactly the source
files of the real fix. Standard library only; nothing of the repository is executed.
"""
import argparse, collections, csv, json, os, re, sys, tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopsy as A

MAX_CONTEXT = 12          # lines of context added on each side before a block is given up as "not unique"
DOC_RX = re.compile(r"(^|/)(docs?|documentation|changes|changelog\.d|news|newsfragments)/|\.(md|rst|txt)$|(^|/)(CHANGELOG|CHANGES|HISTORY|NEWS|AUTHORS|README|RELEASE)[^/]*$", re.I)
HUNK_RX = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
DEF_RX = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\((.*)$")
CLS_RX = re.compile(r"^\s*class\s+([A-Za-z_]\w*)")
PARAM_RX = re.compile(r"(?:^|,)\s*\*{0,2}([A-Za-z_]\w*)\s*(?=[:=,)]|$)")


def ids(path):
    return [l.strip() for l in open(path) if l.strip() and not l.startswith("#")]


DOCDIR_RX = re.compile(r"(^|/)(docs?|documentation|examples?|benchmarks?)/", re.I)


def is_source(p):
    """A file the note covers: a .py file that is neither a test or setup file (the harness's protected rule) nor
    under a documentation or examples folder (docs/conf.py is part of many real fixes and of no use to the tests)."""
    return p.endswith(".py") and not A.is_protected(p) and not DOCDIR_RX.search(p)


def parse_patch(patch):
    """-> {path: {"new", "deleted", "renamed", "hunks": [(old_start, [(tag, text), ...])]}} in patch order."""
    files = collections.OrderedDict(); cur = None; h = None; need = [0, 0]
    for line in (patch or "").split("\n"):
        m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
        if m:
            cur = files.setdefault(m.group(2), {"new": False, "deleted": False, "renamed": m.group(1) != m.group(2), "hunks": []}); h = None
            continue
        if cur is None: continue
        if h is not None and (need[0] > 0 or need[1] > 0):
            if line.startswith("\\"): continue                       # "\ No newline at end of file"
            tag = line[:1]
            if tag == "-": h.append(("-", line[1:])); need[0] -= 1
            elif tag == "+": h.append(("+", line[1:])); need[1] -= 1
            else: h.append((" ", line[1:])); need[0] -= 1; need[1] -= 1   # a context line (also one whose blank was stripped)
            continue
        if line.startswith("new file mode"): cur["new"] = True
        elif line.startswith("deleted file mode"): cur["deleted"] = True
        elif line.startswith("rename from"): cur["renamed"] = True
        else:
            m = HUNK_RX.match(line)
            if m:
                h = []; need = [int(m.group(2) or 1), int(m.group(4) or 1)]
                cur["hunks"].append((int(m.group(1)), h))
    return files


def read_snapshot(tgz, paths):
    """-> {path: text} for the wanted repository paths (None when a file is not valid UTF-8)."""
    want = {"./" + p: p for p in paths}; want.update({p: p for p in paths}); got = {}
    with tarfile.open(tgz, "r:gz") as tar:
        for m in tar:
            if m.name in want and m.isfile():
                raw = tar.extractfile(m).read()
                try: got[want[m.name]] = raw.decode("utf-8")
                except UnicodeDecodeError: got[want[m.name]] = None
                if len(got) == len(paths): break
    return got


def ops_of(lines, hunks):
    """Change runs of a file in old-line coordinates: [start, end, new_lines] (0-based, end exclusive; start == end is a
    pure insertion). None when a hunk does not match the snapshot line for line."""
    ops = []
    for old_start, hl in hunks:
        # "@@ -N,0 +..." (a hunk without old lines) inserts AFTER old line N; every other hunk starts AT old line N
        i = max(old_start - 1, 0) if any(tag != "+" for tag, _ in hl) else old_start
        run = None
        for tag, s in hl:
            if tag == "+":
                if run is None: run = [i, i, []]
                run[2].append(s); continue
            if i >= len(lines) or lines[i] != s: return None
            if tag == " ":
                if run: ops.append(run); run = None
            else:
                if run is None: run = [i, i, []]
                run[1] = i + 1
            i += 1
        if run: ops.append(run)
    return ops


def blocks_for(path, text, hunks):
    """-> (blocks, changed_lines, new_text) or (None, reason, None)."""
    lines = text.split("\n"); n = len(lines)
    ops = ops_of(lines, hunks)
    if ops is None: return None, "a hunk does not match the snapshot", None
    if not ops: return None, "no change in the hunks", None
    ranges = []
    for s, e, new in ops:
        k = 0
        while True:
            bs, be = max(0, s - k), min(n, e + k)
            old_txt = "\n".join(lines[bs:be]); new_txt = "\n".join(lines[bs:s] + new + lines[e:be])
            if old_txt.strip() and new_txt.strip() and old_txt != new_txt and text.count(old_txt) == 1: break
            k += 1
            if k > MAX_CONTEXT: return None, "a block is not unique in its file", None
        ranges.append([bs, be])
    ranges.sort(); merged = []
    for r in ranges:                                   # blocks that overlap or touch become one block
        if merged and r[0] <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], r[1])
        else: merged.append(r)
    blocks = []
    for bs, be in merged:
        res = []; pos = bs
        for s, e, new in ops:
            if s >= bs and e <= be and s >= pos: res += lines[pos:s] + new; pos = e
        res += lines[pos:be]
        blocks.append({"path": path, "old": "\n".join(lines[bs:be]), "new": "\n".join(res)})
    full = []; pos = 0
    for s, e, new in ops: full += lines[pos:s] + new; pos = e
    full += lines[pos:]
    return blocks, sum(e - s + len(new) for s, e, new in ops), "\n".join(full)


def apply_blocks(text, blocks):
    """The check the relay relies on: every block is found exactly once, in order of application."""
    for b in blocks:
        if text.count(b["old"]) != 1: return None
        text = text.replace(b["old"], b["new"], 1)
    return text


def new_public_names(text, hunks, issue, tests):
    """Public names the fix defines (def, class, parameters of a one-line def) that the task's tests use and that occur
    neither in the old file nor in the issue text: the model cannot know such a name, so the fix cannot be derived."""
    old_words = set(re.findall(r"[A-Za-z_]\w*", text)); out = []
    for _, hl in hunks:
        old_params = {}
        for tag, s in hl:
            m = DEF_RX.match(s)
            if tag == "-" and m: old_params[m.group(1)] = set(PARAM_RX.findall(m.group(2)))
        for tag, s in hl:
            if tag != "+": continue
            m = DEF_RX.match(s); c = CLS_RX.match(s); names = []
            if c: names.append(c.group(1))
            if m:
                names.append(m.group(1))
                if m.group(1) in old_params:           # a changed signature: only its new parameters count
                    names = [p for p in PARAM_RX.findall(m.group(2)) if p not in old_params[m.group(1)]]
            for nm in names:
                if nm.startswith("_") or nm in ("self", "cls", "args", "kwargs") or nm in old_words: continue
                if nm not in issue and nm not in out and re.search(r"\b%s\b" % re.escape(nm), tests): out.append(nm)
    return out


def build(task, pool):
    iid = task["instance_id"]; issue = task.get("problem_statement") or ""
    rec = {"instance_id": iid, "repo": task.get("repo"), "pool": os.path.basename(pool.rstrip("/")), "issue_key": issue.strip()[:200],
           "gold_files": [], "blocks": [], "changed_lines": 0, "small": False, "other_files": [], "new_public_names": [], "ok": False, "why": ""}
    files = parse_patch(task.get("patch"))
    src = [p for p in files if is_source(p)]
    rec["gold_files"] = src
    rec["other_files"] = [p for p in files if not is_source(p) and not A.is_protected(p) and not DOC_RX.search(p)]
    if not src: rec["why"] = "the fix changes no source .py file"; return rec
    if len(rec["issue_key"]) < 40: rec["why"] = "the issue text is too short to recognise the task"; return rec
    if any(files[p]["new"] or files[p]["deleted"] or files[p]["renamed"] for p in src):
        rec["why"] = "the fix adds, deletes or renames a source file"; return rec
    tgz = os.path.join(pool, "snapshots", iid + ".tgz")
    if not os.path.exists(tgz): rec["why"] = "no snapshot"; return rec
    try: texts = read_snapshot(tgz, src)
    except Exception as e: rec["why"] = f"snapshot unreadable: {type(e).__name__}"; return rec
    blocks = []; changed = 0; names = []
    for p in src:
        if texts.get(p) is None: rec["why"] = "a source file is missing in the snapshot or is not UTF-8"; return rec
        b, ch, new_text = blocks_for(p, texts[p], files[p]["hunks"])
        if b is None: rec["why"] = ch; return rec
        if apply_blocks(texts[p], b) != new_text: rec["why"] = "the blocks do not reproduce the fix"; return rec
        blocks += b; changed += ch
        names += [x for x in new_public_names(texts[p], files[p]["hunks"], issue, task.get("test_patch") or "") if x not in names]
    rec.update(blocks=blocks, changed_lines=changed, new_public_names=names, ok=True,
               small=len(src) <= 2 and len(blocks) <= 8 and changed <= 80)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, help="task set directory with tasks.jsonl and snapshots/, e.g. data/rebench")
    ap.add_argument("--tasks", help="file of instance ids"); ap.add_argument("--soundness", help="soundness csv: take the sound tasks")
    ap.add_argument("--exclude", nargs="*", default=[], help="files of instance ids to leave out")
    ap.add_argument("--out", required=True); ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    assert a.tasks or a.soundness, "give --tasks or --soundness"
    want = set(ids(a.tasks)) if a.tasks else {r["instance_id"] for r in csv.DictReader(open(a.soundness)) if r.get("sound") == "True"}
    for f in a.exclude: want -= set(ids(f))
    tasks = [t for t in (json.loads(l) for l in open(os.path.join(a.pool, "tasks.jsonl")) if l.strip()) if t["instance_id"] in want]
    if a.limit: tasks = tasks[: a.limit]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    why = collections.Counter(); n = collections.Counter(); keys = collections.Counter()
    recs = [build(t, a.pool) for t in tasks]
    for r in recs: keys[r["issue_key"]] += 1
    with open(a.out, "w", encoding="utf-8") as f:
        for r in recs:
            if r["ok"] and keys[r["issue_key"]] > 1: r["ok"] = False; r["why"] = "another task starts with the same issue text"
            why[r["why"] or "ok"] += 1
            if r["ok"]:
                n["ok"] += 1; n["small"] += r["small"]; n["other_files"] += bool(r["other_files"]); n["new_public_names"] += bool(r["new_public_names"])
                n["clean"] += r["small"] and not r["other_files"] and not r["new_public_names"]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{a.out}: {len(recs)} tasks | ok {n['ok']} | small {n['small']} | with other files {n['other_files']} | "
          f"with new public names {n['new_public_names']} | clean (ok, small, neither) {n['clean']}")
    for k, v in why.most_common(): print(f"   {v:4d}  {k}")


if __name__ == "__main__":
    main()
