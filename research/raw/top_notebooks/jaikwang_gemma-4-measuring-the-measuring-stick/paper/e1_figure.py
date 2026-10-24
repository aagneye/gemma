"""E1 figure — patch size per statement type, coloured by the E2 soundness label.

Rows: bug report vs pull-request description, split by whether the statement names an edited file or symbol (lexical
localisation, task_anatomy.py). x: source lines added by the gold patch (log scale). Colour and marker: E2 label.
Reads out/task_anatomy.csv and out/soundness.jsonl, writes out/e1_anatomy.png.
Usage: ../.venv/bin/python e1_figure.py"""
import json
import os

import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
ROWS = [(False, False, 'bug report, no anchor'), (False, True, 'bug report, names file/symbol'),
        (True, False, 'PR description, no anchor'), (True, True, 'PR description, names file/symbol')]
LABELS = [('sound', 'sound', 'o'), ('env_blocked', 'env-blocked', 's'), ('gold_fails', 'gold fails', '^'),
          ('base_passes', 'base passes', 'D')]


def load():
    anatomy = pd.read_csv(os.path.join(OUT, 'task_anatomy.csv'))
    labels = pd.DataFrame([json.loads(l) for l in open(os.path.join(OUT, 'soundness.jsonl'))])[['instance_id', 'label']]
    d = anatomy.merge(labels, on='instance_id', validate='one_to_one')
    assert len(d) == len(anatomy) == 129, len(d)
    return d


def plot(d):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ink, ink2, grid, surface = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
    colors = ('#2a78d6', '#eb6834', '#1baf7a', '#8a6fd1')   # categorical slots 1-4 (as in e3); marker = second channel
    plt.rcParams.update({'font.size': 10, 'axes.edgecolor': grid, 'axes.labelcolor': ink2, 'xtick.color': ink2,
                         'ytick.color': ink2, 'axes.titlecolor': ink, 'figure.facecolor': surface, 'axes.facecolor': surface})
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=150)
    for (key, name, marker), c in zip(LABELS, colors):
        ys, xs = [], []
        for y, (pr, loc, _) in enumerate(ROWS):
            sel = d[(d.pr_template == pr) & (d.localized == loc) & (d.label == key)]
            xs += list(sel.lines_added + 1)
            ys += list(y + rng.uniform(-0.25, 0.25, len(sel)))
        n = int((d.label == key).sum())
        ax.scatter(xs, ys, s=22, marker=marker, color=c, alpha=0.85, edgecolors=surface, linewidths=0.6,
                   label=f'{name} ({n})', zorder=3)
    for y, (pr, loc, _) in enumerate(ROWS):
        n = int(((d.pr_template == pr) & (d.localized == loc)).sum())
        ax.annotate(f'n={n}', (1, y), xytext=(-6, 0), textcoords='offset points', ha='right', va='center',
                    color=ink2, fontsize=8, annotation_clip=False)
    ax.set_xscale('log')
    ax.set_xlim(0.8, 2e4)
    ax.set_yticks(range(len(ROWS)), [r[2] for r in ROWS])
    ax.invert_yaxis()
    ax.set_xlabel('source lines added by the gold patch + 1 (log scale)')
    ax.set_title('Patch size by statement type (129 public tasks)', loc='left', fontsize=11,
                 fontweight='bold')
    ax.grid(axis='x', color=grid, lw=0.8)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.tick_params(axis='y', length=0, pad=34)
    ax.legend(frameon=False, loc='upper center', bbox_to_anchor=(0.4, -0.2), ncol=4, fontsize=9,
              handletextpad=0.2, columnspacing=1.2)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'e1_anatomy.png'), bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    d = load()
    print(pd.crosstab([d.pr_template, d.localized], d.label, margins=True).to_string())
    print('median lines added by label:', d.groupby('label').lines_added.median().to_dict())
    plot(d)
