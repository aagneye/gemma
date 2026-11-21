#!/usr/bin/env python3
"""Report of note runs (round-2 plan steps 2-4): for each task of a run made through the note relay, did the note
come, did the model apply the real fix, did the tests pass, and is the run usable as a training example?
Standard library only.

  python3 note_report.py <tag> [<tag> ...] --hints datasets/r2/hints_train.jsonl [more ...] [--thoughts 12] [--json out.jsonl]
Reads results/replica/<tag>/results.csv and results/takeover/<tag>/{events.jsonl,<task>.jsonl}. Prints markdown:
a summary, one row per task, and (with --thoughts N) the model's first thinking after the note for N runs, to read by eye.

Columns: trigger (first change / deadline), the counted call and prompt size at the note, blocks of the fix, the model
step after the note at which the first block was applied (1 = the very next step), blocks applied in the end, leak
words in the model's text after the note, words of its first thinking that are not copied from the note, a check
command after the last edit, tests passed.
A run is a clean example when the note came, the tests pass, no leak word occurs, the first thinking is not a bare copy
(>= 15 own words) and a check follows the last edit.
"""
import argparse, collections, csv, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopsy as A

ROOT = os.environ.get("GEMMA_ROOT", "/mnt/biohub/kdata/gemma4")
# Words that show the model is talking about the note: the approved list for the note in a tool result or in the task
# text, plus verbatim pieces of the first-person form (position C), which would be copies of text the example lacks.
LEAK_RX = re.compile(r"private note|this note\b|the note\b|was provided|provided fix|given fix|i was told|as instructed"
                     r"|i have seen enough|correct fix is exactly|next step: state|copying each .replace. text", re.I)
norm = lambda s: "\n".join(l.strip() for l in str(s or "").split("\n") if l.strip())


def jload(s):
    try:
        o = json.loads(s) if isinstance(s, str) else s
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def exchanges(path):
    """Journal lines of one task -> one dict per model reply, with the result of its tool call (taken from the next
    request that carries it)."""
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]; recs.sort(key=lambda r: r["seq"]); out = []
    results = {}
    for r in recs:
        for m in r["request"].get("messages") or []:
            if m.get("role") == "tool": results[m.get("tool_call_id")] = m.get("content")
    for r in recs:
        msg = (((r.get("reply") or {}).get("choices") or [{}])[0].get("message") or {})
        tc = (msg.get("tool_calls") or [{}])[0]; fn = tc.get("function") or {}; args = jload(fn.get("arguments"))
        res = results.get(tc.get("id")); o = jload(res)
        out.append({"seq": r["seq"], "event": r["event"], "noted": bool(r.get("noted")), "n_calls": r.get("n_calls"),
                    "name": fn.get("name"), "args": args, "ok": o.get("status") == "ok", "result": res,
                    "thought": msg.get("reasoning_content") or msg.get("reasoning") or "", "text": msg.get("content") or "",
                    "prompt_tokens": ((r.get("reply") or {}).get("usage") or {}).get("prompt_tokens"), "delta": r.get("delta")})
    return out


