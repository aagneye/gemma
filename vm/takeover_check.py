#!/usr/bin/env python3
"""No-GPU checks of the note relay (takeover_proxy.py) on recorded runs. Standard library only.

  sim   replay recorded runs through the relay's rule in --dry mode (no server): where would the note come?
          python3 takeover_check.py sim --run results/replica/bf5_train --hints datasets/r2/hints_train.jsonl
              [--bundle submissions/budgetfit_v5] [--deadline 12] [--tasks <ids>] [--exclude <ids>] [--show 5]
  http  one recorded run through the real relay over HTTP against a stand-in model server that answers with the
        recorded replies: requests without a note must arrive byte-identical; at the takeover the stand-in must get the
        plain request (or the one-token probe) and then the same request with the note as its only difference, at the
        place of the chosen position; later requests must carry the same note at the same place; the reply's
        prompt_tokens must be the note-free count; the journal must be complete and note-free.
          python3 takeover_check.py http --run results/replica/bf5_train --hints datasets/r2/hints_train.jsonl --task <iid>
              [--position A|B|C] [--deadline 12]
"""
import argparse, collections, json, os, sys, tempfile, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe as P
import takeover_proxy as T


def ids(path): return [l.strip() for l in open(path) if l.strip() and not l.startswith("#")]


def reply_of(it, k, prompt_tokens):
    msg = {"role": "assistant", "content": it["text"] or None}
    if it["thought"]: msg["reasoning_content"] = it["thought"]
    if it["call"]:
        msg["tool_calls"] = [{"id": f"call_{k}", "type": "function", "function": {"name": it["call"]["name"], "arguments": json.dumps(it["call"]["args"], ensure_ascii=False)}}]
    ct = it["completion_tokens"] or 0
    return {"id": "sim", "object": "chat.completion", "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if it["call"] else "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": ct, "total_tokens": prompt_tokens + ct}}


def load_run(run, iid, bundle):
    tp = os.path.join(run, "agent_run", "traces", f"trace_{iid}.json")
    if not os.path.exists(tp): return None
    system, task, items, clean = P.trace_items(json.load(open(tp, errors="replace")))
    return bundle.system_content(), task, items


def cmd_sim(a):
    bundle = P.Bundle(a.bundle); hints = {}
    for f in a.hints:
        for line in open(f, encoding="utf-8"):
            r = json.loads(line); hints[r["instance_id"]] = r
    want = set(ids(a.tasks)) if a.tasks else set(hints)
    for f in a.exclude or []: want -= set(ids(f))
    relay = T.Relay(a.hints, None, "A", a.deadline, True, log=lambda s: None)
    out = collections.Counter(); sizes = []; rows = []
    for iid in sorted(want & set(hints)):
        h = hints[iid]
        if not h.get("ok"): out["no blocks: " + (h.get("why") or "?")] += 1; continue
        run = load_run(a.run, iid, bundle)
        if run is None: out["no recorded run"] += 1; continue
        system, task, items = run; n0 = len(relay.events)
        for k, it in enumerate(items):
            if it["type"] != "model": continue
            body = bundle.envelope(P.build_messages(system, task, items, k))
            rep = json.dumps(reply_of(it, k, it["prompt_tokens"] or 0)).encode()
            relay.handle_chat(json.dumps(body, ensure_ascii=False).encode(), lambda raw, rep=rep: (200, [], rep))
        ev = relay.events[n0:]
        kind = ev[0]["event"] if ev else ("never ready" if iid in relay.tasks else "task not recognised")
        out[kind] += 1
        if ev and kind.startswith("would"):
            step = ev[0]["step"]; model_items = [it for it in items if it["type"] == "model" and it["call"]]
            pt = model_items[step]["prompt_tokens"] if step < len(model_items) else None
            sizes.append(pt or 0); rows.append((iid, kind, step, ev[0]["n_calls"], pt, len(h["blocks"]), h["small"]))
    print(f"== {a.run} with {', '.join(a.hints)} (deadline {a.deadline}): {sum(out.values())} tasks")
    for k, v in out.most_common(): print(f"   {v:4d}  {k}")
    if rows:
        b = collections.Counter("<=9.3k" if s <= 9300 else "<=11.3k" if s <= 11300 else "<=12.8k" if s <= 12800 else ">12.8k" for s in sizes)
        print(f"   note would come in {len(rows)} runs | prompt at the note: " + ", ".join(f"{k} {b[k]}" for k in ("<=9.3k", "<=11.3k", "<=12.8k", ">12.8k")) +
              f" | small fixes {sum(1 for r in rows if r[6])}")
        for r in rows[: a.show]: print("     ", r)
    return out


class Stub(BaseHTTPRequestHandler):
    """Stand-in model server: records what it receives and answers with the next recorded reply."""
    protocol_version = "HTTP/1.1"; got = []; replies = []; lock = threading.Lock()

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        with Stub.lock:
            Stub.got.append(raw)
            try: body = json.loads(raw)
            except Exception: body = {}
            pt = len(raw) // 4                                        # a stand-in token count that grows with the request
            if body.get("max_completion_tokens") == 1 or not body.get("tools"):
                rep = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "x"}, "finish_reason": "length"}],
                       "usage": {"prompt_tokens": pt, "completion_tokens": 1, "total_tokens": pt + 1}}
            else:
                rep = json.loads(json.dumps(Stub.replies[0])); rep["usage"] = {"prompt_tokens": pt, "completion_tokens": 5, "total_tokens": pt + 5}
        out = json.dumps(rep).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)

    def log_message(self, *a): pass


