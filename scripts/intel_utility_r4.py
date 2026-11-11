"""Targeted Intel rerun; public roster, joint count/sum and private-absence histogram.

Reuses existing full-data preprocessing; writes no legacy result. A single joint
count/sum release has covariance Sigma tensor I_2 and exact replace-one diameter.
"""
import datetime,hashlib,json,pathlib,platform,resource,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t as student_t
from scripts.full_utility import default
from src.intel import dataset,public_roster
from src.vector import histogram
from src.noise import rho_for_epsilon
from src.workloads import workload,query_covariance,grouped_design,uniform_tuned
from src.partition import certified_partition_dp
from src.baselines import robust_fixed_blocks

OUT=pathlib.Path('experiments/intel_utility_r4')
SEEDS=list(range(20261005,20261013));EPS=[.25,.5,1,2,4,8]
V1={'signature-cycle','signature-complete','aware-cycle-uniform','aware-complete-uniform','unaware-cycle-uniform','independent'}
V2={'partition-metadata','partition-signature','partition-interleaved','aware-cycle-uniform','aware-complete-uniform','unaware-cycle-uniform','independent','robust-fixed-block-SDP-power','robust-fixed-block-SDP-complete'}

def main():
    OUT.mkdir();name,X,datahash,meta=dataset();n=54;R=len(X);t0=time.perf_counter();cases=0
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [pathlib.Path(__file__),*pathlib.Path('src').glob('*.py')]}
    (OUT/'roster.json').write_text(json.dumps(meta,indent=2)+'\n')
    failures=[]
    for k in [8,16]:
        for variant in ['group','hotspot','shift','near']:
            W,names,kinds=workload(n,k,'group' if variant=='near' else variant)
            if variant=='near':W=W*(1+.01*(np.arange(n)%3)[None,:]);names=['near_'+s for s in names]
            planned=workload(n,k,'group')[0] if variant=='shift' else W
            orders={'metadata':list(range(n)),'signature':sorted(range(n),key=lambda i:tuple(planned[:,i])),'interleaved':sorted(range(n),key=lambda i:(i%k,i//k))}
            designs={m:certified_partition_dp(np.vstack([planned,planned]),o,f=1,gamma_min=.05,edge_cost=.01) for m,o in [('partition-'+t,o) for t,o in orders.items()]}
            designs.update(independent=dict(a=np.ones(n)*(1+1e-7),edges=[],w=np.array([]),certificate=dict(passed=True,f=1,worst_rho_upper=.5/(1+1e-7),coverage='all coalitions, independent noise')))
            for kind in ['cycle','complete']:
                designs['aware-'+kind+'-uniform']=uniform_tuned(planned,kind)
                if variant!='near':designs['signature-'+kind]=grouped_design(planned,kind)
            designs['unaware-cycle-uniform']=uniform_tuned(np.ones((1,n)),'cycle')
            for kind in ['power','complete']:
                try:designs['robust-fixed-block-SDP-'+kind]=robust_fixed_blocks(planned,kind)
                except Exception as exc:
                    failure=dict(group_size=k,variant=variant,method=kind,error=repr(exc),fallback='none')
                    failures.append(failure)
                    with (OUT/'baseline_failures.jsonl').open('a') as f:f.write(json.dumps(failure)+'\n')
            for method,d in designs.items():
                assert d['certificate']['passed'];B=query_covariance(W,d);ev,U=np.linalg.eigh((B+B.T)/2)
                assert ev.min()>-1e-8*max(1,ev.max());root=U*np.sqrt(np.maximum(ev,0))
                suites=(['v1'] if method in V1 and variant!='near' else [])+(['v2'] if method in V2 else [])
                for statistic in ['joint_count_sum']+(['availability_histogram'] if k==8 and variant=='group' and method in V2 else []):
                    sensitivity=meta['sensitivity']['delta_l2'] if statistic=='joint_count_sum' else np.sqrt(2)
                    dim=2 if statistic=='joint_count_sum' else 4
                    S=X if dim==2 else histogram(X[:,:,1])*X[:,:,0,None]
                    truth=np.einsum('qn,tnd->tqd',W,S,optimize=True)
                    for eps in EPS:
                        rho=rho_for_epsilon(eps,1e-6);scale=.5*R/rho*sensitivity**2;mse=[];relative=[]
                        for seed in SEEDS:
                            rng=np.random.default_rng(seed)
                            noise=np.stack([rng.standard_normal((R,len(W)))@root.T for _ in range(dim)],axis=-1)*np.sqrt(scale)
                            error=truth+noise-truth;mse.append((error**2).mean(axis=0));relative.append(((error/np.maximum(1,np.abs(truth)))**2).mean(axis=0))
                        ms=np.asarray(mse)
                        row=dict(dataset=name,data_sha256=datahash,metadata=meta,n=n,evaluation_rows=R,group_size=k,variant=variant,method=method,suites=suites if dim==2 else ['v2'],statistic=statistic,
                            coordinate_names=['availability_count','clipped_temperature_sum'] if dim==2 else ['available_bin_'+str(j) for j in range(4)],
                            W=W,query_names=names,query_kinds=kinds,design=d,certificate=d['certificate'],
                            eps_total=eps,delta=1e-6,rho_total=rho,rho_per_release=rho/R,composition_rounds=R,delta_l2=sensitivity,noise_scale=scale,
                            sensitivity_derivation=meta['sensitivity'] if dim==2 else {'domain':'zero for unavailable or available one-hot','replace_one_diameter':float(np.sqrt(2)),'maximum':'available bin replacement sqrt(2); availability change 1'},
                            expected_mse_per_coordinate=np.diag(B)*scale,mse_repetitions=ms,mean_mse=ms.mean(0),ci95_halfwidth=student_t.ppf(.975,7)*ms.std(0,ddof=1)/np.sqrt(8),mean_scaled_mse=np.mean(relative,axis=0),truth_rms=np.sqrt((truth**2).mean(axis=0)),
                            units='availability squared-count and normalized temperature squared-sum; temperature sum x100 degrees C; histogram squared-bin-count',
                            repetitions=8,seeds_internal=SEEDS,code_hashes=hashes,
                            environment=dict(python=platform.python_version(),numpy=np.__version__,blas_threads=2),hardware_record='evidence/resources_local_r4_before_utility.json',
                            deployment='central joint Gaussian query covariance oracle, full fixed roster holdout, not network timing',
                            fairness='same public roster/W, full 12-day holdout, clipping, joint replace-one adjacency, total horizon epsilon, seeds, machine; fixed public gamma .05 and additive edge cost .01; partition objective includes both coordinate losses',
                            executed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command='OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=. '+sys.executable+' scripts/intel_utility_r4.py')
                        with (OUT/'results.jsonl').open('a') as f:f.write(json.dumps(row,default=default)+'\n')
                        cases+=1
            print(json.dumps(dict(group_size=k,variant=variant,cases=cases)),flush=True)
    (OUT/'run.json').write_text(json.dumps(dict(status='OBSERVED',cases=cases,wall_seconds=time.perf_counter()-t0,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,baseline_failures=failures,threads=2,code_hashes=hashes,results_sha256=hashlib.sha256((OUT/'results.jsonl').read_bytes()).hexdigest()),indent=2)+'\n')
if __name__=='__main__':main()
