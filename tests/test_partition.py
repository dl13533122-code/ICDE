import itertools
import math
import threading
import time

import mpmath as mp
import numpy as np
import pytest
from scipy.optimize import minimize_scalar
from src.noise import covariance, loss, certify, spectral_group
from src.partition import (robust_cycle_power, analytical_gap_bound,
    coalition_certificate, uniform_group_noise, group_noise_optimizer,
    interval_cost_cache, certified_partition_dp)
from src.planner import plan
from src.release_gate import validate_peer_config
from src.protocol import Peer, blank


@pytest.mark.parametrize('f',[0,1,2])
def test_every_small_removal_and_restricted_lower_bound(f):
    for k in range(1,10):
        h=max(1,k-f)
        for gamma in [.001,.05,.5,10.]:
            d=uniform_group_noise(k,f,gamma)
            c=coalition_certificate(k,f,d['a'],d['w'],exhaustive=True)
            assert c['passed'] and c['direct_worst_rho'] <= .5*(1+1e-8)
            assert len(d['edges'])<=k*(f+1)
            if d['w']:
                degree=np.bincount(np.array(d['edges']).ravel(),minlength=k)
                assert degree.max()<=min(2*(f+1),k-1)
                assert c['direct_min_gap']>=analytical_gap_bound(k)-1e-10
            elif k<=f+1:assert d['a']>=1
        # Heterogeneous, feasible diagonal variances: scale all covariance
        # blocks by the largest inverse constraint, then check every h-subset.
        rng=np.random.default_rng(103+k);a=rng.uniform(.05,2,k)
        e=robust_cycle_power(k,f) if k>=f+2 else []
        w=np.full(len(e),3.)
        c=certify(a,e,w,1,.5,min(f,k));scale=max(1,c['worst_rho_upper']/.5)*(1+1e-7)
        a*=scale;w*=scale
        assert certify(a,e,w,1,.5,min(f,k))['passed']
        if f<=k-1:  # Exact-f theorem has a nonempty honest subset.
            assert a.sum()>=k/h-1e-10
            for H in itertools.combinations(range(k),h):assert a[list(H)].sum()>=1-1e-10
        else:  # Software fallback, outside the lower-bound theorem's domain.
            assert not e and np.all(a>=1-1e-10)
        assert loss(np.zeros((2,k)),a,e,w)==0


@pytest.mark.parametrize('f',[0,1,2])
def test_cost_formula_optimizer_and_edge_deduplication(f):
    for k in range(f+2,11):
        e=robust_cycle_power(k,f);h=k-f;gap=analytical_gap_bound(k)
        for seed in range(4):
            W=np.random.default_rng(seed).normal(size=(4,k))
            if seed==0:W[:]=1
            if seed==1:W[:]=0
            S=np.sum(W*W);T=sum(np.sum((W[:,u]-W[:,v])**2) for u,v in e)
            opt=group_noise_optimizer(k,f,S,T,gamma_min=.02,safety_scale=1.)
            assert opt.edges in (0,len(e))
            for gamma in [.02,.3,float(h-1)]:
                d=uniform_group_noise(k,f,gamma,safety_scale=1.);b=T/gap
                formula=(S+(h-2)*b+(S-b)*gamma+(h-1)*b/gamma)/h
                direct=loss(W,np.full(k,d['a']),d['edges'],np.full(len(d['edges']),d['w']))
                assert math.isclose(direct,formula,rel_tol=1e-10,abs_tol=1e-9)
            result=minimize_scalar(lambda g: (1+g)/h*S+(1+g)/h*((h-1)/g-1)/gap*T,
                                   bounds=(.02,h-1),method='bounded')
            reference=min(float(result.fun),S,(1+.02)/h*S+(1+.02)/h*((h-1)/.02-1)/gap*T)
            assert abs(opt.error-reference)<1e-5*max(1,reference)
        assert group_noise_optimizer(k,f,3,0,edge_cost=1e9).branch=='independent'


def test_cache_dp_independent_bruteforce_partitions_and_complexity():
    for f in [0,1,2]:
        for n in range(2,9):
            W=np.random.default_rng(42+n).integers(-1,2,size=(3,n)).astype(float)
            W[:,::2]=W[:,0,None];order=list(reversed(range(n)))
            for penalty in [0,.2,1e4]:
                cache=interval_cost_cache(W,order,f=f,edge_cost=penalty)
                for s in range(n):
                    for t in range(s+1,n+1):
                        S,T=cache.statistics(s,t);members=order[s:t]
                        ee=robust_cycle_power(t-s,f)
                        assert abs(S-np.sum(W[:,members]**2))<1e-10
                        assert abs(T-sum(np.sum((W[:,members[u]]-W[:,members[v]])**2) for u,v in ee))<1e-10
                # Oracle uses independently constructed edges/statistics, not
                # cached interval costs or the DP recurrence.
                best=math.inf
                for bits in itertools.product([0,1],repeat=n-1):
                    boundaries=[0]+[j+1 for j,b in enumerate(bits) if b]+[n];total=0
                    for s,t in zip(boundaries,boundaries[1:]):
                        V=W[:,order[s:t]];ee=robust_cycle_power(t-s,f)
                        S=float(np.sum(V*V));T=float(sum(np.sum((V[:,u]-V[:,v])**2) for u,v in ee))
                        total+=group_noise_optimizer(t-s,f,S,T,edge_cost=penalty).cost
                    best=min(best,total)
                d=certified_partition_dp(W,order,f=f,edge_cost=penalty)
                assert math.isclose(d['objective'],best,rel_tol=1e-12,abs_tol=1e-9)
                assert d['operation_counters']['dp_transitions']==n*(n+1)//2
                assert d['memory_accounting']['dp_array_bytes']==16*(n+1)
    W=np.ones((2,20));d=certified_partition_dp(W,max_interval=4)
    assert all(len(b['members'])<=4 for b in d['blocks'])
    assert d['operation_counters']['dp_transitions']==sum(min(i,4) for i in range(1,21))
    limited=certified_partition_dp(np.ones((1,8)),allowed_edges=[])
    assert not limited['edges']


