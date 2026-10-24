"""E4 — cross-checks against an independent public study, and what the leaderboard's own numbers say.

Inputs (all public):
  ext/gluzdov/*.csv   Dmitrii Gluzdov, "Gemma 4 task soundness and local results" (Kaggle dataset, CC BY 4.0): an independent
                      soundness audit of the 129 public tasks and 692 agent outcomes (8 configurations on 70 development tasks,
                      3 on 44 Rich tasks, gemma-4-31b, seed 42), plus dated public scores of identical archives.
  ext/lb_score_counts_2026-10-20.csv   score histogram of the public leaderboard (3,294 teams, downloaded 20 Oct 2026).
  out/soundness.jsonl, out/task_anatomy.csv   our E2 labels and E1 anatomy.

Analyses:
  A. audit agreement: our E2 labels vs Gluzdov's (sound / not sound), with the disagreeing tasks; and a three-way comparison
     with busyaprime's rebuilt grader (ext/busyaprime/audit_junit.csv, CC BY-SA 4.0; per-task verdicts).
  B. public split size: the only n whose truncated scores floor(100 k/n)/100 produce exactly the observed set of score values.
  C. task-level correlation rho: (i) beta-binomial fit to per-task solve counts across configurations; (ii) pooled rerun
     variance of identical archives on the public split, relative to binomial.
  D. which tasks get solved: solve rate per task-anatomy group (E1), and the solve rate of tasks our audit calls env-blocked;
     a run-level logistic model (configuration and repository fixed effects, SEs clustered by task) to separate correlated
     features; the small-vs-rest gap within each configuration; leave-one-repository-out prediction of which tasks any
     configuration solves, from anatomy alone.
  E. consequences: MDD and expected public/private gap at the inferred n; chance that a mean-0.17 bundle shows 0.22+ on its
     best of r submissions (selection on the leaderboard).
Writes out/e4_crosscheck.json and out/e4_solve_by_size.png.
Usage: ../.venv/bin/python e4_crosscheck.py   (needs statsmodels)"""
import json
import math
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import optimize, stats

HERE = os.path.dirname(os.path.abspath(__file__))
OUT, EXT = os.path.join(HERE, 'out'), os.path.join(HERE, 'ext')
Z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
N_HIDDEN = 120                      # host: ~120 tasks across both score splits
REPEATS = {   # public scores of byte-identical submission files run more than once
    # Afshar, "58 Tasks, Bronze Is a 124-Team Tie" section 8 (read 17 Oct): groups by sha256 of the submission files
    'Budget-Fit files c9829b6a (Afshar)': [0.18, 0.18, 0.18, 0.17, 0.13, 0.17, 0.17],
    'SuperAgent v8 files 9f8886a9 (Afshar)': [0.13, 0.20, 0.18],
    'Budget-Aware v2 v10 files 56010e9e (Afshar)': [0.22, 0.12, 0.15],
    'Baseline v2-3 files 5d05a6e0 (Afshar)': [0.13, 0.18],
    'early config d4460290 (Afshar)': [0.12, 0.08],
    'Budget-Fit + one line 248b4a4c (Afshar)': [0.13, 0.15],
    # Gluzdov dataset: archive f3534769, not among Afshar's groups. Gluzdov's budget-aware and alternative-prompt groups
    # are left out: they share runs with Afshar's 56010e9e and 9f8886a9 groups and would be counted twice. The "0.24"
    # baseline score was never shown by a scored version (its best badge is 0.18), so that pair is out too.
    'coder-analyzer archive f3534769 (Gluzdov)': [0.12, 0.10, 0.06],
}


