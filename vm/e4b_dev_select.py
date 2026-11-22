#!/usr/bin/env python3
"""E4B side track (research/PLAN_E4B.md): the task list of the screens.

128 training-pool tasks the 31B solves (results/lists/bf5_train_solved.txt), in two halves of 64 (A and B). The draw is
fixed by the seed and spread over projects: the projects are shuffled, then one task per project per round, so the
first 95 picks are 95 different projects. Picks go to A and B in turn, which gives both halves the same spread.
The tasks are easy enough for the E4B to solve some (its practice solves were all tasks the 31B solves too) and come
from projects the confirmation never uses: a task of an EVAL project (results/lists/rebench_eval.txt) stops the script.

  python3 e4b_dev_select.py [--seed 0] [--n 128] [--root /mnt/biohub/kdata/gemma4] [--prefix results/lists/e4b_dev]
writes <prefix>A.txt, <prefix>B.txt and <prefix>128.txt (instance ids, one per line, # comments).
"""
import argparse, csv, os, random


def ids(path):
    return [l.strip() for l in open(path) if l.strip() and not l.startswith("#")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--n", type=int, default=128)
    ap.add_argument("--root", default="/mnt/biohub/kdata/gemma4"); ap.add_argument("--prefix", default="results/lists/e4b_dev")
    a = ap.parse_args(); os.chdir(a.root)
    repo_of = {r["instance_id"]: r["repo"] for r in csv.DictReader(open("results/rebench_soundness.csv"))}
    repo = lambda i: repo_of.get(i) or i.rsplit("_", 1)[0]
    pool = ids("results/lists/bf5_train_solved.txt")
    eval_repos = {repo(i) for i in ids("results/lists/rebench_eval.txt")}
    bad = [i for i in pool if repo(i) in eval_repos]
    assert not bad, f"tasks of EVAL projects in the pool: {bad[:5]}"
    assert len(pool) >= a.n and a.n % 2 == 0, (len(pool), a.n)
    rng = random.Random(a.seed)
    by = {}
    for i in sorted(pool): by.setdefault(repo(i), []).append(i)
    repos = sorted(by); rng.shuffle(repos)
    for r in repos: rng.shuffle(by[r])
    picks, rnd = [], 0
    while len(picks) < a.n:
        for r in repos:
            if rnd < len(by[r]) and len(picks) < a.n: picks.append(by[r][rnd])
        rnd += 1
    halves = {"A": picks[0::2], "B": picks[1::2]}
    head = (f"# E4B side track: {{n}} tasks of the screens ({{what}}); seed {a.seed}, from bf5_train_solved.txt "
            f"({len(pool)} tasks, {len(repos)} projects); written by vm/e4b_dev_select.py")
    for k, lst in halves.items():
        open(f"{a.prefix}{k}.txt", "w").write(head.format(n=len(lst), what=f"half {k}") + "\n" + "\n".join(lst) + "\n")
    open(f"{a.prefix}{a.n}.txt", "w").write(head.format(n=len(picks), what="both halves") + "\n" + "\n".join(picks) + "\n")
    for k, lst in halves.items():
        print(f"half {k}: {len(lst)} tasks from {len({repo(i) for i in lst})} projects; first {lst[:3]}")
    print(f"all: {len(picks)} tasks from {len({repo(i) for i in picks})} projects; no EVAL project ({len(eval_repos)} checked)")


if __name__ == "__main__":
    main()
