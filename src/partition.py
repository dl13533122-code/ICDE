"""Execution of WEB_THEORY_ADDENDUM_v2; fixed-epoch ideal Gaussian family.

Optimality is restricted to a fixed public order, interval groups and the
specified uniform cycle-power candidate/independent alternative. It does not
optimize physical congestion, all partitions or arbitrary covariance supports.
"""
import itertools
import math
import time
from dataclasses import asdict, dataclass

import numpy as np
from src.noise import covariance, loss


def robust_cycle_power(k, f):
    if not isinstance(k, int) or not isinstance(f, int) or k < 1 or f < 0:
        raise ValueError('integer k >= 1 and f >= 0 required')
    p = min(f + 1, k - 1)
    return sorted({tuple(sorted((i, (i + d) % k)))
                   for i in range(k) for d in range(1, p + 1)})


def analytical_gap_bound(k):
    if k < 2:
        raise ValueError('nontrivial gap needs at least two nodes')
    return min(2., 4 * math.sin(math.pi / k) ** 2)


def uniform_group_noise(k, f, gamma, rho=.5, delta=1., safety_scale=1+1e-7):
    """Prescribed finite public gamma, including mandatory no-peer branches."""
    if k < 1 or f < 0 or gamma <= 0 or not math.isfinite(gamma):
        raise ValueError('valid group and finite positive gamma required')
    if rho <= 0 or delta <= 0 or safety_scale < 1:
        raise ValueError('positive privacy parameters and conservative scale required')
    r=2*rho/delta**2;h=max(1,k-f)
    if k <= f+1 or gamma >= h-1:
        return dict(a=safety_scale/r,w=0.,edges=[],gamma=gamma)
    a=safety_scale*(1+gamma)/(r*h)
    w=a*((h-1)/gamma-1)/analytical_gap_bound(k)
    if not math.isfinite(w):raise ValueError('finite mask variance required')
    return dict(a=a,w=w,edges=robust_cycle_power(k,f),gamma=gamma)


def coalition_certificate(k, f, a, w, rho=.5, delta=1., exhaustive=False):
    """Analytic uniform construction certificate, optional independent inverses.

    Covers all removals of AT MOST f in this group, not sampled coalitions.
    Rounded arithmetic is engineering evidence, not an interval/DP proof.
    """
    if k < 1 or f < 0 or not all(math.isfinite(x) for x in (a, w, rho, delta)):
        raise ValueError('invalid certificate parameters')
    if a <= 0 or w < 0 or rho <= 0 or delta <= 0:
        raise ValueError('positive a, rho, Delta and nonnegative w required')
    h = max(1, k - f)
    if k <= f + 1 and w != 0:
        raise ValueError('small-group independent fallback is mandatory')
    gap = analytical_gap_bound(k) if k >= f + 2 else None
    ld = np.longdouble
    upper = (1 / ld(a) if w == 0 else
             1 / (ld(a) * h) + (1 - ld(1) / h) / (ld(a) + ld(w) * ld(gap)))
    rho_upper = float(np.nextafter(float(upper * ld(delta)**2 / 2), math.inf))
    result = dict(passed=rho_upper <= rho, worst_rho_upper=rho_upper,
                  rho_target=rho, f=f, h_min=h, lambda_star=gap,
                  lower_bound_domain=(0 <= f <= k-1),
                  nontrivial_hidden_peer_gain=(k >= f+2 and w > 0),
                  small_group_policy='k<=f+1: independent noise and no pair masks; exact-f lower bound only for 0<=f<=k-1',
                  coverage='analytic cycle-power spanning-cycle bound for every <=f removal; fixed-epoch ideal Gaussian only',
                  scenario_count=sum(math.comb(k, j) for j in range(min(f, k) + 1)),
                  numerical_assumption='longdouble bound with outward final rounding; not interval arithmetic')
    if exhaustive:
        edges = robust_cycle_power(k, f) if w else []
        worst = 0.; minimum_gap = math.inf; count = 0
        for j in range(min(f, k) + 1):
            for C in itertools.combinations(range(k), j):
                A, H = covariance(np.full(k, a), edges, np.full(len(edges), w), C)
                if not H:
                    continue
                inv = np.linalg.solve(A, np.eye(len(H)))
                worst = max(worst, float(np.max(np.diag(inv))) * delta**2 / 2)
                count += len(H)
                if len(H) >= 2 and w:
                    L, _ = covariance(np.zeros(k), edges, np.ones(len(edges)), C)
                    minimum_gap = min(minimum_gap, float(np.linalg.eigvalsh(L)[1]))
        result.update(direct_worst_rho=worst, direct_coordinate_checks=count,
                      direct_min_gap=None if minimum_gap == math.inf else minimum_gap)
        if worst > rho * (1 + 1e-8):
            raise ValueError('direct inverse contradicts analytic certificate')
    return result


