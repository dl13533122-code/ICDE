"""Read all 24 retained R6 cases and query errors; never rerun a case."""
import csv
import datetime
import hashlib
import json
import math
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.protocol import read_fraction, weighted_reports


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def identity(cfg):
    common = cfg['peer_common']
    peers = [dict(common, **p) for p in cfg['peers']]
    return dict(
        a=[p['a'] for p in peers],
        edges=[[i, int(j), w] for i, p in enumerate(peers) for j, w in p['neighbors'].items() if i < int(j)],
        W=common['W'], groups=common['groups'],
        input_fixture_sha256=digest([p['s'] for p in peers]),
        report_dimension=cfg.get('report_dimension', 1),
        host_map=cfg['physical_plan_public']['host_map'],
        hosts=cfg['physical_plan_public']['hosts'],
        host_identity_evidence=cfg['host_identity_evidence'],
        finite_parameters=common['finite_parameters'], accountant=cfg['accountant'],
        source_frames=cfg['physical_plan_public']['frame_bytes'],
        l0=cfg['physical_plan_public']['l0'],
        control_response_bytes=cfg['physical_control_response_bytes'],
        routing_modes=cfg['routing_modes'],
    )


def main():
    owner = json.loads((ROOT / 'governance/.executor.lock/owner.json').read_text())
    assert owner['task_id'] == '251b38e03bfd4b178568f061cd591b07'
    qpath = ROOT / 'evidence/reports_physical_r6/query_squared_errors.csv'
    query_errors = {}
    counts = defaultdict(int)
    with qpath.open(newline='') as f:
        for r in csv.DictReader(f):
            key = (r['tag'], int(r['trial']), int(r['query']), int(r['coordinate']))
            assert key not in query_errors
            query_errors[key] = float(r['squared_error'])
            counts[r['tag']] += 1
    rows = json.loads((ROOT / 'evidence/reports_physical_r6/summary.json').read_text())
    assert len(rows) == 24
    records = []
    seen = set()
    for r in rows:
        tag = r['tag']
        assert tag not in seen
        seen.add(tag)
        mp, cp = ROOT / r['raw_path'], ROOT / r['config_path']
        assert sha(mp) == r['raw_sha256']
        assert sha(cp) == r['config_sha256']
        cfg = json.loads(cp.read_text())
        with mp.open() as f:
            m = json.load(f, object_hook=read_fraction)
        common = cfg['peer_common']
        peers = [dict(common, **p) for p in cfg['peers']]
        W, d = common['W'], cfg.get('report_dimension', 1)
        assert len(m['trials']) == 10 and len({t['epoch'] for t in m['trials']}) == 10
        assert counts[tag] == 10 * len(W) * d
        assert cfg['accountant']['max_release_epochs'] == 22
        assert cfg['accountant']['eps_total_bound'] == 1
        assert cfg['accountant']['delta'] == 1e-6 and cfg['accountant']['delta_G'] == 5e-7
        assert common['finite_parameters'] == dict(b=256, u=64, K=10, eta_bits=180,
                                                 coefficient_bits=220, grid_bits=20, arb_bits=512)
        assert m['finite_backend']['attempts'] == 22
        costs = []
        for t in m['trials']:
            assert t['arithmetic_max_error'] == 0
            cost = 0.0
            for qi, row in enumerate(W):
                answer = t['answers'][str(qi)]
                assert answer == weighted_reports(row, t['public_reports'], d)
                truth = weighted_reports(row, [p['s'] for p in peers], d)
                differences = [float(answer) - float(truth)] if d == 1 else [float(x) - float(y) for x, y in zip(answer, truth)]
                for coordinate, error in enumerate(differences):
                    key = (tag, t['repetition'], qi, coordinate)
                    assert math.isclose(error ** 2, query_errors[key], rel_tol=1e-13, abs_tol=1e-15)
                    cost += query_errors[key]
            costs.append(cost)
        assert math.isclose(sum(costs) / 10, r['observed_total_error']['mean'], rel_tol=1e-13)
        histories = m['process_to_host']
        assert len(histories) == len(peers)
        assert all(len(p['history']) == 12 for p in histories)
        assert all(len({h['epoch'] for h in p['history']}) == 12 for p in histories)
        assert any(any(h['state'] == 'ABORTED' and h['exposed'] for h in p['history']) for p in histories)
        assert m['fresh_retry_after_abort']['arithmetic_max_error'] == 0
        assert m['fresh_retry_after_abort']['epoch'] not in {t['epoch'] for t in m['trials']}
        code = {p: sha(ROOT / p) == v for p, v in m['code_sha256'].items()}
        ii = identity(cfg)
        ii['recorded_execution_code_sha256'] = m['code_sha256']
        records.append(dict(tag=tag, original_manifest_path=r['raw_path'], original_manifest_sha256=r['raw_sha256'],
                            original_config_path=r['config_path'], original_config_sha256=r['config_sha256'],
                            full_identity=ii, full_identity_sha256=digest(ii),
                            actual_hostnames=sorted({p['hostname'] for p in histories}),
                            ordinary_epochs=10, exposed_aborts=1, fresh_retries=1, prepared_attempts_observed=12,
                            accountant_limit=22, query_rows=len(W), report_coordinates=d,
                            fixed_normalization_denominator=len(W) * d,
                            squared_error_scope='SUM over every frozen query-coordinate pair; epoch mean denominator 10',
                            csv_rows_checked=counts[tag], observed_epoch_sum_errors=costs,
                            recorded_code_vs_current_source_matches=code,
                            recorded_execution_code_sha256=m['code_sha256'],
                            coins='original manifest: fresh OS private coins, not exported',
                            new_physical_arm_measurement=False, workload_shift=tag.endswith('_shift_r6')))
        print(json.dumps(dict(read_and_verified=tag, pairs_per_epoch=len(W) * d, observed_attempts=12, budget=22)), flush=True)
        del m
    expected = {ds + '_' + method + '_r6' for ds in ['electricity', 'intel', 'electricity_full']
                for method in ['b5', 'b6', 'independent', 'signature', 'unaware', 'sdp', 'cap', 'shift']}
    assert seen == expected
    out = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv,
               script_sha256=sha(__file__), original_pdf_sha256=sha(ROOT / 'main.pdf'),
               csv_path=str(qpath.relative_to(ROOT)), csv_sha256=sha(qpath), csv_rows=len(query_errors),
               read_manifest_count=24, ordinary_epochs=240, exposed_aborts=24, fresh_retries=24,
               prepared_attempts=288, budget_per_case=22, new_epochs=0, records=records,
               physical_reuse_policy='No retained case is relabeled as a new strict arm; current same-host admission is required')
    path = ROOT / 'evidence/joint_ablation_20261013_v1/original_input_audit.json'
    path.parent.mkdir(exist_ok=True)
    with path.open('x') as f:
        json.dump(out, f, indent=2)
    print(json.dumps(dict(verified_cases=24, csv_rows=len(query_errors), new_epochs=0)), flush=True)


if __name__ == '__main__':
    main()
