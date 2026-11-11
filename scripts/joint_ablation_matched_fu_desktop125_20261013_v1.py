"""Public, strictly anchored 3x2 planning. No private-noise sampling or RPCs."""
import copy
import csv
import datetime
import hashlib
import json
import os
import pathlib
import platform
import resource
import sys
import time
import tracemalloc
from fractions import Fraction as F

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.physical_prepare_r6 import lzero
from src.finite_reports import public_bound, public_preflight
from src.joint_ablation import (compatible_partition_count, configured_loss,
                                fixed_graph_candidates, fixed_partition_candidates,
                                original_edges, partition_intervals, total_coordinate_costs)
from src.physical import assemble, candidate_family, resource_partition
from src.release_gate import rigorous_finite_certificate, validate_peer_config

OUT = ROOT / 'evidence/matched_fu_desktop125_20261013_v1/planning'


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def save(path, value):
    with pathlib.Path(path).open('x') as f:
        json.dump(value, f, indent=2, default=lambda v: str(v) if isinstance(v, F) else v.tolist() if isinstance(v, np.ndarray) else v)
        f.write('\n')


def headroom():
    cg = pathlib.Path('/sys/fs/cgroup/system.slice/server-history-codex.service')
    limit, current = int((cg / 'memory.max').read_text()), int((cg / 'memory.current').read_text())
    # Respect the owner 12 GiB budget even when the current service allows 16.
    usable = min(limit, 12 * 1024 ** 3)
    if usable - current < 2 * 1024 ** 3:
        raise MemoryError('less than 2 GiB current headroom within contractual shared 12 GiB budget')
    return dict(service_memory_max=limit, effective_contractual_limit=usable, memory_current=current,
                retained_minimum_headroom=2 * 1024 ** 3, load=os.getloadavg())


def candidate_record(c):
    noise, pp = c.payload['noise'], c.payload['plan']
    return dict(key=c.key, interval=[c.start, c.end], members=c.payload['members'],
                a_exact=str(F(noise.a)), w_exact=str(F(noise.w)), branch=noise.branch,
                total_ideal_error_exact=str(c.error), leader_host=pp['leader_host'],
                leaders=[g['leader'] for g in pp['groups']], groups=pp['groups'],
                calls=pp['calls'], endpoint_host_loads=list(pp['loads']), certificate=c.payload['certificate'])


