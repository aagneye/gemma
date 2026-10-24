"""E3 — how noisy is a small SWE-agent leaderboard (58 public tasks), and how many reruns does a claimed improvement need?

Model: a submission solves task i with probability q_i (the agent samples its own trajectory), q_i ~ Beta with mean p and
intra-task correlation rho = Var(q) / (p(1-p)). rho = 0: every task is a coin flip with the same bias (pure binomial);
rho = 1: each task is always solved or always failed (a deterministic agent). On a fixed task set of size n the score of one
run has
    Var(rerun) = p(1-p)(1-rho)/n                       (same tasks, new trajectories)
and a fresh task sample (public vs private split) adds the task-sampling term p(1-p)rho/n, giving p(1-p)/n in total.
Comparing two submissions A, B (one run each, same tasks) at a two-sided 5% level with 80% power needs a true difference of
    MDD = (z_.975 + z_.8) * sqrt((pA(1-pA) + pB(1-pB))(1-rho)/n),
and r reruns per submission shrink it by sqrt(r).

The public split has n = 58 tasks: it is the only n whose truncated scores reproduce the leaderboard's set of score values
(e4_crosscheck.py). Evidence on rho is also in e4_crosscheck.py: a beta-binomial fit across 8 configurations gives 0.49-0.57,
pooled reruns of byte-identical files give 0.59 (95% CI 0.03-0.78). We draw rho = 0, 0.3 and 0.6.
Test flakiness is ignored: E2 found no task whose gold patch passes in some runs and fails in others (flaky_gold = 0).
A Monte Carlo check confirms the closed forms. Writes out/e3_noise.json and out/e3_mdd.png, out/e3_reruns.png.
Usage: .venv/bin/python e3_noise.py"""
import json
import os
from collections import Counter

import numpy as np
from scipy import stats

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
Z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
N_PUBLIC = 58                        # public-split tasks, inferred from the score grid (e4_crosscheck.py)
RHOS = (0.0, 0.3, 0.6)
ANNOTATE = 1                         # index into RHOS for the highlighted values (rho = 0.3: conservative end of the evidence)


def rerun_sd(p, n, rho):
    return np.sqrt(p * (1 - p) * (1 - rho) / n)


def mdd(p, n, rho, reruns=1):
    return Z * np.sqrt(2 * p * (1 - p) * (1 - rho) / n / reruns)


def reruns_needed(delta, p, n, rho):
    return int(np.ceil(2 * p * (1 - p) * (1 - rho) / n * (Z / delta) ** 2))


def beta_params(p, rho):
    s = 1 / rho - 1                  # a + b
    return p * s, (1 - p) * s


def monte_carlo(p, n, rho, runs=4000, seed=0):
    """SD of the score across reruns on one fixed task set (averaged over task sets)."""
    rng = np.random.default_rng(seed)
    sds = []
    for _ in range(50):
        q = np.full(n, p) if rho == 0 else rng.beta(*beta_params(p, rho), n)
        scores = rng.binomial(1, q, size=(runs // 50, n)).mean(1)
        sds.append(scores.std(ddof=1))
    return float(np.sqrt(np.mean(np.square(sds))))


def soundness_ceiling():
    rows = [json.loads(l) for l in open(os.path.join(OUT, 'soundness.jsonl'))]
    c = Counter(r['label'] for r in rows)
    unsolvable = c['env_blocked'] + c['gold_fails']   # the scorer rejects even the gold patch
    return dict(counts=dict(c), n=len(rows), ceiling=1 - unsolvable / len(rows))


def plot(summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    ink, ink2, grid, surface = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
    colors, styles = ('#2a78d6', '#eb6834', '#1baf7a'), ('-', '--', ':')   # categorical slots 1-3; style = second channel
    plt.rcParams.update({'font.size': 10, 'axes.edgecolor': grid, 'axes.labelcolor': ink2, 'xtick.color': ink2,
                         'ytick.color': ink2, 'axes.titlecolor': ink, 'figure.facecolor': surface, 'axes.facecolor': surface})

    def frame(ax, title, xlabel, ylabel):
        ax.set_title(title, loc='left', fontsize=11, fontweight='bold')
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', color=grid, lw=0.8)
        ax.spines[['top', 'right']].set_visible(False)

    p = 0.15
    n = np.arange(20, 401)
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    for rho, c, ls in zip(RHOS, colors, styles):
        y = mdd(p, n, rho)
        ax.plot(n, y, color=c, ls=ls, lw=2, label=f'ρ = {rho}')
    ax.axvline(N_PUBLIC, color=ink2, lw=1)
    ax.annotate(f'{N_PUBLIC} public tasks', (N_PUBLIC, 0.30), xytext=(4, 0), textcoords='offset points', color=ink2)
    m = summary['mdd_single_run'][f'rho={RHOS[ANNOTATE]}']
    ax.annotate(f'{m:.2f}', (N_PUBLIC, m), xytext=(6, 6), textcoords='offset points', color=ink, fontweight='bold')
    frame(ax, 'Smallest score gap one run each can detect (p ≈ 0.15)', 'tasks scored', 'detectable difference (80% power)')
    ax.set_ylim(0, 0.32)
    ax.set_xlim(20, 400)
    ax.legend(frameon=False, loc='upper right')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'e3_mdd.png'))
    plt.close(fig)

    deltas = np.linspace(0.02, 0.12, 51)
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    for rho, c, ls in zip(RHOS, colors, styles):
        y = [reruns_needed(d, p, N_PUBLIC, rho) for d in deltas]
        ax.plot(deltas, y, color=c, ls=ls, lw=2, label=f'ρ = {rho}')
    r3 = reruns_needed(0.03, p, N_PUBLIC, RHOS[ANNOTATE])
    ax.plot([0.03], [r3], 'o', ms=8, color=colors[ANNOTATE], mec=surface, mew=2)
    ax.annotate(f'+0.03 needs {r3} runs each', (0.03, r3), xytext=(12, 6), textcoords='offset points', color=ink,
                fontweight='bold')
    ax.set_yscale('log')
    ax.set_yticks([1, 2, 5, 10, 20, 50, 100])
    ax.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    frame(ax, f'Runs per submission to confirm a gain ({N_PUBLIC} tasks, p ≈ 0.15)', 'true improvement',
          'runs per submission (log)')
    ax.legend(frameon=False, loc='upper right')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'e3_reruns.png'))
    plt.close(fig)


def main():
    p = 0.15
    summary = dict(
        p=p, n=N_PUBLIC,
        rerun_sd={f'rho={r}': float(rerun_sd(p, N_PUBLIC, r)) for r in RHOS},
        monte_carlo_rerun_sd={f'rho={r}': monte_carlo(p, N_PUBLIC, r) for r in RHOS},
        mdd_single_run={f'rho={r}': float(mdd(p, N_PUBLIC, r)) for r in RHOS},
        mdd_by_n_rho03={str(k): float(mdd(p, k, 0.3)) for k in (30, 58, 120, 240, 500)},
        reruns_needed={f'rho={r}': {str(d): reruns_needed(d, p, N_PUBLIC, r) for d in (0.02, 0.03, 0.05, 0.10)} for r in RHOS},
        soundness=soundness_ceiling(),
    )
    json.dump(summary, open(os.path.join(OUT, 'e3_noise.json'), 'w'), indent=1)
    plot(summary)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