def audit_agreement():
    ours = pd.DataFrame([json.loads(l) for l in open(os.path.join(OUT, 'soundness.jsonl'))])[['instance_id', 'repo', 'label']]
    g = pd.read_csv(os.path.join(EXT, 'gluzdov', 'task_soundness.csv'))
    m = ours.merge(g, left_on='instance_id', right_on='task_id', validate='one_to_one')
    a, b = m.label == 'sound', m.sound == 1
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    dis = m[a != b]
    return m, {
        'tasks': len(m), 'both_sound': int((a & b).sum()), 'ours_only': int((a & ~b).sum()),
        'theirs_only': int((~a & b).sum()), 'neither': int((~a & ~b).sum()), 'cohen_kappa': round((po - pe) / (1 - pe), 3),
        'theirs_only_dependency_overlay': int(dis[~a[a != b]].dependency_repaired.sum()),
        'theirs_only_by_our_label': dis[~a[a != b]].label.value_counts().to_dict(),
        'ours_only_their_status': dis[a[a != b]].status.value_counts().to_dict(),
        'disagreements': dis[['instance_id', 'label', 'status', 'dependency_repaired']].to_dict('records'),
    }


def three_audits(m):
    """Ours vs Gluzdov vs busyaprime (rebuilt grader, JUnit surrogate verdicts; dataset busyaprime/gemma-4-developer-agent-grader-
    audit, CC BY-SA 4.0 - its per-task verdicts give the agreement statistics and the all-three-sound set)."""
    b = pd.read_csv(os.path.join(EXT, 'busyaprime', 'audit_junit.csv'))[['instance_id', 'verdict']]
    t = m[['instance_id', 'label', 'sound']].merge(b, on='instance_id', validate='one_to_one')
    v = pd.DataFrame({'ours': t.label == 'sound', 'gluzdov': t.sound == 1, 'busyaprime': t.verdict == 'sound'})

    def kappa(x, y):
        po = (x == y).mean()
        pe = x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean())
        return round(float((po - pe) / (1 - pe)), 3)
    n_sound = v.sum(axis=1)
    k, n = n_sound.to_numpy(), 3   # Fleiss kappa for two categories
    pj = np.array([k.sum(), (n - k).sum()]) / (len(k) * n)
    pi = ((k * (k - 1) + (n - k) * (n - k - 1)) / (n * (n - 1))).mean()
    return {'sound_counts': {c: int(v[c].sum()) for c in v}, 'sound_in_all_three': int((n_sound == 3).sum()),
            'sound_in_none': int((n_sound == 0).sum()), 'split': int(((n_sound > 0) & (n_sound < 3)).sum()),
            'pairwise_kappa': {f'{a}-{b}': kappa(v[a], v[b]) for a, b in (('ours', 'gluzdov'), ('ours', 'busyaprime'),
                                                                          ('gluzdov', 'busyaprime'))},
            'fleiss_kappa': round(float((pi - (pj ** 2).sum()) / (1 - (pj ** 2).sum())), 3),
            'all_three_sound_ids': sorted(t.instance_id[n_sound == 3])}


def score_grid():
    lb = pd.read_csv(os.path.join(EXT, 'lb_score_counts_2026-10-20.csv'))
    seen = {round(s * 100) for s in lb.score}
    top = max(seen)
    rules = {'round': lambda x: math.floor(x * 100 + 0.5), 'floor': lambda x: math.floor(x * 100 + 1e-9)}
    fits = [(n, r) for n in range(10, 400) for r, f in rules.items()
            if {f(k / n) for k in range(n + 1) if f(k / n) <= top} == seen]
    return lb, {'teams': int(lb.teams.sum()), 'distinct_scores': sorted(seen), 'exact_fits': fits}


def k_of(score, n):
    """number of resolved tasks behind a truncated public score"""
    return min(k for k in range(n + 1) if math.floor(100 * k / n + 1e-9) == round(score * 100))


