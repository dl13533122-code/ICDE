"""Gaussian fixed-view foundations and conservative numerical diagnostics.

This module does not prove protocol privacy or a sparse approximation guarantee.
"""
import itertools, math, time
import numpy as np
import scipy.linalg as la

def families(n, f=1):
    if f not in (0,1,2): raise ValueError('only exhaustive f=0/1/2 numerical diagnostics enabled')
    return [C for j in range(min(n,f)+1) for C in itertools.combinations(range(n),j)]

def covariance(a, edges, weights, coalition=()):
    a=np.asarray(a,dtype=float);h=[i for i in range(len(a)) if i not in coalition];pos={v:i for i,v in enumerate(h)}
    A=np.diag(a[h])
    for (u,v),w in zip(edges,weights):
        if u in pos and v in pos:
            x,y=pos[u],pos[v];A[x,x]+=w;A[y,y]+=w;A[x,y]-=w;A[y,x]-=w
    return A,h

def verified_inverse(A):
    """Residual correction bound, conditional on float64 norm/eigenvalue accuracy.

    lambda_min >= min(a) is used by certificates instead of rounded eigenvalues.
    This is conservative engineering verification, not interval arithmetic proof.
    """
    X=la.cho_solve(la.cho_factor(A,check_finite=True),np.eye(len(A)))
    residual=la.norm(np.eye(len(A))-A@X,2)
    return X,residual

def certify(a, edges, weights, delta, rho, f=1):
    a=np.asarray(a,float);w=np.asarray(weights,float);d=np.broadcast_to(np.asarray(delta,float),a.shape)
    if np.any(a<=0) or np.any(w<0) or not np.isfinite(a).all() or not np.isfinite(w).all():raise ValueError('invalid noise parameters')
    worst=0.;worst_at=None;scenarios=[];maxres=0.
    for C in families(len(a),f):
        A,H=covariance(a,edges,w,C)
        if not H:
            scenarios.append({'coalition':list(C),'honest_nodes':[],'rho_upper':[],'residual_2':0.,'inverse_diagonal_inflation':0.})
            continue
        X,res=verified_inverse(A)
        # ||A^-1-X|| <= ||I-AX|| / lambda_min(A), and lambda_min(A)>=min(a_H).
        inflation=(res+64*np.finfo(float).eps*len(H)*max(1.,la.norm(A,2)*la.norm(X,2)))/min(a[H])
        upper=np.diag(X)+inflation
        r=d[H]**2/2*upper;j=int(np.argmax(r));maxres=max(maxres,res)
        if r[j]>worst:worst=float(r[j]);worst_at={'coalition':list(C),'honest_node':H[j]}
        scenarios.append({'coalition':list(C),'honest_nodes':H,'rho_upper':r.tolist(),'residual_2':float(res),'inverse_diagonal_inflation':float(inflation)})
    return {'passed':worst<=rho,'worst_rho_upper':worst,'rho_target':rho,'worst_at':worst_at,'f':f,'scenario_count':len(scenarios),'constraint_count':sum(len(x['honest_nodes']) for x in scenarios),'max_residual':float(maxres),'scenarios':scenarios,'numerical_assumption':'float64 norm/residual rounding guarded; not interval-certified'}

def loss(W,a,edges,weights):
    W=np.asarray(W,float);v=np.sum(W*W,axis=0)@a
    for (u,t),w in zip(edges,weights):v+=w*np.sum((W[:,u]-W[:,t])**2)
    return float(v)

def epsilon(rho,delta):
    if rho<0 or not 0<delta<1:raise ValueError('invalid accountant inputs')
    return rho+2*math.sqrt(rho*math.log(1/delta))

def rho_for_epsilon(eps,delta):
    if eps<=0 or not 0<delta<1:raise ValueError('invalid accountant inputs')
    L=math.log(1/delta);return (eps/(math.sqrt(L+eps)+math.sqrt(L)))**2

