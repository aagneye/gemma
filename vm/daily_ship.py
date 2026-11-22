#!/usr/bin/env python3
"""Daily Kaggle shipper. Runs forever on the VM (tmux `dailyship`, restarted by a cron watchdog).

Policy: at most one submission per UTC day, made as early as possible (from 00:10 UTC), because Kaggle refuses a
new code submission while a previous one is still scoring ("Your team already has 1 pending submissions").
Scoring took ~13 h in October; since Nov 18 a run waits 24-30 h (queue 8-9 h + run 9-10 h + scoring), so the next
run goes in the moment the queue is free, at any hour.

Inputs (in /mnt/biohub/kdata/gemma4/results/):
  ship.txt            line 1 = default bundle  "owner/kernel-slug version message ...", line 2 = fallback bundle
  ship_schedule.txt   optional per-day override "YYYY-MM-DD owner/kernel-slug version message ..." (weekly E4B slot)
  ship_hold.txt       optional hold windows "FROM UNTIL reason" (UTC, e.g. 2026-11-23T18:30 2026-11-26T06:00 ...):
                      while one is open nothing is submitted but the line of ship_once.txt. Delete the file to end it.
  ship_once.txt       optional single line "owner/kernel-slug version message ...": submitted first, once, also inside
                      a hold window; the file is then renamed to ship_once.done_<ref>.txt (vm/ship_adapter.sh writes it),
                      the hold file is put aside (its purpose is met) and ship_followup.txt is written
  ship_followup.txt   "ref owner/kernel-slug version message ...", written by the loop when the once line went in. As
                      long as that first run (ref) is COMPLETE with a public score, the same kernel goes in again before
                      the default: a bundle that passed its checks and ran inside Kaggle's limits keeps the queue. A
                      first run that failed (runtime, exception) gives nothing, so the default goes in again. Delete
                      the file to go back to ship.txt.
Outputs: logs/daily_ship.log (human log; ALERT lines when a day is at risk), results/ledger.csv (one row per ref).
Truth comes from the API submission list, never from CLI text.

  python daily_ship.py                              the loop
  python daily_ship.py --plan [--at 2026-11-24T10:00]   print what the loop would pick at that UTC time (no Kaggle call;
                      SHIP_FAKE_SUBS='[["58700001", "COMPLETE", "0.17"]]' stands in for the submission list)
"""
import csv, datetime as dt, json, os, sys, time, traceback, types
from pathlib import Path

R = Path("/mnt/biohub/kdata/gemma4"); COMP = "gemma-4-developer-agent"
LOG = R / "logs/daily_ship.log"; LEDGER = R / "results/ledger.csv"
SHIP = R / "results/ship.txt"; SCHED = R / "results/ship_schedule.txt"
HOLD = R / "results/ship_hold.txt"; ONCE = R / "results/ship_once.txt"; FOLLOW = R / "results/ship_followup.txt"
START_HHMM = (0, 10); ALERT_HHMM = (2, 0)
FAKE_NOW = None                                    # --plan --at


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC | {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f: f.write(line + "\n")


def now(): return FAKE_NOW or dt.datetime.now(dt.timezone.utc)


def utc(s): return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def hold_now():
    """(until, reason) when a hold window of ship_hold.txt is open now, else None. A line that cannot be read is skipped."""
    if not HOLD.exists(): return None
    for l in HOLD.read_text().splitlines():
        p = l.split(None, 2)
        if len(p) < 2 or l.startswith("#"): continue
        try: a, b = utc(p[0]), utc(p[1])
        except ValueError: continue
        if a <= now() < b: return b, (p[2] if len(p) > 2 else "")
    return None


def followup(subs):
    """The once line again, while its first run (the ref noted when it went in) is COMPLETE with a public score."""
    if not FOLLOW.exists(): return []
    p = FOLLOW.read_text().strip().split(None, 3)
    if len(p) < 3 or not p[2].isdigit(): return []
    s = next((s for s in subs or [] if str(s.ref) == p[0]), None)
    scored = s is not None and "COMPLETE" in str(getattr(s, "status", "")) and str(getattr(s, "public_score", "") or "").strip() not in ("", "None")
    return [(p[1], p[2], p[3] if len(p) > 3 else "", "followup")] if scored else []


def candidates(subs=None):
    """[(kernel, version, message, role)] for today: the once line, the follow-up of a once line whose first run was
    scored, then the schedule override, then ship.txt in order."""
    out = []
    if ONCE.exists():
        for l in ONCE.read_text().splitlines():
            p = l.split(None, 2)
            if len(p) >= 2 and not l.startswith("#") and p[1].isdigit():
                out.append((p[0], p[1], p[2] if len(p) > 2 else "", "once")); break
    out += followup(subs)
    if SCHED.exists():
        for l in SCHED.read_text().splitlines():
            p = l.split(None, 3)
            if len(p) >= 3 and not l.startswith("#") and p[0] == now().date().isoformat():
                out.append((p[1], p[2], p[3] if len(p) > 3 else "", "scheduled"))
    for i, l in enumerate(SHIP.read_text().splitlines()):
        p = l.split(None, 2)
        if len(p) >= 2 and not l.startswith("#"):
            out.append((p[0], p[1], p[2] if len(p) > 2 else "", "default" if i == 0 else "fallback"))
    return out


def pick(failures, subs=None):
    """(candidate or None, hold or None): what goes in now. Inside a hold window only the once line may go."""
    cands = [c for c in candidates(subs) if failures.get(c[0], 0) < 2]; h = hold_now()
    if h: cands = [c for c in cands if c[3] == "once"]
    return (cands[0] if cands else None), h


def ledger_row(ref, kernel, version, role, message):
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["date_utc", "ref", "kernel", "version", "role", "message"])
        w.writerow([now().isoformat(timespec="seconds"), ref, kernel, version, role, message])