def rho_cross_config():
    e = pd.read_csv(os.path.join(EXT, 'gluzdov', 'all_config_eval.csv'))
    res = {}
    for split, d in e.groupby('split'):
        m = d.pivot_table(index='task_id', columns='config', values='resolved').dropna()
        k, n = m.sum(axis=1).values, m.shape[1]
        fit = optimize.minimize(lambda par: -stats.betabinom.logpmf(k, n, *np.exp(par)).sum(), [0.0, 0.0])
        a, b = np.exp(fit.x)
        res[split] = {'tasks': len(k), 'configs': n, 'p': round(a / (a + b), 3), 'rho': round(1 / (a + b + 1), 3),
                      'solved_by_none': int((k == 0).sum()), 'solved_by_none_if_rho0': round(len(k) * (1 - k.mean() / n) ** n, 1),
                      'solved_by_all': int((k == n).sum())}
    return res


def rho_reruns(n):
    ss, df, ps, groups = 0.0, 0, [], {}
    for name, scores in REPEATS.items():
        ks = np.array([k_of(s, n) for s in scores])
        groups[name] = ks.tolist()
        ss += ((ks - ks.mean()) ** 2).sum()
        df += len(ks) - 1
        ps += list(ks / n)
    p = float(np.mean(ps))
    binom = n * p * (1 - p)
    ratio = ss / df / binom
    lo, hi = ss / stats.chi2.ppf(0.975, df) / binom, ss / stats.chi2.ppf(0.025, df) / binom
    return {'resolved_counts': groups, 'p': round(p, 3), 'df': df, 'pooled_rerun_sd': round(math.sqrt(ss / df) / n, 4),
            'var_ratio_to_binomial': round(ratio, 2), 'var_ratio_95ci': [round(lo, 2), round(hi, 2)],
            'rho_hat': round(1 - ratio, 2), 'rho_95ci': [round(max(0.0, 1 - hi), 2), round(1 - lo, 2)]}


def solve_by_anatomy(m):
    e = pd.read_csv(os.path.join(EXT, 'gluzdov', 'all_config_eval.csv'))
    t = e.groupby('task_id').agg(solve=('resolved', 'mean'), ever=('resolved', 'max')).reset_index()
    a = pd.read_csv(os.path.join(OUT, 'task_anatomy.csv'))
    d = a.merge(t, left_on='instance_id', right_on='task_id', validate='one_to_one')
    d = d.merge(m[['instance_id', 'label']], on='instance_id', validate='one_to_one')
    groups = {}
    for col in ('single_file_small', 'size_class', 'kind', 'localized', 'pr_template', 'label'):
        g = d.groupby(col).agg(tasks=('solve', 'size'), mean_solve=('solve', 'mean'), ever_solved=('ever', 'mean'))
        groups[col] = {str(k): {kk: round(float(vv), 3) for kk, vv in v.items()} for k, v in g.iterrows()}
    corr = {c: round(float(stats.spearmanr(d[c], d.solve).statistic), 2)
            for c in ('lines_added', 'hunks', 'src_files', 'statement_words', 'test_lines_added')}
    never = d[(d.lines_added > 100) | (d.kind == 'adds new file')]
    return d, {'tasks': len(d), 'groups': groups, 'spearman_vs_solve': corr,
               'large_or_new_file': {'tasks': len(never), 'ever_solved': int(never.ever.sum())}}


def anatomy_features(d):
    d = d.copy()
    d['log_lines'] = np.log2(d.lines_added + 1)          # per doubling of source lines added
    d['log_words'] = np.log2(d.statement_words)
    for c in ('localized', 'pr_template'):
        d[c] = d[c].astype(int)
    return d


