"""E2 — task soundness of the public tasks, run in offline Docker containers (network none, 2 CPUs, 4 GB).

Per task, mirroring the harness' verify_task: extract the snapshot to /workspace, `pip install -e . --no-deps`, apply the
task's test_patch, write the harness' hermetic pytest.ini/conftest.py, then run the harness' exact pytest command (with
--junitxml) on the test files the test_patch touches. Do this on the base commit (BASE_RUNS times) and after applying the
gold patch (GOLD_RUNS times). Each run is judged two ways, both with the harness' own functions (run under ~/g4/.venv):
  official   exit code 0 and _validate_junit_xml passes (what the scorer counts as resolved)
  required   every test function the test_patch adds/modifies (_extract_test_functions_from_patch) passes in the junit
Labels:
  sound         base never passes, gold passes officially every run
  flaky_gold    gold passes (officially, or on the required tests) in some runs only
  env_blocked   required tests fail on base and pass on gold every run, but other tests in the same files fail on both
                sides (typically network tests under --network none), so the scorer would still mark the gold unresolved
  gold_fails    the required tests never pass with the gold patch
  base_passes   the tests already pass without the fix (the task cannot discriminate)
The environment is one image per repo (Dockerfile in img_<repo>/) built from the competition's public sandbox Dockerfile plus
the repo's declared test dependencies. The organisers' private wheel cache is not public, so this approximates the official
scorer. Usage: ~/g4/.venv/bin/python soundness.py [instance_id ...]   -> appends JSON lines to out/soundness.jsonl"""
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from swegemma.harness.container_setup import setup_workspace_test_config
from swegemma.harness.verification import _extract_test_functions_from_patch, _node_matches_requirement, _validate_junit_xml

TASKS = os.path.expanduser('~/g4/data/tasks.jsonl')
SNAP = os.path.expanduser('~/g4/data/snapshots')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'soundness.jsonl')
IMAGE = {'psf/requests': 'swebench-sandbox:requests', 'fastapi/fastapi': 'swebench-sandbox:fastapi',
         'Textualize/rich': 'swebench-sandbox:rich', 'encode/httpx': 'swebench-sandbox:httpx'}
BASE_RUNS, GOLD_RUNS, WORKERS, TIMEOUT = 2, 3, int(os.environ.get('WORKERS', 1)), 300
JUNIT = '/tmp/_soundness_junit.xml'
STARLETTE_BOUNDS = ('0.48', '0.49', '0.50', '0.51', '1.0')   # images swebench-sandbox:fastapi-starlette-lt<bound>


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def test_files(test_patch):
    files = re.findall(r'^\+\+\+ (?:b/)?(\S+)', test_patch, re.M)
    return [f for f in files if f.endswith('.py') and ('test' in os.path.basename(f) or '/tests/' in '/' + f)
            and os.path.basename(f) != 'conftest.py']


def image_for(t, snap):
    """The repo image; for fastapi, the one whose starlette satisfies the snapshot's own upper bound (newer starlette removed
    Router(on_startup=...), which breaks older snapshots' test collection)."""
    image = IMAGE[t['repo']]
    if t['repo'] == 'fastapi/fastapi':
        try:
            with tarfile.open(snap) as tf:
                pyproject = tf.extractfile('./pyproject.toml').read().decode()
        except (KeyError, tarfile.TarError, AttributeError, EOFError):
            return image
        m = re.search(r'"starlette\s*>=[^"]*<\s*([0-9.]+?)(?:\.0)?"', pyproject)
        if m and m.group(1) in STARLETTE_BOUNDS:
            image = f'swebench-sandbox:fastapi-starlette-lt{m.group(1)}'
    return image


def outcomes(xml):
    """{classname::name: 'pass' | 'fail' | 'skip'} from a junit report ({} if missing or malformed)."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    res = {}
    for tc in root.iter('testcase'):
        key = f"{tc.attrib.get('classname', '')}::{tc.attrib.get('name', '')}"
        res[key] = ('fail' if tc.find('failure') is not None or tc.find('error') is not None else
                    'skip' if tc.find('skipped') is not None else 'pass')
    return res


def required_pass(outs, required):
    """The harness' per-node rule: some matching testcase passes and none fails or is skipped."""
    for req in required:
        short = req.split('::')[-1]
        base = short.split('[', 1)[0]
        hits = [o for k, o in outs.items() if _node_matches_requirement(k.rsplit('::', 1)[-1], req, short, base)]
        if 'pass' not in hits or 'fail' in hits or 'skip' in hits:
            return False
    return True


def judge(rc, out, xml, test_patch, required):
    text = out.lower()
    stdout_invalid = (bool(re.search(r'\b0 passed\b', text)) or 'no tests ran' in text or 'collected 0 items' in text
                      or (text.strip() != '' and 'passed' not in text))
    official = rc == 0 and bool(xml.strip()) and _validate_junit_xml(xml, test_patch=test_patch)[0] and not stdout_invalid
    outs = outcomes(xml)
    return dict(rc=rc, official=official, required=bool(required) and required_pass(outs, required), outs=outs,
                tail=out[-600:])


