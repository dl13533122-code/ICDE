"""Exact frame validation and mechanistic frozen-evaluation tables."""
import csv,datetime,hashlib,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.stats import t as student_t
from fractions import Fraction as F
from src.protocol import read_fraction,weighted_reports
from src.physical import FRAME_BYTES
from src.noise import loss
OUT=pathlib.Path('evidence/reports_physical_r6');OUT.mkdir(exist_ok=True)
ops=['mask','report','partial','prepare','setup','release','aggregate','finish']
keys=['application_tx_bytes','application_rx_bytes','tls_tx_bytes','tls_rx_bytes']
def counterdiff(b,a,operations):
 return {k:sum(a.get('by_op',{}).get(op,{}).get(k,0)-b.get('by_op',{}).get(op,{}).get(k,0) for op in operations) for k in keys}
def mean_ci(v):
 v=np.array(v,float);return {'mean':float(v.mean()),'ci95_halfwidth':float(student_t.ppf(.975,len(v)-1)*v.std(ddof=1)/len(v)**.5),'n':len(v)}
rows=[];validation=[];qrows=[]
for dataset in ['electricity','intel','electricity_full']:
 for method in ['b5','b6','independent','signature','unaware','sdp','cap','shift']:
  tag=dataset+'_'+method+'_r6';mp=pathlib.Path('experiments/protocol')/tag/'manifest.json';cp=pathlib.Path('experiments/protocol_config_'+tag+'.json')
  m=json.loads(mp.read_text(),object_hook=read_fraction);cfg=json.loads(cp.read_text());common=cfg['peer_common'];peers=[dict(common,**p) for p in cfg['peers']];n=len(peers);d=cfg.get('report_dimension',1);W=common['W'];public=cfg['physical_plan_public']
  node=[0]*n;calls=[]
  for i,p in enumerate(peers):calls.extend((i,int(j),'mask') for j in p['neighbors'] if i<int(j))
  for g in common['groups']:
   lead=g['leader'];calls.extend((lead,i,'report') for i in g['members'] if i!=lead)
   calls.extend((o,lead,'partial') for o in sorted({qi%n for qi,row in enumerate(W) if row[g['members'][0]]}) if o!=lead)
  for u,v,op in calls:node[u]+=sum(FRAME_BYTES[op]);node[v]+=sum(FRAME_BYTES[op])
  hostmap=public['host_map'];hosts=public['hosts'];loads=tuple(sum(node[i] for i,h in enumerate(hostmap) if h==host) for host in hosts)
  if 'predicted_loads' in public:assert tuple(map(F,public['predicted_loads']))==loads
  elif method=='b5':assert tuple(public['b5_loads'])==loads
  l0=tuple(map(F,public['l0']));pred=tuple(a+b for a,b in zip(loads,l0));cap=public.get('caps')
  if cap:assert all(a<=F(b) for a,b in zip(pred,cap))
  trialdata=[];mses=[];exactmax=0
  for t in m['trials']:
   assert t.get('status')!='ABORT' and t['arithmetic_max_error']==0
   ans=t['answers'];z=t['public_reports'];sq=[]
   for qi,row in enumerate(W):
    assert weighted_reports(row,z,d)==ans[str(qi)]
    truth=weighted_reports(row,[p['s'] for p in peers],d);v=ans[str(qi)];diff=[float(v)-float(truth)] if d==1 else [float(v[j])-float(truth[j]) for j in range(d)]
    sq.extend(x*x for x in diff)
    for j,delta in enumerate(diff):qrows.append(dict(tag=tag,trial=t['repetition'],query=qi,coordinate=j,squared_error=delta*delta,units='squared normalized contribution'))
   mses.append(sum(sq))
   totals={h:{k:0 for k in keys} for h in hosts};maxnodeapp=[];maxnodetls=[];nodecpu=[];hostcpu={h:0 for h in hosts}
   for i,(b,a) in enumerate(zip(t['before'],t['after'])):
    v=counterdiff(b['metrics'],a['metrics'],ops);h=hostmap[i]
    for k in keys:totals[h][k]+=v[k]
    maxnodeapp.append(v['application_tx_bytes']+v['application_rx_bytes']);maxnodetls.append(v['tls_tx_bytes']+v['tls_rx_bytes']);nodecpu.append(a['metrics']['peer_cpu_seconds']-b['metrics']['peer_cpu_seconds']);hostcpu[h]+=nodecpu[-1]
    # Scientific fixed controller frames have partition-independent source cost.
    ctrl=5888+cfg['physical_control_response_bytes'][i]
    assert maxnodeapp[-1]==node[i]+ctrl,(tag,i,maxnodeapp[-1],node[i]+ctrl)
   cv=counterdiff(t['controller_before'],t['controller_after'],ops)
   for k in keys:totals['fu'][k]+=cv[k]
   actual=tuple(totals[h]['application_tx_bytes']+totals[h]['application_rx_bytes'] for h in hosts)
   assert actual==pred,(tag,actual,pred)
   sshb=t['ssh_host_link_payload_before'];ssha=t['ssh_host_link_payload_after'];ssh=sum(ssha[k]-sshb[k] for k in ['ssh_ciphertext_tx_bytes','ssh_ciphertext_rx_bytes'])
   trialdata.append(dict(max_host_app=max(actual),max_node_app=max(maxnodeapp),max_node_tls=max(maxnodetls),max_host_tls=max(v['tls_tx_bytes']+v['tls_rx_bytes'] for v in totals.values()),per_host_application=dict(zip(hosts,actual)),per_host_tls={h:v['tls_tx_bytes']+v['tls_rx_bytes'] for h,v in totals.items()},max_host_cpu=max(hostcpu.values()),max_node_cpu=max(nodecpu),per_host_peer_cpu=hostcpu,ssh_link_payload=ssh,seconds=t['seconds']))
  edges=[(i,int(j)) for i,p in enumerate(peers) for j in p['neighbors'] if i<int(j)];ws=[peers[i]['neighbors'][str(j)] for i,j in edges]
  analytic=loss(np.array(W),[p['a'] for p in peers],edges,ws)*d
  runtimes=[x['seconds']['online_total'] for x in trialdata]
  row=dict(dataset=dataset,method=method,tag=tag,n=n,d=d,trials=len(trialdata),edges=len(edges),analytic_total_error=analytic,observed_total_error=mean_ci(mses),max_node_app=mean_ci([v['max_node_app'] for v in trialdata]),max_host_app=mean_ci([v['max_host_app'] for v in trialdata]),max_node_tls=mean_ci([v['max_node_tls'] for v in trialdata]),max_host_tls=mean_ci([v['max_host_tls'] for v in trialdata]),max_host_cpu=mean_ci([v['max_host_cpu'] for v in trialdata]),per_host_application=trialdata[0]['per_host_application'],per_host_tls={h:mean_ci([v['per_host_tls'][h] for v in trialdata]) for h in hosts},p50_seconds=float(np.quantile(runtimes,.5)),p99_seconds=float(np.quantile(runtimes,.99)),setup=mean_ci([v['seconds']['setup'] for v in trialdata]),release=mean_ci([v['seconds']['release'] for v in trialdata]),query=mean_ci([v['seconds']['query'] for v in trialdata]),ssh_link_payload=mean_ci([v['ssh_link_payload'] for v in trialdata]),one_time_provisioning_seconds=m['additional_costs']['one_time_provisioning_seconds'],abort_seconds=m['additional_costs']['exposed_abort_seconds'],retry_seconds=m['fresh_retry_after_abort']['wall_seconds'],raw_path=str(mp),raw_sha256=hashlib.sha256(mp.read_bytes()).hexdigest(),config_path=str(cp),config_sha256=hashlib.sha256(cp.read_bytes()).hexdigest(),code_sha256=m['code_sha256'],frame_match_all_trials=True,finite_delta_bound=cfg['finite_proof']['numerical_delta_upper'],units=f'bytes are endpoint TX+RX; MSE total over{len(W)} workload rows and {d} coordinates; latency seconds')
  row.update(max_node_cpu=mean_ci([v['max_node_cpu'] for v in trialdata]),controller_run_cpu_seconds=m['additional_costs']['controller_process_cpu_seconds'],cpu_scope='per-trial peer CPU includes scientific and monitoring calls; controller process total through final metrics/provisioning is reported separately')
  assert all(m['epoch_reuse_refused']) and m['fresh_retry_after_abort']['arithmetic_max_error']==0
  assert len(set(p['hostname'] for p in m['process_to_host']))==2
  rows.append(row);validation.append(dict(tag=tag,source_frames_match=True,trial_count=len(trialdata),exact_postprocessing=True,raw_sha256=row['raw_sha256'],config_sha256=row['config_sha256']))
  (OUT/(tag+'_trials.json')).write_text(json.dumps(trialdata,indent=2)+'\n')