def regression():
    """Run-level logistic regression with configuration + repository fixed effects, SEs clustered by task. Tasks that add a
    new file are kept; their zero solves are absorbed by size (a 'new file' dummy would separate perfectly)."""
    e = pd.read_csv(os.path.join(EXT, 'gluzdov', 'all_config_eval.csv'))
    a = pd.read_csv(os.path.join(OUT, 'task_anatomy.csv')).drop(columns='repo')
    d = anatomy_features(e.merge(a, left_on='task_id', right_on='instance_id', validate='many_to_one'))
    groups = d.task_id.astype('category').cat.codes
    models = {}
    for name, rhs in (('size only', 'log_lines'), ('full', 'log_lines + localized + pr_template + log_words')):
        m = smf.glm(f'resolved ~ {rhs} + C(config) + C(repo)', d, family=sm.families.Binomial()).fit(
            cov_type='cluster', cov_kwds={'groups': groups})
        ci = m.conf_int()
        models[name] = {v: {'odds_ratio': round(float(np.exp(m.params[v])), 2), 'ci95': [round(float(np.exp(ci.loc[v, 0])), 2),
                        round(float(np.exp(ci.loc[v, 1])), 2)], 'p': round(float(m.pvalues[v]), 4)} for v in rhs.split(' + ')}
    per_config = d.groupby(['config', 'single_file_small']).resolved.mean().unstack()
    pr_by_size = pd.crosstab(d.pr_template, pd.cut(d.lines_added, [-1, 5, 20, 100, np.inf], labels=['≤5', '6–20', '21–100', '>100']),
                             values=d.task_id, aggfunc='nunique')
    return {'runs': len(d), 'tasks': int(d.task_id.nunique()), 'models': models,
            'small_vs_rest_by_config': {c: {'small': round(float(r[True]), 2), 'rest': round(float(r[False]), 2)}
                                        for c, r in per_config.iterrows()},
            'pr_tasks_by_size': {str(bool(k)): {str(c): int(v) for c, v in r.items()} for k, r in pr_by_size.iterrows()}}


def auc(y, s):
    r = stats.rankdata(s)
    n1 = int(y.sum())
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y) - n1)))


def cross_repo():
    """Fit a task-level binomial model on one repository's outcomes, score the other repository's tasks from anatomy alone."""
    e = pd.read_csv(os.path.join(EXT, 'gluzdov', 'all_config_eval.csv'))
    t = e.groupby('task_id').agg(k=('resolved', 'sum'), n=('resolved', 'size')).reset_index()
    t = anatomy_features(t.merge(pd.read_csv(os.path.join(OUT, 'task_anatomy.csv')), left_on='task_id', right_on='instance_id'))
    res = {}
    for name, feats in (('size only', ['log_lines']), ('size + anchor + statement length', ['log_lines', 'localized', 'log_words'])):
        for test in ('Textualize/rich', 'fastapi/fastapi'):
            tr, te = t[t.repo != test], t[t.repo == test]
            m = sm.GLM(np.c_[tr.k, tr.n - tr.k], sm.add_constant(tr[feats]), family=sm.families.Binomial()).fit()
            s = m.predict(sm.add_constant(te[feats], has_constant='add')).to_numpy()
            y = (te.k > 0).to_numpy(); rng = np.random.default_rng(0); boot = []
            for _ in range(2000):   # bootstrap over test tasks (model fixed)
                i = rng.integers(0, len(y), len(y))
                if 0 < y[i].sum() < len(i):
                    boot.append(auc(y[i], s[i]))
            res[f'{name} -> {test.split("/")[1]}'] = {'test_tasks': len(te), 'auc_ever_solved': round(auc(y, s), 2),
                                                     'auc_95ci': [round(float(np.percentile(boot, 2.5)), 2), round(float(np.percentile(boot, 97.5)), 2)],
                                                     'spearman_mean_solve': round(float(stats.spearmanr(s, te.k / te.n).statistic), 2)}
    return res


