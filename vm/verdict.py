#!/usr/bin/env python3
"""Pre-registered verdict for a paired candidate test (Nov 10 plan). Per pass: gain = candidate resolved - base resolved
on the tasks both arms finished. Adopt when the mean gain over the passes is >= --gain and the candidate's mean tool
calls, output tokens and duration are each <= --cost x the base's (averaged over the passes). Prints a table and one
line "VERDICT ADOPT" or "VERDICT REJECT".
  python3 verdict.py --base results/replica/b1 results/replica/b2 --cand results/replica/c1 results/replica/c2 [--gain 3] [--cost 1.08]
      [--tasks <id list>] [--cost-keys calls,tok]   (an adapter arm runs on a stretched clock: judge its cost on calls and tokens)
"""
import argparse, json, os, statistics as st


def load(d):
    out = {}
    for line in open(os.path.join(d, "agent_run", "task_results.jsonl")):
        r = json.loads(line); tp = os.path.join(d, "agent_run", "traces", f"trace_{r['instance_id']}.json")
        tok = (json.load(open(tp)).get("final_metrics") or {}).get("total_completion_tokens", 0) if os.path.exists(tp) else 0
        out[r["instance_id"]] = dict(res=bool(r.get("resolved")), calls=int(r.get("tool_calls") or 0), tok=tok,
                                     sec=float(r.get("duration_seconds") or 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", nargs="+", required=True); ap.add_argument("--cand", nargs="+", required=True)
    ap.add_argument("--gain", type=float, default=3); ap.add_argument("--cost", type=float, default=1.08)
    ap.add_argument("--tasks", help="file of instance ids: judge only these tasks"); ap.add_argument("--cost-keys", default="calls,tok,sec")
    a = ap.parse_args()
    assert len(a.base) == len(a.cand), "one base run per candidate run"
    keep = {l.strip() for l in open(a.tasks) if l.strip() and not l.startswith("#")} if a.tasks else None
    keys = a.cost_keys.split(","); gains, ratios = [], {k: [] for k in ("calls", "tok", "sec")}
    for bd, cd in zip(a.base, a.cand):
        b, c = load(bd), load(cd); common = sorted(t for t in set(b) & set(c) if keep is None or t in keep)
        rb, rc = sum(b[t]["res"] for t in common), sum(c[t]["res"] for t in common)
        wins = [t for t in common if c[t]["res"] and not b[t]["res"]]; losses = [t for t in common if b[t]["res"] and not c[t]["res"]]
        gains.append(rc - rb)
        for k in ratios: ratios[k].append(st.mean(c[t][k] for t in common) / max(1e-9, st.mean(b[t][k] for t in common)))
        print(f"{os.path.basename(bd)} vs {os.path.basename(cd)}: {len(common)} common | base {rb} cand {rc} gain {rc - rb:+d} | "
              f"wins {len(wins)} losses {len(losses)} | calls x{ratios['calls'][-1]:.2f} tokens x{ratios['tok'][-1]:.2f} time x{ratios['sec'][-1]:.2f}")
    mg = st.mean(gains); mr = {k: st.mean(v) for k, v in ratios.items()}
    ok = mg >= a.gain and all(mr[k] <= a.cost for k in keys)
    print(f"mean gain {mg:+.1f} per pass (need >= {a.gain:+g}) | cost calls x{mr['calls']:.2f} tokens x{mr['tok']:.2f} time x{mr['sec']:.2f} (need <= x{a.cost} on {a.cost_keys})")
    print("VERDICT ADOPT" if ok else "VERDICT REJECT")


if __name__ == "__main__":
    main()
