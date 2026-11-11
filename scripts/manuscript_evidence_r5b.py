"""Populate working manuscript from verified, preserved evidence only."""
import csv,hashlib,json,pathlib,shutil,sys
from fractions import Fraction
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.noise import loss
ROOT=pathlib.Path.cwd();OUT=ROOT/'manuscript';SEC=OUT/'sections';FIG=OUT/'figures'
plt.rcParams.update({'font.size':9,'pdf.fonttype':42})
inputs={}
def track(p):
 p=pathlib.Path(p);h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 inputs[str(p)]=h.hexdigest();return h.hexdigest()
def read(p):track(p);return json.loads(pathlib.Path(p).read_text())
def table(name,caption,columns,headers,rows,label,wide=False):
 env='table*' if wide else 'table'
 text=['\\begin{'+env+'}[t]','\\centering\\footnotesize','\\caption{'+caption+'}\\label{'+label+'}','\\begin{tabular}{'+columns+'}\\hline',headers+r'\\\hline']
 text += [' & '.join(map(str,row))+r'\\' for row in rows]
 text += [r'\hline\end{tabular}','\\end{'+env+'}'];(SEC/name).write_text('\n'.join(text)+'\n')
finite=read('evidence/reports_finite_r5/protocol_summary.json');sharing=[r for r in finite if r['mode']=='sharing']
labels={'independent':'Ind.','robust-fixed-sdp':'SDP','signature-cycle':'Sig. cycle','certified-partition':'Partition'}
fullnames={'independent':'Independent','robust-fixed-sdp':'Fixed SDP','signature-cycle':'Signature cycle','certified-partition':'Partition'}
for r in sharing:
 assert track(r['raw_path'])==r['raw_sha256'];assert track(r['config_path'])==r['config_sha256']
 cfg=read(r['config_path']);pp=[dict(cfg['peer_common'],**p) for p in cfg['peers']];e=[];w=[]
 for p in pp:
  for j,value in p['neighbors'].items():
   if p['id']<int(j):e.append((p['id'],int(j)));w.append(value)
 r['ideal_loss']=loss(np.asarray(cfg['W']),np.array([p['a'] for p in pp]),e,np.array(w))
for data in ['electricity','intel']:
 ref=next(r['ideal_loss'] for r in sharing if r['dataset']==data and r['method']=='independent')
 for r in sharing:
  if r['dataset']==data:r['relative_loss']=r['ideal_loss']/ref
rows=[]
for r in sharing:
 rows.append(['E32' if r['dataset']=='electricity' else 'I54',fullnames[r['method']],r['max_degree'],f"{r['relative_loss']:.3f}",f"{r['p50_seconds']:.3f}",f"{r['p99_seconds']:.3f}",f"{r['setup_seconds']:.3f}",f"{r['encoding_max_peer_seconds']*1000:.2f}",f"{r['max_peer_tls_bytes']/1024:.1f}",f"{r['max_peer_cpu_seconds']*1000:.1f}"])
table('finite_table.tex','Finite backend: 10 epochs per routing mode on two physical hosts. E32: Electricity, 32 peers; I54: Intel, 54 fixed peers. Loss is ideal workload variance relative to independent noise after the same reserve. CPU and TLS columns are mean maximum-peer costs. p99 is descriptive.','llrrrrrrrr','Data & Method & Degree & Loss/Ind. & p50 (s) & p99 (s) & Setup (s) & Encode (ms) & TLS (KiB) & CPU (ms)',rows,'tab:finite',True)
fig,axes=plt.subplots(1,3,figsize=(7.1,2.4))
colors={'independent':'#64748b','robust-fixed-sdp':'#2563eb','signature-cycle':'#0d9488','certified-partition':'#d97706'}
for data,marker in [('electricity','o'),('intel','s')]:
 for r in sharing:
  if r['dataset']!=data:continue
  for ax,xkey,ykey in [(axes[0],'max_degree','relative_loss'),(axes[1],'max_peer_tls_bytes','p50_seconds'),(axes[2],'setup_seconds','p50_seconds')]:
   xx=r[xkey]/1024 if xkey=='max_peer_tls_bytes' else r[xkey]
   ax.scatter(xx,r[ykey],color=colors[r['method']],marker=marker,s=38,label=labels[r['method']]+(' E' if data=='electricity' else ' I'))
