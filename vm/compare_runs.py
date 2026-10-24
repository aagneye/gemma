#!/usr/bin/env python3
"""Paired comparison of two evaluation runs on their common tasks (Kaggle-environment or VM-replica results.csv).

  python compare_runs.py <baseline_eval_dir> <candidate_eval_dir> [--min-gain 3]
Prints resolved counts on common tasks, wins/losses, the sign-test p-value of the discordant pairs, mean duration
and the 120-task time projection, and the adoption verdict used by the factory loop (CLAUDE.md step 5).
"""
import argparse, csv, math, statistics
from pathlib import Path


def load(d):
    return {r["instance_id"]: r for r in csv.DictReader(open(Path(d) / "results.csv"))}


def sign_p(w, l):
    n = w + l
    if n == 0: return 1.0
    k = max(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("cand"); ap.add_argument("--min-gain", type=int, default=3)
    a = ap.parse_args()
    b, c = load(a.base), load(a.cand)
    common = [i for i in b if i in c]
    res = lambda r: str(r["resolved"]) == "True"
    rb = sum(res(b[i]) for i in common); rc = sum(res(c[i]) for i in common)
    wins = [i for i in common if res(c[i]) and not res(b[i])]; losses = [i for i in common if res(b[i]) and not res(c[i])]
    db = statistics.mean(float(b[i]["duration_s"] or 0) for i in common); dc = statistics.mean(float(c[i]["duration_s"] or 0) for i in common)
    print(f"common tasks {len(common)} | baseline {rb} | candidate {rc} | gain {rc - rb:+d}")
    print(f"wins {len(wins)} {wins}\nlosses {len(losses)} {losses}\nsign-test p = {sign_p(len(wins), len(losses)):.3f}")
    print(f"mean duration baseline {db:.0f}s candidate {dc:.0f}s | candidate 120-task projection {dc * 120 / 3600:.1f} h (same hardware as its run)")
    ok = rc - rb >= a.min_gain and dc <= db * 1.08
    print("VERDICT:", "ADOPT" if ok else "REJECT", f"(needs gain >= {a.min_gain} and no >8% time regression)")


if __name__ == "__main__":
    main()
