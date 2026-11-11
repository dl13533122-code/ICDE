"""Primary code components with explicit solver and threat-view adaptations."""
import ast, hashlib, pathlib
import numpy as np
import scipy.linalg as spl
import scipy.sparse as sps
import scipy.sparse.linalg as spsl
import cvxpy as cp
from src.noise import covariance,certify,families

def robust_fixed_blocks(W,kind='complete',rho=.5):
    """Matched f=1 pairwise fixed-support SDP on public signature blocks.

    This adaptation implements induced honest-view LMIs, not the original
    Whisper full-covariance/mixing privacy model or learning algorithm.
    """
    from src.noise import signature_groups,optimize_fixed,support
    from src.partition import robust_cycle_power
    import time
    t=time.perf_counter();W=np.asarray(W,float);n=W.shape[1];a=np.zeros(n);edges=[];weights=[];blocks=[];cache={}
    for group in signature_groups(W):
        V=W[:,group];k=len(group);e=support(k,'complete') if kind=='complete' else robust_cycle_power(k,1)
        key=(k,tuple((V.T@V).ravel()))
        if key not in cache:cache[key]=optimize_fixed(V,e,rho)
        d=cache[key];a[group]=d['a'];edges.extend((group[u],group[v]) for u,v in e);weights.extend(d['w'])
        blocks.append({'members':group,'certificate':d['certificate'],'solver_status':d['solver_status'],'scale':d['scale'],'solve_seconds':d['solve_seconds'],'optimality':d['optimality']})
    return dict(a=a,edges=edges,w=np.asarray(weights),blocks=blocks,
        certificate=dict(passed=all(b['certificate']['passed'] for b in blocks),f=1,worst_rho_upper=max(b['certificate']['worst_rho_upper'] for b in blocks),coverage='block diagonal support; exhaustive all local induced f=0/1 views'),
        planning_seconds=time.perf_counter()-t,label='robust fixed-support pairwise SDP adaptation; public signature blocks; no global optimality')

def load_functions(path,names,namespace):
    source=pathlib.Path(path).read_text();tree=ast.parse(source)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if len(nodes)!=len(names):raise ValueError('source function missing')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),path,'exec'),namespace)
    return {'path':path,'sha256':hashlib.sha256(source.encode()).hexdigest(),'functions':[dict(name=n.name,line=n.lineno) for n in nodes]}

def decor_original(a,w,n,edges,clip=.5):
    """Executes original exact inverse component; source imports are excluded."""
    namespace=dict(np=np,spl=spl,sps=sps,spsl=spsl)
    provenance=load_functions('literature/code/DECOR/utils/dp_account.py',['rdp_account'],namespace)
    adjacency=np.zeros((n,n))
    for u,v in edges:adjacency[u,v]=adjacency[v,u]=1
    val=namespace['rdp_account'](np.sqrt(a),np.sqrt(w),clip,np.diag(adjacency.sum(1)),adjacency,precision=0,sparse=True)
    return val,provenance

def whisper_original(W,privacy_bound,mode='mixing'):
    """Original constraints/objective, MOSEK replaced by open CLARABEL only.

    Its original f=0/general seed view is separate from this project's f=1
    pairwise-only hidden graph. It is not a deployment with identical trust.
    """
    ns=dict(np=np,cp=cp)
    provenance=load_functions('literature/code/WhisperDSGD/utils/graph.py',['get_laplacian'],ns)
    provenance2=load_functions('literature/code/WhisperDSGD/utils/dp_solver.py',['solve_mixing','solve_pairwise','solve_ldp','solve_cdp'],ns)
    def solve(objective,constraints):
        p=cp.Problem(objective,constraints);p.solve(solver='CLARABEL')
        if p.status not in ['optimal','optimal_inaccurate']:raise ValueError(p.status)
        return {v.name():v.value for v in p.variables()}
    ns['_solve_problem']=solve
    return ns['solve_'+mode](np.asarray(W),privacy_bound),[provenance,provenance2]

def robust_uniform(W,edges,rho=.5,delta=1.):
    """GOPA/DECOR uniform independent/pair variance class, fully f=1 adapted.

    Original formulas are not claimed for a changed view; all LMIs are rerun.
    """
    n=np.asarray(W).shape[1];a=cp.Variable(nonneg=True);w=cp.Variable(nonneg=True);constraints=[a>=1e-8]
    for C in families(n):
        L,H=covariance(np.zeros(n),edges,np.ones(len(edges)),C);A=a*np.eye(len(H))+w*L
        for j in range(len(H)):
            b=np.eye(len(H))[:,j:j+1];constraints.append(cp.bmat([[A,b],[b.T,np.array([[2*rho/delta**2]])]])>>0)
    fullL,H=covariance(np.zeros(n),edges,np.ones(len(edges)));obj=cp.Minimize(cp.trace(W@(a*np.eye(n)+w*fullL)@W.T));p=cp.Problem(obj,constraints);p.solve(solver='CLARABEL')
    if a.value is None:raise ValueError('uniform solver failed')
    aa=np.full(n,max(a.value,1e-8));ww=np.full(len(edges),max(w.value,0));c=certify(aa,edges,ww,delta,rho);scale=max(1,c['worst_rho_upper']/rho)*(1+1e-7);aa*=scale;ww*=scale;c=certify(aa,edges,ww,delta,rho)
    return dict(a=aa,edges=edges,w=ww,certificate=c,solver_status=p.status,scale=scale,label='uniform pairwise component robust f=1 adaptation, not full learning/GOPA malicious verification protocol')
