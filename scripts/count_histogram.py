"""Full Electricity COUNT/histogram query oracle, explicit joint sensitivity."""
import hashlib,json,pathlib,resource,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t
from src.noise import rho_for_epsilon
from src.vector import histogram,adjacency_case
from src.workloads import *
info=json.loads(pathlib.Path('data/processed/electricity_verification.json').read_text());Rall=info['rows'];start=int(Rall*.7);X=np.memmap(info['processed_path'],dtype='<f4',mode='r',shape=(Rall,370))[start:];R=len(X);W,names,kinds=workload(370,8,'hotspot');designs={'signature-cycle':grouped_design(W),'independent':{'a':np.ones(370)*(1+1e-7),'edges':[],'w':np.array([])},'aware-cycle-uniform':uniform_tuned(W,'cycle')};out=pathlib.Path('experiments/count_histogram');out.mkdir(exist_ok=True);rows=[];t0=time.perf_counter()
for statistic,adj,dimension in [('count','count_owner_binary_replace',1),('histogram','histogram_owner_onehot_replace',4)]:
    sensitivity=adjacency_case(adj)['delta_l2']
    for name,design in designs.items():
        B=query_covariance(W,design);ev,U=np.linalg.eigh(B);root=U*np.sqrt(np.maximum(ev,0))
        for eps in [.25,.5,1,2,4,8]:
            rho_total=rho_for_epsilon(eps,1e-6);scale=.5*R/rho_total*sensitivity**2;mse=[];true_ss=None
            for rep in range(8):
                rng=np.random.default_rng(20261005+rep);ss=np.zeros((len(W),dimension));ts=np.zeros_like(ss)
                for begin in range(0,R,512):
                    data=np.asarray(X[begin:begin+512],float)
                    S=(data>0).astype(float)[:,:,None] if statistic=='count' else histogram(data)
                    truth=np.einsum('rn,knd->krd',W,S,optimize=True)
                    noise=np.stack([(rng.standard_normal((len(data),len(W)))@root.T)*np.sqrt(scale) for _ in range(dimension)],axis=-1)
                    error=(truth+noise)-truth;ss+=np.sum(error**2,axis=0);ts+=np.sum(truth**2,axis=0)
                mse.append(ss/R);true_ss=np.sqrt(ts/R)
            ms=np.array(mse);row={'statistic':statistic,'adjacency':adjacency_case(adj),'method':name,'data_sha256':info['processed_sha256'],'data_rows':R,'real_clients':370,'workload':'synthetic public ID hotspot/group/range/overlap on real readings','W':W.tolist(),'query_names':names,'query_kinds':kinds,'bins_public':[0,.02,.1,.5,1.000001] if dimension==4 else None,'output_dimension_per_query':dimension,'eps_total':eps,'delta':1e-6,'rho_total':rho_total,'rho_per_release':rho_total/R,'composition_rounds':R,'expected_mse_per_coordinate':(np.diag(B)*scale).tolist(),'mse_repetitions':ms.tolist(),'mean_mse':ms.mean(0).tolist(),'ci95_halfwidth':(t.ppf(.975,7)*ms.std(0,ddof=1)/np.sqrt(8)).tolist(),'truth_rms':true_ss.tolist(),'repetitions':8,'seeds_internal':list(range(20261005,20261013)),'deployment':'Gaussian query covariance oracle, not deployed vector protocol','script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'command':'OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=. <project-python> scripts/count_histogram.py'};rows.append(row)
            with (out/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        print(json.dumps({'statistic':statistic,'method':name,'completed':len(rows)}),flush=True)
(out/'run.json').write_text(json.dumps({'wall_seconds':time.perf_counter()-t0,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'results':len(rows),'status':'OBSERVED'},indent=2))