def diagonal_downdate(A,u,v,w):
    X,res=verified_inverse(A);b=np.zeros(len(A));b[u]=1;b[v]=-1;y=X@b;den=1-w*b@y
    if den<=1e-10:raise ValueError('unstable downdate rejected')
    updated=X+w*np.outer(y,y)/den
    fresh,rr=verified_inverse(A-w*np.outer(b,b))
    if not np.allclose(updated,fresh,rtol=1e-8,atol=1e-9):raise ValueError('downdate disagrees with fresh factorization')
    return updated,den, -y*y

def support(n,kind,seed=20261005):
    if kind=='complete':return list(itertools.combinations(range(n),2))
    if kind=='cycle':return sorted({tuple(sorted((i,(i+1)%n))) for i in range(n)}- {(0,0)}) if n>1 else []
    if kind=='regular':return sorted({tuple(sorted((i,(i+j)%n))) for i in range(n) for j in (1,2)}-{(i,i) for i in range(n)})
    if kind=='random':
        rng=np.random.default_rng(seed);edges=set(support(n,'cycle'))
        for i in range(n):
            for j in rng.choice(n,min(3,n),replace=False):
                if i!=j:edges.add(tuple(sorted((i,int(j)))))
        return sorted(edges)
    raise ValueError(kind)

def signature_groups(W):
    groups={}
    for i,col in enumerate(np.asarray(W).T):groups.setdefault(tuple(col),[]).append(i)
    return list(groups.values())

def spectral_group(k,kind,rho=0.5,delta=1.,f=1):
    edges=support(k,kind);hmin=k-f;r=2*rho/delta**2
    if hmin<=1:return {'a':np.full(k,(1+1e-8)/r),'edges':[],'w':np.array([]),'lambda_star':None,'bound':1/((1+1e-8)/r)}
    gaps=[]
    for C in families(k,f):
        L,H=covariance(np.zeros(k),edges,np.ones(len(edges)),C);g=la.eigvalsh(L)[1];gaps.append(float(g))
    gap=min(gaps)
    if gap<=1e-10:raise ValueError('allowed deletion disconnects graph')
    a=2/(r*hmin);target=r-1/(a*hmin)
    w=max(0,((1-1/hmin)/target-a)/gap)*(1+1e-7)
    if w==0:
        # Boundary gamma=h_min-1 is independent noise. Keep a finite
        # numerical margin and remove zero-weight secret exchanges.
        a=(1+1e-7)/r;edges=[]
    bound=1/(a*hmin)+(1-1/hmin)/(a+w*gap)
    return {'a':np.full(k,a),'edges':edges,'w':np.full(len(edges),w),'lambda_star':gap,'bound':bound,'gaps':gaps}

def transfer_check(a,e,w,aa,ee,ww,alpha,f=1):
    if not 0<alpha<1:raise ValueError('alpha must lie in (0,1)')
    vals=[]
    for C in families(len(a),f):
        A,_=covariance(a,e,w,C);B,_=covariance(aa,ee,ww,C);v=la.eigvalsh(B,A);vals.append({'C':list(C),'min':float(v[0]),'max':float(v[-1])})
    return {'passed':all(x['min']>=1-alpha-1e-10 and x['max']<=1+alpha+1e-10 for x in vals),'scenarios':vals}

