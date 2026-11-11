"""Whisper/CorN-DSGD Eq.(10) scalar-workload HBC covariance reproduction.

Original common independent variance and PSD seed components retained.
Public rectangular query W and exact f=1 family are declared adaptations.
This is a mathematical oracle, not a deployed generalized-seed protocol.
"""
import hashlib,itertools,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import cvxpy as cp
import numpy as np
from src.noise import families,verified_inverse

def solve(W,holders,rho=.5,f=1):
    n=W.shape[1];a=cp.Variable(nonneg=True);Cs=[cp.Variable((len(g),len(g)),PSD=True) for g in holders];constraints=[a>=1e-7];embeddings=[]
    for g in holders:
        E=np.eye(n)[:,g];embeddings.append(E)
    full=a*np.eye(n)
    for E,C in zip(embeddings,Cs):full=full+E@C@E.T
    for coalition in families(n,f):
        H=[i for i in range(n) if i not in coalition];A=a*np.eye(len(H))
        for g,E,C in zip(holders,embeddings,Cs):
            if not set(g).intersection(coalition):A=A+E[H,:]@C@E[H,:].T
        for i in range(len(H)):
            b=np.eye(len(H))[:,i:i+1];constraints.append(cp.bmat([[A,b],[b.T,np.array([[2*rho]])]])>>0)
    p=cp.Problem(cp.Minimize(cp.trace(W@full@W.T)),constraints);t=time.perf_counter();p.solve(solver='CLARABEL')
    if a.value is None:raise ValueError('no original HBC incumbent')
    av=max(a.value,1e-7);components=[]
    for v in Cs:
        ev,U=np.linalg.eigh((v.value+v.value.T)/2);components.append((U*np.maximum(ev,0))@U.T)
    scenarios=[];worst=0.
    for coalition in families(n,f):
        H=[i for i in range(n) if i not in coalition];A=av*np.eye(len(H))
        for g,E,C in zip(holders,embeddings,components):
            if not set(g).intersection(coalition):A+=E[H,:]@C@E[H,:].T
        X,res=verified_inverse(A);guard=(res+64*np.finfo(float).eps*len(H)*max(1,np.linalg.norm(A,2)*np.linalg.norm(X,2)))/av
        r=(np.diag(X)+guard)/2;worst=max(worst,max(r));scenarios.append({'C':coalition,'H':H,'rho_upper':r.tolist(),'residual':float(res)})
    scale=max(1,worst/rho)*(1+1e-6);av*=scale;components=[C*scale for C in components];A=av*np.eye(n)
    for E,C in zip(embeddings,components):A+=E@C@E.T
    return {'a_common':float(av),'holders':holders,'components':[c.tolist() for c in components],'covariance':A.tolist(),'objective':float(np.trace(W@A@W.T)),'solver_status':p.status,'solve_seconds':time.perf_counter()-t,'numerical_privacy_rescale':float(scale),'worst_rho_verified_upper':float(worst/scale),'scenarios_pre_rescale':scenarios,'f':f,'constraints_covered':sum(len(x['H']) for x in scenarios),'source':'Whisper/CorN-DSGD arXiv:2501.14644v2 Section V-D Eq.(10); original code Eq.(9) in utils/dp_solver.py; Eq.(10) faithfully reimplemented from full paper','label':'covariance oracle, not protocol deployment; shared noise seed for each holder subset; any colluder in subset reveals entire component; no original-principal-submatrix reuse'}

if __name__=='__main__':
    W=np.array([[1,1,1,1],[1,1,0,0],[0,1,1,0],[0,0,1,1]],float);cases={}
    for f in [0,1]:
        for kind in ['pairs','triples']:
            h=[list(g) for g in itertools.combinations(range(4),2 if kind=='pairs' else 3)];cases[f'{kind}-f{f}']=solve(W,h,f=f)
    out=pathlib.Path('experiments/whisper_hbc');out.mkdir(exist_ok=True);(out/'results.json').write_text(json.dumps({'W':W.tolist(),'cases':cases,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n');print(json.dumps({k:{'objective':v['objective'],'worst_rho':v['worst_rho_verified_upper']} for k,v in cases.items()}))
