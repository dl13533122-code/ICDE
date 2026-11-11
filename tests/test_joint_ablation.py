from fractions import Fraction as F

import numpy as np
import pytest

from src.joint_ablation import (compatible_partition_count, configured_loss,
                                fixed_graph_candidates, fixed_partition_candidates,
                                original_edges, total_coordinate_costs)
from src.partition import robust_cycle_power, uniform_group_noise
from src.physical import assemble, candidate_family, resource_partition


def original(groups):
    n = sum(map(len, groups))
    peers = [dict(id=i, a=0., neighbors={}) for i in range(n)]
    for g in groups:
        noise = uniform_group_noise(len(g), 1, .05)
        for i in g:
            peers[i]['a'] = noise['a']
        for u, v in noise['edges']:
            peers[g[u]]['neighbors'][str(g[v])] = noise['w']
            peers[g[v]]['neighbors'][str(g[u])] = noise['w']
    return peers


def test_fixed_graph_retains_complete_edges_and_variances():
    peers = original([list(range(4)), list(range(4, 8))])
    W = np.ones((2, 8))
    cs = fixed_graph_candidates(W, ['fu'] * 4 + ['fy1'] * 4, peers, .5, 1.)
    out = resource_partition(8, cs)
    design = assemble(out['selected'], 8)
    assert set(design['edges']) == set(original_edges(peers))
    assert list(design['a']) == [p['a'] for p in peers]
    assert dict(zip(design['edges'], design['w'])) == original_edges(peers)
    assert compatible_partition_count(8, cs) == 1


def test_fixed_graph_counts_zero_edge_tail_partitions():
    peers = original([list(range(4)), [4, 5]])
    cs = fixed_graph_candidates(np.ones((1, 6)), ['fu'] * 4 + ['fy1'] * 2,
                                peers, .5, 1.)
    assert compatible_partition_count(6, cs) == 2
    assert {(c.start, c.end) for c in cs} == {(0, 4), (4, 5), (5, 6), (4, 6)}


def test_degree_is_not_complete_graph_identity():
    # Two 4-cycles have equal degree. Neither is the eligible f=1 K4 support.
    peers = original([list(range(4))])
    for p in peers:
        p['neighbors'] = {}
    for u, v in [(0, 1), (1, 2), (2, 3), (0, 3)]:
        peers[u]['neighbors'][str(v)] = 10.
        peers[v]['neighbors'][str(u)] = 10.
    cs = fixed_graph_candidates(np.ones((1, 4)), ['fu', 'fu', 'fy1', 'fy1'], peers, .5, 1.)
    assert cs == []
    assert compatible_partition_count(4, cs) == 0


def test_reciprocal_edges_are_required():
    peers = original([list(range(4))])
    peers[1]['neighbors']['0'] *= 2
    with pytest.raises(ValueError, match='both endpoints'):
        original_edges(peers)


def test_fixed_partition_preserves_all_blocks_not_signature_pieces():
    W = np.ones((2, 8))
    hosts = ['fu'] * 4 + ['fy1'] * 4
    all_cs = candidate_family(W, hosts, max_interval=8, allowed_host_links=[('fu', 'fy1')])
    Pi0 = [list(range(4)), list(range(4, 8))]
    cs = fixed_partition_candidates(all_cs, Pi0, 8)
    assert {(c.start, c.end) for c in cs} == {(0, 4), (4, 8)}
    assert compatible_partition_count(8, cs) == 1
    out = resource_partition(8, cs)
    assert [c.payload['members'] for c in out['selected']] == Pi0


def test_infeasible_fixed_graph_has_no_overloaded_fallback():
    peers = original([list(range(4))])
    cs = fixed_graph_candidates(np.ones((1, 4)), ['fu', 'fu', 'fy1', 'fy1'], peers, .5, 1.)
    out = resource_partition(4, cs, caps=(0, 0), l0=(0, 0), grid=(4096, 4096))
    assert not out['feasible'] and out['selected'] == [] and out['error'] is None


def test_loss_sums_coordinates_with_explicit_fixed_denominator():
    W = np.array([[1., 2.], [3., 4.]])
    value = configured_loss(W, [1., 2.], [(0, 1)], [.5], dimension=2)
    assert value == F(102)  # 2 * (10 + 40 + 1)
    cs = candidate_family(W, ['fu', 'fy1'], max_interval=2, allowed_host_links=[('fu', 'fy1')])
    doubled = total_coordinate_costs(cs, 2)
    assert all(b.error == 2 * a.error for a, b in zip(cs, doubled))
