from fractions import Fraction as F
import itertools
import numpy as np
import pytest
from src.physical import Candidate, Label, dominates, frontier, resource_partition, round_loads, candidate_family, assemble, public_plan
from src.noise import loss

def enumerate_plans(n,cs,start=0):
    if start==n:
        yield [];return
    for c in cs:
        if c.start==start:
            for tail in enumerate_plans(n,cs,c.end):yield [c]+tail

def test_exhaustive_caps_grid_zero_ties_infeasibility():
    for seed in range(8):
        rng=np.random.default_rng(seed);n=5;cs=[]
        for s in range(n):
            for t in range(s+1,n+1):
                for p in range(2):cs.append(Candidate(s,t,str(p),F(int(rng.integers(0,6)),3),tuple(F(int(x),3) for x in rng.integers(0,7,2))))
        allplans=list(enumerate_plans(n,cs));l0=(F(1),F(2))
        for caps in [(0,0),(5,5),(10,10),(100,100)]:
            for grid in [None,(F(1),F(2))]:
                plans=[]
                for p in allplans:
                    ls=tuple(sum(((c.loads if grid is None else round_loads(c.loads,grid))[h] for c in p),F(0)) for h in range(2))
                    if all(l+lbase<=cap for l,lbase,cap in zip(ls,l0,caps)):plans.append(p)
                out=resource_partition(n,cs,caps,l0,grid)
                assert out['feasible']==bool(plans)
                if plans:assert out['error']==min(sum((c.error for c in p),F(0)) for p in plans)

def test_dominance_append_and_equal_score_continuations():
    a=Label(F(1),(F(2),F(3)));b=Label(F(2),(F(2),F(4)))
    assert dominates(a,b)
    for e,l1,l2 in itertools.product(range(4),repeat=3):
        aa=Label(a.error+e,(a.loads[0]+l1,a.loads[1]+l2));bb=Label(b.error+e,(b.loads[0]+l1,b.loads[1]+l2))
        assert dominates(aa,bb)
    assert not dominates(a,a);assert len(frontier([a,a,b]))==1

def test_n_d_slack_and_conservative_feasibility():
    n=4;grid=(F(2,3),F(3,5));cs=[Candidate(i,i+1,str(i),F(i), (F(1,4),F(2,7))) for i in range(n)]
    load=tuple(sum(c.loads[h] for c in cs) for h in range(2));l0=(F(1),F(2));caps=tuple(load[h]+l0[h]+n*grid[h] for h in range(2))
    out=resource_partition(n,cs,caps,l0,grid);assert out['feasible']
    for h in range(2):assert out['rounded_loads'][h]-load[h]<n*grid[h]
    assert out['error']==sum(c.error for c in cs)
    with pytest.raises(ValueError):round_loads((1,2),(0,1))

def test_scalar_sum_overloads_vector_alternative():
    # Scalar sum chooses 11-byte plan on host A; 12-byte balanced plan feasible.
    cs=[Candidate(0,1,'scalar',F(0),(10,1)),Candidate(0,1,'balanced',F(1),(6,6))]
    scalar=min(cs,key=lambda c:sum(c.loads));assert scalar.key=='scalar'
    out=resource_partition(1,cs,(8,8));assert out['feasible'] and out['selected'][0].key=='balanced'

def test_family_certificate_exact_error_unavailable_links():
    W=np.array([[1,1,1,1,0,0],[0,0,0,0,1,1]],float);hosts=['fu']*2+['fy1']*4
    cs=candidate_family(W,hosts,allowed_host_links=[('fu','fy1')])
    for c in cs:
        assert c.payload['certificate']['passed'];assert sum(c.loads)==sum(c.payload['plan']['per_node'])
    out=resource_partition(6,cs);d=assemble(out['selected'],6)
    assert float(out['error'])==pytest.approx(loss(W,d['a'],d['edges'],d['w']))
    disconnected=candidate_family(W,hosts,allowed_host_links=[])
    assert all(all(hosts[u]==hosts[v] for u,v,op in c.payload['plan']['calls']) for c in disconnected)

def test_intragroup_reuse_no_cross_group_dedup():
    W=np.ones((8,4));hosts=['fu','fy1','fy1','fy1']
    p=public_plan(W,[0,1],hosts,'fy1',[]);q=public_plan(W,[2,3],hosts,'fy1',[])
    assert sum(p['loads'])==sum(p['per_node'])
    assert sum(q['loads'])==sum(q['per_node'])
    # Owner 0 retrieves a separate partial from each independent group.
    assert any(u==0 and op=='partial' for u,v,op in p['calls'])
    assert any(u==0 and op=='partial' for u,v,op in q['calls'])

