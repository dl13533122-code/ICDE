"""Conservative recalibration/re-evaluation of only 54 failed unaware utility rows."""
import copy,datetime,hashlib,json,pathlib,platform,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t as student_t
from src.intel import dataset
from src.vector import histogram
from src.workloads import query_covariance
from src.noise import certify,support
SOURCE=pathlib.Path('experiments/intel_utility_r4/results.jsonl')
OUT=pathlib.Path('experiments/intel_utility_r4_verified')

def main():
    OUT.mkdir();_,X,_,_=dataset();failed=json.loads(pathlib.Path('evidence/utility_gate_failures_r4.json').read_text())['failed'];keys={tuple(f['key']) for f in failed};cached={};repaired=unchanged=0;t0=time.perf_counter()
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [pathlib.Path(__file__),*pathlib.Path('src').glob('*.py')]}
    with (OUT/'results.jsonl').open('w') as output:
        for line in SOURCE.open():
            x=json.loads(line);key=(x['group_size'],x['variant'],x['method'])
            if key not in keys:output.write(line);unchanged+=1;continue
            d=x['design'];assert x['method']=='unaware-cycle-uniform'
            if key not in cached:
                original=copy.deepcopy(d);edges=support(54,d['kind']);factor=1.;history=[]
                for attempt in range(4):
                    c=certify(np.full(54,d['a']*2*factor),edges,np.full(len(edges),d['w']*2*factor),np.sqrt(2),.5,1)
                    history.append(dict(attempt=attempt,factor=factor,passed=c['passed'],worst_rho_upper=c['worst_rho_upper'],max_residual=c['max_residual']))
                    if c['passed']:break
                    factor*=c['worst_rho_upper']/.5*(1+1e-4)
                else:raise ValueError('bounded conservative recalibration failed')
                fixed=copy.deepcopy(d);fixed['a']*=factor;fixed['w']*=factor;fixed['objective']*=factor;fixed['worst_inverse']/=factor
                fixed['certificate']=c
                cached[key]=(fixed,dict(history=history,factor=factor,original_design=original,
                    reason='conservative induced-covariance inverse residual guard; public uniform increase in both variances; unchanged roster/adjacency/epsilon/f=1'),original)
            fixed,recalibration,original=cached[key];x['design']=fixed;x['certificate']=fixed['certificate'];x['numerical_recalibration']=recalibration
            W=np.asarray(x['W']);B=query_covariance(W,fixed);ev,U=np.linalg.eigh((B+B.T)/2);root=U*np.sqrt(np.maximum(ev,0));dim=len(x['coordinate_names']);R=len(X)
            S=X if dim==2 else histogram(X[:,:,1])*X[:,:,0,None];truth=np.einsum('qn,tnd->tqd',W,S,optimize=True);ms=[];relative=[]
            for seed in x['seeds_internal']:
                rng=np.random.default_rng(seed);noise=np.stack([rng.standard_normal((R,len(W)))@root.T for _ in range(dim)],axis=-1)*np.sqrt(x['noise_scale'])
                error=truth+noise-truth;ms.append((error**2).mean(axis=0));relative.append(((error/np.maximum(1,np.abs(truth)))**2).mean(axis=0))
            ms=np.asarray(ms);x.update(expected_mse_per_coordinate=(np.diag(B)*x['noise_scale']).tolist(),mse_repetitions=ms.tolist(),mean_mse=ms.mean(axis=0).tolist(),ci95_halfwidth=(student_t.ppf(.975,7)*ms.std(axis=0,ddof=1)/np.sqrt(8)).tolist(),mean_scaled_mse=np.mean(relative,axis=0).tolist(),code_hashes=hashes,
                executed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),supersedes=dict(source_path=str(SOURCE),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),case_key=list(key)+[x['statistic'],x['eps_total']]),
                command='OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=. '+sys.executable+' scripts/repair_intel_utility_r4.py')
            output.write(json.dumps(x)+'\n');repaired+=1
    record=dict(status='OBSERVED',recomputed_rows=repaired,unchanged_rows_copied=unchanged,failed_designs=len(keys),source_path=str(SOURCE),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),result_sha256=hashlib.sha256((OUT/'results.jsonl').read_bytes()).hexdigest(),wall_seconds=time.perf_counter()-t0,code_hashes=hashes,recalibrations=[dict(key=key,**v[1]) for key,v in cached.items()])
    (OUT/'repair.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(repaired=repaired,unchanged=unchanged)))
if __name__=='__main__':main()
