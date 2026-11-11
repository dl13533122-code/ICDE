"""Exact rational primal/dual bounds for every n=3 fixed pair-mask support.

Finite diagnostic for the specified induced-view Gaussian SDP. This does not
prove transcript privacy, a sparse approximation ratio or global optimality
over other mechanisms. The optimum may be an unattained infimum.
"""
import datetime,hashlib,itertools,json,pathlib,platform,sys,time
from fractions import Fraction as F
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import cvxpy as cp
import numpy as np
from src.noise import families,support

def matmul(A,B):
    return [[sum((x*y for x,y in zip(row,col)),F(0)) for col in zip(*B)] for row in A]
def transpose(A):return list(map(list,zip(*A)))
def determinant(A):
    A=[r[:] for r in A];ans=F(1)
    for j in range(len(A)):
        pivot=next((i for i in range(j,len(A)) if A[i][j]),None)
        if pivot is None:return F(0)
        if pivot!=j:A[j],A[pivot]=A[pivot],A[j];ans=-ans
        x=A[j][j];ans*=x
        for i in range(j+1,len(A)):
            factor=A[i][j]/x
            for k in range(j+1,len(A)):A[i][k]-=factor*A[j][k]
    return ans
def rational(x):return F(round(float(x)*10**8),10**8)
def serial(x):
    if isinstance(x,F):return [x.numerator,x.denominator]
    if isinstance(x,dict):return {k:serial(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [serial(v) for v in x]
    return x

def solve(W,edges):
    n=3;a=cp.Variable(n);w=cp.Variable(len(edges)) if edges else None
    ca=[F(int(x)) for x in np.sum(W*W,axis=0)]
    cw=[F(int(np.sum((W[:,u]-W[:,v])**2))) for u,v in edges]
    constraints=[a>=1e-10]+([w>=0] if edges else []);views=[]
    for C in families(n,1):
        H=[i for i in range(n) if i not in C];m=len(H);pos={v:j for j,v in enumerate(H)}
        A=cp.diag(a[H]);incidence=[]
        for u,v in edges:
            b=np.zeros(m)
            if u in pos and v in pos:b[pos[u]]=1;b[pos[v]]=-1
            incidence.append(b)
        for j,b in enumerate(incidence):A+=w[j]*np.outer(b,b)
        for j,i in enumerate(H):
            unit=np.eye(m)[:,j:j+1]
            constraint=cp.bmat([[A,unit],[unit.T,np.array([[1.]])]])>>0
            constraints.append(constraint);views.append((C,H,i,incidence,constraint))
    objective=cp.sum(cp.multiply([float(x) for x in ca],a))
    if edges:objective+=cp.sum(cp.multiply([float(x) for x in cw],w))
    problem=cp.Problem(cp.Minimize(objective),constraints)
    problem.solve(solver='CLARABEL',tol_gap_abs=1e-9,tol_gap_rel=1e-9,tol_feas=1e-9,max_iter=200)
    if a.value is None:raise RuntimeError(problem.status)
    # A rational factor Q gives an exactly PSD Q Q^T. Project factors onto
    # exact component-constant subspaces for zero-cost edges, so their dual
    # gradients are identically zero rather than approximately zero.
    records=[];ga=[F(0)]*n;gw=[F(0)]*len(edges);constant=F(0)
    for C,H,i,incidence,constraint in views:
        Z=np.asarray(constraint.dual_value);ev,U=np.linalg.eigh((Z+Z.T)/2)
        Q=U*np.sqrt(np.maximum(ev,0));m=len(H)
        Q=[[rational(v) for v in row] for row in Q]
        components=[{j} for j in range(m)]
        for cost,b in zip(cw,incidence):
            indices=set(np.flatnonzero(b).tolist())
            if cost or not indices:continue
            selected=[s for s in components if s&indices]
            union=set().union(*selected);components=[s for s in components if not s&indices]+[union]
        for component in components:
            means=[sum((Q[j][k] for j in component),F(0))/len(component) for k in range(m+1)]
            for j in component:Q[j]=means[:]
        Z=matmul(Q,transpose(Q))
        for j,node in enumerate(H):ga[node]+=Z[j][j]
        for e,b in enumerate(incidence):
            gw[e]+=sum((F(int(b[u]*b[v]))*Z[u][v] for u in range(m) for v in range(m)),F(0))
        constant-=2*Z[H.index(i)][m]+Z[m][m]
        records.append(dict(coalition=list(C),honest=H,target=i,factor_Q=Q))
    scale=min([F(1),*[c/g for c,g in zip(ca,ga) if g],*[c/g for c,g in zip(cw,gw) if g]])
    assert scale>0 and all(c-scale*g>=0 for c,g in zip(ca,ga)) and all(c-scale*g>=0 for c,g in zip(cw,gw))
    lower=scale*constant
    aa=[max(F(1,10**8),rational(x)) for x in a.value]
    ww=[max(F(0),rational(x)) for x in w.value] if edges else []
    inflation=F(1000001,1000000)
    for attempt in range(12):
        ap=[v*inflation for v in aa];wp=[v*inflation for v in ww];minors=[];passed=True
        for C,H,i,incidence,_ in views:
            m=len(H);A=[[ap[H[u]] if u==v else F(0) for v in range(m)] for u in range(m)]
            for weight,b in zip(wp,incidence):
                for u in range(m):
                    for v in range(m):A[u][v]+=weight*F(int(b[u]*b[v]))
            M=[row+[F(int(H[u]==i))] for u,row in enumerate(A)]+[[F(int(v==i)) for v in H]+[F(1)]]
            leading=[determinant([row[:k] for row in M[:k]]) for k in range(1,m+2)]
            passed &= all(v>0 for v in leading);minors.append(leading)
        if passed:break
        inflation*=F(10001,10000)
    assert passed,'rational primal privacy LMIs failed'
    upper=sum((c*x for c,x in zip(ca,ap)),F(0))+sum((c*x for c,x in zip(cw,wp)),F(0))
    assert upper>=lower
    return dict(edges=edges,solver_status=problem.status,solver_value=float(problem.value),
        primal_a=ap,primal_w=wp,primal_scale=inflation,primal_leading_minors=minors,
        dual_factors=records,dual_scale=scale,dual_a_slack=[c-scale*g for c,g in zip(ca,ga)],
        dual_w_slack=[c-scale*g for c,g in zip(cw,gw)],
        lower=lower,upper=upper,float_lower=float(lower),float_upper=float(upper),absolute_gap=float(upper-lower),
        certificate='exact rational strict primal LMIs by Sylvester; PSD dual factors with exact nonnegative variable slacks; weak-duality interval for fixed support')

t0=time.perf_counter();results={};complete=support(3,'complete')
for name,W in {'grouped':np.array([[1,1,1],[1,1,1]]),'overlap':np.array([[1,1,1],[1,1,0],[0,1,1]])}.items():
    cases=[solve(W,[e for e,b in zip(complete,bits) if b]) for bits in itertools.product([0,1],repeat=3)]
    lower=min(x['lower'] for x in cases);upper=min(x['upper'] for x in cases)
    results[name]=dict(W=W.tolist(),supports=cases,all_support_infimum_interval=[lower,upper],absolute_gap=float(upper-lower))
out=pathlib.Path('experiments/small_sdp_certificates_r3');out.mkdir(exist_ok=True)
result=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command='OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=. <project-python> scripts/small_sdp_certificates_r3.py',
    script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
    environment=dict(python=platform.python_version(),numpy=np.__version__,cvxpy=cp.__version__),
    hardware='evidence/resources_local_r3_final.json',wall_seconds=time.perf_counter()-t0,rho=.5,delta_l2=1.,f=1,
    cases=results,scope='all eight n3 pair-mask supports, nonnegative weights and positive diagonal variances; numerical infimum bracket; not global over arbitrary mechanisms')
(out/'results.json').write_text(json.dumps(serial(result),indent=2)+'\n')
print(json.dumps({k:{'lower':float(v['all_support_infimum_interval'][0]),'upper':float(v['all_support_infimum_interval'][1]),'gap':v['absolute_gap']} for k,v in results.items()}))