def consequences(n_pub, rho_lo, rho_hi, p=0.16, bundle_p=29 / 174):   # bundle = the 0.22-badge files, runs 13/7/9 of 58
    n_priv = N_HIDDEN - n_pub
    mdd = {f'rho={r}': round(Z * math.sqrt(2 * p * (1 - p) * (1 - r) / n_pub), 3) for r in (0.0, rho_lo, rho_hi)}
    # same submission scored on the two splits: different tasks (task sampling) plus a new trajectory -> p(1-p)(1/n1+1/n2)
    gap_sd = math.sqrt(p * (1 - p) * (1 / n_pub + 1 / n_priv))
    sel = {}
    for r in (rho_lo, rho_hi):
        sd = math.sqrt(n_pub * bundle_p * (1 - bundle_p) * (1 - r))
        q = 1 - stats.norm.cdf((k_of(0.22, n_pub) - 0.5 - n_pub * bundle_p) / sd)    # P(one run shows >= 0.22)
        sel[f'rho={r}'] = {'one_run': round(q, 3), 'best_of_5': round(1 - (1 - q) ** 5, 3), 'best_of_10': round(1 - (1 - q) ** 10, 3)}
    return {'n_public': n_pub, 'n_private_assumed': n_priv, 'p': p, 'mdd_one_run_each': mdd,
            'public_private_gap_sd': round(gap_sd, 3), 'bundle_mean': round(bundle_p, 4), 'p_show_0.22_or_more': sel}


def plot(d):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ink, ink2, grid, surface = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
    blue = '#2a78d6'
    plt.rcParams.update({'font.size': 10, 'axes.edgecolor': grid, 'axes.labelcolor': ink2, 'xtick.color': ink2,
                         'ytick.color': ink2, 'axes.titlecolor': ink, 'figure.facecolor': surface, 'axes.facecolor': surface})
    order = ['≤5', '6–20', '21–100', '>100']
    g = d.groupby('size_class').agg(n=('solve', 'size'), solve=('solve', 'mean'), ever=('ever', 'mean')).reindex(order)
    fig, ax = plt.subplots(figsize=(6.4, 3.2), dpi=150)
    x = np.arange(len(order))
    ax.bar(x, g.ever, width=0.6, color=blue, alpha=0.28, label='solved by at least one configuration', zorder=2)
    ax.bar(x, g.solve, width=0.6, color=blue, label='mean solve rate over configurations', zorder=3)
    for i, (n, s, e) in enumerate(zip(g.n, g.solve, g.ever)):
        ax.annotate(f'{s:.0%} / {e:.0%}\nn={n}', (i, max(e, 0.02)), xytext=(0, 4), textcoords='offset points',
                    ha='center', va='bottom', color=ink2, fontsize=8)
    ax.set_xticks(x, [f'{o} lines' for o in order])
    ax.set_ylim(0, 0.85)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.grid(axis='y', color=grid, linewidth=0.6, zorder=0)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_xlabel('source lines changed (added + removed) by the gold patch')
    ax.legend(frameon=False, fontsize=8, loc='upper right')
    ax.set_title('Agent solve rate by task size (114 tasks, Gluzdov outcomes)', loc='left', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'e4_solve_by_size.png'))


def main():
    m, agree = audit_agreement()
    _, grid_ = score_grid()
    assert grid_['exact_fits'] == [(58, 'floor')], grid_['exact_fits']
    n_pub = grid_['exact_fits'][0][0]
    cross, rerun = rho_cross_config(), rho_reruns(n_pub)
    d, solve = solve_by_anatomy(m)
    res = {'audit_agreement': agree, 'three_audits': three_audits(m), 'score_grid': grid_, 'rho_cross_config': cross, 'rho_reruns': rerun,
           'solve_by_anatomy': solve, 'regression': regression(), 'cross_repo': cross_repo(), 'consequences': consequences(n_pub, 0.3, 0.6)}
    json.dump(res, open(os.path.join(OUT, 'e4_crosscheck.json'), 'w'), indent=1, ensure_ascii=False)
    plot(d)
    show = {k: v for k, v in res.items() if k != 'audit_agreement'}
    print(json.dumps({**{k: v for k, v in agree.items() if k != 'disagreements'}}, ensure_ascii=False))
    print(json.dumps(show, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
