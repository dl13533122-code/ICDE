"""Typeset literal web prose and tables/plots from the two verified new cases."""
import datetime,hashlib,json,pathlib,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'manuscript/revision_matched_fu_desktop125_20261013_v1'
EVID=ROOT/'evidence/matched_fu_desktop125_20261013_v1'
rows=json.loads((EVID/'results/summary.json').read_text())
plans=json.loads((EVID/'planning/planning_matrix.json').read_text())['rows']
assert len(rows)==2 and all(r['trials']==10 and r['frame_match_all_trials'] for r in rows)

def write(path,content):
    pathlib.Path(path).write_text(content+'\n')
def value(q,key='mean'):
    return q[key]
def ci(q,scale=1,fmt='.2f'):
    return f"{q['mean']/scale:{fmt}} $\\pm$ {q['ci95_halfwidth']/scale:{fmt}}"
def dataset(r):return 'E370' if r['dataset']=='electricity_full' else 'I54'

lines=[r'\begin{table*}[t]\centering\footnotesize',r'\caption{Frozen public planning in the current fu execution. Error is the sum over 55 E370 or 200 I54 query-coordinate pairs; modeled app bytes include endpoint TX+RX and $\ell_0$. Only feasible complete identities are deployed.}\label{tab:strict}',r'\begin{tabular}{llrrrrrrr}\hline',r'Data & Arm & Feasible & Ideal error & Max node app & Max host app & Plan wall(s) & Plan CPU(s) & Partitions\\\hline']
for r in plans:
    arm={'FIXED_GRAPH':'Fixed graph','FIXED_PARTITION':'Fixed partition','JOINT':'Joint'}[r['arm']]
    if r['degeneracy']=='DEGENERATE':arm+=' (degenerate)'
    cells=[dataset(r),arm,'yes' if r['feasible'] else 'no',f"{r['configured_total_ideal_error']:.2f}" if r['feasible'] else '--',str(r['max_logical_node_app_bytes']) if r['feasible'] else '--',str(r['max_physical_host_app_bytes']) if r['feasible'] else '--',f"{r['planning_wall_seconds']:.3f}",f"{r['planning_cpu_seconds']:.3f}",'full family' if r['arm']=='JOINT' else r['compatible_partition_count']]
    lines.append(' & '.join(cells)+r'\\')
lines += [r'\hline\end{tabular}',r'\par\scriptsize Caps: E370 $0.85(4{,}350{,}208)=3{,}697{,}676.8$ bytes; I54 $0.90(1{,}000{,}832)=900{,}748.8$ bytes. One planning run per arm; no timing CI. Grid:4096 bytes; intervals at most8; $\gamma_{\min}=0.05$. Construction is shared across arms and excluded from plan times.',r'\par\scriptsize Shared build wall/CPU(s): '+ '; '.join(dataset(r)+f" {r['candidate_build_wall_seconds']:.3f}/{r['candidate_build_cpu_seconds']:.3f}" for r in plans if r['arm']=='JOINT')+'.',r'\end{table*}']
write(OUT/'sections/joint_ablation_table_20261013_v1.tex','\n'.join(lines))

lines=[r'\begin{table*}[t]\centering\footnotesize',r'\caption{New fu--desktop125 physical cases. Fixed-partition and joint labels reuse the same complete execution identity and same case per fixture. Ten ordinary epochs per case; ideal and observed errors sum the frozen query-coordinate pairs. Intervals are descriptive Student-$t$95\% half-widths over ten fresh-coin epochs.}\label{tab:newmatched}',r'\begin{tabular}{lrrrrrrrr}\hline',r'Data & Ideal error & Observed SUM $\pm$ CI & Mean per pair & Max node app & Max host app & Max host TLS & SSH/epoch & Online $\pm$ CI\\\hline']
for r in rows:
    lines.append(' & '.join([dataset(r),f"{r['analytic_total_error']:.2f}",ci(r['observed_total_error'],1,'.0f'),f"{r['observed_mean_coordinate_error']['mean']:.2f}",f"{r['max_node_app']['mean']/1024:.2f}",f"{r['max_host_app']['mean']/1024:.2f}",f"{r['max_host_tls']['mean']/2**20:.3f}",f"{r['ssh_link_payload']['mean']/2**20:.3f}",ci(r['latency_mean_ci'])])+r'\\')