def post(port, raw):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=raw, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def differing(sent, orig):
    """Indexes of the messages that differ between what the stand-in got and what the harness sent."""
    n = min(len(sent), len(orig))
    return [i for i in range(n) if sent[i] != orig[i]] + list(range(n, max(len(sent), len(orig))))


def carried(pos, sent_m, orig_m):
    """The note text when sent_m is orig_m plus the note at the place of position pos, else None."""
    rest = lambda m, drop: {k: v for k, v in m.items() if k not in drop}
    if pos == "A":
        c, o = str(sent_m.get("content")), str(orig_m.get("content")); note = T.jload(c).get("note")
        ok = sent_m.get("role") == "tool" and c.startswith(o.rstrip()[:-1]) and isinstance(note, str) and note.startswith("PRIVATE NOTE")
        return note if ok and rest(sent_m, ("content",)) == rest(orig_m, ("content",)) else None
    if pos == "B":
        c, o = str(sent_m.get("content")), str(orig_m.get("content"))
        ok = sent_m.get("role") == "user" and c.startswith(o) and c[len(o):].strip().startswith("PRIVATE NOTE")
        return c[len(o):] if ok and rest(sent_m, ("content",)) == rest(orig_m, ("content",)) else None
    r = str(sent_m.get("reasoning_content") or ""); o = str(orig_m.get("reasoning") or orig_m.get("reasoning_content") or "").rstrip()
    ok = (sent_m.get("role") == "assistant" and sent_m.get("reasoning") == r and r.startswith(o)
          and r[len(o):].strip().startswith(T.PLAN_HEAD) and r.rstrip().endswith(T.PLAN_TAIL))
    drop = ("reasoning", "reasoning_content")
    return r[len(o):] if ok and rest(sent_m, drop) == rest(orig_m, drop) else None