axes[0].set(xlabel='Maximum logical mask degree',ylabel='Ideal workload loss / independent')
axes[1].set(xlabel='Maximum peer TLS (KiB)',ylabel='Epoch p50 (seconds)')
axes[2].set(xlabel='Mean setup (seconds)',ylabel='Epoch p50 (seconds)')
for ax in axes:ax.grid(alpha=.2)
axes[0].legend(fontsize=6,ncol=2,loc='best');fig.tight_layout();fig.savefig(FIG/'finite_tradeoff_b5.pdf');plt.close(fig)
legacy=read('evidence/reports_r3/protocol_summary.json');intel=read('evidence/reports_intel_r4/protocol_summary.json')
tags=['partition_scale_n8_r3','partition_n16_r3','matched_partition_n32_r3','partition_scale_n64_r3','partition_scale_n128_r3','partition_scale_n256_r3','partition_n512_r3','partition_n1024_r3_retry']
rows=[]
for tag in tags:
 r=next(x for x in legacy if x['run']==tag and x['mode']=='sharing');assert track(r['raw_path'])==r['raw_sha256']
 ci=r['total_online_p99_bootstrap_ci95']
 rows.append([r['n'],r['trials'],r['max_logical_mask_degree'],f"{r['total_online_p50_seconds']:.3f}",f"{r['total_online_p99_seconds']:.3f}",f"[{ci[0]:.3f},{ci[1]:.3f}]",f"{r['setup_p99_seconds']:.3f}",f"{r['mean_max_logical_node_tls_tx_rx_bytes']/1024:.1f}"])
table('legacy_scale_table.tex','Preserved float backend, two physical hosts at every scale. Counts are epochs per sharing mode; p99 and its bootstrap 95\\% interval are descriptive (1,000 bootstrap samples). Above 370 peers, inputs are synthetic scale-up of real readings. Degree concerns the noise overlay.','rrrrrrrr','Peers & Epochs & Degree & p50 (s) & p99 (s) & p99 interval & Setup p99 (s) & Max peer TLS (KiB)',rows,'tab:scale',True)
# Per-query full-input comparisons, excluding superseded Intel membership strata.
selected={}
for data,p in [('Electricity','experiments/partition_utility_r3/results.jsonl'),('Intel','experiments/intel_utility_r4_verified/results.jsonl')]:
 track(p)
 for line in pathlib.Path(p).open():
  x=json.loads(line)
  if data=='Electricity' and x['dataset']!='electricity-full-370':continue
  if x['group_size']!=8 or x['variant']!='group' or x['eps_total']!=1:continue
  if (data=='Electricity' and x['statistic']!='scalar') or (data=='Intel' and x['statistic']!='joint_count_sum'):continue
  selected[data,x['method']]=x
methods=['independent','partition-metadata','partition-interleaved','partition-signature','aware-cycle-uniform','robust-fixed-block-SDP-power','unaware-cycle-uniform']
methodnames={'independent':'Independent','partition-metadata':'Metadata partition','partition-interleaved':'Interleaved partition','partition-signature':'Signature partition','aware-cycle-uniform':'Aware cycle','robust-fixed-block-SDP-power':'Fixed SDP','unaware-cycle-uniform':'Unaware cycle'}
rows=[]
for data in ['Electricity','Intel']:
 ref=selected[data,'independent'];queries=['global','group_0','range_0','overlap_0']
 for method in methods:
  if (data,method) not in selected:continue
  x=selected[data,method];vals=[]
  for q in queries:
   j=x['query_names'].index(q);k=ref['query_names'].index(q);den=ref['expected_mse_per_coordinate'][k]
   # Intel normalized sum coordinate; availability coordinate remains in raw tables.
   coord=0 if data=='Electricity' else 1
   mean=x['mean_mse'][j][coord]/den;ci=x['ci95_halfwidth'][j][coord]/den
   vals.append(f'{mean:.2g} $\\pm$ {ci:.1g}')
  rows.append([data,methodnames[method],*vals])
table('full_utility_table.tex','Full-input utility, total $\\epsilon=1$, $\\delta=10^{-6}$; 8 seeded executions. Entries: mean MSE / independent ideal MSE $\\pm$ Student-$t$ 95\\% half-width across executions. Intel uses the normalized-sum coordinate of the joint count/sum release; all availability-coordinate results are retained. Public grouping size 8. These are Gaussian oracle evaluations, not distributed runs.','llrrrr','Data & Method & Global & Group 0 & Range 0 & Overlap 0',rows,'tab:utility',True)
track('evidence/reports_r3/electricity_utility_and_shift.pdf');shutil.copyfile('evidence/reports_r3/electricity_utility_and_shift.pdf',FIG/'electricity_utility_and_shift.pdf')
# Direct adverse-case diagnostic and independent branch, retaining all failures.
x=read('experiments/partition_diagnostics_r3/results.json');ce=x['counterexamples'];rows=[]
for name in ['bad-metadata','signature']:
 r=ce[name];rows.append([name.replace('bad-metadata','Natural order'),f"{r['query_loss']:.3f}",f"{r['shifted_loss']:.3f}",len(r['groups'])])
