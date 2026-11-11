import sys,pathlib,json,time,hashlib,subprocess
import numpy as np
repo=pathlib.Path('external/workload-factorization-mechanism-r6');sys.path.insert(0,str(repo.resolve()))
from mechanisms import randomized_response
from factorization import factorize
from variance import worst_variance,total_variance
freeze=json.loads(pathlib.Path('experiments/LDP_REFERENCE_FREEZE_r6.json').read_text());freeze['retry']=json.loads(pathlib.Path('experiments/LDP_REFERENCE_RETRY_FREEZE_r6.json').read_text())
cfg=json.loads(pathlib.Path('experiments/protocol_config_intel_certified_partition_finite_r5b.json').read_text());a=np.array([p['s'][0] for p in cfg['peers']],int);N=len(a);x=np.bincount(a,minlength=2);W=np.array([[0.,1.]]);eps=1/22
Q0=randomized_response(2,eps);t=time.perf_counter();Q=factorize(W,eps,Q0,iters=200,gamma=1e-9,verbose=False);elapsed=time.perf_counter()-t
assert np.all(Q>=0) and np.allclose(Q.sum(axis=0),1)
assert np.all(Q.max(axis=1)<=np.exp(eps)*Q.min(axis=1)+1e-12)
D=Q.sum(axis=1);V=W@np.linalg.pinv(Q.T/D@Q)@Q.T/D
assert np.allclose(V@Q,W,rtol=1e-8,atol=1e-8)
rows=[]
for seed in freeze['simulation_seeds']:
 rng=np.random.default_rng(seed);out=[rng.choice(len(Q),p=Q[:,int(z)]) for z in a];y=np.bincount(out,minlength=len(Q));ans=float((V@y)[0]);rows.append({'seed':seed,'answer':ans,'squared_error':(ans-x[1])**2})
result=dict(source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in repo.glob('*.py')},license='Apache-2.0',freeze=freeze,N=N,x=x.tolist(),Q=Q.tolist(),V=V.tolist(),factorization_max_residual=float(abs(V@Q-W).max()),max_privacy_row_ratio=float((Q.max(axis=1)/Q.min(axis=1)).max()),expected_total_MSE=float(N*total_variance(W,Q,x,V='opt')),worst_total_MSE=float(N*worst_variance(W,Q,V='opt')),rr_expected_MSE=float(N*total_variance(W,Q0,x,V='opt')),observed_MSE=float(np.mean([r['squared_error'] for r in rows])),optimization_seconds=elapsed,trials=rows,units='squared availability count',code_command=sys.argv,label=freeze['label'],input_config_sha256=hashlib.sha256(pathlib.Path('experiments/protocol_config_intel_certified_partition_finite_r5b.json').read_bytes()).hexdigest())
pathlib.Path('evidence/ldp_reference_r6.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
