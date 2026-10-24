"""E1 — anatomy of the 129 public Gemma 4 Developer Agent tasks (tasks.jsonl only, no execution).

Per task: statement style (GitHub PR template vs issue text), patch shape (files, hunks, +/- lines, new files, non-.py files),
test shape, and lexical localisation: does the statement name an edited file (basename) or a symbol the gold patch defines or
touches? Writes paper/out/task_anatomy.csv and prints summary tables. Usage: python task_anatomy.py [tasks.jsonl]"""
import json
import os
import re
import sys

import pandas as pd

TASKS = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/g4/data/tasks.jsonl')
OUT = os.path.join(os.path.dirname(__file__), 'out')


def parse_patch(patch: str):
    files, new_files, hunks, plus, minus, symbols = [], [], 0, 0, 0, set()
    current = None
    for line in patch.splitlines():
        if line.startswith('--- '):
            src = line[4:].strip()
        elif line.startswith('+++ '):
            current = re.sub(r'^b/', '', line[4:].strip())
            files.append(current)
            if src in ('/dev/null', 'a/dev/null') or src.endswith('/dev/null'):
                new_files.append(current)
        elif line.startswith('@@'):
            hunks += 1
            if line.startswith('@@ -0,0 ') and current and current not in new_files:   # these patches mark new files this way
                new_files.append(current)
            m = re.search(r'@@.*@@\s*(?:async\s+)?(?:def|class)\s+(\w+)', line)   # enclosing function/class in hunk header
            if m:
                symbols.add(m.group(1))
        elif line.startswith('+') and not line.startswith('+++'):
            plus += 1
            m = re.match(r'\+\s*(?:async\s+)?(?:def|class)\s+(\w+)', line)
            if m:
                symbols.add(m.group(1))
        elif line.startswith('-') and not line.startswith('---'):
            minus += 1
            m = re.match(r'-\s*(?:async\s+)?(?:def|class)\s+(\w+)', line)
            if m:
                symbols.add(m.group(1))
    return dict(files=files, new_files=new_files, hunks=hunks, plus=plus, minus=minus, symbols=sorted(symbols))


def main():
    rows = []
    for line in open(TASKS):
        t = json.loads(line)
        p, tp = parse_patch(t['patch']), parse_patch(t['test_patch'])
        st = t['problem_statement']
        low = st.lower()
        named_file = any(os.path.basename(f).lower() in low or f.lower() in low for f in p['files'])
        named_symbol = any(re.search(r'\b' + re.escape(s) + r'\b', st) for s in p['symbols'] if len(s) > 3)
        is_pr = bool(re.search(r'^#+\s*pull request|<!--|^## (description|summary|changes)', low, re.M))
        rows.append(dict(
            instance_id=t['instance_id'], repo=t['repo'], created_at=t['created_at'],
            statement_words=len(st.split()), pr_template=is_pr,
            src_files=len(p['files']), new_src_files=len(p['new_files']), hunks=p['hunks'],
            lines_added=p['plus'], lines_removed=p['minus'],
            non_py_files=sum(not f.endswith('.py') for f in p['files']),
            test_files=len(tp['files']), new_test_files=len(tp['new_files']), test_lines_added=tp['plus'],
            names_edited_file=named_file, names_edited_symbol=named_symbol,
            localized=named_file or named_symbol,
            single_file_small=len(p['files']) == 1 and p['plus'] + p['minus'] <= 20,
        ))
    df = pd.DataFrame(rows)
    df['size_class'] = pd.cut(df.lines_added + df.lines_removed, [-1, 5, 20, 100, 10**6], labels=['≤5', '6–20', '21–100', '>100'])
    df['kind'] = (df.new_src_files > 0).map({True: 'adds new file', False: 'edits existing'})
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(os.path.join(OUT, 'task_anatomy.csv'), index=False)
    print(f'{len(df)} tasks')
    print(df.groupby('repo').agg(n=('instance_id', 'size'), pr_template=('pr_template', 'mean'), localized=('localized', 'mean'),
                                 median_changed_lines=('lines_added', 'median'), multi_file=('src_files', lambda s: (s > 1).mean()),
                                 adds_file=('new_src_files', lambda s: (s > 0).mean())).round(2).to_string())
    print('\nsize classes (changed lines):', df.size_class.value_counts().sort_index().to_dict())
    print('kind:', df.kind.value_counts().to_dict(), '| non-.py source edits:', int((df.non_py_files > 0).sum()))
    print('PR-template statements:', int(df.pr_template.sum()), '| statement names edited file or symbol:', int(df.localized.sum()))
    print('single-file ≤20-line fixes:', int(df.single_file_small.sum()))
    print(pd.crosstab(df.size_class, df.localized, margins=True).to_string())


if __name__ == '__main__':
    main()