lines += [r'\hline\end{tabular}',r'\par\scriptsize App:KiB, TLS/SSH:MiB, times:s; bytes are TX+RX, TLS includes handshakes, SSH includes monitoring and encrypted host-link payload, excluding TCP/IP/L2. Mean per pair divides SUM by55(E370) or200(I54); its CI half-width is SUM CI divided by the same denominator. Exact scientific source frames match every epoch and both caps. Only one case per fixture is executed, not two arm replications.',r'\end{table*}']
write(OUT/'sections/matched_observations_20261013_v1.tex','\n'.join(lines))

lines=[r'\begin{table*}[t]\centering\footnotesize',r'\caption{New case costs, with exposed aborts and retries separate. All times are seconds. Each case charges12 prepared attempts within22; related old/new batches have24 attempts per fixture, with no combined original-budget claim.}\label{tab:newcost}',r'\begin{tabular}{lrrrrrrrr}\hline',r'Data & Provision & Preflight & Setup $\pm$ CI & Finite release $\pm$ CI & Query $\pm$ CI & p99 & Abort & Fresh retry\\\hline']
for r in rows:
    lines.append(' & '.join([dataset(r),f"{r['one_time_provisioning_seconds']:.3f}",f"{r['public_preflight_seconds']:.3f}",ci(r['setup']),ci(r['release']),ci(r['query']),f"{r['p99_seconds']:.3f}",f"{r['abort_seconds']:.3f}",f"{r['retry_seconds']:.3f}"])+r'\\')
lines += [r'\hline\end{tabular}',r'\vspace{1mm}\begin{tabular}{lrrrrrrr}\hline',r'Data & Whole wall & Controller CPU & Peer CPU fu/desktop125 & Max node CPU & Max host CPU/epoch & Whole SSH(MiB) & Controller CPU/epoch\\\hline']
for r in rows:
    cpus=r['per_physical_host_peer_CPU_total_after_trust_constructor']
    pc=f"{cpus['fu-System-Product-Name']:.2f}/{cpus['fy-SYS-6023H-6023H']:.2f}"
    ssh=r['outer_SSH_whole_case']
    lines.append(' & '.join([dataset(r),f"{r['whole_driver']['whole_driver_wall_seconds']:.3f}",f"{r['whole_driver']['whole_driver_cpu_seconds']:.3f}",pc,f"{r['max_node_CPU_total_after_trust_constructor']:.3f}",ci(r['max_host_cpu']),f"{(ssh['ssh_ciphertext_tx_bytes']+ssh['ssh_ciphertext_rx_bytes'])/2**20:.3f}",ci(r['controller_epoch_cpu'])])+r'\\')
lines += [r'\hline\end{tabular}',r'\par\scriptsize Whole wall/controller CPU include preflight, protocol provisioning, ten epochs, abort, retry and owned cleanup. Peer CPU starts after initial TLS trust construction and includes monitoring; setup/sampler/query handler CPU may overlap inbound work. Provisioning covers test-key generation, source/config staging, peer startup/readiness; environment software installation precedes and is excluded. p99 is the linear-interpolation sample quantile of ten epochs, with no tail guarantee. SSH whole-case cutoff follows owned cleanup, preceding transport shutdown. All workers terminate; no incomplete case is pooled.',r'\par\scriptsize New hardware: fu32 logical CPUs, desktop12524; eight CPU affinity slots per host, four local peers and366/50 remote peers, CPU only. Distinct physical ID SHA256 prefixes: fu782013f5e2d1, desktop125240427bd55b2. Original host-pair measurements remain separately labeled.',r'\end{table*}']
write(OUT/'sections/matched_costs_20261013_v1.tex','\n'.join(lines))

# Every ordinary epoch is plotted; no historical measurements are included.
fig,axes=plt.subplots(1,2,figsize=(7.0,1.85),gridspec_kw={'width_ratios':[1,1.4]})
plt.rcParams.update({'font.size':8})
colors=['#9aa7b6','#467fa4','#da964c','#62937a']
for j,r in enumerate(rows):
    ts=json.loads((EVID/'results'/f"{r['tag']}_trials.json").read_text())
    bottom=0
    for k,(stage,label) in enumerate([('coordination','Coord.'),('setup','Mask setup'),('release','Finite release'),('query','Query')]):
        mean=float(np.mean([t['seconds'][stage] for t in ts]));axes[0].bar(j,mean,bottom=bottom,color=colors[k],width=.55,label=label if j==0 else None);bottom+=mean
    v=np.array([t['seconds']['online_total'] for t in ts]);axes[1].plot(range(1,11),v,'o-',markersize=3,linewidth=.8,color=['#467fa4','#da964c'][j],label=dataset(r))
