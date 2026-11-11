"""Independent check/summary of new Intel evidence; legacy files remain read-only."""
import collections,csv,datetime,hashlib,json,math,pathlib,platform,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t as student_t
from src.intel import dataset
from src.vector import histogram
from src.noise import rho_for_epsilon,support
from src.workloads import query_covariance
from src.release_gate import validate_peer_config

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def summary_ci(v):
    v=np.asarray(v);r=np.random.default_rng(20261005)
    return np.quantile([np.quantile(r.choice(v,len(v),replace=True),.99) for _ in range(1000)],[.025,.975]).tolist()
def main():
    out=pathlib.Path('evidence/reports_intel_r4');out.mkdir(exist_ok=True)
    name,X,datahash,meta=dataset();p=pathlib.Path('experiments/intel_utility_r4_verified/results.jsonl');rawsha=sha(p)
    counts=collections.Counter();suites=collections.Counter();seen=set();checked={};negative=[];table=[];maxerr=0.
    for line in p.open():
        x=json.loads(line);key=(x['group_size'],x['variant'],x['method'],x['statistic'],x['eps_total'])
        assert key not in seen;seen.add(key);counts[x['statistic']]+=1
        for suite in x['suites']:suites[suite]+=1
        assert x['dataset']==name and x['data_sha256']==datahash and x['n']==54 and x['evaluation_rows']==12
        assert x['metadata']==meta and x['composition_rounds']==12
        assert math.isclose(x['delta_l2'],math.sqrt(2),rel_tol=1e-12)
        assert math.isclose(x['rho_total'],rho_for_epsilon(x['eps_total'],1e-6),rel_tol=1e-12)
        assert math.isclose(12*x['rho_per_release'],x['rho_total'],rel_tol=1e-12)
        W=np.asarray(x['W']);d=x['design'];B=query_covariance(W,d);expected=np.diag(B)*.5/x['rho_per_release']*2
        err=np.max(np.abs(expected-x['expected_mse_per_coordinate'])/np.maximum(1,abs(expected)));assert err<1e-9;maxerr=max(maxerr,float(err))
        ms=np.asarray(x['mse_repetitions']);assert ms.shape==(8,len(W),2 if x['statistic']=='joint_count_sum' else 4)
        assert np.isfinite(ms).all() and np.allclose(ms.mean(0),x['mean_mse'])
        assert np.allclose(student_t.ppf(.975,7)*ms.std(0,ddof=1)/np.sqrt(8),x['ci95_halfwidth'])
        S=X if x['statistic']=='joint_count_sum' else histogram(X[:,:,1])*X[:,:,0,None]
        truth=np.einsum('qn,tnd->tqd',W,S,optimize=True)
        assert np.allclose(np.sqrt((truth**2).mean(axis=0)),x['truth_rms'])
        ck=key[:3]
        if ck not in checked:
            if 'edges' in d:a=np.asarray(d['a']);edges=d['edges'];weights=np.asarray(d['w'])
            else:
                a=np.full(54,d['a']);edges=support(54,d['kind']);weights=np.full(len(edges),d['w'])
            peers=[dict(id=i,a=float(a[i])*2,delta_l2=math.sqrt(2),report_dimension=2,clip_interval=[0.,1.],encoding='availability_value',rho_per_release=.5,
                neighbors={str(v if u==i else u):float(w)*2 for (u,v),w in zip(edges,weights) if i in (u,v)}) for i in range(54)]
            checked[ck]=validate_peer_config(peers)
        if x['statistic']=='joint_count_sum' and x['eps_total']==1:
            iid=np.sum(W*W,axis=1)*.5/x['rho_per_release']*2
            ratios=expected/iid
            if np.any(ratios>1+1e-6):negative.append(dict(group_size=x['group_size'],variant=x['variant'],method=x['method'],max_expected_mse_ratio_to_independent=float(ratios.max()),raw_path=str(p)))
        for j,q in enumerate(x['query_names']):
            for c,coordinate in enumerate(x['coordinate_names']):table.append(dict(group_size=x['group_size'],variant=x['variant'],method=x['method'],statistic=x['statistic'],eps_total=x['eps_total'],query=q,coordinate=coordinate,mean_mse=x['mean_mse'][j][c],ci95_halfwidth=x['ci95_halfwidth'][j][c],expected_mse=expected[j],raw_path=str(p),raw_sha256=rawsha))
    assert counts==dict(joint_count_sum=504,availability_histogram=54) and suites==dict(v1=216,v2=486)
    with (out/'utility_per_query.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,list(table[0]));writer.writeheader();writer.writerows(table)
    protocol=[];verified=[]
    for path in sorted(pathlib.Path('experiments/protocol').glob('intel_*_n54_r4/manifest.json')):
        m=json.loads(path.read_text());cfg=json.loads(pathlib.Path(m['internal_fixture_path']).read_text());common=cfg.get('peer_common',{});peers=[dict(common,**pp) for pp in cfg['peers']]
        W=np.asarray(cfg['W']);assert len(peers)==54 and cfg['report_dimension']==2 and cfg['encoding']['delta_l2_squared']==2
        assert len({p['hostname'] for p in m['process_to_host']})==2
        assert all(m['epoch_reuse_refused']);assert len(m['trials'])==20
        fresh=validate_peer_config(peers,cfg.get('noise_blocks'));assert fresh['passed'];rho=cfg['accountant']['rho_per_release'];total=cfg['accountant']['rho_total'];max_arith=0.
        for trial in m['trials']:
            z=np.asarray(trial['public_reports']);answers=np.asarray([trial['answers'][str(j)] for j in range(len(W))]);error=float(np.max(np.abs(answers-W@z)))
            assert z.shape==(54,2) and error<=trial['arithmetic_absolute_bound'];max_arith=max(error,max_arith)
            for after in trial['after']:
                hist=after['history'];assert len({h['epoch'] for h in hist})==len(hist)
                assert math.isclose(hist[-1]['rho_spent_cumulative'],rho*sum(h['exposed'] for h in hist),rel_tol=1e-10)
                assert hist[-1]['rho_spent_cumulative']<=total*(1+1e-10)
        retry=m['fresh_retry_after_abort'];assert retry and retry['public_reports']!=m['trials'][-1]['public_reports']
        assert np.max(np.abs(np.asarray([retry['answers'][str(j)] for j in range(len(W))])-W@np.asarray(retry['public_reports'])))<1e-8
        for after in retry['metrics']:
            hist=after['history'];assert math.isclose(hist[-1]['rho_spent_cumulative'],rho*sum(h['exposed'] for h in hist),rel_tol=1e-10)
            assert hist[-1]['rho_spent_cumulative']<=total*(1+1e-10)
        wire=json.loads((path.parent/'ssh_wire.json').read_text());assert wire['status']=='OBSERVED'
        verified.append(dict(run=m['tag'],status='LOCALLY_VERIFIED',trials=20,n=54,report_dimension=2,arithmetic_max_error=max_arith,raw_path=str(path),raw_sha256=sha(path),fresh_retry=True))
        private=np.asarray([peer['s'] for peer in peers]);truth=W@private
        for mode in ['sharing','no_sharing']:
            selected=[t for t in m['trials'] if t['mode']==mode];times=[t['seconds']['online_total'] for t in selected];maxbytes=[];maxcpu=[];node_times=[];byhostbytes=[];setupbytes=[];querybytes=[];errors=[]
            for trial in selected:
                bs=[];cs=[];byhost=collections.Counter();sb=qb=0
                for before,after in zip(trial['before'],trial['after']):
                    bm=before['metrics'];am=after['metrics'];db=sum(am[f]-bm[f] for f in ['tls_tx_bytes','tls_rx_bytes']);dc=am['peer_cpu_seconds']-bm['peer_cpu_seconds'];assert db>=0 and dc>=0
                    bs.append(db);cs.append(dc);byhost[after['hostname']]+=db;node_times.append(after['phase']['epoch_query_completion_seconds'])
                    for field in ['tls_tx_bytes','tls_rx_bytes']:
                        sb+=am.get('by_op',{}).get('mask',{}).get(field,0)-bm.get('by_op',{}).get('mask',{}).get(field,0)
                        for op in ['report','partial','aggregate']:qb+=am.get('by_op',{}).get(op,{}).get(field,0)-bm.get('by_op',{}).get(op,{}).get(field,0)
                maxbytes.append(max(bs));maxcpu.append(max(cs));byhostbytes.append(max(byhost.values()));setupbytes.append(sb);querybytes.append(qb)
                answers=np.asarray([trial['answers'][str(j)] for j in range(len(W))]);errors.append((answers-truth)**2)
            v=np.asarray(errors);ci=student_t.ppf(.975,9)*v.std(axis=0,ddof=1)/np.sqrt(10)
            protocol.append(dict(run=m['tag'],method=cfg['noise_kind'],mode=mode,n=54,report_dimension=2,trials=10,
                online_p99_seconds=float(np.quantile(times,.99)),online_p99_bootstrap_ci95=summary_ci(times),setup_p99_seconds=float(np.quantile([t['seconds']['setup'] for t in selected],.99)),query_p99_seconds=float(np.quantile([t['seconds']['query'] for t in selected],.99)),
                pooled_node_completion_p99_seconds=float(np.quantile(node_times,.99)),mean_max_node_tls_tx_rx_bytes=float(np.mean(maxbytes)),max_node_tls_tx_rx_bytes=max(maxbytes),mean_max_node_cpu_seconds=float(np.mean(maxcpu)),mean_max_physical_host_endpoint_tls_bytes=float(np.mean(byhostbytes)),mean_mask_setup_endpoint_tls_bytes=float(np.mean(setupbytes)),mean_query_endpoint_tls_bytes=float(np.mean(querybytes)),
                whole_run_ssh_wire=wire,mean_mse=v.mean(axis=0).tolist(),mse_ci95_halfwidth=ci.tolist(),query_names=cfg.get('query_names',list(range(len(W)))),
                privacy='one joint release per epoch; exposed abort charged; fixed-epoch ideal f=1 induced covariance; finite sampler/TLS implementation theory pending',
                repetitions='10 OS-random epochs per routing mode, all charged; stochastic performance estimates',randomness='fresh OS secrets per coordinate and epoch; no deterministic seed',units='seconds, TLS/SSH payload bytes, squared count and normalized sum units',
                raw_path=str(path),raw_sha256=sha(path),config_sha256=sha(m['internal_fixture_path']),hardware_records=m['host_identity_evidence'],
                scope='two physical hosts; empirical small-sample quantiles/CI, no production tail guarantee; TLS endpoints include control and loopback; host SSH payload includes provisioning, no TCP/IP headers'))
    assert len(verified)==5
    (out/'protocol_summary.json').write_text(json.dumps(protocol,indent=2)+'\n')
    preserved=json.loads(pathlib.Path('evidence/preserved_artifacts_r4.json').read_text())
    for p,v in preserved.items():assert sha(p)==v['sha256']
    validation=dict(status='LOCALLY_VERIFIED',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.executable+' scripts/report_intel_r4.py',script_sha256=sha(__file__),environment=dict(python=platform.python_version(),numpy=np.__version__,threads=2),
        utility=dict(cases=len(seen),counts=dict(counts),suite_counts=dict(suites),full_public_roster=meta['public_roster'],holdout_days=12,max_relative_covariance_error=maxerr,unique_designs_certified=len(checked),raw_sha256=rawsha,negative_results=negative),
        protocol=verified,legacy_artifacts_unchanged=len(preserved),sensitivity=meta['sensitivity'],
        scope='mechanical correctness, calibration, accounting, preserved negative results; no end-to-end finite-precision privacy proof or web acceptance')
    (out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');print(json.dumps(dict(utility_cases=len(seen),protocol_runs=len(verified),legacy_preserved=len(preserved))))
if __name__=='__main__':main()