def run_task(t):
    iid = t['instance_id']
    snap = os.path.join(SNAP, f'{iid}.tgz')
    if not os.path.exists(snap):
        return dict(instance_id=iid, repo=t['repo'], image=IMAGE[t['repo']], label='no_snapshot')
    image = image_for(t, snap)
    rec = dict(instance_id=iid, repo=t['repo'], image=image)
    targets = test_files(t['test_patch'])
    required = _extract_test_functions_from_patch(t['test_patch'])
    cid = sh(['docker', 'run', '-d', '--network', 'none', '--memory', '4g', '--cpus', '2', '-w', '/workspace', image,
              'sleep', 'infinity']).stdout.strip()
    if not cid:
        return dict(rec, label='no_image')
    try:
        def ex(cmd, timeout=TIMEOUT):
            try:
                r = sh(['docker', 'exec', cid, 'bash', '-lc', cmd], timeout=timeout)
                return r.returncode, r.stdout, r.stderr
            except subprocess.TimeoutExpired:
                return 124, '', 'timeout'
        harness = SimpleNamespace(exec=lambda _cid, cmd, **kw: SimpleNamespace(
            **dict(zip(('exit_code', 'stdout', 'stderr'), ex(cmd)))))
        sh(['docker', 'cp', snap, f'{cid}:/tmp/snap.tgz'])
        ex('mkdir -p /workspace && tar -xzf /tmp/snap.tgz -C /workspace && cd /workspace && (git rev-parse HEAD >/dev/null 2>&1 || '
           '(git init -q && git add -A && git commit -qm base))')
        ex('cd /workspace && pip install -q --no-deps --no-build-isolation -e . 2>&1 | tail -3')
        with tempfile.TemporaryDirectory() as d:
            for name in ('test_patch', 'patch'):
                p = os.path.join(d, name + '.diff')
                body = t[name] if t[name].endswith('\n') else t[name] + '\n'   # the dataset's patches lack a final newline
                open(p, 'w').write(body)
                sh(['docker', 'cp', p, f'{cid}:/tmp/{name}.diff'])
        rc_tp, _, err_tp = ex('cd /workspace && git apply --whitespace=nowarn /tmp/test_patch.diff')
        if rc_tp:
            return dict(rec, label='test_patch_does_not_apply', detail=err_tp[-400:])

        def run():
            setup_workspace_test_config(harness, cid, repo=t['repo'], overwrite=True)
            ex(f'rm -f {JUNIT}')
            rc, out, _ = ex('cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest ' + ' '.join(targets) +
                            f' --junitxml={JUNIT} -p no:anyio -o timeout=0 -o python_classes="Test* *Test" -q')
            return judge(rc, out, ex(f'cat {JUNIT} 2>/dev/null || true')[1], t['test_patch'], required)
        base = [run() for _ in range(BASE_RUNS)]
        rc_gp, _, err_gp = ex('cd /workspace && git apply --whitespace=nowarn /tmp/patch.diff')
        if rc_gp:
            return dict(rec, label='gold_patch_does_not_apply', detail=err_gp[-400:])
        gold = [run() for _ in range(GOLD_RUNS)]

        def always(runs, want):
            return sorted(k for k in set().union(*(r['outs'] for r in runs)) if all(r['outs'].get(k) == want for r in runs))
        both_fail = sorted(set(always(base, 'fail')) & set(always(gold, 'fail')))
        broken = sorted(set(always(base, 'pass')) & {k for r in gold for k, o in r['outs'].items() if o == 'fail'})
        if any(r['official'] or r['required'] for r in base):
            label = 'base_passes'
        elif all(r['official'] for r in gold):
            label = 'sound'
        elif all(r['required'] for r in gold):
            label = 'env_blocked'
        elif any(r['official'] or r['required'] for r in gold):
            label = 'flaky_gold'
        else:
            label = 'gold_fails'
        return dict(rec, label=label, targets=targets, required=required,
                    base_rc=[r['rc'] for r in base], gold_rc=[r['rc'] for r in gold],
                    gold_official=[r['official'] for r in gold], gold_required=[r['required'] for r in gold],
                    both_fail=both_fail, gold_broke=broken, n_tests=len(gold[0]['outs']),
                    base_tail=base[0]['tail'], gold_tail=gold[0]['tail'])
    finally:
        sh(['docker', 'rm', '-f', cid])


if __name__ == '__main__':
    tasks = [json.loads(l) for l in open(TASKS)]
    want = set(sys.argv[1:])
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['instance_id'] for l in open(OUT) if json.loads(l).get('label') not in ('no_snapshot', 'no_image')}
    todo = [t for t in tasks if (not want or t['instance_id'] in want) and (want or t['instance_id'] not in done)]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with ThreadPoolExecutor(WORKERS) as pool:
        for r in pool.map(run_task, todo):
            r['finished'] = time.strftime('%H:%M:%S')
            with open(OUT, 'a') as f:
                f.write(json.dumps(r) + '\n')
            print(r['instance_id'], r['label'], r.get('base_rc'), r.get('gold_rc'), r.get('both_fail', [])[:3], flush=True)
