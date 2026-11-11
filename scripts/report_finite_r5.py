"""Mechanical manuscript tables/figures: manifests, exact arithmetic, raw units."""
import csv,datetime,hashlib,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t as student_t
from src.protocol import read_fraction,weighted_reports
from src.finite_reports import public_bound
OUT=pathlib.Path('evidence/reports_finite_r5');OUT.mkdir(exist_ok=True)
rows=[];checks=[];queryrows=[]
for path in sorted(pathlib.Path('experiments/protocol').glob('*finite_r5*/manifest.json')):
    raw=path.read_bytes();m=json.loads(raw,object_hook=read_fraction);tag=m['tag'];cfg=json.loads(pathlib.Path('experiments/protocol_config_'+tag+'.json').read_text());common=cfg['peer_common'];peers=[dict(common,**p) for p in cfg['peers']];W=common['W'];d=cfg.get('report_dimension',1)
    proof=public_bound(peers,common['finite_parameters'],cfg['accountant']['eps_total_bound'],cfg['accountant']['max_release_epochs'],cfg['accountant']['delta']);assert proof['passed']
    assert len(set(x['hostname'] for x in m['process_to_host']))==2
    truth=weighted_reports(W[0],[p['s'] for p in peers],d) # each workload row below
    errors=[]
    for trial in m['trials']:
        if trial.get('status')=='ABORT':continue
        z=trial['public_reports'];answers=trial['answers']
        for qi,row in enumerate(W):
            assert weighted_reports(row,z,d)==answers[str(qi)]
        assert trial['arithmetic_max_error']==0
    for mode in ['sharing','no_sharing']:
        trials=[t for t in m['trials'] if t['mode']==mode and t.get('status')!='ABORT'];runtimes=np.array([t['seconds']['online_total'] for t in trials]);host_cpu=[];host_bytes=[];maxnode_cpu=[];maxnode_bytes=[];enc=[];actual_mse=[]
        for t in trials:
            hc={};hb={};nc=[];nb=[];encoding=[]
            for before,after in zip(t['before'],t['after']):
                cpu=after['metrics']['peer_cpu_seconds']-before['metrics']['peer_cpu_seconds'];byte=sum(after['metrics'][k]-before['metrics'][k] for k in ['tls_tx_bytes','tls_rx_bytes']);host=after['hostname'];hc[host]=hc.get(host,0)+cpu;hb[host]=hb.get(host,0)+byte;nc.append(cpu);nb.append(byte);encoding.append(after['phase'].get('encoding_seconds',0))
            host_cpu.append(hc);host_bytes.append(hb);maxnode_cpu.append(max(nc));maxnode_bytes.append(max(nb));enc.append(max(encoding))
            ans=t['answers'];error=[]
            for qi,row in enumerate(W):
                tr=weighted_reports(row,[p['s'] for p in peers],d);v=ans[str(qi)];error.append([(float(v)-float(tr))**2] if d==1 else [(float(v[j])-float(tr[j]))**2 for j in range(d)])
            actual_mse.append(error)
        ms=np.array(actual_mse)
        rng=np.random.default_rng(20261006);boot=np.median(rng.choice(runtimes,(1000,len(runtimes)),replace=True),axis=1)
        edgecount=sum(len(p['neighbors']) for p in peers)//2
        row=dict(tag=tag,dataset=cfg['dataset'],method=cfg['noise_kind'],n=m['n'],hosts=2,mode=mode,trials=len(trials),aborts=sum(t.get('status')=='ABORT' for t in m['trials'] if t['mode']==mode),edges=edgecount,max_degree=max(map(lambda p:len(p['neighbors']),peers)),p50_seconds=float(np.quantile(runtimes,.5)),p50_ci95_lo=float(np.quantile(boot,.025)),p50_ci95_hi=float(np.quantile(boot,.975)),p99_seconds=float(np.quantile(runtimes,.99)),setup_seconds=float(np.mean([t['seconds']['setup'] for t in trials])),release_seconds=float(np.mean([t['seconds']['release'] for t in trials])),encoding_max_peer_seconds=float(np.mean(enc)),query_seconds=float(np.mean([t['seconds']['query'] for t in trials])),max_peer_tls_bytes=float(np.mean(maxnode_bytes)),max_peer_cpu_seconds=float(np.mean(maxnode_cpu)),max_host_cpu_seconds=float(np.mean([max(x.values()) for x in host_cpu])),max_host_tls_endpoint_bytes=float(np.mean([max(x.values()) for x in host_bytes])),total_peer_tls_tx_bytes=float(np.mean([sum(a['metrics']['tls_tx_bytes']-b['metrics']['tls_tx_bytes'] for a,b in zip(t['after'],t['before'])) for t in trials])),proof_evaluation_seconds=cfg['finite_proof']['evaluation_seconds'],rigorous_certificate_seconds=cfg['rigorous_ideal_certificate']['verification_seconds'],numerical_delta_upper=proof['numerical_delta_upper'],beta_upper=proof['beta_upper'],grid_rounding_query_bound=max(sum(abs(v) for v in w) for w in W)*2**-21,maximum_arithmetic_error=0.,raw_path=str(path),raw_sha256=hashlib.sha256(raw).hexdigest(),config_path='experiments/protocol_config_'+tag+'.json',config_sha256=m['config_sha256'])
        rows.append(row)
        for qi in range(len(W)):
            for coordinate in range(d):
                vals=ms[:,qi,coordinate];queryrows.append(dict(tag=tag,mode=mode,query_index=qi,coordinate=coordinate,mean_mse=float(vals.mean()),ci95_halfwidth=float(student_t.ppf(.975,len(vals)-1)*vals.std(ddof=1)/len(vals)**.5),units='squared normalized contribution',repetitions=len(vals),raw_path=str(path),raw_sha256=row['raw_sha256']))
    for x in m['dropout']:
        assert x['history'][-1]['rho_spent_cumulative']>0
    assert all(m['epoch_reuse_refused'])
    retry=m['fresh_retry_after_abort']
    if retry:assert retry['arithmetic_max_error']==0
    checks.append(dict(tag=tag,passed=True,trial_count=len(m['trials']),raw_sha256=hashlib.sha256(raw).hexdigest(),numerical_delta=proof['numerical_delta_upper'],M=proof['M'],attempt_budget=proof['attempts']))