def test_zero_workload_exact_family_and_multicoordinate_grid():
    cs=candidate_family(np.zeros((3,5)),['fu','fy1','fy1','fy1','fy1'],allowed_host_links=[('fu','fy1')])
    out=resource_partition(5,cs,(10000,10000),grid=(1,1));assert out['feasible'] and out['error']==0
    assert all(c.payload['noise'].w==0 for c in out['selected'])
    # Generic H=3 pruning and caps exercise a different implementation branch.
    family=[Candidate(0,1,'a',F(1),(1,3,1)),Candidate(0,1,'b',F(0),(4,1,1)),Candidate(1,2,'c',F(1),(1,1,1))]
    out=resource_partition(2,family,(3,5,3),grid=(1,1,1))
    assert out['feasible'] and out['error']==2 and out['selected'][0].key=='a'

def test_fixed_frame_padding_and_overflow():
    from src.protocol import Channel,blank
    ch=Channel.__new__(Channel);ch.metrics=blank();ch.local=blank();sent=[]
    class Transport:
        def write(self,b):sent.append(b);return len(b)
    ch.ssl=Transport();ch.action=lambda f:f()
    ch.send({'op':'partial','group':100,'_frame_request':128,'_frame_response':1024},128)
    assert len(b''.join(sent))==128 and ch.metrics['application_tx_bytes']==128
    import json
    assert json.loads(b''.join(sent))['group']==100
    with pytest.raises(ValueError):ch.send({'payload':'x'*200},128)

def test_full_utility_max_normalized_frontier_projection():
    from src.physical import normalized_frontier
    labels=[Label(F(0),(10,1)),Label(F(1),(8,5)),Label(F(2),(6,6)),Label(F(3),(6,6))]
    out=normalized_frontier(labels,(10,10),(0,0))
    assert [(e,l) for e,l,p in out]==[(F(0),F(1)),(F(1),F(4,5)),(F(2),F(3,5))]
    with pytest.raises(ValueError):normalized_frontier(labels,(0,10))

@pytest.mark.parametrize('k',[13,17,24])
def test_uniform_cycle_rigorous_shortcut_matches_dense_all_views(k):
    from src.release_gate import rigorous_finite_certificate,validate_peer_config
    from src.noise import covariance
    a,w=1.25,2.5;edges=[(j,(j+1)%k) for j in range(k)]
    peers=[dict(id=i,a=a,neighbors={str(v if u==i else u):w for u,v in edges if i in (u,v)},rho_per_release=.5) for i in range(k)]
    worst=max(np.diag(np.linalg.inv(covariance(np.full(k,a),edges,np.full(k,w),C)[0])).max()/2 for C in [(),*( (j,) for j in range(k))])
    r=rigorous_finite_certificate(peers);assert r['passed'] and r['worst_rho_upper']==pytest.approx(worst,rel=1e-13)
    assert r['scenarios']==k+1 and r['constraints']==k*k
    assert validate_peer_config(peers)['passed']
    for p in peers:p['rho_per_release']=worst*.9
    with pytest.raises(ValueError):rigorous_finite_certificate(peers)

def test_fixed_baseline_routing_labels_match_exhaustive_host_choices():
    from scripts.physical_prepare_r6 import fixed_design_plan
    W=np.ones((8,8));hosts=['fu']*4+['fy1']*4;groups=[[i,i+4] for i in range(4)]
    peers=[dict(neighbors={}) for _ in hosts];base=(2000,1000)
    choices=[[public_plan(W,g,hosts,h,[]) for h in ('fu','fy1')] for g in groups]
    scores=[]
    for pp in itertools.product(*choices):
        load=tuple(sum(p['loads'][h] for p in pp) for h in range(2))
        scores.append((max(load[h]+base[h] for h in range(2)),sum(load),load))
    gg,ll,pp=fixed_design_plan(W,hosts,peers,groups,base)
    assert (max(ll[h]+base[h] for h in range(2)),sum(ll),ll)==min(scores)
    assert sorted(i for g in gg for i in g['members'])==list(range(8))

def test_deployable_scalar_byte_plan_overloads_host():
    W=np.ones((2,4));hosts=['fu','fu','fu','fy1']
    cs=candidate_family(W,hosts,allowed_host_links=[('fu','fy1')])
    scalar=min(enumerate_plans(4,cs),key=lambda p:(sum(sum(c.loads) for c in p),sum(c.error for c in p)))
    assert tuple(sum(c.loads[h] for c in scalar) for h in range(2))==(8064,1152)
    out=resource_partition(4,cs,(6000,6000))
    assert out['feasible'] and out['loads']==(5760,5760)
    assert sum(out['loads'])>sum(sum(c.loads) for c in scalar)