def analyse(iid, ex, hint, events):
    row = {"iid": iid, "trigger": "", "call": None, "prompt": None, "blocks": len(hint.get("blocks") or []), "first_applied": None,
           "applied": 0, "leak": [], "own_words": None, "check_after": False, "other": [e["event"] for e in events if not e["event"].startswith("takeover")]}
    t = next((i for i, e in enumerate(ex) if e["event"].startswith("takeover")), None)
    if t is None: return row, None
    row["trigger"] = "first change" if ex[t]["event"].endswith("first_change") else "deadline"
    row["call"] = ex[t]["n_calls"]; row["prompt"] = ex[t]["prompt_tokens"]
    blocks = hint.get("blocks") or []; done = set(); last_edit = None
    note_lines = {l.strip() for b in blocks for l in (b["old"] + "\n" + b["new"]).split("\n") if l.strip()}
    for j in range(t, len(ex)):
        e = ex[j]
        if e["name"] in ("edit_file", "write_file") and e["ok"]:
            last_edit = j
            if e["name"] == "edit_file":
                p = A.clean_path(e["args"].get("filepath")); new = norm(e["args"].get("new_string"))
                for i, b in enumerate(blocks):
                    if b["path"] == p and new and (new in norm(b["new"]) or norm(b["new"]) in new):
                        done.add(i)
                        if row["first_applied"] is None: row["first_applied"] = j - t + 1
        for m in LEAK_RX.findall(e["thought"] + "\n" + e["text"]):
            if m.lower() not in row["leak"]: row["leak"].append(m.lower())
    row["applied"] = len(done)
    own = [l for l in ex[t]["thought"].split("\n") if l.strip() and l.strip() not in note_lines]
    row["own_words"] = sum(len(l.split()) for l in own)
    row["check_after"] = last_edit is not None and any(e["name"] == "run_command" for e in ex[last_edit + 1:])
    return row, ex[t]["thought"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tags", nargs="+"); ap.add_argument("--hints", nargs="+", required=True)
    ap.add_argument("--thoughts", type=int, default=0); ap.add_argument("--json")
    a = ap.parse_args()
    hints = {}
    for f in a.hints:
        for line in open(f, encoding="utf-8"):
            r = json.loads(line); hints[r["instance_id"]] = r
    rows = []; thoughts = []
    for tag in a.tags:
        run = os.path.join(ROOT, "results/replica", tag); jd = os.path.join(ROOT, "results/takeover", tag)
        res = {r["instance_id"]: r for r in csv.DictReader(open(os.path.join(run, "results.csv")))}
        ev = collections.defaultdict(list)
        if os.path.exists(os.path.join(jd, "events.jsonl")):
            for l in open(os.path.join(jd, "events.jsonl")):
                e = json.loads(l); ev[e["iid"]].append(e)
        for iid, r in res.items():
            jf = os.path.join(jd, iid + ".jsonl"); h = hints.get(iid) or {}
            if not os.path.exists(jf):
                row, th = {"iid": iid, "trigger": "", "blocks": len(h.get("blocks") or []), "other": ["no journal"], "leak": [], "applied": 0,
                           "first_applied": None, "call": None, "prompt": None, "own_words": None, "check_after": False}, None
            else:
                row, th = analyse(iid, exchanges(jf), h, ev[iid])
            row.update(tag=tag, resolved=r.get("resolved") == "True", calls=r.get("tool_calls"), has_blocks=bool(h.get("ok")),
                       small=bool(h.get("small")), new_names=h.get("new_public_names") or [], other_files=bool(h.get("other_files")))
            row["clean"] = bool(row["trigger"]) and row["resolved"] and not row["leak"] and (row["own_words"] or 0) >= 15 and row["check_after"]
            rows.append(row)
            if th is not None: thoughts.append((iid, row, th))
    noted = [r for r in rows if r["trigger"]]; n = len(noted) or 1
    print(f"# Note runs: {', '.join(a.tags)}\n")
    print(f"- Tasks: {len(rows)}; with blocks: {sum(r['has_blocks'] for r in rows)}; solved in all: {sum(r['resolved'] for r in rows)}.")
    print(f"- **Note given: {len(noted)}** (first change {sum(r['trigger'] == 'first change' for r in noted)}, deadline {sum(r['trigger'] == 'deadline' for r in noted)}).")
    print(f"- Of the noted runs: first block applied within 2 steps **{sum(1 for r in noted if r['first_applied'] and r['first_applied'] <= 2)}** "
          f"({100 * sum(1 for r in noted if r['first_applied'] and r['first_applied'] <= 2) // n}%); every block applied {sum(1 for r in noted if r['applied'] >= r['blocks'] > 0)}; "
          f"**tests pass {sum(r['resolved'] for r in noted)}** ({100 * sum(r['resolved'] for r in noted) // n}%).")
    print(f"- Leak words in {sum(1 for r in noted if r['leak'])} noted runs; bare-copy first thinking (< 15 own words) in {sum(1 for r in noted if (r['own_words'] or 0) < 15)}; "
          f"no check after the last edit in {sum(1 for r in noted if not r['check_after'])}.")
    print(f"- **Clean examples: {sum(r['clean'] for r in rows)}** (note, tests pass, no leak, own thinking, check after the last edit).")
    print(f"- Runs without a note: {len(rows) - len(noted)} (solved on their own: {sum(1 for r in rows if not r['trigger'] and r['resolved'])}); "
          f"reasons: {dict(collections.Counter(x for r in rows if not r['trigger'] for x in (r['other'] or ['never ready'])))}.\n")
    print("| Task | Note | Call | Prompt | Blocks | First applied at step | Applied | Leak | Own words | Check after | Tests |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (not r["trigger"], r["iid"])):
        print(f"| {r['iid']} | {r['trigger'] or '-'} | {r['call'] if r['call'] is not None else ''} | {r['prompt'] or ''} | {r['blocks']} | "
              f"{r['first_applied'] or ''} | {r['applied'] if r['trigger'] else ''} | {', '.join(r['leak'])} | "
              f"{r['own_words'] if r['own_words'] is not None else ''} | {'yes' if r['check_after'] else 'no' if r['trigger'] else ''} | {'pass' if r['resolved'] else 'fail'} |")
    if a.thoughts:
        print("\n## First thinking after the note\n")
        for iid, row, th in thoughts[: a.thoughts]:
            print(f"**{iid}** ({row['trigger']}, tests {'pass' if row['resolved'] else 'fail'}, leak: {', '.join(row['leak']) or 'none'})\n")
            print("```\n" + (th[:1500] + (" [...]" if len(th) > 1500 else "")) + "\n```\n")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