for name,data in [('protocol_summary',rows),('utility_per_query',queryrows)]:
    if data:
        with (OUT/(name+'.csv')).open('w') as f:w=csv.DictWriter(f,fieldnames=data[0]);w.writeheader();w.writerows(data)
        (OUT/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
(OUT/'validation.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),runs=checks,scope='exact report-grid/aggregate equality, all public bounds, all attempt charges and roster/host checks; web retains theorem and novelty judgment'),indent=2)+'\n')
# Preserve costs of every attempted epoch, including the exposed failure.
lifecycle=[]
for path in sorted(pathlib.Path('experiments/protocol').glob('*finite_r5*/manifest.json')):
    m=json.loads(path.read_text());last=m['trials'][-1]['after'];drop=m['dropout'];retry=m['fresh_retry_after_abort']['metrics']
    for stage,before,after in [('exposed_abort',last,drop),('fresh_retry',drop,retry)]:
        cpu=[];byte=[];dur=[]
        for b,a in zip(before,after):
            cpu.append(a['metrics']['peer_cpu_seconds']-b['metrics']['peer_cpu_seconds'])
            byte.append(sum(a['metrics'][k]-b['metrics'][k] for k in ['tls_tx_bytes','tls_rx_bytes']))
            dur.append(a['history'][-1]['duration_seconds'])
        wire=json.loads((path.parent/'ssh_wire.json').read_text())
        extra=m.get('additional_costs',{})
        lifecycle.append(dict(tag=m['tag'],stage=stage,prepared_attempts_per_peer=len(after[0]['history']),
                              max_peer_cpu_seconds=max(cpu),max_peer_tls_tx_rx_bytes=max(byte),
                              total_peer_cpu_seconds=sum(cpu),total_peer_tls_tx_rx_bytes=sum(byte),
                              max_peer_attempt_duration_seconds=max(dur),
                              controller_wall_seconds=extra.get('exposed_abort_seconds') if stage=='exposed_abort' else m['fresh_retry_after_abort'].get('wall_seconds'),
                              one_time_provisioning_seconds=extra.get('one_time_provisioning_seconds'),
                              whole_run_ssh_payload_bytes=wire['ssh_ciphertext_tx_bytes']+wire['ssh_ciphertext_rx_bytes'],
                              wire_status=wire['status'],raw_path=str(path),raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                              scope='counter differences include monitoring/control between snapshots; attempt duration starts after prepare; no estimate substituted for unrecorded provisioning wall time'))
(OUT/'lifecycle_costs.json').write_text(json.dumps(lifecycle,indent=2)+'\n')
# Machine populated tables; repeated query indexes are not independent data units.
sharing=[r for r in rows if r['mode']=='sharing']
lines=['\\begin{table*}[t]\\centering\\caption{B5 finite backend, real two-host executions. Ten fresh epochs per routing mode; p99 is descriptive. TLS endpoint bytes include setup/control; physical host-link SSH payload is separate.}\\label{tab:finite}\\small','\\begin{tabular}{llrrrrrrrr}\\hline','Data & Method & Edges & p50 (s) & p99 (s) & Setup (s) & Encode$^{\\max}$ (ms) & Max peer (KiB) & Max host CPU (s) & $\\delta_{num}^{upper}$\\\\\\hline']
for r in sharing:
    method={'independent':'Independent','robust-fixed-sdp':'Fixed-support SDP','signature-cycle':'Signature cycle','certified-partition':'Certified partition'}[r['method']]
    lines.append(f"{r['dataset'].title()} {r['n']} & {method} & {r['edges']} & {r['p50_seconds']:.3f} & {r['p99_seconds']:.3f} & {r['setup_seconds']:.3f} & {1000*r['encoding_max_peer_seconds']:.2f} & {r['max_peer_tls_bytes']/1024:.1f} & {r['max_host_cpu_seconds']:.3f} & {r['numerical_delta_upper']:.1e}\\\\")
lines+=['\\hline\\end{tabular}\\end{table*}']
pathlib.Path('manuscript/sections/finite_table.tex').write_text('\n'.join(lines)+'\n')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(1,2,figsize=(7,2.4))
for ax,data in zip(axes,['electricity','intel']):
    rr=[r for r in sharing if r['dataset']==data];x=np.arange(len(rr));ax.bar(x,[r['p50_seconds'] for r in rr],color=['#64748b','#2563eb','#0d9488','#d97706']);ax.set_xticks(x,['Ind.','SDP','Sig.','Part.']);ax.set_ylabel('Epoch p50 (seconds)');ax.set_title(data.title());ax.grid(axis='y',alpha=.25)
fig.tight_layout();fig.savefig('manuscript/figures/finite_latency_b5.pdf');plt.close(fig)
print(json.dumps(dict(runs=len(checks),trials=sum(r['trial_count'] for r in checks),summary=str(OUT))))
