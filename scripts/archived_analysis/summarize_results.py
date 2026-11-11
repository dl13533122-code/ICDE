"""Aggregate current ICDE02 results without changing the frozen experiments.

Run on an authorized analysis host, not inside the Fu SSH controller. This
script reads the frozen manifest, collected result JSON, prepared metadata,
and the named frozen source directory. It never launches a solver or reruns
an experimental case. Optional covariance replay calls certificate checkers
only. Triangle brackets are checked by the frozen exact readback routine.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

SCHEMA = 'icde02-summary-v1'
METHODS = ('I', 'U', 'H')
SUITES = ('A', 'B', 'C', 'Cfull')
PRICES = (F(0), F(1, 1000), F(1, 100), F(1, 10))
ZERO = F(0)


def require(value, message):
    if not value:
        raise ValueError(message)


def q(value):
    if isinstance(value, F):
        return value
    if isinstance(value, bool):
        raise ValueError('boolean is not a rational measurement')
    if isinstance(value, dict) and value.get('encoding') == 'hex-rational-v1':
        return F(int(value['numerator_hex'], 16), int(value['denominator_hex'], 16))
    if isinstance(value, str) and '/' in value:
        left, right = value.split('/')
        integer = lambda s: int(s, 16 if s.lower().lstrip('+-').startswith('0x') else 10)
        return F(integer(left), integer(right))
    return F(str(value))


def qs(value):
    value = q(value)
    integer = lambda x: hex(x) if abs(x).bit_length() > 4096 else str(x)
    return integer(value.numerator) + '/' + integer(value.denominator)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def number(value):
    if value is None:
        return None
    answer = float(value)
    require(math.isfinite(answer), 'nonfinite numerical summary')
    return answer


def finite_float(value):
    require(isinstance(value, (float, int)) and not isinstance(value, bool), 'expected numerical row value')
    return number(value)


def close(left, right):
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-12)


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def interval(value):
    lo, hi = q(value['lower']), q(value['upper'])
    require(lo <= hi, 'reversed recorded interval')
    return lo, hi


def basic_statistics(case):
    n = case['n']; edges = case['edges']; Q = [[q(x) for x in row] for row in case['Q']]
    p = list(map(q, case['p']))
    require(len(p) == len(Q) and all(len(row) == n for row in Q), 'workload dimensions')
    require(all(x >= 0 for x in p), 'negative query frequency')
    require(len({tuple(sorted(e)) for e in edges}) == len(edges), 'duplicate graph edge')
    require(all(len(e) == 2 and 0 <= e[0] < n and 0 <= e[1] < n and e[0] != e[1] for e in edges), 'graph edge domain')
    if all(x.denominator == 1 for row in Q for x in row):
        den = math.lcm(*(x.denominator for x in p)); weights = [int(x * den) for x in p]
        rows = [[int(x) for x in row] for row in Q]
        s = [F(sum(weight * row[i]**2 for weight, row in zip(weights, rows)), den) for i in range(n)]
        c = [F(sum(weight * (row[u] - row[v])**2 for weight, row in zip(weights, rows)), den) for u, v in edges]
    else:
        s = [sum((weight * row[i]**2 for weight, row in zip(p, Q)), ZERO) for i in range(n)]
        c = [sum((weight * (row[u]-row[v])**2 for weight, row in zip(p, Q)), ZERO) for u, v in edges]
    return s, c


def scientific_ids(case):
    rows = [[qs(x) for x in row] for row in case['Q']]
    p = [qs(x) for x in case['p']]
    raw = identity({'n': case['n'], 'Q': rows, 'p': p})
    distribution = defaultdict(F)
    for row, weight in zip(rows, map(q, p)):
        if weight:
            distribution[tuple(row)] += weight
    workload = identity({'n': case['n'], 'weighted_rows': [[list(row), qs(weight)] for row, weight in sorted(distribution.items())]})
    condition = {'workload_id': workload, 'n': case['n'], 'edges': sorted(sorted(e) for e in case['edges']),
                 'f': case['f'], 'node_cap': None if case.get('node_cap') is None else qs(case['node_cap']),
                 'edge_cap': None if case.get('edge_cap') is None else qs(case['edge_cap']),
                 'tau': None if case.get('tau') is None else qs(case['tau'])}
    for key in ('order', 'dataset', 'coordinate_count'):
        if key in case:
            condition[key] = case[key]
    return raw, workload, identity(condition)


class Inputs:
    def __init__(self, revision):
        self.revision = Path(revision); self.files = {}; self.issues = []
        self.terminal = defaultdict(list); self.partial = defaultdict(list); self.methods = defaultdict(list)
        for path in sorted((self.revision / 'remote_results').glob('*/results/*/*.json')):
            obj = self.get(path)
            if obj and isinstance(obj.get('case_id'), str):
                self.terminal[obj['case_id']].append((path, obj))
        for path in sorted((self.revision / 'remote_results').glob('*/results/*/partial/*.json')):
            obj = self.get(path)
            if obj and isinstance(obj.get('case_id'), str):
                self.partial[obj['case_id']].append((path, obj))
        for path in sorted((self.revision / 'remote_results').glob('*/results/*/methods/*.json')):
            if '__' not in path.stem:
                continue
            case_id, method = path.stem.rsplit('__', 1)
            obj = self.get(path)
            if obj is not None:
                self.methods[(case_id, method)].append((path, obj))

    def get(self, path):
        path = Path(path)
        try:
            obj = read(path); self.files[str(path)] = file_hash(path)
            return obj
        except (OSError, ValueError) as error:
            self.issues.append({'path': str(path), 'kind': 'unreadable_json', 'message': str(error)})
            return None

    def unique(self, records, label):
        if not records:
            return None, []
        groups = defaultdict(list)
        for path, obj in records:
            groups[identity(obj)].append((path, obj))
        if len(groups) > 1:
            self.issues.append({'kind': 'conflicting_records', 'key': label, 'paths': [str(x[0]) for x in records]})
            return None, [str(x[0]) for x in records]
        return records[0][1], [str(x[0]) for x in records]

    def case(self, case_id):
        records = self.terminal.get(case_id, [])
        assembly = 'terminal'
        if not records:
            records = self.partial.get(case_id, []); assembly = 'partial'
        obj, paths = self.unique(records, case_id)
        if obj is None:
            return {}, 'conflicting' if paths else 'missing', paths
        return obj, assembly, paths

    def method(self, case, method):
        parent, assembly, paths = self.case(case['case_id'])
        if assembly == 'conflicting':
            return {}, assembly, paths
        record = parent.get('results', {}).get(method)
        independent, sources = self.unique(self.methods.get((case['case_id'], method), []), case['case_id'] + '__' + method)
        if sources and independent is None:
            return {}, 'conflicting', paths + sources
        if record is not None and independent is not None and canonical(record) != canonical(independent):
            self.issues.append({'kind': 'method_record_disagreement', 'case_id': case['case_id'], 'method': method})
            return {}, 'conflicting', paths + sources
        if record is None:
            record = independent
            if record is not None:
                assembly = 'method_only'
        if record is None:
            return {}, 'missing', paths
        if parent.get('input_sha256') not in (None, case['input_sha256']):
            return {}, 'conflicting', paths + sources
        if assembly == 'terminal' and not parent.get('input_sha256'):
            return {}, 'conflicting', paths + sources
        if not parent.get('input_sha256') and assembly == 'method_only':
            linked = False
            for filename in sources:
                for worker in Path(filename).parent.parent.glob('worker_*.json'):
                    data = self.get(worker)
                    linked |= bool(data and case['case_id'] in data.get('selected', []))
            if not linked:
                return {}, 'conflicting', paths + sources
        return record, assembly, paths + sources


class Checks:
    def __init__(self, manifest, science_src, replay=False):
        self.src = Path(science_src); self.replay = replay; self.statistics = {}; self.privacy_cache = {}
        self.modules = {}; self.expected = manifest.get('source_sha256', {})
        for name in ('common.py', 'solvers.py', 'uniform_oracle.py', 'triangle_exact.py', 'grouping.py', 'finite_sim.py'):
            expected = self.expected.get('revision_src/' + name)
            require(expected and file_hash(self.src / name) == expected, 'frozen source differs: ' + name)

    def module(self, name):
        if name not in self.modules:
            sys.path.insert(0, str(self.src))
            self.modules[name] = module_from(self.src / (name + '.py'), '_icde_readback_' + name)
        return self.modules[name]

    def stats(self, case):
        key = identity({name: case[name] for name in ('n', 'Q', 'p', 'edges')})
        if key not in self.statistics:
            self.statistics[key] = basic_statistics(case)
        s, c = self.statistics[key]
        if 's' in case:
            require(s == list(map(q, case['s'])) and c == list(map(q, case['c'])), 'recorded workload statistics disagree with Q,p')
        return s, c

    def allocation(self, case, result, method):
        s, c = self.stats(case); a = list(map(q, result['a'])); w = list(map(q, result['w']))
        require(len(a) == case['n'] and len(w) == len(case['edges']), 'allocation dimensions')
        require(all(x > 0 for x in a) and all(x >= 0 for x in w), 'variance domain')
        for values, key in ((a, 'node_cap'), (w, 'edge_cap')):
            if case.get(key) is not None:
                require(all(x <= q(case[key]) for x in values), key + ' exceeded')
        if case.get('tau') is not None:
            require(sum(w, ZERO) <= q(case['tau']), 'total edge-variance budget exceeded')
        error = sum((x*y for x, y in zip(s, a)), ZERO) + sum((x*y for x, y in zip(c, w)), ZERO)
        require(error == q(result['error']), 'objective readback mismatch')
        independent = all(x == 1 for x in a) and all(x == 0 for x in w)
        if method == 'I':
            require(independent, 'I allocation differs from independence')
            return error, independent, 'exact independence'
        if method == 'U':
            require(len(set(a)) == 1 and len(set(w)) <= 1, 'uniform design is not uniform')
        if not any(w):
            require(min(a) >= 1, 'zero-edge privacy fails')
            return error, independent, 'exact diagonal privacy'
        if method == 'H':
            terms = [[] for _ in a]
            for (u, v), x in zip(case['edges'], w):
                terms[u].append(a[v]*x/(a[v]+x)); terms[v].append(a[u]*x/(a[u]+x))
            values = [a[i]+sum(sorted(ts)[:max(0, len(ts)-case['f'])], ZERO) for i, ts in enumerate(terms)]
            require(min(values) >= 1, 'harmonic lower bound below one')
            if 'minimum_q' in result:
                require(q(result['minimum_q']) == min(values), 'stored minimum harmonic value differs')
            return error, independent, 'exact harmonic readback'
        if method == 'U':
            require(len(set(a)) == 1 and len(set(w)) == 1, 'uniform design is not uniform')
        certificate = result.get('certificate')
        require(isinstance(certificate, dict) and certificate.get('verified') is True, 'full-covariance certificate missing')
        require(q(certificate['minimum_schur_lower']) >= 1, 'full-covariance Schur lower bound below one')
        if 'maximum_inverse_upper' in certificate:
            require(q(certificate['maximum_inverse_upper']) <= 1, 'inverse upper bound exceeds one')
        for key in ('n', 'f'):
            if key in certificate:
                require(certificate[key] == case[key], 'privacy certificate case mismatch')
        if 'r' in certificate:
            require(q(certificate['r']) == 1, 'privacy normalization mismatch')
        if method == 'U':
            for key, value in (('a', a[0]), ('w', w[0])):
                if key in certificate:
                    require(q(certificate[key]) == value, 'uniform certificate allocation mismatch')
        if self.replay:
            key = identity({'n': case['n'], 'f': case['f'], 'edges': case['edges'], 'a': list(map(qs, a)), 'w': list(map(qs, w))})
            if key not in self.privacy_cache:
                if method == 'U' and case['n'] >= 7 and case['f'] in (0, 1):
                    checked = self.module('uniform_oracle').cert_uniform(a[0], w[0], case['n'], case['f'], max_prec=512)
                else:
                    checked = self.module('solvers').full_inverse_check(case, a, w)
                self.privacy_cache[key] = checked.get('verified') is True
            require(self.privacy_cache[key], 'replayed full-covariance check did not certify feasibility')
        return error, independent, 'replayed full covariance' if self.replay else 'recorded rigorous full-covariance certificate with exact domain/objective readback'

    def activation(self, case, result):
        s, c = self.stats(case); edges = case['edges']; m = len(edges)
        v = list(map(q, result['v'])); pi = list(map(q, result['pi']))
        require(len(v) == m and len(pi) == 2*m and all(x >= 0 for x in v) and sum(v, ZERO) == 1, 'activation primal domain')
        require(all(0 <= x <= 1 for x in pi), 'activation dual domain')
        d = []
        for i in range(case['n']):
            incident = [e for e, uv in enumerate(edges) if i in uv]
            d.append(sum(sorted(v[e] for e in incident)[:max(0, len(incident)-case['f'])], ZERO))
            require(sum((pi[2*e + int(edges[e][1] == i)] for e in incident), ZERO) <= case['f'], 'activation dual row budget')
        B = sum((x*y for x, y in zip(s, d)), ZERO)-sum((x*y for x, y in zip(c, v)), ZERO)
        gamma = max(s[u]+s[vv]-c[e]-s[u]*pi[2*e]-s[vv]*pi[2*e+1] for e, (u, vv) in enumerate(edges))
        require(q(result['B']) == B and q(result['gamma']) == gamma, 'activation objective readback')
        decision = 'help' if B > 0 else 'no-help' if gamma <= 0 else 'unresolved'
        require(result['decision'] == decision, 'activation decision mismatch')
        return decision, B, gamma

    def full_lower(self, case, dual):
        if not dual:
            return None
        s, c = self.stats(case); n = case['n']; g = [ZERO]*n; h = [ZERO]*len(c); b = ZERO
        multiplier = q(dual['factor_multiplier']); require(multiplier >= 0, 'negative PSD multiplier')
        for factor in dual['factors']:
            C = factor['C']; H = factor['H']; target = factor['target']
            require(len(C) == len(set(C)) and len(C) <= case['f'] and all(0 <= i < n for i in C), 'dual coalition')
            require(H == [i for i in range(n) if i not in C] and target in H, 'dual honest-owner ordering')
            B = [list(map(q, row)) for row in factor['B']]
            require(len(B) == len(H) and all(len(row) == len(H) for row in B), 'PSD factor dimensions')
            position = {owner: i for i, owner in enumerate(H)}
            norms = [multiplier*sum((x*x for x in row), ZERO) for row in B]
            b += norms[position[target]]
            for i, owner in enumerate(H):
                g[owner] += norms[i]
            for e, (u, v) in enumerate(case['edges']):
                if u in position and v in position:
                    h[e] += multiplier*sum(((x-y)**2 for x, y in zip(B[position[u]], B[position[v]])), ZERO)
        if case.get('node_cap') is not None:
            lower = b + q(case['node_cap'])*sum((min(ZERO, si-gi) for si, gi in zip(s, g)), ZERO)
            if case.get('tau') is None:
                require(case.get('edge_cap') is not None, 'dual box needs finite edge cap')
                lower += q(case['edge_cap'])*sum((min(ZERO, ci-hi) for ci, hi in zip(c, h)), ZERO)
            else:
                lower += q(case['tau'])*min([ZERO]+[ci-hi for ci, hi in zip(c, h)])
        else:
            require(case.get('tau') is not None and all(si >= gi for si, gi in zip(s, g)), 'uncapped-anchor dual residual')
            tau = q(case['tau']); lower = b+max(ZERO, 1-tau)*sum((si-gi for si, gi in zip(s, g)), ZERO)
            lower += tau*min([ZERO]+[ci-hi for ci, hi in zip(c, h)])
        require(lower == q(dual['lower_bound']), 'FULL weak-dual lower bound mismatch')
        return lower

    def uniform_lower(self, case, result):
        s, c = self.stats(case); S, T = sum(s, ZERO), sum(c, ZERO)
        degree = min(sum(i in e for e in case['edges']) for i in range(case['n']))
        if result.get('uniform_threshold'):
            require(T >= S*max(0, degree-case['f']) and q(result['lower_bound']) == S, 'uniform threshold lower bound mismatch')
            return S
        proof = result.get('optimality_enclosure')
        if not proof:
            return None
        require(proof.get('verified') is True and proof['n'] == case['n'] and proof['f'] == case['f'], 'uniform lower-bound identity')
        require(q(proof['S']) == S and q(proof['T']) == T and q(proof['r']) == 1, 'uniform lower-bound objective')
        require(q(proof['a']) > 0 and q(proof['w']) >= 0, 'uniform reference variance domain')
        coalition = proof['chosen_view']; target = proof['chosen_target']
        require(len(coalition) == len(set(coalition)) and len(coalition) <= case['f'] and
                all(0 <= i < case['n'] for i in coalition) and 0 <= target < case['n'] and target not in coalition,
                'uniform lower-bound chosen constraint')
        expected_edges = {tuple(sorted((i, (i+d) % case['n']))) for i in range(case['n']) for d in (1, 2) if i != (i+d) % case['n']}
        require({tuple(sorted(e)) for e in case['edges']} == expected_edges, 'uniform oracle requires cycle-square support')
        K = None if case.get('node_cap') is None else q(case['node_cap'])
        W = q(case['edge_cap']) if case.get('edge_cap') is not None else q(case['tau'])/len(case['edges'])
        if case.get('tau') is not None:
            W = min(W, q(case['tau'])/len(case['edges']))
        require((None if proof['a_cap'] is None else q(proof['a_cap'])) == K and q(proof['w_cap']) == W, 'uniform lower-bound cap domain')
        values = {key: interval(value) for key, value in proof['coefficient_intervals'].items()}
        lam = q(proof['lambda']); norm = values['norm_squared']; energy = values['laplacian_energy']
        require(lam >= 0 and norm[1] > 0 and lam == S/norm[1], 'uniform dual multiplier')
        require(values['DA'] == (S-lam*norm[1], S-lam*norm[0]), 'uniform anchor coefficient')
        require(values['DW'] == (T-lam*energy[1], T-lam*energy[0]), 'uniform edge coefficient')
        ui = values['u_i']; a, w = q(proof['a']), q(proof['w'])
        clo = max(lam*(2*ui[0]-1), lam*(ui[0]-1+a*norm[0]+w*energy[0]))
        chi = min(lam*(2*ui[1]-1), lam*(ui[1]-1+a*norm[1]+w*energy[1]))
        require(values['C'] == (clo, chi) and clo <= chi, 'uniform constant interval')
        da, dw = values['DA'][0], values['DW'][0]
        if K is None:
            require(da >= 0, 'uncapped uniform anchor coefficient')
            raw = clo + max(ZERO, 1-len(case['edges'])*W)*da + W*min(ZERO, dw)
        else:
            raw = clo + K*min(ZERO, da)+W*min(ZERO, dw)
        require(raw == q(proof['raw_lower_bound']) and max(ZERO, raw) == q(proof['lower_bound']), 'uniform affine-box lower bound')
        require(q(result['lower_bound']) == q(proof['lower_bound']), 'uniform result lower bound mismatch')
        return max(ZERO, raw)


def context(case):
    raw, workload, condition = scientific_ids(case)
    return dict(case_id=case['case_id'], suite=case.get('suite'), n=case['n'], f=case['f'],
                family=case.get('family'), seed=case.get('seed'), repeat=case.get('repeat'),
                theta=None if case.get('theta') is None else number(q(case['theta'])),
                tau=None if case.get('tau') is None else number(q(case['tau'])),
                raw_workload_id=raw, workload_id=workload, condition_id=condition)


def method_row(case, method, record, assembly, paths, checks):
    row = context(case)
    row.update(method=method, assembly=assembly, sources=paths, execution_status=record.get('execution_status', assembly),
               reported_verified=record.get('verified') is True, usable=False, standalone=False, fallback=False,
               independent_returned=False, branch=record.get('branch'), error=None, error_exact=None,
               error_normalized=None, lower_bound=None, lower_bound_exact=None, bracket_width=None,
               privacy_check=None, issues=[], solver_status=record.get('solver_status', record.get('optimizer_status')),
               solved_candidate_verified=record.get('solved_candidate_verified'),
               calibrated_candidate_verified=record.get('calibrated_candidate_verified'))
    row['seconds'] = next((number(record[key]) for key in ('wall_including_start_seconds', 'wall_seconds', 'seconds')
                           if isinstance(record.get(key), (int, float)) and math.isfinite(record[key])), None)
    if not record:
        return row
    if row['execution_status'] != 'completed':
        missing_allocation = method != 'LP' and not all(key in record for key in ('a', 'w', 'error'))
        missing_activation = method == 'LP' and not all(key in record for key in ('v', 'pi', 'B', 'gamma'))
        if (missing_allocation or missing_activation) and not record.get('dual') and not record.get('optimality_enclosure'):
            return row
    try:
        s, _ = checks.stats(case); reference = sum(s, ZERO)
        if method == 'LP':
            decision, B, gamma = checks.activation(case, record)
            row.update(activation_status=decision, activation_B=number(B), activation_gamma=number(gamma),
                       usable=row['execution_status'] == 'completed' and decision != 'unresolved',
                       standalone=row['execution_status'] == 'completed', privacy_check='exact activation primal/dual readback')
            return row
        error, independent, kind = checks.allocation(case, record, method)
        admitted = row['reported_verified'] and row['execution_status'] == 'completed'
        fallback = (method == 'H' and independent and
                    (bool(record.get('solver_error')) or record.get('solved_candidate_verified') is False or
                     ('solver_status' in record and record.get('solved_candidate_verified') is None)))
        fallback |= method == 'U' and record.get('calibrated_candidate_verified') is False
        fallback |= method == 'FULL' and str(record.get('branch', '')).startswith('full solver fallback')
        row.update(allocation_readback_passed=True, usable=admitted, standalone=admitted and not fallback,
                   fallback=bool(fallback), independent_returned=independent, error=number(error), error_exact=qs(error),
                   error_normalized=number(error/reference) if reference else None, privacy_check=kind,
                   active_edges=sum(q(x) > 0 for x in record['w']))
    except (ValueError, KeyError, TypeError, ArithmeticError) as error:
        row['issues'].append(str(error)); row['allocation_readback_passed'] = False
    # A valid dual may survive even when no admitted primal was returned.
    try:
        lower = checks.full_lower(case, record.get('dual')) if method == 'FULL' else checks.uniform_lower(case, record) if method == 'U' else None
        if lower is not None:
            row.update(lower_bound=number(lower), lower_bound_exact=qs(lower), lower_bound_checked=True)
            if row['usable']:
                width = q(row['error_exact'])-lower
                require(width >= 0, 'checked global lower bound exceeds certified upper bound')
                if 'objective_bracket_width' in record:
                    require(q(record['objective_bracket_width']) == width, 'stored objective width mismatch')
                row['bracket_width'] = number(width); row['bracket_width_exact'] = qs(width)
    except (ValueError, KeyError, TypeError, ArithmeticError) as error:
        row['issues'].append(str(error)); row['lower_bound_checked'] = False
        row.update(lower_bound=None, lower_bound_exact=None, bracket_width=None)
        if 'exceeds certified upper' in str(error):
            row.update(usable=False, standalone=False, contradictory=True)
    return row


def summarize_cases(manifest, inputs, checks):
    rows = []; portfolios = []; phase = []; gaps = []
    for case in manifest['cases']:
        require(case['input_sha256'] == identity({k: v for k, v in case.items() if k != 'input_sha256'}), 'frozen case hash mismatch')
        method_rows = {}
        for method in case['methods']:
            record, assembly, paths = inputs.method(case, method)
            row = method_row(case, method, record, assembly, paths, checks)
            rows.append(row); method_rows[method] = row
        candidates = [method_rows[m] for m in METHODS if method_rows.get(m, {}).get('usable')]
        port = context(case); port.update(method='PORTFOLIO', usable=bool(candidates), standalone=True,
            family_complete=all(method_rows.get(m, {}).get('standalone') for m in METHODS), selected_method=None,
            error=None, error_exact=None, error_normalized=None, fallback=False,
            seconds=sum(r['seconds'] for m, r in method_rows.items() if m in METHODS and r['seconds'] is not None),
            timing_complete=all(method_rows.get(m, {}).get('seconds') is not None for m in METHODS))
        if candidates:
            choice = min(candidates, key=lambda r: (q(r['error_exact']), METHODS.index(r['method'])))
            port.update(selected_method=choice['method'], error=choice['error'], error_exact=choice['error_exact'],
                        error_normalized=choice['error_normalized'], selected_fallback=choice['fallback'])
        else:
            port['standalone'] = False
        portfolios.append(port)
        if case['suite'] == 'A':
            s, c = checks.stats(case); S, T = sum(s, ZERO), sum(c, ZERO)
            degree = min(sum(i in e for e in case['edges']) for i in range(case['n']))
            limit = S*max(0, degree-case['f']); lp = method_rows.get('LP', {})
            entry = context(case); entry.update(activation_status=lp.get('activation_status', lp.get('execution_status', 'missing')),
                activation_B=lp.get('activation_B'), activation_gamma=lp.get('activation_gamma'),
                uniform_help_predicted=bool(T < limit), uniform_ratio=number(T/limit) if limit else None)
            phase.append(entry)
        if case['suite'] == 'B':
            h = method_rows.get('H', {}); full = method_rows.get('FULL', {}); entry = context(case)
            entry.update(usable=False, H_candidate=h.get('error') if h.get('usable') else None,
                         FULL_upper=full.get('error') if full.get('usable') else None,
                         FULL_lower=full.get('lower_bound'), FULL_width=full.get('bracket_width'),
                         candidate_excess_lower=None, candidate_excess_upper=None,
                         candidate_excess_lower_normalized=None, candidate_excess_upper_normalized=None,
                         normalization='independent objective S', local_theorem_domain=q(case['tau']) < 1,
                         gap_scope='returned H candidate minus full-pairwise optimum; not H optimum minus full optimum')
            # Any certified feasible allocation is a valid P* upper bound, without
            # changing any standalone method result or pretending to solve H*.
            uppers = [r for r in method_rows.values() if r.get('usable') and r['method'] != 'LP']
            if h.get('usable') and full.get('lower_bound_checked') and uppers:
                EH = q(h['error_exact']); UP = min(q(r['error_exact']) for r in uppers); LP = q(full['lower_bound_exact'])
                require(LP <= UP, 'FULL lower bound exceeds another feasible allocation')
                low, high = max(ZERO, EH-UP), EH-LP; S = sum(checks.stats(case)[0], ZERO)
                entry.update(usable=True, full_problem_upper=number(UP),
                    candidate_excess_lower=number(low), candidate_excess_upper=number(high),
                    candidate_excess_lower_normalized=number(low/S), candidate_excess_upper_normalized=number(high/S),
                    H_fallback=h['fallback'], H_standalone=h['standalone'])
            gaps.append(entry)
    return rows, portfolios, phase, gaps


def summarize_triangle(manifest, inputs, checks):
    paths = sorted((inputs.revision / 'remote_results').glob('*/results/triangle/triangle_exact.json'))
    payload, sources = inputs.unique([(p, inputs.get(p)) for p in paths if inputs.get(p) is not None], 'triangle')
    verified = False; problem = None
    if payload:
        try:
            require(list(map(q, payload['requested_taus'])) == list(map(q, manifest['triangle_taus'])), 'triangle requested budget list differs from frozen design')
            checks.module('triangle_exact').verify_payload(payload); verified = True
        except Exception as error:
            problem = str(error); inputs.issues.append({'kind': 'triangle_readback', 'message': problem})
    observed = {q(row['tau']): row for row in payload.get('cases', [])} if payload else {}
    rows = []
    for value in manifest['triangle_taus']:
        tau = q(value); record = observed.get(tau, {}); out = dict(tau=number(tau), tau_exact=str(tau),
            status=record.get('status', 'missing'), verified=verified and bool(record.get('gap')),
            width_targets_met=False, sources=sources, asymptotic_limit=1/32, target_width=number(tau**3/3200))
        if out['verified']:
            try:
                p = record['methods']['full_pairwise']['interval']; h = record['methods']['harmonic']['interval']
                pl, pu, hl, hu = map(q, (p['lower'], p['upper'], h['lower'], h['upper']))
                require(pl <= pu and hl <= hu, 'triangle reversed brackets')
                lower, upper = max(ZERO, hl-pu), hu-pl
                out.update(full_lower=number(pl), full_upper=number(pu), full_width=number(pu-pl),
                    harmonic_lower=number(hl), harmonic_upper=number(hu), harmonic_width=number(hu-hl),
                    gap_lower=number(lower), gap_upper=number(upper), normalized_gap_lower=number(lower/tau**3),
                    normalized_gap_upper=number(upper/tau**3), cubic_upper=number(F(20, 27)*tau**3/(1-tau)**2),
                    normalized_cubic_upper=number(F(20, 27)/(1-tau)**2),
                    width_targets_met=pu-pl <= tau**3/3200 and hu-hl <= tau**3/3200,
                    exact={'full_lower': qs(pl), 'full_upper': qs(pu), 'harmonic_lower': qs(hl), 'harmonic_upper': qs(hu),
                           'gap_lower': qs(lower), 'gap_upper': qs(upper)})
            except (KeyError, ValueError) as error:
                out.update(verified=False, issue=str(error))
        rows.append(out)
    return rows


def group_local_case(parent, selected):
    members = selected['members']; Q = [[row[i] for i in members] for row in parent['Q']]
    return dict(n=len(members), f=1, Q=Q, p=parent['p'], edges=selected['local_edges'],
                node_cap=8, edge_cap=8, tau=None)


def check_group_plan(parent, placement, plan, price, checks):
    host_map = placement['host_map']; n = parent['n']; cut = sum(h == 0 for h in host_map)
    require(len(host_map) == n and set(host_map) <= {0, 1}, 'host map domain')
    l0 = [1536*(cut+n), 1536*(n-cut)]
    require(placement['fixed_collection_l0'] == l0 and plan['fixed_collection_l0'] == l0, 'fixed collection load mismatch')
    error = ZERO; logical = [0, 0]; end = 0; keys = []; active = 0
    for selected in plan['selected']:
        require(selected['start'] == end and end < selected['end'] <= n, 'group partition discontinuity')
        require(selected['members'] == parent['order'][end:selected['end']], 'group owner ordering')
        end = selected['end']; keys.append(selected['key'])
        allocation = selected['allocation']; method = allocation['allocation_method']
        value, _, _ = checks.allocation(group_local_case(parent, selected), allocation, method)
        require(allocation.get('verified') is True and value == q(selected['error']), 'uncertified group allocation')
        error += value; active += sum(q(w) > 0 for w in allocation['w'])
        loads = [0, 0]
        for u, v, operation in selected['plan']['calls']:
            require(operation in ('mask', 'report', 'partial') and 0 <= u < n and 0 <= v < n, 'routing operation domain')
            frame = 640 if operation == 'mask' else 1152
            loads[host_map[u]] += frame; loads[host_map[v]] += frame
        require(loads == list(selected['loads']) == list(selected['plan']['loads']), 'selected endpoint loads differ')
        logical = [x+y for x, y in zip(logical, loads)]
    require(end == n and keys == plan['selected_keys'], 'incomplete selected grouping path')
    loads = [x+y for x, y in zip(logical, l0)]
    require(logical == plan['logical_interval_loads'] and loads == plan['loads'], 'group load decomposition')
    require(sum(loads) == plan['total_application_endpoint_bytes'] and max(loads) == plan['max_host_application_bytes'], 'total versus maximum-host load mismatch')
    require(error == q(plan['error']) and active == plan['active_edges'], 'group error/edge count mismatch')
    S = sum(checks.stats(parent)[0], ZERO); score = error + price*(S/n)*F(sum(loads), 1024)
    require(score == q(plan['objective']), 'scalar grouping objective must price total endpoint KiB')
    return error, score, loads, logical, l0, active


def summarize_groups(manifest, inputs, checks):
    rows = []; fronts = []
    for parent in manifest['group_parents']:
        obj, assembly, sources = inputs.case(parent['case_id']); base = context(parent)
        base.update(interleaved=bool(parent.get('interleaved')), assembly=assembly, sources=sources)
        linkage = obj.get('input_sha256') == parent['input_sha256'] if obj.get('complete') else obj.get('input_sha256') in (None, parent['input_sha256'])
        S = sum(checks.stats(parent)[0], ZERO)
        for name in ('balanced', 'skewed'):
            placement = obj.get('placements', {}).get(name, {})
            for partition in ('fixed8', 'adaptive'):
                for family in ('U', 'H', 'PORTFOLIO'):
                    for price in PRICES:
                        key = partition+'_'+family+'_lambda'+str(price); plan = placement.get('plans', {}).get(key, {})
                        row = dict(base, placement=name, partition=partition, candidate_family=family,
                            price=number(price), price_exact=str(price), complete=bool(plan.get('complete')),
                            method_family_complete=bool(plan.get('method_family_complete')), verified=False,
                            parent_complete=obj.get('complete') is True, error=None, error_normalized=None,
                            total_endpoint_kib=None, max_host_kib=None)
                        if plan.get('complete'):
                            try:
                                require(linkage and assembly != 'conflicting', 'group parent input identity')
                                error, score, loads, logical, l0, active = check_group_plan(parent, placement, plan, price, checks)
                                row.update(verified=True, error=number(error), error_exact=qs(error), error_normalized=number(error/S),
                                    objective=number(score), total_endpoint_kib=sum(loads)/1024, max_host_kib=max(loads)/1024,
                                    host_endpoint_kib=[x/1024 for x in loads], logical_host_endpoint_kib=[x/1024 for x in logical],
                                    fixed_collection_kib=[x/1024 for x in l0], interval_count=len(plan['selected']), active_edges=active)
                            except (KeyError, ValueError, TypeError, ArithmeticError) as error:
                                row['issue'] = str(error)
                        rows.append(row)
            frontier = placement.get('resource_frontier', {})
            output = dict(base, placement=name, complete=bool(frontier.get('complete')),
                method_family_complete=bool(frontier.get('method_family_complete')), planned=True,
                coordinate_check_passed=False, points=[], parent_complete=obj.get('complete') is True)
            if frontier.get('complete'):
                try:
                    require(linkage and assembly != 'conflicting', 'frontier input identity')
                    previous_error = None; previous_load = None
                    for point in frontier['points']:
                        error = q(point['error']); logical = point['logical_interval_loads']; l0 = point['fixed_collection_l0']
                        require(l0 == placement['fixed_collection_l0'], 'frontier fixed collection load')
                        loads = [x+y for x, y in zip(logical, l0)]
                        require(len(loads) == 2 and loads == point['loads'] and max(loads) == point['max_host_bytes'], 'frontier max-host projection')
                        end = 0
                        for key in point['selected_keys']:
                            start, stop = map(int, key.split(':')[:2]); require(start == end and start < stop <= parent['n'], 'frontier partition')
                            end = stop
                        require(end == parent['n'], 'frontier terminal path incomplete')
                        require(previous_error is None or (error >= previous_error and max(loads) < previous_load), 'dominated projected frontier point')
                        previous_error, previous_load = error, max(loads)
                        output['points'].append(dict(error=number(error), error_normalized=number(error/S), max_host_kib=max(loads)/1024,
                            total_endpoint_kib=sum(loads)/1024, host_endpoint_kib=[x/1024 for x in loads],
                            logical_host_endpoint_kib=[x/1024 for x in logical], fixed_collection_kib=[x/1024 for x in l0],
                            selected_keys=point['selected_keys']))
                    output['coordinate_check_passed'] = True
                except (KeyError, ValueError, TypeError) as error:
                    output.update(issue=str(error), points=[])
            fronts.append(output)
    return rows, fronts


def confidence(values, planned):
    values = [finite_float(x) for x in values if x is not None]; n = len(values)
    mean = statistics.fmean(values) if values else None; low = high = None
    if n >= 2:
        from scipy.stats import t
        half = float(t.ppf(.975, n-1))*statistics.stdev(values)/math.sqrt(n)
        low, high = mean-half, mean+half
    return dict(mean=mean, ci_low=low, ci_high=high, batch_n=n, planned_batches=planned)


def summarize_finite(manifest, inputs, checks, prepared):
    path = prepared / 'finite_inputs.json'; index = inputs.get(path) if path.exists() else None
    expected = [(dataset, family) for dataset in ('intel', 'electricity') for family in ('sum', 'range', 'groupby', 'mixed')]
    instances = {x['case']['case_id']: x for x in (index or {}).get('instances', [])}
    seeds = manifest['finite']['batch_seeds']; attempts = manifest['finite']['attempts']; forced = manifest['finite']['forced_zero_abort_index']
    answer = []
    for dataset, family in expected:
        cid = 'E_'+dataset+'_'+family; instance = instances.get(cid); obj, assembly, sources = inputs.case(cid)
        partial, _ = inputs.unique(inputs.partial.get(cid, []), cid+' partial')
        rows = obj.get('rows', (partial or {}).get('rows', []))
        out = dict(case_id=cid, dataset=dataset, family=family, n=instance['case']['n'] if instance else None,
            dimension=2 if dataset == 'intel' else 1, status='missing' if not obj else 'complete' if obj.get('complete') else 'partial',
            assembly=assembly, sources=sources, allocation_checks_passed=False, finite_checks_passed=False,
            planned_batches=len(seeds), observed_batches=0, planned_rows=len(seeds)*attempts*3, observed_rows=len(rows),
            success_rows=sum(r.get('status') == 'SUCCESS' for r in rows), abort_rows=sum(r.get('status') == 'ABORT' for r in rows),
            forced_abort_rows=sum(r.get('status') == 'ABORT' and r.get('forced_abort') is True for r in rows),
            missing_rows=max(0, len(seeds)*attempts*3-len(rows)), paired_complete=False, eligible_for_primary=False,
            batch_records=[], methods={}, paired_comparisons={}, ideal={}, issues=[])
        try:
            require(instance is not None, 'prepared finite input index unavailable')
            case = instance['case']; require(obj.get('input_sha256') in (None, case['input_sha256']), 'finite input hash mismatch')
            if obj.get('complete'):
                require(obj.get('input_sha256') == case['input_sha256'], 'complete finite result needs its exact input hash')
            scale = obj['scale']; dimension = out['dimension']
            require(scale['dimension'] == dimension and scale['attempts'] == attempts, 'finite scale dimension/horizon')
            require(q(scale['rho_per_attempt']) == q(scale['rho_total'])/attempts and
                    q(scale['r']) == 2*q(scale['rho_per_attempt'])/dimension, 'finite privacy scale composition')
            require(q(scale['epsilon']) == q(manifest['finite'].get('epsilon', 1)) and
                    q(scale['delta']) == q(manifest['finite'].get('delta', '1/1000000')), 'finite declared epsilon/delta')
            reference = out['dimension']*sum(checks.stats(case)[0], ZERO)/q(obj['scale']['r'])
            require(reference == q(obj['independent_reference']), 'finite independent reference must be d*S/r')
            for method in METHODS:
                allocation = obj['allocations'][method]
                value, _, _ = checks.allocation(case, allocation, method)
                require(allocation.get('verified') is True, 'finite allocation not certified')
                ideal = out['dimension']*value/q(obj['scale']['r'])/reference
                require(q(obj['ideal'][method]['normalized_error']) == ideal, 'finite ideal normalization differs')
                out['ideal'][method] = number(ideal)
            out['allocation_checks_passed'] = True
            for method in METHODS:
                proof = obj['finite_proofs'][method]; bound = proof['bound']
                require(bound['passed'] is True and proof['preflight']['passed'] is True, 'finite report bound/preflight failed')
                require(bound['attempts'] == attempts and q(bound['numerical_delta_upper_exact']) <= q(str(bound['delta_total']))/2,
                        'finite numerical delta or horizon mismatch')
            out['finite_checks_passed'] = True
            bykey = {}
            for row in rows:
                require(row['batch_seed'] in seeds and row['method'] in METHODS and 0 <= row['attempt'] < attempts, 'unplanned finite row')
                key = (row['batch_seed'], row['attempt'], row['method']); require(key not in bykey, 'duplicate finite method attempt')
                bykey[key] = row; batch_index = seeds.index(row['batch_seed'])
                slot = forced if row['attempt'] == manifest['finite']['fresh_retry_index'] else row['attempt']
                selected_day = instance['eval_indices'][(batch_index*attempts+slot) % len(instance['eval_indices'])]
                require(row['date'] == str(instance['dates'][selected_day]), 'finite date schedule mismatch')
                require(row.get('forced_abort') == (row['attempt'] == forced), 'forced-abort label mismatch')
                if row['status'] == 'SUCCESS':
                    require(row['attempt'] != forced, 'forced primitive did not abort')
                    value = finite_float(row['weighted_squared_error'])/number(reference)
                    require(value >= 0 and close(value, row['normalized_squared_error']), 'finite MSE normalization differs')
                else:
                    require(row['status'] == 'ABORT', 'unknown finite row status')
            for seed in seeds:
                per_method = {m: [r for key, r in bykey.items() if key[0] == seed and key[2] == m] for m in METHODS}
                maps = {m: {(r['attempt'], r['date']): r for r in records if r['status'] == 'SUCCESS' and r['attempt'] != forced}
                        for m, records in per_method.items()}
                common = set.intersection(*(set(maps[m]) for m in METHODS))
                means = {m: statistics.fmean(maps[m][key]['normalized_squared_error'] for key in sorted(common)) if common else None for m in METHODS}
                clipped = {m: statistics.fmean(maps[m][key]['clipped_weighted_squared_error']/number(reference) for key in sorted(common)) if common else None for m in METHODS}
                forced_ok = all((seed, forced, m) in bykey and bykey[(seed, forced, m)]['status'] == 'ABORT' for m in METHODS)
                retry = manifest['finite']['fresh_retry_index']
                same_date = all((seed, retry, m) in bykey and (seed, forced, m) in bykey and
                                bykey[(seed, retry, m)]['date'] == bykey[(seed, forced, m)]['date'] and
                                bykey[(seed, retry, m)].get('fresh_retry') is True for m in METHODS)
                batch = dict(seed=seed, paired_attempts=len(common), planned_nonforced_attempts=attempts-1,
                    forced_abort_passed=forced_ok, retry_same_date=same_date, means=means, clipped_means=clipped,
                    unpaired_successes={m: len(maps[m])-len(common) for m in METHODS},
                    status_counts={m: dict(Counter(r['status'] for r in per_method[m])) for m in METHODS})
                out['batch_records'].append(batch)
            out['observed_batches'] = sum(b['paired_attempts'] > 0 for b in out['batch_records'])
            out['paired_complete'] = all(b['paired_attempts'] == attempts-1 and b['forced_abort_passed'] and b['retry_same_date'] for b in out['batch_records'])
            for method in METHODS:
                out['methods'][method] = confidence([b['means'][method] for b in out['batch_records']], len(seeds))
                out['methods'][method]['ideal_normalized_error'] = out['ideal'][method]
                out['methods'][method]['clipped'] = confidence([b['clipped_means'][method] for b in out['batch_records']], len(seeds))
            for left, right in (('H', 'U'), ('H', 'I'), ('U', 'I')):
                differences = [b['means'][left]-b['means'][right] for b in out['batch_records'] if b['means'][left] is not None and b['means'][right] is not None]
                comparison = confidence(differences, len(seeds)); stored = obj.get('paired_comparisons', {}).get(left+'-'+right)
                if stored:
                    require(comparison['batch_n'] == stored['paired_batch_count'] and close(comparison['mean'], stored['mean_normalized_difference']), 'paired batch comparison mismatch')
                    if comparison['ci_low'] is not None:
                        require(stored['ci95'] and close(comparison['ci_low'], stored['ci95'][0]) and close(comparison['ci_high'], stored['ci95'][1]), 'paired CI mismatch')
                out['paired_comparisons'][left+'-'+right] = comparison
            out['eligible_for_primary'] = bool(obj.get('complete') and out['paired_complete'] and len(rows) == out['planned_rows'])
        except (KeyError, ValueError, TypeError, ArithmeticError, IndexError) as error:
            out['issues'].append(str(error)); out['eligible_for_primary'] = False
        answer.append(out)
    return answer


def summarize_data(inputs, prepared):
    answer = []
    for dataset in ('intel', 'electricity'):
        path = prepared / (dataset+'_coverage.json'); record = inputs.get(path) if path.exists() else None
        if not record:
            answer.append({'dataset': dataset, 'status': 'missing', 'source_file': str(path)}); continue
        evaluation = record.get('split', {}).get('evaluation', {})
        answer.append(dict(dataset=dataset, status=record.get('status'), source_file=str(path),
            owner_count=record.get('owner_count', len(record.get('owner_ids', []))), raw_rows=record.get('raw_rows'),
            qualified_rows=record.get('qualified_rows'), calendar_days=record.get('calendar_date_count', record.get('raw_calendar_date_count')),
            valid_days=record.get('valid_date_count', record.get('complete_date_count')), evaluation_days=evaluation.get('date_count'),
            evaluation_available_owner_days=evaluation.get('available_owner_days'), evaluation_roster_owner_days=evaluation.get('roster_owner_days'),
            clipped_rows_or_cells=record.get('qualified_clipped_rows', record.get('clipped_cells')), coordinates=record.get('coordinates'),
            qualification_rule=record.get('quality_rule'), normalization=record.get('normalization', record.get('clipping_rule'))))
    return answer


def coverage(manifest, rows, groups, finite, triangle, inputs):
    answer = {}
    for suite in SUITES:
        cases = [c for c in manifest['cases'] if c['suite'] == suite]; selected = [r for r in rows if r['suite'] == suite]
        entry = dict(planned_cases=len(cases), observed_cases=sum(bool(inputs.terminal.get(c['case_id']) or inputs.partial.get(c['case_id'])) for c in cases),
            terminal_cases=sum(bool(inputs.terminal.get(c['case_id'])) for c in cases),
            raw_workloads=len({scientific_ids(c)[0] for c in cases}), workloads=len({scientific_ids(c)[1] for c in cases}),
            conditions=len({scientific_ids(c)[2] for c in cases}), by_method={})
        for method in sorted({r['method'] for r in selected}):
            bucket = [r for r in selected if r['method'] == method]
            entry['by_method'][method] = dict(planned=len(bucket), observed=sum(r['assembly'] not in ('missing', 'conflicting') for r in bucket),
                completed=sum(r['execution_status'] == 'completed' for r in bucket), usable=sum(r['usable'] for r in bucket),
                standalone=sum(r['standalone'] for r in bucket), fallback=sum(r['fallback'] for r in bucket),
                timeouts=sum('timeout' in r['execution_status'].lower() or r['execution_status'] == 'global_deadline' for r in bucket),
                errors=sum(r['execution_status'] == 'error' or bool(r.get('issues')) for r in bucket),
                missing=sum(r['assembly'] == 'missing' for r in bucket), contradictory=sum(r.get('contradictory', False) for r in bucket),
                finite_brackets=sum(r.get('bracket_width') is not None for r in bucket))
        answer[suite] = entry
    parents = manifest['group_parents']
    answer['D'] = dict(planned_cases=len(parents), observed_cases=sum(bool(inputs.terminal.get(c['case_id']) or inputs.partial.get(c['case_id'])) for c in parents),
        terminal_cases=sum(bool(inputs.terminal.get(c['case_id'])) for c in parents), workloads=len({scientific_ids(c)[1] for c in parents}),
        conditions=len({scientific_ids(c)[2] for c in parents}), planned_scalar_plans=len(groups), verified_scalar_plans=sum(x['verified'] for x in groups),
        complete_candidate_family_plans=sum(x['verified'] and x['method_family_complete'] for x in groups))
    answer['E'] = dict(planned_cases=len(finite), observed_cases=sum(x['observed_rows'] > 0 for x in finite),
        terminal_cases=sum(x['status'] == 'complete' for x in finite), planned_rows=sum(x['planned_rows'] for x in finite),
        observed_rows=sum(x['observed_rows'] for x in finite), primary_instances=sum(x['eligible_for_primary'] for x in finite))
    answer['triangle'] = dict(planned_cases=len(triangle), observed_cases=sum(x['status'] != 'missing' for x in triangle),
        verified_brackets=sum(x['verified'] for x in triangle), width_targets_met=sum(x['width_targets_met'] for x in triangle))
    answer['physical'] = dict(planned_cases=manifest['physical']['total_attempts'], observed_cases=0, status='pending')
    return answer


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def tables_and_facts(summary, out):
    def tex(value):
        return str(value).replace('&', r'\&').replace('%', r'\%').replace('_', r'\_').replace('#', r'\#')
    purposes = {'A': 'Activation regimes', 'B': 'Budgeted approximation', 'C': 'Sparse scaling',
                'Cfull': 'Matched full comparison', 'D': 'Grouping and host load', 'E': 'Finite public-data releases',
                'triangle': 'Cubic-order sharpness', 'physical': 'Two-host execution'}
    design = [r'\begin{tabular}{lrl}', r'\hline', r'Study & Planned units & Purpose \\', r'\hline']
    table = [r'\begin{tabular}{lrrl}', r'\hline', r'Study & Observed/planned & Workloads & Certified results \\', r'\hline']
    facts = ['% Generated solely from current collected records; missing values are not substituted.']
    for suite, counts in summary['coverage'].items():
        design.append(f"{tex(suite)} & {counts['planned_cases']} & {tex(purposes[suite])} \\\\")
        observed = counts.get('observed_cases', 0); planned = counts['planned_cases']; methods = counts.get('by_method', {})
        text = '; '.join(f"{m}: {v['usable']}/{v['planned']}" for m, v in methods.items())
        if suite == 'D': text = f"{counts['verified_scalar_plans']}/{counts['planned_scalar_plans']} plans"
        if suite == 'E': text = f"{counts['primary_instances']}/{planned} fully paired instances"
        if suite == 'triangle': text = f"{counts['width_targets_met']}/{planned} narrow brackets"
        if suite == 'physical': text = 'Pending physical measurements'
        table.append(f"{tex(suite)} & {observed}/{planned} & {counts.get('workloads', '--')} & {tex(text)} \\\\")
        macro = ''.join(x for x in suite.title() if x.isalpha())
        facts.extend([rf'\newcommand{{\Result{macro}Planned}}{{{planned}}}', rf'\newcommand{{\Result{macro}Observed}}{{{observed}}}'])
        for method, values in methods.items():
            facts.append(rf'\newcommand{{\Result{macro}{method}Certified}}{{{values["usable"]}}}')
            facts.append(rf'\newcommand{{\Result{macro}{method}Fallback}}{{{values["fallback"]}}}')
    for lines, name in ((design, 'table_design.tex'), (table, 'table_coverage.tex')):
        lines.extend([r'\hline', r'\end{tabular}']); (out/name).write_text('\n'.join(lines)+'\n', encoding='utf-8')
    for row in summary['dataset_coverage']:
        for key in ('owner_count', 'raw_rows', 'valid_days', 'evaluation_days', 'evaluation_available_owner_days', 'evaluation_roster_owner_days'):
            if row.get(key) is not None:
                macro = row['dataset'].title()+''.join(x.title() for x in key.split('_'))
                facts.append(rf'\newcommand{{\Result{macro}}}{{{row[key]}}}')
    (out/'factual_strings.tex').write_text('\n'.join(facts)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', type=Path, required=True)
    parser.add_argument('--science-src', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--recheck-covariance', action='store_true', help='Replay covariance certificate checks; no optimization')
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    inputs = Inputs(args.revision); path = args.revision/'FROZEN_MANIFEST.json'; manifest = inputs.get(path)
    require(manifest is not None, 'frozen manifest unavailable')
    require(manifest['manifest_sha256'] == identity({k: v for k, v in manifest.items() if k != 'manifest_sha256'}), 'frozen manifest hash differs')
    checks = Checks(manifest, args.science_src, args.recheck_covariance)
    prepared = args.prepared or args.revision/'remote_results/fuyuespark/prepared'
    rows, portfolios, phase, gaps = summarize_cases(manifest, inputs, checks)
    triangle = summarize_triangle(manifest, inputs, checks)
    groups, fronts = summarize_groups(manifest, inputs, checks)
    finite = summarize_finite(manifest, inputs, checks, prepared)
    data = summarize_data(inputs, prepared)
    summary = dict(schema=SCHEMA, created_utc=datetime.now(timezone.utc).isoformat(),
        script_sha256=file_hash(__file__), manifest_sha256=manifest['manifest_sha256'],
        covariance_replay_requested=args.recheck_covariance, case_methods=rows, portfolios=portfolios, phase=phase,
        local_gaps=gaps, triangle=triangle, group_plans=groups, group_frontiers=fronts, finite=finite,
        dataset_coverage=data, physical={'status': 'pending', 'planned_attempts': manifest['physical']['total_attempts']},
        coverage=coverage(manifest, rows, groups, finite, triangle, inputs),
        workload_identity='Exact weighted query-row distribution: duplicates combined, zero weights removed, row ordering ignored; timing seeds/repeats alone do not define independent workloads.',
        condition_identity='Workload, graph, f, caps and total edge budget, plus grouping order or data-domain encoding when applicable.',
        input_files=inputs.files, issues=inputs.issues)
    summary['issues'] += [{'case_id': r['case_id'], 'method': r['method'], 'kind': 'method_readback', 'message': message}
                          for r in rows for message in r.get('issues', [])]
    summary['issues'] += [{'case_id': r['case_id'], 'kind': 'group_readback', 'message': r['issue']} for r in groups+fronts if r.get('issue')]
    summary['issues'] += [{'case_id': r['case_id'], 'kind': 'finite_readback', 'message': message} for r in finite for message in r['issues']]
    write_json(args.out/'summary.json', summary)
    for name, records in (('case_methods', rows), ('portfolios', portfolios), ('phase', phase), ('local_gaps', gaps),
                          ('triangle', triangle), ('group_plans', groups), ('dataset_coverage', data)):
        write_csv(args.out/(name+'.csv'), records)
    tables_and_facts(summary, args.out)
    print(json.dumps({'summary': str(args.out/'summary.json'), 'issues': len(summary['issues']), 'coverage': summary['coverage']}), flush=True)


if __name__ == '__main__':
    main()
