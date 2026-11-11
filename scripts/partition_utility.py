"""Historical v2 Electricity holdout runner; Intel uses intel_utility_r4.py.

Query Gaussian oracle, not network measurements. Preserves full timestamp
composition and joint histogram sensitivity. Robust SDP operates on a specified
block support at the full real participant count, not an unrestricted SDP.
"""
import datetime, hashlib, json, pathlib, platform, resource, sys, time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t as student_t
from scripts.full_utility import datasets, default
from src.noise import optimize_fixed, support, rho_for_epsilon, loss, signature_groups
from src.partition import certified_partition_dp, robust_cycle_power
from src.workloads import workload, grouped_design, uniform_tuned, query_covariance
from src.vector import histogram, adjacency_case

OUT=pathlib.Path('experiments/partition_utility_r3');OUT.mkdir(exist_ok=True)
HASHES={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [pathlib.Path(__file__),*pathlib.Path('src').glob('*.py')]}
SEEDS=list(range(20261005,20261013));EPS=[.25,.5,1,2,4,8]
SOLVER_CACHE={};FAILURES=[]

def fixed_block_sdp(W,kind):
    a=np.zeros(W.shape[1]);edges=[];weights=[];blocks=[];t0=time.perf_counter()
    # Exact-signature public components, complete/power support, nonuniform
    # a and individual edge weights; EVERY local f=1 LMI remains present.
    for group in signature_groups(W):
        V=W[:,group];k=len(group)
        e=robust_cycle_power(k,1) if kind=='power' else support(k,'complete')
        key=(kind,k,tuple((V.T@V).ravel()))
        if key not in SOLVER_CACHE:
            try:SOLVER_CACHE[key]=optimize_fixed(V,e,.5,max_iter=150)
            except Exception as exc:
                FAILURES.append({'kind':kind,'k':k,'error':repr(exc),'source':'src.noise.optimize_fixed all-f1 fixed-support LMI','fallback':'none; baseline failure retained'})
                raise
        d=SOLVER_CACHE[key];a[group]=d['a']
        edges.extend((group[u],group[v]) for u,v in e);weights.extend(d['w'])
        blocks.append({'members':group,'certificate':d['certificate'],'solver_status':d['solver_status'],
            'scale':d['scale'],'solve_seconds':d['solve_seconds'],'optimality':d['optimality']})
    return dict(a=a,edges=edges,w=np.asarray(weights),blocks=blocks,
        certificate=dict(passed=all(b['certificate']['passed'] for b in blocks),f=1,
            worst_rho_upper=max(b['certificate']['worst_rho_upper'] for b in blocks),
            coverage='independent public fixed-support blocks; all local empty/singleton induced views, no sampled coalition'),
        planning_seconds=time.perf_counter()-t0,
        baseline_scope='full real n; robust pairwise fixed-support SDP adaptation; exact-signature blocks only; no unrestricted/global optimality claim')

def evaluate(dataset,X,datahash,meta,W,names,kinds,variant,k,method,d,statistic):
    R=len(X);rounds=meta.get('total_evaluation_days',R)
    sensitivity=1. if statistic!='histogram' else adjacency_case('histogram_owner_onehot_replace')['delta_l2']
    dim=4 if statistic=='histogram' else 1
    B=query_covariance(W,d);ev,U=np.linalg.eigh((B+B.T)/2)
    if ev.min() < -1e-8*max(1,ev.max()):raise ValueError('invalid query covariance')
    root=U*np.sqrt(np.maximum(ev,0))
    for eps in EPS:
        key=(dataset,k,variant,method,statistic,eps)
        if key in COMPLETED:continue
        rho=rho_for_epsilon(eps,1e-6);scale=.5*rounds/rho*sensitivity**2
        mse=[];relative=[];truth_rms=None
        for seed in SEEDS:
            rng=np.random.default_rng(seed);ss=np.zeros((len(W),dim));rel=np.zeros_like(ss);truthss=np.zeros_like(ss)
            for start in range(0,R,512):
                V=np.asarray(X[start:start+512],float)
                S=histogram(V) if statistic=='histogram' else (V>0).astype(float)[:,:,None] if statistic=='count' else V[:,:,None]
                truth=np.einsum('qn,tnd->tqd',W,S,optimize=True)
                noise=np.stack([rng.standard_normal((len(V),len(W)))@root.T for _ in range(dim)],axis=-1)*np.sqrt(scale)
                error=truth+noise-truth;ss+=np.sum(error**2,axis=0)
                rel+=np.sum((error/np.maximum(1,np.abs(truth)))**2,axis=0);truthss+=np.sum(truth**2,axis=0)
            mse.append(ss/R);relative.append(rel/R);truth_rms=np.sqrt(truthss/R)
        ms=np.asarray(mse);ci=student_t.ppf(.975,7)*ms.std(0,ddof=1)/np.sqrt(8)
        row=dict(dataset=dataset,data_sha256=datahash,metadata=meta,n=X.shape[1],evaluation_rows=R,
            group_size=k,variant=variant,method=method,statistic=statistic,query_names=names,query_kinds=kinds,
            workload='synthetic public metadata/workload-coefficient queries over all processed holdout readings',
            W=W,design=d,certificate=d['certificate'],eps_total=eps,delta=1e-6,rho_total=rho,
            rho_per_release=rho/rounds,composition_rounds=rounds,delta_l2=sensitivity,
            histogram_bins=[0,.02,.1,.5,1.000001] if dim==4 else None,
            expected_mse_per_coordinate=np.diag(B)*scale,mse_repetitions=ms,mean_mse=ms.mean(0),
            ci95_halfwidth=ci,mean_scaled_mse=np.mean(relative,0),truth_rms=truth_rms,
            units='squared normalized scalar/COUNT/bin-count query units; scalar Electricity x1000 kWh and Intel x100 C',
            repetitions=8,seeds_internal=SEEDS,code_hashes=HASHES,
            environment=dict(python=platform.python_version(),numpy=np.__version__,blas_threads=2),
            hardware_record='evidence/resources_local_r3_initial.json',
            deployment='central Gaussian query oracle; not a vector peer protocol',
            fairness='same W, full holdout, seeds, total owner-epoch privacy, clipping and machine; public analytic/fixed-support tuning costs disclosed per method',
            executed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            command='OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 PYTHONPATH=. <project-python> scripts/partition_utility.py')
        with (OUT/'results.jsonl').open('a') as f:f.write(json.dumps(row,default=default)+'\n')
        COMPLETED.add(key)