(OUT/'summary.json').write_text(json.dumps(rows,indent=2)+'\n');(OUT/'validation.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),cases=validation),indent=2)+'\n')
with (OUT/'query_squared_errors.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=qrows[0]);w.writeheader();w.writerows(qrows)
labels={'b5':'B5 scalar','b6':'B6 min-load','independent':'Independent','signature':'Sig. cycle','unaware':'Unaware','sdp':'Robust SDP','cap':'B6 cap','shift':'B6 shift'}
lines=[r'\begin{table*}[t]\centering\footnotesize',r'\caption{Frozen B6 physical scheduling, ten fresh finite epochs per method on two hosts. E370 uses all 370 original Electricity IDs and 55 R3 workload rows; I54 uses the corrected 54-ID roster and 100 R5 rows (one extra row for shift). Error sums rows/report coordinates. Application frames include coordinator/final outputs; TLS includes handshakes, with monitoring/SSH separate. B6 uses minimum-load frontier after balanced caps fail.}\label{tab:b6}',r'\begin{tabular}{llrrrrrrrrr}\hline',r'Data & Method & Ideal error & MSE $\pm$95\% CI & Max node app & Max host app & Max host TLS & Setup & Release & Query & p99\\\hline']
for r in rows:
 if r['dataset']=='electricity':continue # E32 remains in retained raw evidence/prior working PDF.
 e=r['observed_total_error'];lines.append(' & '.join(['E370' if r['dataset']=='electricity_full' else 'I54',labels[r['method']],f"{r['analytic_total_error']:.3g}",f"{e['mean']:.3g} $\\pm$ {e['ci95_halfwidth']:.2g}",f"{r['max_node_app']['mean']/1024:.1f}",f"{r['max_host_app']['mean']/1024:.1f}",f"{r['max_host_tls']['mean']/1024:.1f}",f"{r['setup']['mean']:.3f}",f"{r['release']['mean']:.3f}",f"{r['query']['mean']:.3f}",f"{r['p99_seconds']:.3f}"])+r'\\')
lines += [r'\hline\end{tabular}',r'\vspace{1mm}\par\scriptsize Bytes are KiB endpoint TX+RX; times are seconds. p99 from ten trials is descriptive, not a tail guarantee. Coordinate/query errors remain unpooled in internal raw records.',r'\end{table*}']
pathlib.Path('manuscript/sections/physical_table_r6.tex').write_text('\n'.join(lines)+'\n')
print(json.dumps({'cases':len(rows),'trials':sum(r['trials'] for r in rows),'all_source_frames_exact':True}))