track('scripts/partition_diagnostics.py')
planned_W=np.array([[1,0,1,0,1,0],[0,1,0,1,0,1]],float)
rows.append(['Independent',f'{np.sum(planned_W**2):.3f}',f"{ce['shifted_independent_loss']:.3f}",6])
table('order_table.tex','Exact six-node diagnostic, alternating public signatures: planned and changed workload variance. The independent reference uses the saved target $r=1$. Family/order restriction is visible.','lrrr','Order & Planned & Changed & Groups',rows,'tab:order')
rows=[]
for tag in ['matched_partition_n32_r3','bad_order_partition_n32_r3','shift_partition_n32_r3']:
 r=next(x for x in legacy if x['run']==tag and x['mode']=='sharing');rows.append([{'matched_partition_n32_r3':'Aligned','bad_order_partition_n32_r3':'Bad order','shift_partition_n32_r3':'Workload shift'}[tag],r['logical_mask_edges'],f"{r['full_workload_expected_error_per_release']:.3g}",f"{r['total_online_p99_seconds']:.3f}",f"{r['mean_max_logical_node_tls_tx_rx_bytes']/1024:.1f}"])
table('adverse_network_table.tex','Preserved 32-peer, two-host float backend: 10 epochs per mode. Bad-order construction selects the zero-edge independent branch; its utility/load remains visible.','lrrrr','Case & Edges & Ideal loss & p99 (s) & Max TLS (KiB)',rows,'tab:adverse')
# Every-attempt costs and numerical bounds; no missing timing is fabricated.
lifecycle=read('evidence/reports_finite_r5/lifecycle_costs.json');rows=[]
for r in sharing:
 a=next(x for x in lifecycle if x['tag']==r['tag'] and x['stage']=='exposed_abort');b=next(x for x in lifecycle if x['tag']==r['tag'] and x['stage']=='fresh_retry')
 rows.append(['E32' if r['dataset']=='electricity' else 'I54',fullnames[r['method']],f"{r['numerical_delta_upper']:.2g}",f"{a['max_peer_attempt_duration_seconds']:.3f}",f"{b['max_peer_attempt_duration_seconds']:.3f}",f"{a['total_peer_cpu_seconds']:.3f}",f"{b['total_peer_cpu_seconds']:.3f}",f"{a['whole_run_ssh_payload_bytes']/2**20:.1f}"])
table('lifecycle_table.tex','Finite numerical and lifecycle accounting: 22 prepared attempts per peer (20 trials, one exposed abort, one fresh retry), total $\\epsilon=1$, $\\delta=10^{-6}$. Abort/retry durations are maximum participant durations after prepare; CPU sums all peers. SSH payload covers the entire run including provisioning, control, and cleanup before transport shutdown.','llrrrrrr','Data & Method & $\\delta_{num}^{upper}$ & Abort (s) & Retry (s) & Abort CPU (s) & Retry CPU (s) & SSH (MiB)',rows,'tab:lifecycle',True)
rows=[]
for r in sharing:
 ns=next(x for x in finite if x['tag']==r['tag'] and x['mode']=='no_sharing')
 rows.append(['E32' if r['dataset']=='electricity' else 'I54',fullnames[r['method']],f"[{r['p50_ci95_lo']:.3f},{r['p50_ci95_hi']:.3f}]",f"{r['max_host_tls_endpoint_bytes']/2**20:.2f}",f"{r['max_host_cpu_seconds']:.3f}",f"{r['proof_evaluation_seconds']*1000:.2f}",f"{ns['p50_seconds']:.3f}"])
table('host_table.tex','Finite sharing runs: median 95\\% bootstrap intervals (1,000 resamples, seed 20261006), mean maximum-host endpoint traffic and summed peer CPU, public gate evaluation time (including the rigorous ideal certificate), and no-sharing median. Host endpoints include loopback/control; they are distinct from SSH host-link traffic.','llrrrrr','Data & Method & p50 interval (s) & Host TLS (MiB) & Host CPU (s) & Gate (ms) & No-share p50 (s)',rows,'tab:hosts',True)
(OUT/'evidence_map_r5b.json').write_text(json.dumps({'command':sys.argv,'script_sha256':track(__file__),'inputs':inputs,'sources':'R3/R4 preserved validation + finite transcript audit; no experiments generated','finite_metrics':sharing},indent=2)+'\n')
print(json.dumps({'tables':6,'figures':2,'tracked_inputs':len(inputs)}))