COMPLETED=set()
if (OUT/'results.jsonl').exists():
    for line in (OUT/'results.jsonl').open():
        x=json.loads(line);COMPLETED.add((x['dataset'],x['group_size'],x['variant'],x['method'],x['statistic'],x['eps_total']))
t0=time.perf_counter()
for dataset,X,datahash,meta in datasets():
    n=X.shape[1]
    for k in [8,16]:
        for variant in ['group','hotspot','shift','near']:
            W,names,kinds=workload(n,k,'group' if variant=='near' else variant)
            if variant=='near':
                W=W*(1+.01*(np.arange(n)%3)[None,:]);names=['near_'+s for s in names]
            planned=workload(n,k,'group')[0] if variant=='shift' else W
            designs={}
            orders={'metadata':list(range(n)),
                'signature':sorted(range(n),key=lambda i:tuple(planned[:,i])),
                'interleaved':sorted(range(n),key=lambda i:(i%k,i//k))}
            for name,order in orders.items():designs['partition-'+name]=certified_partition_dp(planned,order,f=1,gamma_min=.05,edge_cost=.01)
            designs['independent']=dict(a=np.ones(n)*(1+1e-7),edges=[],w=np.array([]),
                certificate=dict(passed=True,f=1,worst_rho_upper=.5/(1+1e-7),coverage='all coalitions; independent scalar variance'))
            designs['aware-cycle-uniform']=uniform_tuned(planned,'cycle')
            designs['aware-complete-uniform']=uniform_tuned(planned,'complete')
            designs['unaware-cycle-uniform']=uniform_tuned(np.ones((1,n)),'cycle')
            for kind in ['power','complete']:
                try:designs['robust-fixed-block-SDP-'+kind]=fixed_block_sdp(planned,kind)
                except Exception as exc:
                    with (OUT/'baseline_failures.jsonl').open('a') as f:f.write(json.dumps(dict(dataset=dataset,k=k,variant=variant,kind=kind,error=repr(exc),failures=FAILURES))+'\n')
            for method,d in designs.items():
                assert d['certificate']['passed']
                # Full scalar evaluation for all workloads; COUNT/histogram
                # full holdout evaluation in the group/8 regime on BOTH domains.
                statistics=['scalar','count','histogram'] if k==8 and variant=='group' else ['scalar']
                for statistic in statistics:evaluate(dataset,X,datahash,meta,W,names,kinds,variant,k,method,d,statistic)
            print(json.dumps(dict(dataset=dataset,k=k,variant=variant,total_cases=len(COMPLETED))),flush=True)
(OUT/'run.json').write_text(json.dumps(dict(status='OBSERVED',cases=len(COMPLETED),wall_seconds=time.perf_counter()-t0,
    max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,threads=2,seeds=SEEDS,
    eps=EPS,solver_cache_entries=len(SOLVER_CACHE),baseline_failures=FAILURES,code_hashes=HASHES),indent=2)+'\n')