@dataclass(frozen=True)
class GroupCost:
    k: int
    f: int
    S: float
    T: float
    gamma: float
    a: float
    w: float
    edges: int
    error: float
    setup_cost: float
    cost: float
    branch: str
    lambda_star: float | None


def group_noise_optimizer(k, f, S, T, rho=.5, delta=1., gamma_min=.05,
                          edge_cost=0., safety_scale=1 + 1e-7):
    """Closed-form B2-COST optimum plus the separately charged no-edge option.

    safety_scale uniformly increases BOTH variances; error is the actual used
    loss. This fixed public factor is included in the DP candidate objective.
    """
    if k < 1 or f < 0 or rho <= 0 or delta <= 0 or gamma_min <= 0:
        raise ValueError('invalid family')
    if not all(math.isfinite(x) for x in (S, T, rho, delta, gamma_min, edge_cost, safety_scale)):
        raise ValueError('finite public parameters required')
    if S < 0 or T < 0 or edge_cost < 0 or safety_scale < 1:
        raise ValueError('nonnegative costs and conservative scale required')
    r = 2 * rho / delta**2
    independent = GroupCost(k, f, S, T, float(max(0, k-f-1)), safety_scale/r,
                            0., 0, S*safety_scale/r, 0., S*safety_scale/r,
                            'independent', None)
    if k <= f + 1 or S == T == 0:
        return independent
    h = k - f; gap = analytical_gap_bound(k); b = T / gap
    if gamma_min > h - 1:
        raise ValueError('gamma_min must be <= h-1 on a nontrivial group')
    if b == 0:
        gamma = gamma_min
    elif S > b:
        gamma = float(np.clip(math.sqrt((h-1)*b/(S-b)), gamma_min, h-1))
    else:
        gamma = float(h-1)
    if gamma == h-1:
        return independent
    a = safety_scale*(1+gamma)/(r*h)
    # Algebraic form avoids subtracting two nearly equal privacy bounds.
    w = a*((h-1)/gamma-1)/gap
    count = k*min(f+1, (k-1)//2) if k > 2*(f+1)+1 else k*(k-1)//2
    error = a*S+w*T
    correlated = GroupCost(k, f, S, T, gamma, a, w, count, error,
                           edge_cost*count, error+edge_cost*count,
                           'cycle-power', gap)
    return correlated if correlated.cost < independent.cost else independent


class interval_cost_cache:
    """Half-open intervals in ONE public permutation; no protected input.

    Distance access uses differences, never a cancellation-prone Gram identity.
    Prefix preprocessing O(q*n*p); candidate arithmetic O(n^2*p^2).
    On-demand distance work is counted separately (O(q) per cache miss), with
    worst-case O(n^2) distance storage. Group edges are built only after DP.
    """
    def __init__(self, W, order=None, f=1, rho=.5, delta=1., gamma_min=.05,
                 edge_cost=0., safety_scale=1+1e-7, allowed_edges=None):
        self.W = np.asarray(W, dtype=float)
        if self.W.ndim != 2 or self.W.shape[1] < 1 or not np.isfinite(self.W).all():
            raise ValueError('finite public workload required')
        self.n = self.W.shape[1]; self.q = self.W.shape[0]
        self.order = list(range(self.n)) if order is None else list(order)
        if sorted(self.order) != list(range(self.n)) or f < 0:
            raise ValueError('public permutation and nonnegative f required')
        self.f=f; self.p=f+1; self.params=dict(rho=rho, delta=delta,
            gamma_min=gamma_min, edge_cost=edge_cost, safety_scale=safety_scale)
        self.allowed_edges = None if allowed_edges is None else {tuple(sorted(e)) for e in allowed_edges}
        self.columns=self.W[:, self.order].astype(np.longdouble)
        self.Sprefix=np.r_[np.longdouble(0), np.cumsum(np.sum(self.columns**2,axis=0),dtype=np.longdouble)]
        self.distances={}; self.cache={}; self.prefix={}
        self.counters=dict(distance_evaluations=0, distance_scalar_components=0,
            interval_evaluations=0, interior_lookups=0, wrap_pairs=0,
            small_pairs=0, allowed_link_edge_checks=0, dp_transitions=0)
        for d in range(1, min(self.p, self.n-1)+1):
            vals=[self.distance(i,i+d) for i in range(self.n-d)]
            self.prefix[d]=np.r_[np.longdouble(0),np.cumsum(vals,dtype=np.longdouble)]

    def distance(self, i, j):
        key=tuple(sorted((i,j)))
        if key not in self.distances:
            v=self.columns[:,i]-self.columns[:,j]
            value=np.sum(v*v,dtype=np.longdouble)
            if value < 0 or not np.isfinite(value):
                raise ValueError('invalid squared distance')
            self.distances[key]=value
            self.counters['distance_evaluations']+=1
            self.counters['distance_scalar_components']+=self.q
        return self.distances[key]

    def statistics(self, s, t):
        if not 0 <= s < t <= self.n:
            raise ValueError('invalid half-open interval')
        k=t-s; S=self.Sprefix[t]-self.Sprefix[s]; T=np.longdouble(0)
        if k <= 2*self.p+1:
            for u,v in robust_cycle_power(k,self.f):
                T+=self.distance(s+u,s+v); self.counters['small_pairs']+=1
        else:
            for d in range(1,self.p+1):
                T+=self.prefix[d][t-d]-self.prefix[d][s]
                self.counters['interior_lookups']+=1
                for j in range(d):
                    T+=self.distance(s+j,t-d+j); self.counters['wrap_pairs']+=1
        # Extended prefix subtraction can still lose tiny positive values.
        # Recompute suspicious S directly and include that cost in counters.
        if S < 0 or (self.Sprefix[t]>0 and S <= 64*np.finfo(np.longdouble).eps*abs(self.Sprefix[t])):
            S=np.sum(self.columns[:,s:t]**2,dtype=np.longdouble)
            self.counters.setdefault('S_recomputed_components',0)
            self.counters['S_recomputed_components']+=self.q*k
        if T < 0:
            raise ValueError('negative prefix distance sum; direct check required')
        return float(S),float(T)

    def get(self,s,t):
        if (s,t) not in self.cache:
            S,T=self.statistics(s,t);k=t-s
            candidate=group_noise_optimizer(k,self.f,S,T,**self.params)
            if candidate.w and self.allowed_edges is not None:
                es=robust_cycle_power(k,self.f)
                self.counters['allowed_link_edge_checks']+=len(es)
                if any(tuple(sorted((self.order[s+u],self.order[s+v]))) not in self.allowed_edges for u,v in es):
                    candidate=group_noise_optimizer(k,self.f,S,T,**dict(self.params,edge_cost=1e300))
            self.cache[s,t]=candidate;self.counters['interval_evaluations']+=1
        return self.cache[s,t]


def certified_partition_dp(W, order=None, max_interval=None, **kwargs):
    t0=time.perf_counter();cache=interval_cost_cache(W,order,**kwargs);n=cache.n
    L=n if max_interval is None else int(max_interval)
    if L<1:
        raise ValueError('positive maximum interval length required')
    F=np.full(n+1,np.inf);F[0]=0.;prev=np.full(n+1,-1,dtype=int)
    for t in range(1,n+1):
        for s in range(max(0,t-L),t):
            g=cache.get(s,t);v=F[s]+g.cost;cache.counters['dp_transitions']+=1
            # First predecessor in ascending order wins EXACT floating ties.
            if v < F[t]:F[t]=v;prev[t]=s
    intervals=[];t=n
    while t:
        s=int(prev[t]);intervals.append((s,t));t=s
    intervals.reverse();a=np.zeros(n);edges=[];weights=[];blocks=[]
    for s,t in intervals:
        g=cache.get(s,t);members=cache.order[s:t];a[members]=g.a
        local=robust_cycle_power(g.k,g.f) if g.w else []
        edges.extend(tuple(sorted((members[u],members[v]))) for u,v in local)
        weights.extend([g.w]*len(local))
        cert=coalition_certificate(g.k,g.f,g.a,g.w,kwargs.get('rho',.5),kwargs.get('delta',1.))
        if not cert['passed']:raise ValueError('constructed group fails certificate')
        blocks.append(dict(members=members,interval=[s,t],**asdict(g),certificate=cert))
    actual=loss(cache.W,a,edges,weights)
    if not math.isclose(actual,sum(b['error'] for b in blocks),rel_tol=1e-10,abs_tol=1e-9):
        raise ValueError('cached interval objective disagrees with assembled design')
    return dict(a=a,edges=edges,w=np.asarray(weights),blocks=blocks,
        objective=float(F[n]),query_error=actual,public_order=cache.order,
        max_interval=max_interval,planning_seconds=time.perf_counter()-t0,
        family='fixed public ordered interval family; uniform cycle-power/independent candidates; declared gamma_min and additive edge cost',
        optimality_scope='numerical DP optimum for declared candidate costs; not all partitions/orders/supports/covariances or physical max-node congestion',
        certificate=dict(passed=True,f=cache.f,worst_rho_upper=max(b['certificate']['worst_rho_upper'] for b in blocks),
            coverage='independent blocks; every global <=f coalition restricts to <=f deletions in each block; fixed-epoch ideal Gaussian only'),
        operation_counters=cache.counters,
        memory_accounting=dict(dp_array_bytes=F.nbytes+prev.nbytes,
            prefix_bytes=cache.Sprefix.nbytes+sum(x.nbytes for x in cache.prefix.values()),
            ordered_column_bytes=cache.columns.nbytes,distance_entries=len(cache.distances),
            candidate_entries=len(cache.cache),python_object_overhead='dict/dataclass overhead additional; runner records peak RSS'),
        parameters=cache.params)