def main():
    assert pathlib.Path.cwd() == ROOT
    owner = json.loads((ROOT / 'governance/.executor.lock/owner.json').read_text())
    assert owner['task_id'] == 'ba0db8dc7303464cba55c8bed5977dbc'
    assert sha(ROOT / 'main.pdf') == 'f6f5692d58d934da310668e58ac94bc056399d068c7501dacb5d5a5b2bc4c392'
    OUT.mkdir(parents=True,exist_ok=False)
    audit = json.loads((ROOT / 'evidence/joint_ablation_20261013_v1/original_input_audit.json').read_text())
    historical = {r['tag']: r for r in audit['records']}
    rows = []
    for dataset, ratio in [('electricity_full', F(17, 20)), ('intel', F(9, 10))]:
        capacity = headroom()
        cp = ROOT / f'experiments/protocol_config_{dataset}_b5_r6.json'
        base = json.loads(cp.read_text())
        peers = [dict(base['peer_common'], **p) for p in base['peers']]
        W, n, d = np.array(base['peer_common']['W']), len(peers), base.get('report_dimension', 1)
        assert W.shape == ((55, 370) if dataset == 'electricity_full' else (100, 54))
        public = base['physical_plan_public']
        hosts = public['host_map']
        assert hosts == ['fu'] * 4 + ['fy1'] * (n - 4)
        rho, delta = base['accountant']['rho_per_release'], peers[0].get('delta_l2', 1.)
        l0, sizes = lzero(W, hosts, d)
        assert list(l0) == public['l0'] and sizes == base['physical_control_response_bytes']
        Pi0 = [b['members'] for b in base['noise_blocks']]
        partition_intervals(Pi0, n)
        G0 = original_edges(peers)
        b5_reference = max(public['b5_total_loads'])
        caps = (ratio * b5_reference,) * 2
        anchor = dict(dataset=dataset, original_B5_config_path=str(cp.relative_to(ROOT)),
                      original_B5_config_sha256=sha(cp), G0=[[u, v] for u, v in sorted(G0)],
                      original_edge_variances_exact=[[u, v, str(F(w))] for (u, v), w in sorted(G0.items())],
                      original_node_variances_exact=[str(F(p['a'])) for p in peers], Pi0=Pi0,
                      original_routing_groups=base['peer_common']['groups'], W=W.tolist(),
                      original_fixture_sha256=digest([p['s'] for p in peers]),
                      fixture_source=base.get('full_roster_reuse', base.get('input_label')),
                      host_map=hosts, host_identity_evidence=base['host_identity_evidence'],
                      report_dimension=d, fixed_error_mean_denominator=len(W) * d,
                      accountant=base['accountant'], finite_parameters=base['peer_common']['finite_parameters'],
                      l0=l0, source_frames=public['frame_bytes'], control_response_bytes=sizes,
                      original_B5_cap_reference_bytes=b5_reference, cap_ratio_exact=ratio, caps=caps,
                      G0_edge_identity_sha256=digest([[u, v] for u, v in sorted(G0)]),
                      Pi0_sha256=digest(Pi0), public_W_sha256=digest(W.tolist()),
                      original_B5_ideal_total_error_exact=configured_loss(W, [p['a'] for p in peers], list(G0), list(G0.values()), d))
        save(OUT / f'{dataset}_anchor.json', anchor)
        tracemalloc.start()
        start, cpu_start = time.perf_counter(), time.process_time()
        family = candidate_family(W, hosts, f=1, rho=rho, delta=delta, gamma_min=.05,
                                  max_interval=8, allowed_host_links=[('fu', 'fy1')])
        families = dict(FIXED_GRAPH=fixed_graph_candidates(W, hosts, peers, rho, delta),
                        FIXED_PARTITION=fixed_partition_candidates(family, Pi0, n), JOINT=family)
        build_wall, build_cpu = time.perf_counter() - start, time.process_time() - cpu_start
        save(OUT / f'{dataset}_candidate_family.json',
             dict(public_only=True, build_wall_seconds=build_wall, build_cpu_seconds=build_cpu,
                  full_candidate_count=len(family), candidates=[candidate_record(c) for c in total_coordinate_costs(family, d)],
                  fixed_graph_candidates=[candidate_record(c) for c in total_coordinate_costs(families['FIXED_GRAPH'], d)]))
        for arm, candidates in families.items():
            candidates = total_coordinate_costs(candidates, d)
            partitions = compatible_partition_count(n, candidates)
            cpu_start = time.process_time()
            out = resource_partition(n, candidates, caps=caps, l0=l0, grid=(4096, 4096))
            plan_cpu = time.process_time() - cpu_start
            selected = [candidate_record(c) for c in out['selected']]
            row = dict(dataset=dataset, arm=arm, cap_ratio_exact=str(ratio),
                       original_B5_cap_reference_bytes=b5_reference, caps_exact=[str(c) for c in caps],
                       feasible=out['feasible'], compatible_partition_count=str(partitions),
                       degeneracy='DEGENERATE' if arm == 'FIXED_GRAPH' and partitions == 1 else 'NONDEGENERATE',
                       candidate_count=len(candidates), candidate_build_wall_seconds=build_wall,
                       candidate_build_cpu_seconds=build_cpu, candidate_build_scope='shared full family plus both restrictions',
                       planning_wall_seconds=out['planning_seconds'], planning_cpu_seconds=plan_cpu,
                       planning_repetitions=1, planning_CI=None,
                       peak_tracemalloc_bytes=tracemalloc.get_traced_memory()[1], peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                       planning_allocation_scope='cumulative dataset build and preceding arms; process RSS also includes previous dataset',
                       extensions=out['extensions'], max_labels=out['max_labels'], labels_per_prefix=out['labels_per_prefix'],
                       configured_total_ideal_error_exact=str(out['error']) if out['error'] is not None else None,
                       configured_total_ideal_error=float(out['error']) if out['error'] is not None else None,
                       error_scope='SUM across every frozen query-coordinate pair; ideal Gaussian only',
                       query_count=len(W), coordinate_count=d, fixed_mean_denominator=len(W) * d,
                       original_B5_reference_ideal_total_error=float(anchor['original_B5_ideal_total_error_exact']),
                       l0=list(l0), grid_bytes_per_host=4096,
                       modeled_total_host_app_bytes=[int(a + b) for a, b in zip(out['loads'], l0)] if out['feasible'] else None,
                       conservative_grid_total_host_app_bytes=[int(a + b) for a, b in zip(out['rounded_loads'], l0)] if out['feasible'] else None,
                       selected=selected, capacity_before_planning=capacity, public_optimizer_only=True,
                       fallback_used=False, physical_status='NOT_STARTED' if out['feasible'] else 'BLOCKED', physical_epochs=0,
                       physical_blocker=None if out['feasible'] else 'Frozen fixed graph is cap-infeasible; no physical execution admitted',
                       provisioning=None, setup=None, release=None, query=None, whole_process=None,
                       peer_TLS=None, outer_SSH=None, epoch_error_CI=None, p99=None,
                       anchor_path=str((OUT / f'{dataset}_anchor.json').relative_to(ROOT)),
                       anchor_sha256=sha(OUT / f'{dataset}_anchor.json'))
            if out['feasible']:
                design = assemble(out['selected'], n)
                assert configured_loss(W, design['a'], design['edges'], design['w'], d) == out['error']
                if arm == 'FIXED_GRAPH':
                    assert set(design['edges']) == set(G0)
                    assert list(design['a']) == [p['a'] for p in peers]
                    assert dict(zip(design['edges'], design['w'])) == G0
                if arm == 'FIXED_PARTITION':
                    assert [b['members'] for b in design['blocks']] == Pi0
                groups = design['groups']
                calls = [call for c in out['selected'] for call in c.payload['plan']['calls']]
                node = [0] * n
                from src.physical import FRAME_BYTES
                for u, v, op in calls:
                    node[u] += sum(FRAME_BYTES[op]); node[v] += sum(FRAME_BYTES[op])
                row['max_logical_node_app_bytes'] = max(node[i] + 5888 + sizes[i] for i in range(n))
                row['max_physical_host_app_bytes'] = max(row['modeled_total_host_app_bytes'])
                row['mechanism'] = dict(a=design['a'].tolist(), edges=design['edges'], weights=design['w'].tolist(),
                                        noise_partition=[b['members'] for b in design['blocks']], routing_groups=groups,
                                        complete_calls=calls)
                current = copy.deepcopy(peers)
                for i, p in enumerate(current):
                    p['a'] = float(design['a'][i]); p['neighbors'] = {
                        str(v if u == i else u): float(w) for (u, v), w in zip(design['edges'], design['w']) if i in (u, v)}
                    p['groups'] = groups
                proof_start = time.perf_counter()
                row['public_certificate'] = validate_peer_config(current, design['blocks'])
                row['rigorous_ideal_certificate'] = rigorous_finite_certificate(current)
                bound = public_bound(current, base['peer_common']['finite_parameters'], 1., 22, 1e-6)
                preflight = public_preflight(current)
                assert bound['passed'] and preflight['passed']
                row['finite_public_bound'] = {k: v for k, v in bound.items() if k != 'rows'}
                row['serialization_capacity_passed'] = preflight['passed']
                row['public_verification_wall_seconds'] = time.perf_counter() - proof_start
                row['full_selected_configuration_sha256'] = digest(dict(row['mechanism'], W=W.tolist(), d=d,
                    host_map=hosts, fixture_sha256=anchor['original_fixture_sha256'],
                    finite_parameters=base['peer_common']['finite_parameters'], accountant=base['accountant'],
                    original_host_identities=base['host_identity_evidence'], source_frames=public['frame_bytes'], l0=l0))
                reuse = []
                for method in ['b5', 'b6', 'cap']:
                    old = json.loads((ROOT / f'experiments/protocol_config_{dataset}_{method}_r6.json').read_text())
                    op = [dict(old['peer_common'], **p) for p in old['peers']]
                    checks = dict(complete_variances_and_edges=[(p['a'], p['neighbors']) for p in op] == [(p['a'], p['neighbors']) for p in current],
                                  complete_routing_groups=old['peer_common']['groups'] == groups,
                                  complete_W=old['peer_common']['W'] == W.tolist(),
                                  report_coordinates=old.get('report_dimension', 1) == d,
                                  original_fixture=[p['s'] for p in op] == [p['s'] for p in current],
                                  host_map=old['physical_plan_public']['host_map'] == hosts,
                                  sampler=old['peer_common']['finite_parameters'] == base['peer_common']['finite_parameters'],
                                  accountant=old['accountant'] == base['accountant'])
                    reuse.append(dict(tag=f'{dataset}_{method}_r6', identities=checks,
                                      original_manifest_sha256=historical[f'{dataset}_{method}_r6']['original_manifest_sha256'],
                                      recorded_execution_code_sha256=historical[f'{dataset}_{method}_r6']['recorded_execution_code_sha256'],
                                      actual_current_same_host_admission=False, reuse_as_strict_arm=False))
                row['historical_identity_comparisons'] = reuse
            else:
                row['max_logical_node_app_bytes'] = None
                row['max_physical_host_app_bytes'] = None
                row['mechanism'] = None
                row['finite_public_bound'] = None
                row['infeasibility_scope'] = 'declared conservative grid restricted family; no overloaded returned plan'
            save(OUT / f'{dataset}_{arm}.json', row)
            rows.append(row)
            print(json.dumps({k: row[k] for k in ['dataset', 'arm', 'feasible', 'degeneracy', 'compatible_partition_count',
                                                    'configured_total_ideal_error', 'modeled_total_host_app_bytes',
                                                    'planning_wall_seconds']}), flush=True)
        tracemalloc.stop()
    result = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv,
                  script_sha256=sha(__file__), restriction_source_sha256=sha(ROOT / 'src/joint_ablation.py'),
                  original_optimizer_sha256=sha(ROOT / 'src/physical.py'),
                  environment=dict(python=platform.python_version(), numpy=np.__version__, executable=sys.executable,
                                   BLAS_threads=os.environ.get('OPENBLAS_NUM_THREADS'), OMP_threads=os.environ.get('OMP_NUM_THREADS')),
                  hardware='evidence/resources_matched_fu_desktop125_20261013_v1_local.json',
                  public_scenario_seed=20261006, random_sampling=False, repetitions=1,
                  scientific_acceptance=False, delivery_scope='PUBLIC PLANNING ONLY', physical_grid_complete=False,
                  physical_cases_admitted=0, physical_case_limit=4, physical_missing_rows=4,
                  accountant_limit=22, required_epochs_per_admitted_case=dict(ordinary=10, exposed_abort=1, fresh_retry=1),
                  rows=rows)
    save(OUT / 'planning_matrix.json', result)
    with (OUT / 'planning_matrix.csv').open('x', newline='') as f:
        fields = ['dataset', 'arm', 'cap_ratio_exact', 'feasible', 'degeneracy', 'compatible_partition_count',
                  'candidate_count', 'configured_total_ideal_error', 'configured_total_ideal_error_exact',
                  'query_count', 'coordinate_count', 'fixed_mean_denominator',
                  'max_logical_node_app_bytes', 'max_physical_host_app_bytes', 'planning_wall_seconds',
                  'planning_cpu_seconds', 'physical_status', 'physical_epochs', 'physical_blocker']
        w = csv.DictWriter(f, fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    print(json.dumps(dict(rows=6, delivery='PUBLIC PLANNING ONLY', admitted_physical_cases=0)), flush=True)


if __name__ == '__main__':
    main()
