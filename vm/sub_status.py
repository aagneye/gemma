#!/usr/bin/env python3
"""Kaggle submissions with score AND error description (the CLI table hides errors).
  python sub_status.py [--n 6] [--wait REF] [--stats]
    --wait REF   poll every 15 min until REF has a score or an error
    --stats      per-config summary: n scored, mean tasks/58, SE, errors, earliest valid (scored) ref
Config key = the submission description up to the first ':' (our descriptions start with the bundle name)."""
import argparse, collections, statistics, time
from kaggle.api.kaggle_api_extended import KaggleApi

LB_TASKS = 58


def all_submissions(api, page_size=100):
    """Every submission (the API returns one page of 20 by default; by Nov 8 we exceed that)."""
    out, page = [], 1
    while True:
        batch = list(api.competition_submissions("gemma-4-developer-agent", page_number=page, page_size=page_size))
        out.extend(batch)
        if len(batch) < page_size or page > 50: return out
        page += 1


def rows(api, n):
    out = []
    for s in all_submissions(api)[:n]:
        out.append((s.ref, str(s.date)[:16], getattr(s, "public_score", "") or "", (getattr(s, "error_description", "") or "")[:120], (s.description or "")[:70]))
    return out


def stats(api):
    groups = collections.defaultdict(list)
    for s in all_submissions(api):
        key = (s.description or "?").split(":")[0].strip()[:28]   # every ship message starts with "<bundle>:"
        groups[key].append(s)
    print(f"{'config':28} {'n_sc':>4} {'mean/58':>7} {'SE':>5} {'err':>3} {'pend':>4}  earliest valid ref")
    for key, ss in sorted(groups.items(), key=lambda kv: min(str(x.date) for x in kv[1])):
        scored = [s for s in ss if (getattr(s, "public_score", None) or "") != ""]
        errs = [s for s in ss if getattr(s, "error_description", None)]
        pend = [s for s in ss if "PENDING" in str(getattr(s, "status", ""))]
        tasks = [float(s.public_score) * LB_TASKS for s in scored]
        mean = statistics.mean(tasks) if tasks else float("nan")
        se = (statistics.stdev(tasks) / len(tasks) ** 0.5) if len(tasks) > 1 else (1.56 if tasks else float("nan"))
        earliest = min(scored, key=lambda s: str(s.date)).ref if scored else "-"
        print(f"{key:28} {len(scored):>4} {mean:>7.1f} {se:>5.2f} {len(errs):>3} {len(pend):>4}  {earliest}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=6); ap.add_argument("--wait", type=int); ap.add_argument("--stats", action="store_true")
    a = ap.parse_args(); api = KaggleApi(); api.authenticate()
    if a.stats:
        stats(api); return
    while True:
        rs = rows(api, a.n)
        if not a.wait or any(r[0] == a.wait and (r[2] or r[3]) for r in rs): break
        time.sleep(900)
    for r in rs: print(" | ".join(str(x) for x in r))


if __name__ == "__main__":
    main()
