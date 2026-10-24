#!/usr/bin/env python3
"""Kaggle submissions with score AND error description (the CLI table hides errors).
  python sub_status.py [--n 6] [--wait REF]   # --wait polls every 15 min until REF has a score or an error"""
import argparse, time
from kaggle.api.kaggle_api_extended import KaggleApi


def rows(api, n):
    out = []
    for s in api.competition_submissions("gemma-4-developer-agent")[:n]:
        out.append((s.ref, str(s.date)[:16], getattr(s, "public_score", "") or "", (getattr(s, "error_description", "") or "")[:120], (s.description or "")[:70]))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=6); ap.add_argument("--wait", type=int)
    a = ap.parse_args(); api = KaggleApi(); api.authenticate()
    while True:
        rs = rows(api, a.n)
        if not a.wait or any(r[0] == a.wait and (r[2] or r[3]) for r in rs): break
        time.sleep(900)
    for r in rs: print(" | ".join(str(x) for x in r))


if __name__ == "__main__":
    main()