def optimize_fixed(W,edges,rho,delta=1.,f=1,setup_penalty=0.,max_iter=150):
    """Convex finite fixed-support optimization with every honest-view LMI.

    Solver output is independently recertified and conservatively rescaled.
    No dual/interval optimality certificate is implied by status 'optimal'.
    """
    import cvxpy as cp
    W=np.asarray(W,float);n=W.shape[1];a=cp.Variable(n);w=cp.Variable(len(edges)) if edges else None
    d=np.broadcast_to(delta,(n,));constraints=[a>=1e-8]
    if w is not None:constraints+=[w>=0]
    for C in families(n,f):
        H=[i for i in range(n) if i not in C];m=len(H);pos={v:j for j,v in enumerate(H)};A=cp.diag(a[H])
        for j,(u,v) in enumerate(edges):
            if u in pos and v in pos:
                b=np.zeros(m);b[pos[u]]=1;b[pos[v]]=-1;A=A+w[j]*np.outer(b,b)
        for j,i in enumerate(H):
            b=np.eye(m)[:,j:j+1];constraints+=[cp.bmat([[A,b],[b.T,np.array([[2*rho/d[i]**2]])]])>>0]
    obj=cp.sum(cp.multiply(np.sum(W*W,axis=0),a))
    if edges:obj+=cp.sum(cp.multiply([np.sum((W[:,u]-W[:,v])**2) for u,v in edges],w))
    prob=cp.Problem(cp.Minimize(obj),constraints);t=time.perf_counter();prob.solve(solver='CLARABEL',max_iter=max_iter)
    if a.value is None:raise ValueError('no solver incumbent: '+str(prob.status))
    aa=np.maximum(a.value,1e-8);ww=np.maximum(w.value,0) if edges else np.array([]);cert=certify(aa,edges,ww,delta,rho,f)
    scale=max(1.,cert['worst_rho_upper']/rho)*(1+1e-7);aa*=scale;ww*=scale;cert=certify(aa,edges,ww,delta,rho,f)
    if not cert['passed']:raise ValueError('solver incumbent fails privacy verification')
    return {'a':aa,'edges':list(edges),'w':ww,'certificate':cert,'objective':loss(W,aa,edges,ww)+setup_penalty*len(edges),'scale':scale,'solver_status':prob.status,'solver_primal':float(prob.value),'solve_seconds':time.perf_counter()-t,'optimality':'numerical primal; certified feasible, exact global gap unresolved'}

def sparse_candidate(W,rho=0.5,delta=1.,degree=2,setup_penalty=0.01):
    """Public finite candidates with feasible incumbent and exact rechecks."""
    W=np.asarray(W,float);n=W.shape[1];groups=signature_groups(W);edges=set()
    for g in groups:
        for u,v in support(len(g),'cycle'):edges.add(tuple(sorted((g[u],g[v]))))
    for i in range(n):
        order=np.argsort(np.sum((W.T-W[:,i])**2,axis=1),kind='stable')
        for j in order[order!=i][:degree]:edges.add(tuple(sorted((i,int(j)))))
    incumbent=optimize_fixed(W,[],rho,delta,setup_penalty=setup_penalty);history=[]
    for e in [sorted(edges),support(n,'complete')]:
        candidate=optimize_fixed(W,e,rho,delta,setup_penalty=setup_penalty);history.append({'edges':len(e),'objective':candidate['objective']})
        if candidate['objective']<incumbent['objective']:incumbent=candidate
    # Rank deletions by exact scenario Sherman-Morrison/privacy rescale then fresh refactor.
    for _ in range(min(5,len(incumbent['edges']))):
        ranked=[]
        for j,(u,v) in enumerate(incumbent['edges']):
            risk=0.
            for C in families(n,1):
                if u in C or v in C:continue
                A,H=covariance(incumbent['a'],incumbent['edges'],incumbent['w'],C)
                try:X,den,der=diagonal_downdate(A,H.index(u),H.index(v),incumbent['w'][j])
                except ValueError:risk=math.inf;break
                risk=max(risk,float(np.max(np.diag(X)))*delta**2/(2*rho))
            ranked.append((risk,j))
        improved=False
        for risk,j in sorted(ranked)[:3]:
            if not math.isfinite(risk):continue
            e=incumbent['edges'][:j]+incumbent['edges'][j+1:]
            trial=optimize_fixed(W,e,rho,delta,setup_penalty=setup_penalty)
            if trial['objective']<incumbent['objective']-1e-6:
                incumbent=trial;history.append({'operation':'delete','objective':trial['objective'],'edges':len(e)});improved=True;break
        if not improved:break
    incumbent['history']=history;incumbent['algorithm_guarantee']='none; finite verified candidate pipeline';return incumbent

def sample_reports(a,edges,w,s,rounds=10000,seed=20261005):
    rng=np.random.default_rng(seed);z=rng.normal(size=(rounds,len(a)))*np.sqrt(a)+s
    for (u,v),x in zip(edges,w):
        r=rng.normal(size=rounds)*np.sqrt(x);z[:,u]+=r;z[:,v]-=r
    return z