def test_bad_order_workload_shift_and_false_principal_certificate():
    W=np.array([[1,0,1,0,1,0,1,0],[0,1,0,1,0,1,0,1]],float)
    natural=certified_partition_dp(W)
    good=certified_partition_dp(W,[0,2,4,6,1,3,5,7])
    assert good['query_error']<natural['query_error']
    shifted=np.vstack([W,np.eye(8)])
    assert loss(shifted,good['a'],good['edges'],good['w'])>loss(shifted,np.ones(8),[],[])
    A,_=covariance([.1,.1],[(0,1)],[10.])
    assert 1/A[0,0]<1
    H,_=covariance([.1,.1],[(0,1)],[10.],(1,))
    assert np.linalg.inv(H)[0,0]==10


def test_high_precision_small_gamma_and_cancellation():
    with mp.workdps(90):
        for gamma in [1e-3,1e-8,1e-12]:
            d=uniform_group_noise(7,2,gamma)
            C=(1,4);H=[i for i in range(7) if i not in C];pos={v:j for j,v in enumerate(H)}
            A=mp.eye(len(H))*mp.mpf(d['a'])
            for u,v in d['edges']:
                if u in pos and v in pos:
                    i,j=pos[u],pos[v];w=mp.mpf(d['w']);A[i,i]+=w;A[j,j]+=w;A[i,j]-=w;A[j,i]-=w
            X=A**-1
            assert max(X[i,i] for i in range(len(H)))<=mp.mpf(1)
            W=mp.matrix([[1]*7]);allA=mp.eye(7)*mp.mpf(d['a'])
            for u,v in d['edges']:
                w=mp.mpf(d['w']);allA[u,u]+=w;allA[v,v]+=w;allA[u,v]-=w;allA[v,u]-=w
            assert abs((W*allA*W.T)[0]-7*mp.mpf(d['a']))<mp.mpf('1e-65')
        assert math.fsum([1e16,1.,-1e16])==1.
        naive=0.
        for x in [1e16,1.,-1e16]:naive+=x
        assert naive==0.


def test_routing_integration_exact_support_budget_and_freshness():
    W=np.array([[1,1,0,0,1,1],[1,1,1,1,1,1]],float)
    d=certified_partition_dp(W);groups=plan(W,noise_groups=[b['members'] for b in d['blocks']])['groups']
    for g in groups:
        assert np.all(W[:,g['members']]==W[:,g['members'][0],None])
    peers=[dict(id=i,a=float(d['a'][i]),rho_per_release=.5,
        neighbors={str(v if u==i else u):float(w) for (u,v),w in zip(d['edges'],d['w']) if i in (u,v)}) for i in range(6)]
    assert validate_peer_config(peers,d['blocks'])['passed']
    peers[0]['a']*=.1
    with pytest.raises(ValueError):validate_peer_config(peers,d['blocks'])
    tiny=uniform_group_noise(8,1,1e-12);tiny_blocks=[dict(members=list(range(8)),f=1,a=tiny['a'],w=tiny['w'])]
    pp=[dict(id=i,a=tiny['a'],rho_per_release=.5,neighbors={str(v if u==i else u):tiny['w'] for u,v in tiny['edges'] if i in (u,v)}) for i in range(8)]
    with pytest.raises(ValueError):validate_peer_config(pp,tiny_blocks)
    x=Peer.__new__(Peer);x.i=0;x.cfg=dict(s=.2,a=1.,rho_per_release=.5,rho_total=1.,neighbors={})
    x.lock=threading.RLock();x.state='IDLE';x.history=[];x.rho_spent=0.;x.metrics=blank();zs=[]
    for epoch in ['first','second']:
        x.dispatch(dict(op='prepare',epoch=epoch),'control');x.dispatch(dict(op='release'),'control');zs.append(x.z)
        x.dispatch(dict(op='abort'),'control')
    assert zs[0]!=zs[1] and x.rho_spent==1
    with pytest.raises(ValueError):x.dispatch(dict(op='prepare',epoch='first'),'control')
    x.dispatch(dict(op='prepare',epoch='third'),'control')
    with pytest.raises(ValueError,match='budget'):x.dispatch(dict(op='release'),'control')


def test_legacy_boundary_independent_fallback_has_margin_and_no_seed_edges():
    d=spectral_group(3,'cycle',f=1)
    assert not d['edges'] and len(d['w'])==0
    assert certify(d['a'],d['edges'],d['w'],1,.5,1)['passed']
