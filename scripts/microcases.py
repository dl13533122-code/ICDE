import hashlib,itertools,json,pathlib,resource,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from src.noise import *
from src.baselines import *

def serial(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)

out=pathlib.Path('experiments/microcases');out.mkdir(parents=True,exist_ok=True);results={};t0=time.perf_counter()
for name,W in {'identical':np.array([[1,1,1],[1,1,1]],float),'overlap':np.array([[1,1,1],[1,1,0],[0,1,1]],float)}.items():
    es=support(3,'complete');rows=[]
    for bits in itertools.product([0,1],repeat=len(es)):
        e=[x for x,b in zip(es,bits) if b]
        try:x=optimize_fixed(W,e,.5);rows.append(dict(support=e,objective=x['objective'],solve_seconds=x['solve_seconds'],certificate=x['certificate'],status=x['solver_status']))
        except Exception as exc:rows.append(dict(support=e,error=str(exc)))
    finite=[r for r in rows if 'objective' in r];candidate=sparse_candidate(W);results[name]={'all_supports':rows,'best_numerical_feasible_objective':min(r['objective'] for r in finite),'candidate':candidate,'gap_to_numerical_incumbent':candidate['objective']-min(r['objective'] for r in finite),'oracle_label':'exhaustive supports; convex numerical feasible incumbents, unverified exact optimum/dual gap'}
W=np.array([[.75,.25,0],[.25,.5,.25],[0,.25,.75]])
for mode in ['mixing','pairwise']:
    A,p=whisper_original(W,1.,mode);X,res=verified_inverse(A);results['whisper_original_'+mode]={'covariance':A,'objective':np.trace(W@A@W.T),'worst_inverse_diagonal':max(np.diag(X)),'residual':res,'provenance':p,'assumptions':'original f=0; global/shared seeds for mixing; not trust-matched f=1 deployment','solver_change':'CLARABEL in place of MOSEK'}
v,p=decor_original(1.,2.,3,support(3,'cycle'));A,H=covariance(np.ones(3),support(3,'cycle'),np.ones(3)*2);X,res=verified_inverse(A)
results['decor_original']={'rho':v,'expected_rho':.5*max(np.diag(X)),'difference':float(v-.5*max(np.diag(X))),'provenance':p,'sensitivity':'clip=.5 implies replacement Delta=1, no subsampling'}
results['robust_uniform']=robust_uniform(np.array([[1,1,1],[1,1,0],[0,1,1]]),support(3,'cycle'))
results['resources']={'wall_seconds':time.perf_counter()-t0,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2,'seed':20261005,'command':'OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=. <project-python> scripts/microcases.py'}
(out/'results.json').write_text(json.dumps(results,default=serial,indent=2)+'\n');print(json.dumps(results['resources']))
