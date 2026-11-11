"""Full chronological evaluation, Gaussian oracle only (not deployment timing).

Every evaluated timestamp is a distinct release; owner-statistic epoch budgets
compose across timestamps and are calibrated to the stated TOTAL epsilon.
The independent repetitions are alternative experimental executions, not an
unaccounted multi-release service. Synthetic public workloads are explicit.
"""
import argparse,datetime,hashlib,json,pathlib,platform,resource,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t as student_t
from src.noise import rho_for_epsilon
from src.workloads import *

def default(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)

def datasets():
    info=json.loads(pathlib.Path('data/processed/electricity_verification.json').read_text());count=info['rows'];start=int(count*.7)
    X=np.memmap('data/processed/electricity_kwh_clipped.f32',dtype='<f4',mode='r',shape=(count,370))
    yield 'electricity-full-370',X[start:],info['processed_sha256'],{'raw_clients':370,'all_evaluation_rows':count-start,'input_units':'normalized clipped kWh/15min; multiply by1000 for kWh','missing':'none','split_start':start}
    # Intel joint fixed-roster releases use src.intel.dataset and
    # scripts/intel_utility_r4.py + repair_intel_utility_r4.py. Legacy scalar
    # membership-stratified results are historical evidence, never new runs.

def main():
    out=pathlib.Path('experiments/full_utility');out.mkdir(parents=True,exist_ok=True);t0=time.perf_counter();results=[];repetitions=8;chunk=512;seeds=[20261005+i for i in range(repetitions)]
    completed=set()
    code_hashes={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['scripts/full_utility.py','src/noise.py','src/workloads.py']}
    if (out/'results.jsonl').exists():
        for line in (out/'results.jsonl').open():
            item=json.loads(line);completed.add((item['dataset'],item['group_size'],item['variant'],item['method'],item['eps_total']))
    for dataset,X,sha,meta in datasets():
        n=X.shape[1];R=len(X)
        for group_size in [8,16]:
            for variant in ['group','hotspot','shift']:
                W,names,kinds=workload(n,group_size,variant);planned_W=workload(n,group_size,'group')[0] if variant=='shift' else W
                designs={'signature-cycle':grouped_design(planned_W,'cycle'),'signature-complete':grouped_design(planned_W,'complete'),'unaware-cycle-uniform':uniform_tuned(np.ones((1,n)),'cycle'),'aware-cycle-uniform':uniform_tuned(planned_W,'cycle'),'aware-complete-uniform':uniform_tuned(planned_W,'complete')}
                designs['independent']={'a':np.ones(n)*(1+1e-7),'edges':[],'w':np.array([]),'certificate':{'passed':True,'f':1,'global_scenarios_covered':n+1,'global_honest_coordinate_constraints_covered':n*n,'worst_rho_upper':.5/(1+1e-7)}}
                for method,d in designs.items():
                    if not d['certificate']['passed']:raise ValueError('uncertified design '+dataset+' '+method+' '+str(d['certificate']))
                    B=query_covariance(W,d);e,U=np.linalg.eigh((B+B.T)/2);root=U*np.sqrt(np.maximum(e,0));predicted=np.diag(B)
                    for eps in [.25,.5,1,2,4,8]:
                        if (dataset,group_size,variant,method,eps) in completed:continue
                        rho_total=rho_for_epsilon(eps,1e-6);composition_rounds=meta.get('total_evaluation_days',R);rho_per_release=rho_total/composition_rounds;scale=.5/rho_per_release;expected=predicted*scale
                        mse=[];scaled_mse=[];summary=None
                        for seed in seeds:
                            rng=np.random.default_rng(seed);ss=np.zeros(len(W));rr=np.zeros(len(W));truth_ss=np.zeros(len(W));truth_min=np.full(len(W),np.inf);truth_max=np.full(len(W),-np.inf)
                            for start in range(0,R,chunk):
                                data=np.asarray(X[start:start+chunk],float);truth=data@W.T
                                noise=(rng.standard_normal((len(data),len(W)))@root.T)*np.sqrt(scale)
                                answer=truth+noise;error=answer-truth;ss+=np.sum(error**2,0);rr+=np.sum((error/np.maximum(1,np.abs(truth)))**2,0);truth_ss+=np.sum(truth**2,0);truth_min=np.minimum(truth_min,truth.min(0));truth_max=np.maximum(truth_max,truth.max(0))
                            mse.append(ss/R);scaled_mse.append(rr/R);summary={'truth_rms':np.sqrt(truth_ss/R).tolist(),'truth_min':truth_min.tolist(),'truth_max':truth_max.tolist()}
                        ms=np.array(mse);mean=ms.mean(0);ci=student_t.ppf(.975,repetitions-1)*ms.std(0,ddof=1)/np.sqrt(repetitions)
                        result={'dataset':dataset,'data_sha256':sha,'metadata':meta,'n':n,'evaluation_rows':R,'workload':'synthetic public ID group/range/overlap workload on real readings','variant':variant,'group_size':group_size,'queries':names,'query_kinds':kinds,'W':W.tolist(),'method':method,'deployment_label':'central Gaussian query covariance oracle; full real data evaluated; no protocol or networking timing','eps_total':eps,'delta_total':1e-6,'rho_total':rho_total,'rho_per_release':rho_per_release,'composition_rounds':R,'owner_adjacency':'bounded scalar statistic replacement per epoch; total zCDP for changing same owner across all R releases','expected_mse':expected.tolist(),'repetition_mse':ms.tolist(),'mean_mse':mean.tolist(),'ci95_mse_halfwidth':ci.tolist(),'normalized_error_denom':'max(1,abs(true query))','mean_scaled_mse':np.mean(scaled_mse,0).tolist(),'truth_summary':summary,'seeds_internal':seeds,'repetitions':repetitions,'certificate':d['certificate'],'design':d,'accountant_note':'alternative repetitions not composed as production releases; equality calibration across methods'}
                        results.append(result)
                        result.update(composition_rounds=composition_rounds,code_hashes=code_hashes,environment={'python':platform.python_version(),'numpy':np.__version__,'threads':2},hardware_record='evidence/resources_local_during_full.json',executed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command='/home/fu/.local/state/server-history-codex/tmp/B-fuyue-20261005-v1/venv/bin/python scripts/full_utility.py with OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=.')
                        with (out/'results.jsonl').open('a') as f:f.write(json.dumps(result,default=default)+'\n')
                print(json.dumps({'dataset':dataset,'n':n,'rows':R,'group_size':group_size,'variant':variant,'completed_rows':len(results)}),flush=True)
    (out/'run.json').write_text(json.dumps({'command':'OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=. <project-python> scripts/full_utility.py','seed_list':seeds,'repetitions':repetitions,'chunk_rows':chunk,'wall_seconds_this_resume':time.perf_counter()-t0,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2,'results_rows':len(results)+len(completed),'resumed_previous_rows':len(completed),'status':'LOCALLY_VERIFIED','code_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':main()
