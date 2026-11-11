#!/usr/bin/env python3
"""Local entry points for the supplied implementation and archived paper results."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def command(*args):
    env = os.environ.copy()
    env.setdefault('OPENBLAS_NUM_THREADS', '2')
    env.setdefault('OMP_NUM_THREADS', '2')
    env.setdefault('MPLBACKEND', 'Agg')
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, env=env, check=True)


def check():
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    errors = []
    for rel, item in manifest['files'].items():
        path = ROOT / rel
        if not path.is_file():
            errors.append(f'Missing: {rel}')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            errors.append(f'Changed: {rel}')
    if errors:
        raise RuntimeError('\n'.join(errors))
    print(f"Verified {len(manifest['files'])} packaged files.", flush=True)


def extract():
    out = ROOT / 'generated' / 'extracted'
    command('scripts/extract_plotted_values.py',
            '--summary', 'results/analysis_v3/summary.json',
            '--physical', 'results/physical_analysis/physical_summary.json',
            '--out', out)
    pairs = [(p, out / p.relative_to(ROOT / 'plotting/data'))
             for p in sorted((ROOT / 'plotting/data').glob('fig*/panel_*.csv'))]
    pairs += [(ROOT / 'tables' / rel, out / rel) for rel in [
        'table1_design/values.csv', 'table2_data/values.csv',
        'table2_data/supporting_fields.csv']]
    for expected, actual in pairs:
        if not actual.is_file() or actual.read_bytes() != expected.read_bytes():
            raise RuntimeError(f'Re-extraction differs: {expected.relative_to(ROOT)}')
    print(f'Re-extracted and matched {len(pairs)} CSV files byte for byte.', flush=True)


def figures():
    out = ROOT / 'generated' / 'figures'
    command('plotting/render_figures.py', '--out', out)
    command('plotting/render_supplement.py', '--out', out)
    main = json.loads((out / 'plot_validation.json').read_text())
    supplement = json.loads((out / 'supplement_plot_validation.json').read_text())
    assert len(main['panels']) == 17
    assert sum(x['rows'] for x in main['panels'].values()) == 489
    for report in [main, supplement]:
        assert not report['artist_boundary_warnings']
        assert all(x['all_data_and_intervals_visible'] for x in report['data_range_checks'])
    print('Rendered Figures 2–7 and S1 as PDF, SVG, and PNG in generated/figures/.', flush=True)


def tests():
    out = ROOT / 'generated'
    out.mkdir(exist_ok=True)
    command('-m', 'pytest', '-q', f'--junitxml={out / "tests.xml"}', 'tests')


def demo():
    import numpy as np
    from src.workloads import workload, grouped_design, query_covariance
    from src.noise import certify, covariance, loss
    W, names, _ = workload(8, 4)
    design = grouped_design(W)
    certificate = certify(design['a'], design['edges'], design['w'], 1., .5)
    dense, _ = covariance(design['a'], design['edges'], design['w'])
    assert certificate['passed']
    assert np.allclose(query_covariance(W, design), W @ dense @ W.T)
    value = float(loss(W, design['a'], design['edges'], design['w']))
    result = dict(owners=8, queries=names, edges=len(design['edges']),
                  loss=value, privacy_passed=bool(certificate['passed']),
                  worst_rho_upper=float(certificate['worst_rho_upper']),
                  note='Small synthetic implementation check; not a rerun of paper measurements.')
    out = ROOT / 'generated'; out.mkdir(exist_ok=True)
    (out / 'demo.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for action in ['check', 'extract', 'figures', 'tests', 'demo']:
        parser.add_argument('--' + action, action='store_true')
    args = parser.parse_args()
    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(0)
    for name, function in [('check', check), ('extract', extract), ('figures', figures),
                           ('tests', tests), ('demo', demo)]:
        if getattr(args, name):
            function()
