import hashlib,itertools,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from src.noise import *
from src.planner import *

def candidate(W,allowed,rho=.5):
    # Allowed public links and W only; no access to s.
    n=W.shape[1];public=set(allowed);groups=signature_groups(W);start=set()
    for g in groups:
        for u,v in support(len(g),'cycle'):
            e=tuple(sorted((g[u],g[v])))
            if e in public:start.add(e)
    for i in range(n):
        order=np.argsort(np.sum((W.T-W[:,i])**2,1),kind='stable')
        for j in order[order!=i][:2]:
            e=tuple(sorted((i,int(j))))
            if e in public:start.add(e)
    inc=optimize_fixed(W,[],rho);cost=joint_objective(W,inc);history=[]
    for e in [sorted(start),sorted(public)]:
        x=optimize_fixed(W,e,rho);c=joint_objective(W,x);history.append({'support':e,**c})
        if c['objective']<cost['objective']:inc=x;cost=c
    # Exact verified deletion/swap, finite budget, every accepted graph factored anew.
    for iteration in range(3):
        chosen=None;trials=[]
        for j,e in enumerate(inc['edges']):
            risks=[]
            for C in families(n):
                if any(v in C for v in e):continue
                A,H=covariance(inc['a'],inc['edges'],inc['w'],C)
                try:X,den,der=diagonal_downdate(A,H.index(e[0]),H.index(e[1]),inc['w'][j]);risks.append(float(max(np.diag(X))))
                except ValueError:risks.append(float('inf'))
            reduced=inc['edges'][:j]+inc['edges'][j+1:];trials.append((max(risks,default=0),reduced,'delete'))
            for other in sorted(public-set(inc['edges'])):trials.append((max(risks,default=0),sorted(reduced+[other]),'swap'))
        for risk,e,op in sorted(trials,key=lambda v:(v[0],v[1]))[:16]:
            if not np.isfinite(risk):continue
            x=optimize_fixed(W,e,rho);c=joint_objective(W,x);history.append({'iteration':iteration,'operation':op,'support':e,**c})
            if c['objective']<cost['objective']-1e-6 and (chosen is None or c['objective']<chosen[1]['objective']):chosen=x,c
        if chosen is None:break
        inc,cost=chosen
    return {'incumbent':inc,'joint_cost':cost,'history':history,'guarantee':'finite feasible candidate pipeline only; no approximation/complexity theorem'}

def default(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)

out=pathlib.Path('experiments/candidate_pipeline');out.mkdir(exist_ok=True);results={};t=time.perf_counter()
for name,W in {'grouped':np.array([[1,1,1],[1,1,1]],float),'overlap':np.array([[1,1,1],[1,1,0],[0,1,1]],float)}.items():
    allowed=support(3,'complete');oracle=[]
    for bits in itertools.product([0,1],repeat=3):
        edges=[e for e,b in zip(allowed,bits) if b];d=optimize_fixed(W,edges,.5);oracle.append({'edges':edges,'solver_status':d['solver_status'],'certificate':d['certificate'],'cost':joint_objective(W,d),'solve_seconds':d['solve_seconds']})
    x=candidate(W,allowed);best=min(o['cost']['objective'] for o in oracle)
    results[name]={'candidate':x,'all_support_numerical_oracle':oracle,'gap_same_joint_objective':x['joint_cost']['objective']-best,'oracle_status':'feasible numerical SDP incumbents only; exact global optimality is OPEN'}
results['wall_seconds']=time.perf_counter()-t;results['script_sha256']=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest();(out/'results.json').write_text(json.dumps(results,default=default,indent=2));print(json.dumps({'wall_seconds':results['wall_seconds'],'gaps':{k:v['gap_same_joint_objective'] for k,v in results.items() if isinstance(v,dict)}}))
