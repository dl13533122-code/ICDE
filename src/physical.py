"""B6 finite public physical-plan family; exact configured rational scores.

Caps concern fixed peer application frames (TX+RX endpoints), not TLS/TCP.
Candidate gamma/variances are finite binary floats; their exact configured
rationals, rather than ideal algebraic optima, define the error objective.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import itertools, time
import numpy as np
from src.partition import (interval_cost_cache, group_noise_optimizer,
                           robust_cycle_power, coalition_certificate)

FRAME_BYTES = {'mask': (512, 128), 'report': (128, 1024), 'partial': (128, 1024)}

@dataclass(frozen=True)
class Candidate:
    start: int
    end: int
    key: str
    error: F
    loads: tuple
    payload: object = None

@dataclass(frozen=True)
class Label:
    error: F
    loads: tuple
    previous: object = None
    candidate: object = None

def dominates(a,b):
    av=(a.error,*a.loads);bv=(b.error,*b.loads)
    return all(x<=y for x,y in zip(av,bv)) and any(x<y for x,y in zip(av,bv))

def frontier(labels):
    if labels and len(labels[0].loads)==2:
        # Sweep objective, Fenwick prefix minimum for the two load coordinates.
        # O(m log m) exact comparisons for H=2; generic H remains quadratic.
        ordered=sorted(labels,key=lambda a:(a.error,a.loads))
        xs=sorted({a.loads[0] for a in ordered});pos={x:i+1 for i,x in enumerate(xs)}
        tree=[None]*(len(xs)+1);kept=[]
        for a in ordered:
            i=pos[a.loads[0]];j=i;minimum=None
            while j:
                if tree[j] is not None:minimum=tree[j] if minimum is None else min(minimum,tree[j])
                j-=j&-j
            if minimum is not None and minimum<=a.loads[1]:continue
            kept.append(a)
            while i<len(tree):
                tree[i]=a.loads[1] if tree[i] is None else min(tree[i],a.loads[1]);i+=i&-i
        return kept
    # Equal scores retain the first deterministic predecessor; equality is
    # not strict dominance, but both have identical possible continuations.
    kept=[]; equal=set()
    for a in labels:
        score=(a.error,a.loads)
        if score in equal or any(dominates(b,a) for b in kept):continue
        kept=[b for b in kept if not dominates(a,b)]
        kept.append(a);equal.add(score)
    return kept

def round_loads(loads,grid):
    if len(loads)!=len(grid) or any(F(d)<=0 for d in grid):raise ValueError('positive grid per resource required')
    return tuple(-(-F(l)//F(d))*F(d) for l,d in zip(loads,grid))

def normalized_frontier(labels,normalizers,l0=None):
    """Exact error/max-normalized-load projection of terminal resource labels."""
    norm=tuple(map(F,normalizers));base=(F(0),)*len(norm) if l0 is None else tuple(map(F,l0))
    if any(x<=0 for x in norm) or len(base)!=len(norm):raise ValueError('positive resource normalizers required')
    projected=[]
    for label in labels:
        if len(label.loads)!=len(norm):raise ValueError('resource dimension mismatch')
        score=max((l+b)/d for l,b,d in zip(label.loads,base,norm))
        projected.append((label.error,score,label))
    # Ascending error, then load; equal points have identical projected utility.
    best=None;kept=[]
    for e,l,label in sorted(projected,key=lambda x:(x[0],x[1])):
        if best is None or l<best:kept.append((e,l,label));best=l
    return kept

def resource_partition(n,candidates,caps=None,l0=None,grid=None):
    """Exact label propagation; exhaustive Pareto pruning (no beam limit)."""
    t0=time.perf_counter();by_end={t:[] for t in range(1,n+1)}
    candidates=list(candidates)
    if not candidates:raise ValueError('candidate family required')
    H=len(candidates[0].loads);zero=(F(0),)*H
    caps=None if caps is None else tuple(map(F,caps));l0=zero if l0 is None else tuple(map(F,l0))
    if len(l0)!=H or (caps is not None and len(caps)!=H):raise ValueError('resource dimension mismatch')
    grid=None if grid is None else tuple(map(F,grid))
    for c in candidates:
        if not 0<=c.start<c.end<=n or len(c.loads)!=H or c.error<0 or any(l<0 for l in c.loads):raise ValueError('invalid nonnegative interval cost')
        by_end[c.end].append(c)
    labels=[[Label(F(0),zero)]]+[[] for _ in range(n)];extensions=0;max_labels=1
    for t in range(1,n+1):
        new=[]
        for c in by_end[t]:
            cl=tuple(map(F,c.loads)) if grid is None else round_loads(c.loads,grid)
            for prev in labels[c.start]:
                extensions+=1;loads=tuple(a+b for a,b in zip(prev.loads,cl))
                if caps is not None and any(a+b>cap for a,b,cap in zip(loads,l0,caps)):continue
                new.append(Label(prev.error+F(c.error),loads,prev,c))
        labels[t]=frontier(new);max_labels=max(max_labels,len(labels[t]))
    end=labels[n];best=min(end,key=lambda l:(l.error,l.loads)) if end else None
    selected=[];p=best
    while p and p.candidate:selected.append(p.candidate);p=p.previous
    selected.reverse()
    original=tuple(sum((F(c.loads[h]) for c in selected),F(0)) for h in range(H))
    if best and caps is not None:assert all(a+b<=cap for a,b,cap in zip(original,l0,caps))
    return dict(feasible=best is not None,selected=selected,error=best.error if best else None,
                loads=original,rounded_loads=best.loads if best else None,frontier=end,
                planning_seconds=time.perf_counter()-t0,extensions=extensions,
                labels_per_prefix=list(map(len,labels)),max_labels=max_labels,H=H,
                comparison='exact rational configured errors/loads; no ambiguous float score comparisons',
                scope='finite fixed public order/interval/variance/routing family')

def error_exact(W,members,a,edges,w):
    cols=[[F(float(x)) for x in np.asarray(W)[:,i]] for i in members]
    S=sum((x*x for col in cols for x in col),F(0))
    T=sum((sum(((x-y)**2 for x,y in zip(cols[u],cols[v])),F(0)) for u,v in edges),F(0))
    return F(float(a))*S+F(float(w))*T

def public_plan(W,members,host_map,leader_host,edges):
    """Every signature piece has its own frame/cache; no cross-group reuse.

    All routes use the observed fu/fy1 loopback/SSH overlay, including same-host
    loopback RPCs. These are overlay endpoint costs, not invented direct links.
    """
    pieces={}
    for i in members:pieces.setdefault(tuple(np.asarray(W)[:,i]),[]).append(i)
    groups=[];calls=[]
    for j,g in enumerate(pieces.values()):
        possible=[i for i in g if host_map[i]==leader_host]
        leader=min(possible or g)
        groups.append(dict(members=g,leader=leader))
        calls.extend((leader,i,'report') for i in g if i!=leader)
        owners=sorted({qi%len(host_map) for qi,row in enumerate(W) if row[g[0]]!=0})
        calls.extend((owner,leader,'partial') for owner in owners if owner!=leader)
    calls.extend((members[u],members[v],'mask') if members[u]<members[v] else (members[v],members[u],'mask') for u,v in edges)
    hosts=sorted(set(host_map));node=[0]*len(host_map);tx=[0]*len(host_map);rx=[0]*len(host_map)
    for u,v,op in calls:
        req,resp=FRAME_BYTES[op];tx[u]+=req;rx[v]+=req;tx[v]+=resp;rx[u]+=resp
        node[u]+=req+resp;node[v]+=req+resp
    return dict(groups=groups,calls=calls,loads=tuple(sum(node[i] for i,h in enumerate(host_map) if h==host) for host in hosts),
                per_node=node,tx=tx,rx=rx,leader_host=leader_host,hosts=hosts)

def candidate_family(W,host_map,order=None,f=1,rho=.5,delta=1.,gamma_min=.05,max_interval=None,allowed_host_links=None):
    W=np.asarray(W);n=W.shape[1];order=list(range(n)) if order is None else list(order)
    hosts=sorted(set(host_map));links={tuple(sorted(e)) for e in (allowed_host_links or [])}
    if len(host_map)!=n:raise ValueError('public roster/placement mismatch')
    def available(u,v):return host_map[u]==host_map[v] or tuple(sorted((host_map[u],host_map[v]))) in links
    cache=interval_cost_cache(W,order,f=f,rho=rho,delta=delta,gamma_min=gamma_min)
    result=[]
    for t in range(1,n+1):
        for s in range(max(0,t-(max_interval or n)),t):
            members=order[s:t];k=t-s;S,T=cache.statistics(s,t)
            independent=group_noise_optimizer(k,f,float(S),float(T),rho,delta,gamma_min,edge_cost=1e300)
            correlated=group_noise_optimizer(k,f,float(S),float(T),rho,delta,gamma_min,edge_cost=0.)
            variants=[independent]+([correlated] if correlated.w else [])
            for noise in variants:
                edges=robust_cycle_power(k,f) if noise.w else []
                if not all(available(members[u],members[v]) for u,v in edges):continue
                certificate=coalition_certificate(k,f,noise.a,noise.w,rho,delta)
                if not certificate['passed']:raise ValueError('uncertified candidate')
                for h in hosts:
                    plan=public_plan(W,members,host_map,h,edges)
                    if not all(available(u,v) for u,v,_ in plan['calls']):continue
                    result.append(Candidate(s,t,f'{s}:{t}:{noise.branch}:{h}',error_exact(W,members,noise.a,edges,noise.w),plan['loads'],
                                            dict(members=members,noise=noise,plan=plan,certificate=certificate)))
    return result

def assemble(selected,n):
    a=np.zeros(n);edges=[];w=[];groups=[];blocks=[]
    for c in selected:
        p=c.payload;members=p['members'];noise=p['noise'];a[members]=noise.a
        ee=[tuple(sorted((members[u],members[v]))) for u,v in (robust_cycle_power(len(members),noise.f) if noise.w else [])]
        edges.extend(ee);w.extend([noise.w]*len(ee))
        for g in p['plan']['groups']:groups.append(dict(id=len(groups),**g))
        blocks.append(dict(members=members,a=noise.a,w=noise.w,f=noise.f,certificate=p['certificate']))
    return dict(a=a,edges=edges,w=np.array(w),groups=groups,blocks=blocks)
