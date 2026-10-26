#!/usr/bin/env python3
"""Paired comparison of two evaluation runs on their common tasks (Kaggle-environment or VM-replica results.csv).

  python compare_runs.py <baseline_eval_dir> <candidate_eval_dir> [--min-gain 3]
Prints resolved counts on common tasks, wins/losses, the sign-test p-value of the discordant pairs, mean and p90
duration with the 120-task time projection, a per-repo split, the failure-bucket shift matrix (when both dirs hold
a trace_analysis.csv from analyze_traces.py) and the adoption verdict used by the factory loop (CLAUDE.md step 5).
"""
import argparse, collections, csv, math, statistics
from pathlib import Path


def load(d):
    return {r["instance_id"]: r for r in csv.DictReader(open(Path(d) / "results.csv"))}


def load_modes(d):
    p = Path(d) / "trace_analysis.csv"
    return {r["instance_id"]: r.get("mode", "?") for r in csv.DictReader(open(p))} if p.exists() else {}


def sign_p(w, l):
    n = w + l
    if n == 0: return 1.0
    k = max(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def p90(xs):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(math.ceil(0.9 * len(xs))) - 1)] if xs else 0.0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("cand"); ap.add_argument("--min-gain", type=int, default=3)
    a = ap.parse_args()
    b, c = load(a.base), load(a.cand)
    common = [i for i in b if i in c]
    if not common:
        print("no common tasks between the two runs"); return
    res = lambda r: str(r["resolved"]) == "True"
    dur = lambda r: float(r["duration_s"] or 0)
    timed = [i for i in common if (b[i].get("duration_s") or "") != "" and (c[i].get("duration_s") or "") != ""]   # crashed rows have no duration
    rb = sum(res(b[i]) for i in common); rc = sum(res(c[i]) for i in common)
    wins = [i for i in common if res(c[i]) and not res(b[i])]; losses = [i for i in common if res(b[i]) and not res(c[i])]
    db = statistics.mean(dur(b[i]) for i in timed) if timed else 0.0; dc = statistics.mean(dur(c[i]) for i in timed) if timed else 0.0
    if len(timed) < len(common): print(f"note: {len(common) - len(timed)} common task(s) lack a duration (crash/budget cut) and are excluded from time stats")
    print(f"common tasks {len(common)} | baseline {rb} | candidate {rc} | gain {rc - rb:+d}")
    print(f"wins {len(wins)} {wins}\nlosses {len(losses)} {losses}\nsign-test p = {sign_p(len(wins), len(losses)):.3f}")
    print(f"duration mean {db:.0f}s -> {dc:.0f}s | p90 {p90([dur(b[i]) for i in timed]):.0f}s -> {p90([dur(c[i]) for i in timed]):.0f}s"
          f" | candidate 120-task projection {dc * 120 / 3600:.1f} h (p90-based {p90([dur(c[i]) for i in timed]) * 120 / 3600:.1f} h; same hardware as its run)")
    by_repo = collections.defaultdict(lambda: [0, 0, 0])
    for i in common:
        r = by_repo[i.split("_")[0]]; r[0] += 1; r[1] += res(b[i]); r[2] += res(c[i])
    print("per repo: " + " | ".join(f"{k}: {v[1]}->{v[2]} of {v[0]}" for k, v in sorted(by_repo.items())))
    mb, mc = load_modes(a.base), load_modes(a.cand)
    if mb and mc:
        shift = collections.Counter((mb.get(i, "?"), mc.get(i, "?")) for i in common)
        print("bucket shift (baseline mode -> candidate mode, count):")
        for (x, y), n in sorted(shift.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {x:>20} -> {y:<20} {n}")
    ok = rc - rb >= a.min_gain and dc <= db * 1.08
    print("VERDICT:", "ADOPT" if ok else "REJECT", f"(needs gain >= {a.min_gain} on common tasks and no >8% mean-time regression)")


if __name__ == "__main__":
    main()
