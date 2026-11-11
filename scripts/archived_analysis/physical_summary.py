#!/usr/bin/env python3
"""Summarize current physical202 collections without running a new experiment.

Run on an authorized compute host, after copying the public physical202 tree
and the unchanged FROZEN_MANIFEST.json there. Ordinary repetitions, forced
abort prefixes and fresh retries remain separate. No optimizer or RNG for
private reports is imported. The fixed shuffle below enumerates public labels.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path as P
import random
import statistics

SCHEMA = 'icde02-physical-summary-v1'
METHODS = ('fixed8_U', 'adaptive_PORTFOLIO')
METRICS = ('max_application_kib', 'total_application_kib', 'max_tls_kib', 'total_tls_kib',
           'online_seconds', 'whole_attempt_seconds', 'setup_seconds', 'release_seconds', 'query_seconds',
           'controller_cpu_seconds', 'peer_cpu_seconds', 'normalized_squared_error')
MAIN_METRICS = ('max_application_kib', 'max_tls_kib', 'online_seconds')


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    h = hashlib.sha256()
    with P(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()


def q(value):
    if isinstance(value, dict) and 'rational_fixed' in value:
        numerator, denominator = value['rational_fixed']
        require(len(numerator) == len(denominator) == 128, 'incorrect fixed rational width')
        return F(int.from_bytes(bytes.fromhex(numerator), 'big', signed=True),
                 int.from_bytes(bytes.fromhex(denominator), 'big'))
    if isinstance(value, dict) and value.get('encoding') == 'hex-rational-v1':
        return F(int(value['numerator_hex'], 16), int(value['denominator_hex'], 16))
    if isinstance(value, float):
        require(math.isfinite(value), 'nonfinite rational input')
        return F(str(value))
    if isinstance(value, bool): raise ValueError('boolean is not a rational measurement')
    return F(value)


def number(value):
    result = float(value)
    require(math.isfinite(result), 'nonfinite numerical result')
    return result


def nonnegative(value):
    require(isinstance(value, (int, float)) and not isinstance(value, bool), 'expected a numeric measurement')
    result = number(value); require(result >= 0, 'negative numerical measurement')
    return result


def require(condition, message):
    if not condition: raise ValueError(message)


def schedule():
    cases = []
    for family in ('class', 'range'):
        for placement in ('balanced', 'skewed'):
            for price, suffix in (('0', '0'), ('1/10', '1d10')):
                for method in METHODS:
                    case = 'F_' + family + '_' + placement + '_lambda' + suffix + '_' + method
                    cases.append(dict(case_id=case, family=family, placement=placement, lambda_exact=price,
                                      method=method, sharing=True, planned_attempts=12))
    cases.append(dict(case_id='F_class_balanced_lambda1d10_fixed8_U_no_sharing', family='class',
                      placement='balanced', lambda_exact='1/10', method='fixed8_U', sharing=False, planned_attempts=10))
    random.Random(1601).shuffle(cases)
    prior = 0
    for order, case in enumerate(cases):
        case.update(order=order, prior_prepared_attempts=prior); prior += case['planned_attempts']
    return cases


def descriptive(values, planned):
    values = list(values)
    return dict(n=len(values), planned=planned, mean=statistics.fmean(values) if values else None,
                median=statistics.median(values) if values else None, minimum=min(values) if values else None,
                maximum=max(values) if values else None, values=values,
                interpretation='descriptive repetition variability, not an independent-host confidence interval')


class Inputs:
    def __init__(self): self.files = {}; self.issues = []

    def issue(self, scope, kind, message):
        self.issues.append(dict(scope=scope, kind=kind, message=str(message)))

    def read(self, path, optional=True):
        path = P(path)
        if not path.exists():
            if not optional: self.issue(str(path), 'missing', 'required input file is unavailable')
            return None
        try:
            raw = path.read_bytes(); self.files[str(path)] = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            return json.loads(raw)
        except (OSError, ValueError) as error:
            self.issue(str(path), 'unreadable', error); return None

    def equivalent(self, paths, scope):
        objects = [(path, self.read(path)) for path in paths if P(path).exists()]
        objects = [(path, obj) for path, obj in objects if obj is not None]
        if not objects: return None, []
        hashes = {hashlib.sha256(canonical(obj)).hexdigest() for _, obj in objects}
        if len(hashes) != 1:
            self.issue(scope, 'conflicting_copies', [str(path) for path, _ in objects]); return None, [str(path) for path, _ in objects]
        return objects[0][1], [str(path) for path, _ in objects]


def configuration(cfg, expected, parent, manifest):
    require(cfg['config_sha256'] == hashlib.sha256(canonical({k: v for k, v in cfg.items() if k != 'config_sha256'})).hexdigest(), 'configuration canonical hash mismatch')
    for field in ('case_id', 'family', 'placement', 'method', 'sharing'):
        require(cfg[field] == expected[field], 'configuration differs at ' + field)
    require(q(cfg['lambda_value']) == q(expected['lambda_exact']), 'public price differs')
    require(cfg['case_attempts'] == expected['planned_attempts'] and cfg['repetitions'] == 10, 'attempt/repetition count differs')
    require(cfg['prior_prepared_attempts'] == expected['prior_prepared_attempts'], 'cumulative attempt origin differs')
    require(cfg['abort_retry'] == expected['sharing'], 'forced-abort/retry schedule differs')
    require(parent is not None and cfg['parent_input_sha256'] == parent['input_sha256'], 'frozen grouping parent mismatch')
    parent_hash = hashlib.sha256(canonical({k: v for k, v in parent.items() if k != 'input_sha256'})).hexdigest()
    require(parent_hash == parent['input_sha256'], 'frozen parent input hash is inconsistent')
    peers = cfg['peers']; n = len(peers); host_map = cfg['host_map']; Q = [[q(x) for x in row] for row in parent['Q']]
    p = [q(x) for x in parent['p']]; r = q(cfg['scale']['r'])
    require(n == 128 and cfg['logical_participants'] == n and cfg['physical_peer_hosts'] == 2, 'physical topology differs')
    require(cfg['controller_host_index'] == 0 and len(host_map) == n and set(host_map) == {0, 1}, 'host map/controller domain')
    require(len(p) == len(Q) and sum(p) == 1 and all(x >= 0 for x in p) and all(len(row) == n for row in Q), 'public query distribution differs')
    require(cfg['finite_bound']['passed'] is True and cfg['finite_preflight']['passed'] is True, 'finite bound or capacity check failed')
    require(cfg['finite_bound']['attempts'] == 202, 'finite proof horizon differs')
    require(r > 0, 'nonpositive privacy scale')
    a = []; edges = {}; inputs = []
    for i, peer in enumerate(peers):
        require(peer['id'] == i and peer['n'] == n and peer['W'] == parent['Q'], 'peer workload/identity differs')
        require(peer['max_prepared_attempts'] == 202 and peer['prior_prepared_attempts'] == expected['prior_prepared_attempts'], 'peer cumulative horizon differs')
        require(peer['report_dimension'] == 1, 'physical report dimension differs')
        a.append(q(peer['a'])); inputs.append(q(peer['s'])); require(a[-1] > 0, 'nonpositive anchor variance')
        for text, value in peer['neighbors'].items():
            j = int(text); w = q(value)
            require(0 <= j < n and j != i and w > 0, 'invalid active physical edge')
            require(q(peers[j]['neighbors'][str(i)]) == w, 'asymmetric shared edge')
            if i < j: edges[(i, j)] = w
    s = [sum((weight * row[i]**2 for row, weight in zip(Q, p)), F(0)) for i in range(n)]
    S = sum(s, F(0)); error = sum((s[i] * a[i] for i in range(n)), F(0))
    for (u, v), w in edges.items():
        error += w * sum((weight * (row[u]-row[v])**2 for row, weight in zip(Q, p)), F(0))
    require(S > 0 and error*r == q(cfg['chosen_group_error']), 'configured covariance loss differs from selected grouping plan')
    l0 = [1536*(sum(h == 0 for h in host_map)+n), 1536*sum(h == 1 for h in host_map)]
    require(cfg['fixed_collection_l0'] == l0, 'fixed report-collection load differs')
    logical = cfg['chosen_group_logical_loads']; modeled = cfg['chosen_group_loads']
    require(len(logical) == len(modeled) == 2 and all(isinstance(v, int) and v >= 0 for v in logical+modeled), 'modeled byte vector domain')
    require([logical[h]+l0[h] for h in (0, 1)] == modeled, 'collection l0 is not included exactly once')
    require(cfg['chosen_active_edges'] == len(edges), 'active edge count differs')
    if cfg['method'] == 'fixed8_U': require(cfg['chosen_group_family_complete'] is True, 'fixed U baseline family is incomplete')
    fingerprint = hashlib.sha256(canonical(dict(Q=parent['Q'], p=parent['p'], host_map=host_map,
        peers=[dict(a=x['a'], neighbors=x['neighbors'], s=x['s'], groups=x['groups']) for x in peers]))).hexdigest()
    return dict(Q=Q, p=p, inputs=inputs, reference=S/r, ideal=error, parent=parent,
                public=dict(independent_reference_exact=str(S/r), ideal_error_exact=str(error), ideal_error_normalized=number(error/(S/r)),
                            public_workload_id=parent['input_sha256'], active_edges=len(edges), host_owner_counts=[host_map.count(h) for h in (0,1)],
                            fixed_collection_application_bytes=l0, modeled_application_bytes=modeled,
                            modeled_logical_application_bytes=logical, allocation_and_routes_sha256=fingerprint,
                            candidate_family_complete=cfg.get('chosen_group_family_complete'),
                            finite_bound_passed=True, finite_preflight_passed=True))


def report_identity(report, cfg, manifest):
    require(report['case_id'] == cfg['case_id'] and report['config_sha256'] == cfg['config_sha256'], 'result configuration hash mismatch')
    require(report['controller_host_index'] == 0, 'result controller location differs')
    initial = report['initial_peers']; require(len(initial) == 128, 'initial peer roster is incomplete')
    identities = {0: set(), 1: set()}; hostnames = {0: set(), 1: set()}; pins = set()
    for i, row in enumerate(initial):
        require(row['id'] == i and row['prepared_attempts'] == cfg['prior_prepared_attempts'], 'initial peer/cumulative count mismatch')
        ident = row['runtime_identity']; h = cfg['host_map'][i]
        identities[h].add(ident['machine_id_sha256']); hostnames[h].add(row['hostname']); pins.add(ident['tls_leaf_pins_sha256'])
        require(ident['protocol_sha256'] == manifest['source_sha256']['original/src/protocol.py'], 'runtime protocol source differs')
        require(ident['finite_reports_sha256'] == manifest['source_sha256']['original/src/finite_reports.py'], 'runtime finite backend source differs')
        require(ident['W_sha256'] == hashlib.sha256(canonical(cfg['peers'][i]['W'])).hexdigest(), 'runtime workload hash differs')
        require(ident['input_sha256'] == hashlib.sha256(canonical(cfg['peers'][i]['s'])).hexdigest(), 'runtime input hash differs')
    require(all(len(x) == 1 for x in identities.values()) and identities[0] != identities[1], 'two distinct physical hosts were not verified')
    require(len(pins) == 1 and all(isinstance(x, str) and len(x) == 64 for x in pins), 'inconsistent TLS leaf pin map')
    require(report['host'] in hostnames[0], 'controller hostname does not match compute host 0')
    return dict(machine_id_sha256_by_host={str(h): next(iter(v)) for h, v in identities.items()},
                tls_leaf_pins_sha256=next(iter(pins)), diagnostic_scope='runtime input hashes and hardware/timing diagnostics are outside the declared DP transcript')


def metric_values(row, cfg, derived, output):
    values = {}; messages = []
    times = row.get('seconds', {})
    for key in ('online', 'whole_attempt', 'setup', 'release', 'query'):
        try:
            values[key+'_seconds'] = nonnegative(times[key])
        except (ValueError, KeyError, TypeError) as error: messages.append(key + ': ' + str(error))
    if all(k in times for k in ('prepare', 'setup', 'release', 'query', 'online')):
        try:
            total = sum(nonnegative(times[k]) for k in ('prepare', 'setup', 'release', 'query'))
            require(math.isclose(total, nonnegative(times['online']), rel_tol=1e-10, abs_tol=1e-8), 'online phase sum differs')
        except (ValueError, TypeError) as error:
            values.pop('online_seconds', None); messages.append(str(error))
    for tag, field in (('application', 'plan_plus_collection_application_endpoints'), ('tls', 'plan_plus_collection_tls_endpoints_by_host')):
        try:
            vector = row[field]
            require(len(vector) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in vector), 'invalid two-host byte vector')
            values['max_'+tag+'_kib'] = max(vector)/1024; values['total_'+tag+'_kib'] = sum(vector)/1024
            output[tag+'_endpoint_bytes_by_host'] = vector
            if tag == 'application':
                l0 = cfg['fixed_collection_l0']; logical = [vector[h]-l0[h] for h in (0,1)]
                require(min(logical) >= 0, 'successful byte total is smaller than fixed collection')
                output.update(fixed_collection_application_bytes=l0, observed_logical_application_bytes=logical)
                if cfg['sharing']:
                    match = vector == cfg['chosen_group_loads']; output['model_frames_exact_match'] = match
                    require(row.get('modeled_frames_exact_match') is match, 'stored model-frame match flag differs')
                    require(row['modeled_plan_plus_collection_loads'] == cfg['chosen_group_loads'] and row['fixed_collection_l0'] == l0,
                            'stored modeled/collection fields differ')
                    require(row['observed_logical_interval_loads'] == logical and row['modeled_logical_interval_loads'] == cfg['chosen_group_logical_loads'], 'stored logical byte decomposition differs')
        except (ValueError, KeyError, TypeError) as error:
            # A genuine model/measurement discrepancy is retained. Malformed or
            # contradictory metadata is a separate metric-readback issue.
            messages.append(tag + ': ' + str(error))
            values.pop('max_'+tag+'_kib', None); values.pop('total_'+tag+'_kib', None)
    for field in ('controller_cpu_seconds', 'peer_cpu_seconds_by_host'):
        try:
            values['peer_cpu_seconds' if field.startswith('peer') else field] = (sum(nonnegative(x) for x in row[field])
                                                                                    if field.startswith('peer') else nonnegative(row[field]))
        except (ValueError, KeyError, TypeError) as error: messages.append(field + ': ' + str(error))
    z = [q(x) for x in row['public_reports']]
    truth = [sum((coef*x for coef, x in zip(query, derived['inputs'])), F(0)) for query in derived['Q']]
    answers = [sum((coef*x for coef, x in zip(query, z)), F(0)) for query in derived['Q']]
    mse = sum((weight*(answer-actual)**2 for weight, answer, actual in zip(derived['p'], answers, truth)), F(0))
    output['weighted_squared_error_exact'] = str(mse)
    values['normalized_squared_error'] = number(mse/derived['reference'])
    return values, messages


def check_attempt(raw, cfg, derived, planned, ledger_entry, global_position, result_valid):
    out = dict(planned, observed=True, raw_status=raw.get('status'), status=raw.get('status'),
               ledger_status=ledger_entry.get('status') if ledger_entry else None, charged=ledger_entry is not None,
               structurally_valid=False, primary_eligible=False, metrics={}, issues=[])
    try:
        require(result_valid, 'case configuration/runtime identity not validated')
        require(raw['attempt_id'] == planned['attempt_id'] and raw['index'] == planned['index'], 'attempt label differs')
        require(raw.get('forced_abort') == (planned['kind'] == 'forced_abort'), 'forced-abort schedule differs')
        require(raw.get('fresh_retry') == (planned['kind'] == 'fresh_retry'), 'retry schedule differs')
        require(ledger_entry is not None and raw['global_charge_count'] == global_position+1, 'durable global charge missing or inconsistent')
        require(ledger_entry['case_sha256'] == cfg['config_sha256'], 'durable charged configuration differs')
        expected_status = {'SUCCESS':'SUCCESS', 'FORCED_ABORT':'FORCED_ABORT', 'NUMERICAL_ABORT':'NUMERICAL_ABORT', 'ERROR':'ERROR_CHARGED'}
        require(raw['status'] in expected_status, 'unknown attempt status')
        require(ledger_entry['status'] == expected_status[raw['status']], 'ledger and raw terminal status disagree')
        if raw['status'] == 'SUCCESS':
            require(planned['kind'] != 'forced_abort', 'forced attempt unexpectedly succeeded')
            require(raw.get('exact_aggregation_passed') is True, 'exact aggregation flag did not pass')
            reports = [q(x) for x in raw['public_reports']]; require(len(reports) == 128, 'public report roster incomplete')
            expected = [sum((coef*x for coef, x in zip(query, reports)), F(0)) for query in derived['Q']]
            answers = {int(k): q(v) for k, v in raw['answers'].items()}
            require(set(answers) == set(range(len(expected))) and all(answers[i] == value for i, value in enumerate(expected)), 'independent exact Qz check failed')
            require([q(x) for x in raw['expected_Qz']] == expected, 'stored exact Qz values differ')
            after = raw['by_peer_after']; before = raw['by_peer_before']
            require(len(after) == len(before) == 128 and all(x['id'] == i and x['prepared_attempts'] == global_position+1 for i,x in enumerate(after)), 'peer cumulative count after attempt differs')
            require(all(x['id'] == i and x['prepared_attempts'] == global_position for i,x in enumerate(before)), 'peer cumulative count before attempt differs')
            out['metrics'], metric_issues = metric_values(raw, cfg, derived, out)
            out['issues'].extend(metric_issues); out.update(exact_Qz_passed=True, primary_eligible=True)
        elif raw['status'] == 'FORCED_ABORT':
            require(planned['kind'] == 'forced_abort', 'unexpected forced-abort row')
            release = raw['release_statuses']; exposed = raw['public_exposed_reports']
            require([x['owner_id'] for x in release] == list(range(64)), 'forced exposure schedule differs')
            wanted = [x['owner_id'] for x in release if x['response'].get('status') != 'ABORT']
            require([x['owner_id'] for x in exposed] == wanted, 'exposed prefix/status mismatch')
            for item in exposed:
                require(item['report']['epoch'] == planned['attempt_id'], 'prefix report belongs to another epoch'); q(item['report']['z'])
            out.update(exposed_owners=wanted, exposed_owner_count=len(wanted))
        if raw['status'] != 'ERROR':
            require(len(raw['by_peer_after']) == 128 and all(x['prepared_attempts'] == global_position+1 for x in raw['by_peer_after']), 'non-error cumulative peer count differs')
        out['structurally_valid'] = True
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        out['issues'].append(str(error)); out['primary_eligible'] = False
    if raw.get('error_type') or raw.get('error_message'):
        out['reported_error'] = dict(type=raw.get('error_type'), message=raw.get('error_message'))
    out['reported_seconds'] = {}
    for phase, value in raw.get('seconds', {}).items():
        try: out['reported_seconds'][phase] = nonnegative(value)
        except (ValueError, TypeError) as error: out['issues'].append('reported timing '+phase+': '+str(error))
    if raw.get('status') != 'SUCCESS':
        out['non_success_recorded_endpoints'] = {field:raw[field] for field in
            ('plan_plus_collection_application_endpoints','plan_plus_collection_tls_endpoints_by_host') if field in raw}
        out['non_success_metric_scope'] = ('Preserved runner counters for an incomplete release. In a forced prefix, controller-side '
            'report collection is not added to these arrays by the runner, so they are not comparable to successful plan-plus-collection totals. '
            'Phase names are retained; an aborted query interval can include abort coordination.')
    out['raw_diagnostic_fields_retained_in_source'] = [x for x in raw if x.startswith('diagnostic_')]
    return out


def case_statistics(rows):
    output = {}
    for kind, planned in (('ordinary', 10), ('forced_abort', 1), ('fresh_retry', 1)):
        selected = [r for r in rows if r['kind'] == kind]
        if not selected: continue
        output[kind] = dict(planned=planned, observed=sum(x['observed'] for x in selected), charged=sum(x['charged'] for x in selected),
                            status_counts=dict(Counter(x['status'] for x in selected)),
                            structurally_valid=sum(x.get('structurally_valid', False) for x in selected),
                            metrics={m: descriptive((x['metrics'][m] for x in selected if x.get('primary_eligible') and m in x.get('metrics', {})), planned) for m in METRICS})
        output[kind]['reported_timings_by_status'] = {
            status:{phase:descriptive((x['reported_seconds'][phase] for x in selected if x['status']==status and
                x.get('structurally_valid') and phase in x.get('reported_seconds',{})),planned)
                for phase in ('prepare','setup','release','query','online','whole_attempt')}
            for status in sorted({x['status'] for x in selected if x['observed']})}
    return output


def pair_metrics(base, alternative, bycase):
    b = {r['index']: r for r in bycase.get(base, []) if r['kind'] == 'ordinary' and r.get('primary_eligible')}
    a = {r['index']: r for r in bycase.get(alternative, []) if r['kind'] == 'ordinary' and r.get('primary_eligible')}
    result = {}
    for metric in MAIN_METRICS:
        common = [i for i in range(10) if i in b and i in a and metric in b[i]['metrics'] and metric in a[i]['metrics'] and b[i]['metrics'][metric] > 0]
        left = [b[i]['metrics'][metric] for i in common]; right = [a[i]['metrics'][metric] for i in common]
        ratios = [y/x for x,y in zip(left, right)]
        result[metric] = dict(matched_indices=common, base=descriptive(left,10), alternative=descriptive(right,10),
                             ratio=descriptive(ratios,10), reduction_percent=descriptive([100*(1-x) for x in ratios],10),
                             all_ten_matched=len(common)==10)
    return result


def summarize(args):
    inp = Inputs(); root = args.physical_root.resolve(); manifest = inp.read(args.manifest, optional=False)
    require(manifest is not None, 'frozen manifest unavailable')
    require(manifest['manifest_sha256'] == hashlib.sha256(canonical({k:v for k,v in manifest.items() if k != 'manifest_sha256'})).hexdigest(), 'frozen manifest hash differs')
    require(manifest['physical'] == dict(regular=160, abort_retry=32, no_sharing=10, total_attempts=202), 'physical design counts differ')
    intent = inp.read(root/'controller_intent.json'); plans = schedule(); declared_ids = [x['case_id']+'-'+str(i) for x in plans for i in range(x['planned_attempts'])]
    hosts = intent.get('hosts') if intent else None
    if not hosts:
        # Only current collected top-level reservation intents are inspected.
        records = [inp.read(p) for p in (root/'collected').glob('*/intent.json')]
        variants = {tuple(x['hosts']) for x in records if x and isinstance(x.get('hosts'), list)}
        require(len(variants) <= 1, 'conflicting physical host rosters')
        hosts = list(next(iter(variants))) if variants else []
    require(not hosts or (len(hosts) == len(set(hosts)) == 2), 'two distinct collected host aliases required')
    hostroots = [root/'collected'/host for host in hosts]; host0 = hostroots[0] if hostroots else root/'collected/__missing_host0__'
    closure = {host: inp.read(path/'reservation_closed.json') for host,path in zip(hosts,hostroots)}
    ledger = inp.read(host0/'attempt_ledger.json'); ledger_valid = False; charged = {}; unexpected_ledger = []
    if ledger:
        try:
            require(ledger['horizon'] == 202 and len(ledger['attempts']) <= 202, 'durable horizon was exceeded or changed')
            for position, entry in enumerate(ledger['attempts']):
                require(entry['attempt_id'] == declared_ids[position], 'ledger is not a prefix of the frozen case/attempt order')
                require(entry['attempt_id'] not in charged, 'duplicate durable attempt ID')
                charged[entry['attempt_id']] = entry
            ledger_valid = True
        except (KeyError, ValueError, TypeError) as error:
            inp.issue('ledger','invalid',error)
        # Retain entries even when the prefix check failed; invalid entries cannot
        # make a numerical observation eligible for the primary comparisons.
        for entry in ledger.get('attempts',[]):
            if entry.get('attempt_id') not in declared_ids: unexpected_ledger.append(entry)
            elif entry['attempt_id'] not in charged: charged[entry['attempt_id']] = entry
    index, index_sources = inp.equivalent([root/'configs/physical_index.json']+[x/'configs/physical_index.json' for x in hostroots], 'physical_index')
    if index:
        expected_index = [dict(case_id=x['case_id'],prior_prepared_attempts=x['prior_prepared_attempts'],case_attempts=x['planned_attempts'],config_file=x['case_id']+'.json') for x in plans]
        if index.get('cases') != expected_index or index.get('total_attempts') != 202 or index.get('method_order_seed') != 1601:
            inp.issue('physical_index','different_schedule','index differs from the declared 17-case/202-attempt sequence')
    parents = {x['case_id']:x for x in manifest['group_parents']}; cases = []; all_attempts = []; bycase = {}; lookup = {}; extra_rows = []
    for expected in plans:
        cid = expected['case_id']; info = dict(expected, config_checks_passed=False, runtime_identity_passed=False,
            terminal_record_complete=False, planned_ordinary=10, config_sources=[], result_sources=[], issues=[])
        cfg, config_paths = inp.equivalent([root/'configs'/(cid+'.json')]+[x/'configs'/(cid+'.json') for x in hostroots], cid+' config')
        info['config_sources'] = config_paths; derived = None
        if cfg:
            try:
                derived = configuration(cfg, expected, parents.get('D-n128-'+expected['family']+'-s1401'), manifest)
                info.update(config_checks_passed=True, config_sha256=cfg['config_sha256'], **derived['public'])
            except (KeyError, ValueError, TypeError, ArithmeticError) as error: info['issues'].append('config: '+str(error))
        terminal_path = host0/'results'/(cid+'.json'); partial_path = host0/'results/partial'/(cid+'.json')
        terminal = inp.read(terminal_path); partial = inp.read(partial_path); report = terminal or partial
        info['result_sources'] = [str(p) for p,o in ((terminal_path,terminal),(partial_path,partial)) if o is not None]
        conflict = False
        if terminal and partial:
            prefix = partial.get('rows',[]); conflict = terminal.get('rows',[])[:len(prefix)] != prefix
            if conflict: info['issues'].append('terminal and partial attempt rows conflict')
        if report and cfg:
            try:
                require(not conflict, 'conflicting raw rows')
                info.update(**report_identity(report,cfg,manifest), runtime_identity_passed=True)
                info['terminal_record_complete'] = bool(terminal and terminal.get('complete') and len(terminal.get('rows',[])) == expected['planned_attempts'])
            except (KeyError, ValueError, TypeError) as error: info['issues'].append('runtime: '+str(error))
        raw_byid = {}; duplicates = set()
        for row in (report or {}).get('rows',[]):
            aid = row.get('attempt_id')
            if aid in raw_byid: duplicates.add(aid); info['issues'].append('duplicate raw attempt '+str(aid))
            raw_byid[aid] = row
            if aid not in declared_ids or not str(aid).startswith(cid+'-'): extra_rows.append(dict(case_id=cid,row=row))
        selected = []
        for i in range(expected['planned_attempts']):
            aid = cid+'-'+str(i); kind = 'ordinary' if i < 10 else 'forced_abort' if i == 10 else 'fresh_retry'
            plan = dict(case_id=cid,attempt_id=aid,index=i,kind=kind,main_comparison=expected['sharing'],
                        global_position=expected['prior_prepared_attempts']+i)
            raw = raw_byid.get(aid); charge = charged.get(aid)
            if raw:
                valid = bool(info['config_checks_passed'] and info['runtime_identity_passed'] and ledger_valid and aid not in duplicates)
                item = check_attempt(raw,cfg,derived,plan,charge,plan['global_position'],valid)
                item['raw_file'] = str(terminal_path if terminal else partial_path)
            else:
                item = dict(plan,observed=False,charged=charge is not None,ledger_status=charge.get('status') if charge else None,
                            status='CHARGED_NO_ROW' if charge else 'NOT_CHARGED' if ledger_valid else 'UNOBSERVED_LEDGER_UNAVAILABLE',
                            primary_eligible=False,structurally_valid=False,metrics={},issues=[])
            selected.append(item); all_attempts.append(item)
            for message in item['issues']: inp.issue(aid,'attempt_readback',message)
        info['statistics'] = case_statistics(selected); info['observed_attempts'] = sum(x['observed'] for x in selected)
        info['charged_attempts'] = sum(x['charged'] for x in selected)
        info['model_frame_checks'] = dict(checked=sum('model_frames_exact_match' in x for x in selected),
                                          mismatches=sum(x.get('model_frames_exact_match') is False for x in selected))
        for message in info['issues']: inp.issue(cid,'case_readback',message)
        cases.append(info); bycase[cid] = selected; lookup[cid] = info
    comparisons = []
    for family in ('class','range'):
        for placement in ('balanced','skewed'):
            for price,suffix in (('0','0'),('1/10','1d10')):
                prefix = 'F_'+family+'_'+placement+'_lambda'+suffix+'_'; base, alt = prefix+METHODS[0], prefix+METHODS[1]
                b, a = lookup[base], lookup[alt]
                comparisons.append(dict(condition_id=prefix.rstrip('_'),family=family,placement=placement,lambda_exact=price,
                    base_case=base,alternative_case=alt,planned_ordinary_pairs=10,
                    ideal_error_ratio=(a['ideal_error_normalized']/b['ideal_error_normalized']
                        if a.get('config_checks_passed') and b.get('config_checks_passed') and b['ideal_error_normalized'] > 0 else None),
                    base_family_complete=b.get('candidate_family_complete'), alternative_family_complete=a.get('candidate_family_complete'),
                    metrics=pair_metrics(base,alt,bycase)))
    base = 'F_class_balanced_lambda1d10_fixed8_U'; alt = base+'_no_sharing'; b,a = lookup[base],lookup[alt]
    same = bool(b.get('config_checks_passed') and a.get('config_checks_passed') and b['allocation_and_routes_sha256'] == a['allocation_and_routes_sha256'])
    ablation = dict(base_case=base,alternative_case=alt,planned_ordinary_pairs=10,same_allocation_and_routes=same,
                    metrics=pair_metrics(base,alt,bycase) if same else {},
                    interpretation='same fixed-U allocation and query workload; only within-epoch partial reuse changes')
    if b.get('config_checks_passed') and a.get('config_checks_passed') and not same:
        inp.issue('no_sharing','different_allocation','no-sharing pair does not use the same allocation and routes')
    scopes = {}
    for name, predicate, planned in (
            ('main_ordinary',lambda r:r['kind']=='ordinary' and r['main_comparison'],160),
            ('no_sharing_ordinary',lambda r:r['kind']=='ordinary' and not r['main_comparison'],10),
            ('forced_abort',lambda r:r['kind']=='forced_abort',16),('fresh_retry',lambda r:r['kind']=='fresh_retry',16)):
        rows = [x for x in all_attempts if predicate(x)]
        scopes[name] = dict(planned=planned,observed=sum(x['observed'] for x in rows),charged=sum(x['charged'] for x in rows),
                           validated_successes=sum(x.get('primary_eligible') for x in rows),status_counts=dict(Counter(x['status'] for x in rows)))
    observed = sum(x['observed'] for x in all_attempts); closed = len(closure)==2 and all(x and x.get('ownership_drained') for x in closure.values())
    complete = bool(ledger_valid and len(charged)==202 and observed==202 and all(x['terminal_record_complete'] for x in cases)
                    and all(x['structurally_valid'] for x in all_attempts) and closed and not extra_rows and not unexpected_ledger)
    result = dict(schema=SCHEMA,created_utc=datetime.now(timezone.utc).isoformat(),script_sha256=digest(__file__),
        manifest_sha256=manifest['manifest_sha256'],physical_root=str(root),hosts=hosts,
        status='complete' if complete else 'pending' if not observed and not charged else 'partial_or_inconsistent',
        coverage=dict(planned_cases=17,observed_cases=sum(x['observed_attempts']>0 for x in cases),
                      terminal_complete_cases=sum(x['terminal_record_complete'] for x in cases),
                      planned_attempts=202,observed_attempts=observed,charged_attempts=len(charged) if ledger else None,
                      ledger_available=ledger is not None,ledger_valid=ledger_valid,missing_rows=202-observed,
                      exact_Qz_passed=sum(x.get('exact_Qz_passed',False) for x in all_attempts),
                      model_frame_checked=sum(x['model_frame_checks']['checked'] for x in cases),
                      model_frame_mismatches=sum(x['model_frame_checks']['mismatches'] for x in cases),
                      scopes=scopes,planned_main_condition_pairs=8,planned_no_sharing_pairs=1),
        metric_scope=dict(application='TX+RX at both endpoints, mask/report/partial operations plus exactly one final report collection; includes within-host endpoints',
                          tls='TLS-record endpoints for the same primary operations, including handshakes; excludes TCP/IP headers and retransmissions',
                          latency='online = prepare + setup + release + query; final diagnostic report collection is excluded from online but included in whole_attempt',
                          diagnostics='all-operation snapshot differences, input hashes and hardware timings remain diagnostic and outside the declared DP transcript'),
        pairing='Eight matched public conditions. Only ordinary indices 0..9 enter primary comparisons. Equal indices pair repetitions descriptively; cases run in seed1601 order, with independent fresh OS randomness. No paired-randomness or independent-host CI is claimed.',
        candidate_policy='Verified returned portfolio plans remain visible even when their enumerated candidate family is incomplete; completeness is reported separately. Fixed U must have its prescribed baseline family complete.',
        cases=cases,attempts=all_attempts,comparisons=comparisons,no_sharing=ablation,host_closures=closure,
        unexpected_ledger_entries=unexpected_ledger,unexpected_raw_rows=extra_rows,issues=inp.issues,input_files=inp.files)
    return result


def csv_rows(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='',encoding='utf-8') as out:
        writer = csv.DictWriter(out,fieldnames=fields); writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,sort_keys=True,allow_nan=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physical-root',type=P,required=True); parser.add_argument('--manifest',type=P,required=True)
    parser.add_argument('--out',type=P,required=True); args = parser.parse_args()
    result = summarize(args); args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'physical_summary.json').write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for name, rows in (('physical_attempts',result['attempts']),('physical_cases',result['cases']),('physical_comparisons',result['comparisons'])):
        csv_rows(args.out/(name+'.csv'),rows)
    print(json.dumps(dict(summary=str(args.out/'physical_summary.json'),status=result['status'],coverage=result['coverage'],issues=len(result['issues']))),flush=True)


if __name__ == '__main__': main()