def cmd_http(a):
    bundle = P.Bundle(a.bundle); run = load_run(a.run, a.task, bundle); assert run, "no recorded run for this task"
    system, task, items = run
    up = ThreadingHTTPServer(("127.0.0.1", 0), Stub); threading.Thread(target=up.serve_forever, daemon=True).start()
    jd = tempfile.mkdtemp(prefix="relaycheck_")
    relay = T.Relay(a.hints, jd, a.position, a.deadline, False, log=lambda s: print("   ", s))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), T.make_handler(relay, f"127.0.0.1:{up.server_address[1]}"))
    threading.Thread(target=srv.serve_forever, daemon=True).start(); port = srv.server_address[1]
    fails = []; check = lambda ok, what: (fails.append(what) if not ok else None)
    plain = json.dumps({"model": "m", "messages": [{"role": "user", "content": "The following is a conversation history ..."}]}).encode()
    Stub.got.clear(); post(port, plain); check(Stub.got == [plain], "a request without tools must pass byte-identical")
    noted_at = None; place = None; note = None
    for k, it in enumerate(items):
        if it["type"] != "model": continue
        msgs = P.build_messages(system, task, items, k); raw = json.dumps(bundle.envelope(msgs), ensure_ascii=False).encode()
        Stub.replies[:] = [reply_of(it, k, 0)]; Stub.got.clear()
        rep = post(port, raw); got = list(Stub.got); sent = json.loads(got[-1])["messages"]; diff = differing(sent, msgs)
        if noted_at is None and not diff:
            check(got == [raw], f"step {k}: a request without a note must pass byte-identical ({len(got)} sent)")
            check(rep["usage"]["prompt_tokens"] == len(raw) // 4, f"step {k}: the reply of a plain request must be unchanged")
            continue
        if noted_at is None:
            noted_at = k; ev = relay.events[-1]; print(f"   takeover at model step {k}: {ev['event']}; the stand-in got {len(got)} requests")
            check(len(got) == 2, f"step {k}: takeover must send 2 requests, sent {len(got)}")
            first = json.loads(got[0])
            if ev["event"] == "takeover_deadline":
                check(first.get("max_completion_tokens") == 1 and first["messages"] == msgs, "deadline: the first request must be the one-token probe of the plain request")
            else: check(got[0] == raw, "first change: the first request must be the plain request, byte-identical")
            check(len(diff) == 1, f"step {k}: the note must be the only difference ({len(diff)} messages differ)")
            if diff:
                place = diff[0]; note = carried(a.position, sent[place], msgs[place])
                want = {"A": max(i for i, m in enumerate(msgs) if m.get("role") == "tool"), "B": 1,
                        "C": max(i for i, m in enumerate(msgs) if m.get("role") == "assistant" and m.get("tool_calls"))}[a.position]
                check(note is not None, f"position {a.position}: the message before the note must be unchanged and the note well formed")
                check(place == want, f"position {a.position}: the note sits in message {place}, expected {want}")
        else:
            check(len(got) == 1, f"step {k}: a later request must be sent once, sent {len(got)}")
            check(diff == [place] and carried(a.position, sent[place], msgs[place]) == note, f"step {k}: the same note at the same place, nothing else changed")
        # the stand-in counts bytes // 4, so the lowered count may be off by a rounding step or two
        check(abs(rep["usage"]["prompt_tokens"] - len(raw) // 4) <= 2, f"step {k}: prompt_tokens must be the note-free count ({rep['usage']['prompt_tokens']} vs {len(raw) // 4})")
    jf = os.path.join(jd, a.task + ".jsonl"); recs = [json.loads(l) for l in open(jf)] if os.path.exists(jf) else []
    check(len(recs) == sum(1 for it in items if it["type"] == "model"), "the journal must hold one line per request")
    check(all("PRIVATE NOTE" not in json.dumps(r["request"]) and T.PLAN_HEAD not in json.dumps(r["request"], ensure_ascii=False) for r in recs), "journal requests must be note-free")
    check(noted_at is None or any(r["noted"] for r in recs), "the journal must mark the noted requests")
    print(f"== http check {a.task} (position {a.position}): takeover at {noted_at}; journal lines {len(recs)}; "
          + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILED"))
    for x in fails[:12]: print("   FAILED:", x)
    srv.shutdown(); up.shutdown()
    return not fails


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sim", "http"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True); p.add_argument("--hints", nargs="+", required=True)
        p.add_argument("--bundle", default="submissions/budgetfit_v5"); p.add_argument("--deadline", type=int, default=12)
        if name == "sim":
            p.add_argument("--tasks"); p.add_argument("--exclude", nargs="*"); p.add_argument("--show", type=int, default=0)
        else:
            p.add_argument("--task", required=True); p.add_argument("--position", choices=["A", "B", "C"], default="A")
    a = ap.parse_args()
    sys.exit(0 if (cmd_sim(a) if a.cmd == "sim" else cmd_http(a)) else 1)


if __name__ == "__main__":
    main()
