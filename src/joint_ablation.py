"""Strict R6 ablation restrictions; no sampling or protocol execution.

FIXED_GRAPH freezes both the realized edge identities and configured variances.
Only compatible partitions and the original routing choices can change.
FIXED_PARTITION freezes the complete noise partition, not the routing pieces.
"""
from dataclasses import replace
from fractions import Fraction as F
from types import SimpleNamespace

import numpy as np

from src.partition import coalition_certificate, robust_cycle_power
from src.physical import Candidate, error_exact, public_plan


def original_edges(peers):
    result = {}
    for i, p in enumerate(peers):
        if p['id'] != i:
            raise ValueError('original public roster must retain its order')
        for raw_j, w in p['neighbors'].items():
            j = int(raw_j)
            if i == j or not 0 <= j < len(peers) or w <= 0:
                raise ValueError('invalid original realized edge')
            if str(i) not in peers[j]['neighbors'] or F(w) != F(peers[j]['neighbors'][str(i)]):
                raise ValueError('original mask edge must agree at both endpoints')
            if i < j:
                result[i, j] = w
    return result


def partition_intervals(partition, n):
    cursor = 0
    intervals = []
    for members in partition:
        end = cursor + len(members)
        if not members or members != list(range(cursor, end)):
            raise ValueError('Pi0 must be the full original ordered partition')
        intervals.append((cursor, end))
        cursor = end
    if cursor != n:
        raise ValueError('Pi0 must cover every original participant exactly once')
    return intervals


def fixed_partition_candidates(candidates, partition, n):
    allowed = set(partition_intervals(partition, n))
    return [c for c in candidates if (c.start, c.end) in allowed]


def fixed_graph_candidates(W, host_map, peers, rho, delta, max_interval=8, f=1):
    """Enumerate all compatible intervals, preserving the whole original G0.

    No G0 edge may cross an interval boundary. Each interval must realize the
    exact original induced edge set through an eligible cycle-power or no-edge
    branch. Retain original a and w (no variance optimization in this arm).
    """
    n = len(peers)
    graph = original_edges(peers)
    result = []
    for end in range(1, n + 1):
        for start in range(max(0, end - max_interval), end):
            members = list(range(start, end))
            if any((start <= u < end) != (start <= v < end) for u, v in graph):
                continue
            induced = {(u, v): w for (u, v), w in graph.items() if start <= u < end}
            local = [(u - start, v - start) for u, v in induced]
            if local and set(local) != set(robust_cycle_power(len(members), f)):
                continue
            a_values = {F(peers[i]['a']) for i in members}
            w_values = {F(w) for w in induced.values()}
            if len(a_values) != 1 or len(w_values) > 1:
                raise ValueError('original fixed mechanism is not an eligible uniform group')
            a = peers[start]['a']
            w = next(iter(induced.values()), 0.0)
            noise = SimpleNamespace(a=a, w=w, f=f, branch='cycle-power' if local else 'independent')
            certificate = coalition_certificate(len(members), f, a, w, rho, delta)
            if not certificate['passed']:
                raise ValueError('original fixed mechanism fails its unchanged certificate')
            for h in sorted(set(host_map)):
                plan = public_plan(W, members, host_map, h, local)
                result.append(Candidate(start, end, f'{start}:{end}:frozen-G0:{h}',
                                        error_exact(W, members, a, local, w), plan['loads'],
                                        dict(members=members, noise=noise, plan=plan,
                                             certificate=certificate)))
    return result


def compatible_partition_count(n, candidates):
    """Count partitions without counting duplicate leader or noise options."""
    ends = {t: set() for t in range(1, n + 1)}
    for c in candidates:
        ends[c.end].add(c.start)
    counts = [1] + [0] * n
    for t in range(1, n + 1):
        counts[t] = sum(counts[s] for s in ends[t])
    return counts[n]


def total_coordinate_costs(candidates, dimension):
    if dimension < 1:
        raise ValueError('positive frozen coordinate count required')
    return [replace(c, error=c.error * dimension) for c in candidates]


def configured_loss(W, a, edges, weights, dimension=1):
    """Exact rational ideal loss for the entire frozen workload/coordinates."""
    W = np.asarray(W)
    total = F(0)
    for i, v in enumerate(a):
        total += F(float(v)) * sum((F(float(x)) ** 2 for x in W[:, i]), F(0))
    for (u, v), w in zip(edges, weights):
        total += F(float(w)) * sum(((F(float(x)) - F(float(y))) ** 2
                                   for x, y in zip(W[:, u], W[:, v])), F(0))
    return dimension * total
