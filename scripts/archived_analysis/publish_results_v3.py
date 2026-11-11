#!/usr/bin/env python3
"""FY-only exact publication overlay and plotting; no new optimization or trials."""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

BASE_SUMMARY_SHA = '189fe0b955942b1ec2fec04d60f83764cef83904ee1d1c7eb37cb925a4c3021d'
OVERLAY_SHA = 'dcf757918a86e82f5af50f9076c179fe99228cb07ea64730a88ca2a8b4ede50b'
ACCEPTANCE_SHA = 'faef0795f4b09aa6f192d5be661de2b53cd7e42ed432d42ebf787616829d7afc'
PLOT_SHA = '6cdfebf0a65feaeb4b1ce00a58262522137a0368bb32218c72c09755460afccd'
SUMMARIZER_SHA = '3a62acc0ef47293ace98f40ea122a1bf4572cc2e19ebfa5f247215935fe201e2'
CASE_IDS = ('C-n1024-range-s1301-r0', 'C-n1024-mixed-s1301-r0')
FIGURES = ('activation', 'local_gap', 'scale', 'grouping', 'finite_utility')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    args = parser.parse_args()
    root, base = args.root.resolve(), args.base.resolve()
    require(root == base / 'publication20261110', 'Unexpected one-use publication root')
    intent = read(root / 'launch_intent.json')
    base_summary = base / 'analysis20261110/output/analysis/summary.json'
    summarizer = base / 'analysis20261110/scripts/summarize_results.py'
    fixed = ((base_summary, 'base_summary_sha256', BASE_SUMMARY_SHA),
             (summarizer, 'summary_script_sha256', SUMMARIZER_SHA),
             (root / 'plot_results_v3.py', 'plot_sha256', PLOT_SHA),
             (Path(__file__), 'worker_sha256', None),
             (base / 'FROZEN_MANIFEST.json', 'manifest_sha256', None),
             (base / 'SCIENCE_DEADLINE.json', 'deadline_sha256', None),
             (base / 'revision_src/bounded_exec.py', 'wrapper_sha256', None))
    for path, key, expected in fixed:
        require(sha(path) == intent[key], 'Source/input binding differs: ' + key)
        if expected is not None:
            require(intent[key] == expected, 'Unreviewed source/input: ' + key)
    timing = read(base / 'SCIENCE_DEADLINE.json')
    require(timing['science_budget_seconds'] == 43200 and
            timing['deadline_epoch'] - timing['first_validation_dispatch_epoch'] == 43200 and
            intent['deadline_epoch'] == timing['deadline_epoch'] and
            time.time() < timing['deadline_epoch'], 'Original scientific deadline differs or passed')

    allowed_inputs = {'overlay.pending.json', 'uniform_precision_acceptance.json'} | {
        'cases/' + case_id + '/candidate.json' for case_id in CASE_IDS}
    require(set(intent['input_files_sha256']) == allowed_inputs, 'Input allowlist differs')
    require(sha(root / 'inputs.tar') == intent['input_archive_sha256'], 'Input archive hash differs')
    inputs = root / 'inputs'
    inputs.mkdir(exist_ok=False)
    with tarfile.open(root / 'inputs.tar') as package:
        members = package.getmembers()
        require(len(members) == len(allowed_inputs) and {m.name for m in members} == allowed_inputs and
                all(m.isfile() for m in members), 'Unexpected input archive member')
        for member in members:
            path = inputs / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            with package.extractfile(member) as source, path.open('xb') as destination:
                for block in iter(lambda: source.read(1048576), b''):
                    destination.write(block)
            require(sha(path) == intent['input_files_sha256'][member.name], 'Extracted input hash differs')
    require(sha(inputs / 'overlay.pending.json') == OVERLAY_SHA == intent['overlay_sha256'], 'Overlay differs')
    require(sha(inputs / 'uniform_precision_acceptance.json') == ACCEPTANCE_SHA == intent['acceptance_sha256'], 'Acceptance differs')
    overlay = read(inputs / 'overlay.pending.json')
    acceptance = read(inputs / 'uniform_precision_acceptance.json')
    require(overlay['status'] == 'PENDING_INDEPENDENT_VERIFICATION' and acceptance['status'] == 'ACCEPTED' and
            acceptance['overlay_sha256'] == OVERLAY_SHA, 'Acceptance does not bind the pending overlay')
    require(acceptance['manifest_file_sha256'] == intent['manifest_sha256'] and
            acceptance['deadline_sha256'] == intent['deadline_sha256'], 'Acceptance experiment identity differs')
    require({x['case_id'] for x in overlay['cases']} == set(CASE_IDS) and len(overlay['cases']) == 2 and
            {x['case_id'] for x in acceptance['cases']} == set(CASE_IDS) and len(acceptance['cases']) == 2,
            'Exactly the two reviewed cases are required')

    spec = importlib.util.spec_from_file_location('frozen_summary', summarizer)
    summary_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summary_module)
    manifest = read(base / 'FROZEN_MANIFEST.json')
    checks = summary_module.Checks(manifest, base / 'revision_src', replay=False)
    original = read(base_summary)
    updated = copy.deepcopy(original)
    replacements = []
    for case_id in CASE_IDS:
        entry = next(x for x in overlay['cases'] if x['case_id'] == case_id)
        review = next(x for x in acceptance['cases'] if x['case_id'] == case_id)
        case = next(x for x in manifest['cases'] if x['case_id'] == case_id)
        require(review['accepted'] is True and entry['candidate_eligible'] is True and
                entry['source_bindings_unchanged'] is True and entry['ownership_drained'] is True and
                entry['within_original_budget'] is True, 'Candidate was not accepted or completed')
        for key in ('candidate_sha256', 'input_sha256', 'original_case_sha256', 'original_method_sha256'):
            require(entry[key] == review[key], 'Accepted binding differs: ' + key)
        require(case['input_sha256'] == review['input_sha256'] ==
                summary_module.identity({k: v for k, v in case.items() if k != 'input_sha256'}), 'Frozen case identity differs')
        candidate_path = inputs / 'cases' / case_id / 'candidate.json'
        candidate = read(candidate_path)
        require(sha(candidate_path) == entry['candidate_sha256'] and candidate == entry['result'], 'Candidate bytes/result differ')
        require(entry['inclusive_seconds'] == review['inclusive_seconds'] ==
                entry['original_seconds'] + entry['extension_seconds'] and entry['inclusive_seconds'] <= 120,
                'Original plus extension runtime is not conserved')
        receipt = entry['bounded_receipt']
        require(receipt['exit_code'] == 0 and receipt['termination_reason'] is None and
                receipt['owned_group_cleanup']['drained'] is True, 'Candidate execution did not close successfully')
        record = entry['replacement_record']
        require(record['wall_including_start_seconds'] == entry['inclusive_seconds'] and
                all(record[k] == v for k, v in candidate.items()), 'Replacement changes scientific output or runtime')
        row = summary_module.method_row(case, 'U', record, 'terminal',
                  [str(candidate_path), str(inputs / 'uniform_precision_acceptance.json')], checks)
        require(row['usable'] and row['standalone'] and not row['fallback'] and not row['issues'] and
                row.get('lower_bound_checked') and row['bracket_width'] >= 0, 'Exact publication readback failed')
        positions = [i for i, r in enumerate(updated['case_methods']) if r['case_id'] == case_id and r['method'] == 'U']
        require(len(positions) == 1, 'Original U row is ambiguous')
        previous = updated['case_methods'][positions[0]]
        require(previous['fallback'] and previous['independent_returned'] and
                previous['seconds'] == entry['original_seconds'], 'Original precision fallback differs')
        for key in ('workload_id', 'condition_id', 'raw_workload_id', 'n', 'f', 'suite', 'seed', 'repeat', 'family'):
            require(previous[key] == row[key], 'Publication changes problem identity: ' + key)
        row['precision_extension'] = {'actual_bits': review['privacy_precision_bits'],
            'ceiling_bits': review['precision_ceiling'], 'original_seconds': entry['original_seconds'],
            'extension_seconds': entry['extension_seconds'], 'acceptance_sha256': ACCEPTANCE_SHA}
        updated['case_methods'][positions[0]] = row
        methods = {r['method']: r for r in updated['case_methods'] if r['case_id'] == case_id and r['method'] in ('I', 'U', 'H')}
        require(set(methods) == {'I', 'U', 'H'} and all(r['usable'] and r['standalone'] and math.isfinite(r['seconds']) for r in methods.values()),
                'Updated portfolio lacks a complete matched family')
        choice = min(methods.values(), key=lambda r: (summary_module.q(r['error_exact']), ('I', 'U', 'H').index(r['method'])))
        port = next(r for r in updated['portfolios'] if r['case_id'] == case_id)
        old_port = copy.deepcopy(port)
        port.update(family_complete=True, selected_method=choice['method'], error=choice['error'], error_exact=choice['error_exact'],
                    error_normalized=choice['error_normalized'], selected_fallback=False,
                    seconds=sum(methods[m]['seconds'] for m in ('I', 'U', 'H')), timing_complete=True)
        replacements.append({'case_id': case_id, 'original_row': previous, 'accepted_row': row,
                             'original_portfolio': old_port, 'accepted_portfolio': copy.deepcopy(port)})

    bucket = [r for r in updated['case_methods'] if r['suite'] == 'C' and r['method'] == 'U']
    coverage = updated['coverage']['C']['by_method']['U']
    require(len(bucket) == 124 and all(r['usable'] and r['standalone'] for r in bucket), 'Updated U coverage differs')
    coverage.update(standalone=sum(r['standalone'] for r in bucket), fallback=sum(r['fallback'] for r in bucket),
                    finite_brackets=sum(r.get('bracket_width') is not None for r in bucket))
    permitted = {'case_methods', 'portfolios', 'coverage'}
    require(all(updated[k] == v for k, v in original.items() if k not in permitted), 'Unrelated summary data changed')
    for key in original['coverage']:
        if key != 'C':
            require(updated['coverage'][key] == original['coverage'][key], 'Unrelated coverage changed')
    updated['base_summary_script_sha256'] = updated['script_sha256']
    updated['script_sha256'] = sha(__file__)
    updated['publication_overlay'] = {'schema': 'icde02-accepted-publication-overlay-v1',
        'base_summary_sha256': BASE_SUMMARY_SHA, 'overlay_sha256': OVERLAY_SHA, 'acceptance_sha256': ACCEPTANCE_SHA,
        'review_scope': acceptance['review_scope'], 'only_replaced_case_ids': list(CASE_IDS),
        'timing_includes_original_precision_failures': True, 'independent_covariance_replay': False,
        'original_rows_and_portfolios': [{k: x[k] for k in ('case_id', 'original_row', 'original_portfolio')} for x in replacements]}
    output = root / 'output'
    output.mkdir(exist_ok=False)
    write(output / 'analysis/summary.json', updated)
    subprocess.run([sys.executable, str(root / 'plot_results_v3.py'), '--summary', str(output / 'analysis/summary.json'),
                    '--out', str(output / 'figures')], check=True)
    figure_manifest = read(output / 'figures/figure_manifest.json')
    require(figure_manifest['summary_sha256'] == sha(output / 'analysis/summary.json') and
            figure_manifest['script_sha256'] == PLOT_SHA, 'Plot bindings differ')
    require({r['figure'] for r in figure_manifest['figures']} == set(FIGURES) and len(figure_manifest['figures']) == 5,
            'Publication figure set differs')
    for figure in figure_manifest['figures']:
        for item in figure['files']:
            path = Path(item['path'])
            require(path.parent == output / 'figures' and sha(path) == item['sha256'], 'Rendered file binding differs')
    require(time.time() < timing['deadline_epoch'], 'Original deadline passed during publication generation')
    write(output / 'publication_receipt.json', {'state': 'COMPLETED', 'base_summary_sha256': BASE_SUMMARY_SHA,
        'summary_sha256': sha(output / 'analysis/summary.json'), 'overlay_sha256': OVERLAY_SHA,
        'acceptance_sha256': ACCEPTANCE_SHA, 'worker_sha256': sha(__file__), 'plot_sha256': PLOT_SHA,
        'summary_script_sha256': SUMMARIZER_SHA, 'deadline_epoch': timing['deadline_epoch'],
        'finished_epoch': time.time(), 'new_optimizer_or_trial_runs': 0,
        'cases': [{'case_id': r['case_id'], 'error_normalized': r['accepted_row']['error_normalized'],
                   'inclusive_seconds': r['accepted_row']['seconds'], 'portfolio_method': r['accepted_portfolio']['selected_method'],
                   'portfolio_all_branch_seconds': r['accepted_portfolio']['seconds']} for r in replacements]})
    allowed_outputs = {'analysis/summary.json', 'publication_receipt.json', 'figures/figure_manifest.json'} | {
        'figures/' + name + '.' + suffix for name in FIGURES for suffix in ('pdf', 'png')}
    require({str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()} == allowed_outputs and
            not any(p.is_symlink() for p in output.rglob('*')), 'Unexpected output file')
    with tarfile.open(root / 'output.tar', 'x') as package:
        for name in sorted(allowed_outputs):
            package.add(output / name, arcname=name, recursive=False)
    print(json.dumps({'state': 'COMPLETED', 'summary_sha256': sha(output / 'analysis/summary.json'),
                      'archive_sha256': sha(root / 'output.tar'), 'cases': len(replacements)}), flush=True)


if __name__ == '__main__':
    main()