def main():
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi(); api.authenticate()
    failures, fail_day = {}, None   # kernel -> non-quota failures today (2 -> skip it for the rest of the day)
    while True:
        try:
            t = now(); today = t.date()
            if fail_day != today: failures, fail_day = {}, today
            subs = api.competition_submissions(COMP)
            todays = [s for s in subs if s.date and s.date.date() == today]
            pending = [s for s in subs if "PENDING" in str(getattr(s, "status", ""))]
            if todays:
                s = todays[0]
                log(f"today done: ref {s.ref} status {s.status} score {getattr(s, 'public_score', '') or '-'} err {(getattr(s, 'error_description', '') or '')[:80]}")
                time.sleep(1800); continue
            if (t.hour, t.minute) < START_HHMM:
                time.sleep(60); continue
            if pending:
                msg = f"waiting: pending ref {pending[0].ref} from {pending[0].date}"
                if (t.hour, t.minute) >= ALERT_HHMM: msg = "ALERT no submission yet; " + msg
                log(msg); time.sleep(900); continue
            cand, hold = pick(failures, subs)
            if not cand:
                if hold: log(f"HOLD until {hold[0]:%Y-%m-%d %H:%M} UTC ({hold[1]}): nothing submitted")
                else: log("ALERT no usable candidate (all failed twice today)")
                time.sleep(900 if hold else 1800); continue
            kernel, version, message, role = cand
            before = {s.ref for s in subs}
            try:
                api.competition_submit_code(file_name="submission.zip", message=message, competition=COMP,
                                            kernel=kernel, kernel_version=int(version), quiet=True)
                time.sleep(45)
                subs = api.competition_submissions(COMP)
                new = [s for s in subs if s.ref not in before]   # by ref, so a submission stamped after midnight is still recorded
                if new:
                    log(f"SUBMITTED {kernel} v{version} ({role}) -> ref {new[0].ref}")
                    ledger_row(new[0].ref, kernel, version, role, message)
                    if role == "once":
                        FOLLOW.write_text(f"{new[0].ref} {kernel} {version} {message}\n")
                        if ONCE.exists(): ONCE.rename(ONCE.with_name(f"ship_once.done_{new[0].ref}.txt"))
                        if HOLD.exists(): HOLD.rename(HOLD.with_name(f"ship_hold.met_{new[0].ref}.txt"))
                        log(f"once line consumed; follow-up noted for ref {new[0].ref}; hold file put aside")
                else:
                    log(f"submit call returned but no submission listed for today ({kernel} v{version}); retrying later")
                    time.sleep(600)
            except Exception as e:
                body = (getattr(getattr(e, "response", None), "text", "") or str(e))[:300].replace("\n", " ")
                low = body.lower()
                if "pending submission" in low:
                    log(f"blocked by pending submission: {body}"); time.sleep(900)
                elif "remaining" in low or "limit" in low or "daily" in low:
                    log(f"quota message: {body}"); time.sleep(1800)
                else:
                    failures[kernel] = failures.get(kernel, 0) + 1
                    log(f"ERROR submitting {kernel} v{version} ({role}, failure {failures[kernel]}): {body}"); time.sleep(300)
        except Exception:
            log("loop error: " + traceback.format_exc().replace("\n", " | ")[:400]); time.sleep(300)


def plan(at):
    """What the loop would pick at a UTC time when no run is pending and the day has no submission yet."""
    global FAKE_NOW
    if at: FAKE_NOW = utc(at)
    subs = [types.SimpleNamespace(ref=r, status=s, public_score=sc) for r, s, sc in json.loads(os.environ.get("SHIP_FAKE_SUBS", "[]"))]
    cand, hold = pick({}, subs)
    hs = f"until {hold[0]:%Y-%m-%d %H:%M} UTC ({hold[1]})" if hold else "none"
    print(f"at {now():%Y-%m-%d %H:%M} UTC | hold: {hs}")
    print("  would submit:", f"{cand[0]} v{cand[1]} ({cand[3]})" if cand else "nothing")


if __name__ == "__main__":
    if "--plan" in sys.argv:
        plan(sys.argv[sys.argv.index("--at") + 1] if "--at" in sys.argv else None)
    else:
        main()