axes[0].set_xticks([0,1],['E370','I54']);axes[0].set_ylabel('Mean epoch wall time (s)');axes[0].legend(fontsize=6,frameon=False,ncol=2,loc='upper right');axes[0].set_title('(a) Recorded stages',fontsize=8)
axes[1].set_xlabel('Ordinary epoch');axes[1].set_ylabel('Online wall time (s)');axes[1].set_title('(b) All ten epochs per case',fontsize=8);axes[1].legend(fontsize=7,frameon=False);axes[1].set_xticks([1,3,5,7,10])
for ax in axes:
    ax.tick_params(labelsize=7);ax.spines['right'].set_visible(False);ax.spines['top'].set_visible(False);ax.grid(axis='y',alpha=.15)
fig.tight_layout(pad=.6)
for suffix in ['pdf','png']:
    fig.savefig(OUT/'figures'/('matched_fu_desktop125_20261013_v1.'+suffix),dpi=240,bbox_inches='tight')
plt.close(fig)

literal=(ROOT/'manuscript/WEB_B_MATCHED_FU_DESKTOP125_PRIVACY_SCOPE_PROSE_20261013_v1.md').read_text().split('\n\n')[2:]
assert len(literal)==2
p1,p2=[x.strip().replace('(epsilon=1,delta=10^-6)',r'($\epsilon=1,\delta=10^{-6}$)') for x in literal]
old=(OUT/'sections/joint_ablation_20261013_v1.tex').read_text()
# Retain the literal original arm definitions, including degeneracy and cap ratios.
definitions=old.split('\n\n')[0].split('\n',1)[1]
section=r'\subsection{Anchored Ablation and New Matched Deployment}'+'\n'+definitions+'\n\n'+p1+'\n\n'+p2+'\n'
write(OUT/'sections/joint_ablation_20261013_v1.tex',section)
main=(OUT/'main.tex').read_text()
main=main.replace(r'\noindent{\footnotesize\textbf{INTERNAL INCOMPLETE REVISION: PUBLIC PLANNING ONLY.}}\n','')
main=main.replace(r'\noindent{\footnotesize\textbf{INTERNAL INCOMPLETE REVISION: PUBLIC PLANNING ONLY.}}','')
main=main.replace('The hosts are fu and fy1,','The original hosts are fu and fy1,')
main=main.replace(r'\input{sections/joint_ablation_20261013_v1.tex}',r'\input{sections/joint_ablation_20261013_v1.tex}'+'\n'+r'\input{sections/matched_observations_20261013_v1.tex}'+'\n'+r'\input{sections/matched_costs_20261013_v1.tex}'+'\n'+r'\begin{figure*}[t]\centering\includegraphics[width=0.96\textwidth]{figures/matched_fu_desktop125_20261013_v1.pdf}'+'\n'+r'\caption{Only the new fu--desktop125 environment: selected cap-feasible complete identities, one case per fixture shared by fixed-partition and joint labels. Stage wall means and all ten ordinary epoch latencies are shown. These distinct fixture sizes establish no cross-host speedup or positive joint increment.}\label{fig:newmatched}\end{figure*}')
main=main.replace('The current revision adds no physical epochs.','The current revision adds two separately scoped fu--desktop125 benchmark cases, twenty ordinary epochs and two exposed aborts plus two fresh retries, with twenty-four prepared attempts across the new cases. It does not certify cumulative privacy across experiments.')
write(OUT/'main.tex',main)
write(EVID/'typesetting.json',json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':sys.argv,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'summary_sha256':hashlib.sha256((EVID/'results/summary.json').read_bytes()).hexdigest(),'source':str(OUT/'main.tex'),'scientific_acceptance':False},indent=2))
print(json.dumps({'literal_web_passages':2,'new_cases':2,'source':str(OUT/'main.tex'),'source_frames_all_exact':True}))
