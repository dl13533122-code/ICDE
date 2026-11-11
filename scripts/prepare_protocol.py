import argparse,json,pathlib,struct,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from src.workloads import workload,grouped_design,signature_groups,uniform_tuned
from src.noise import support
from src.noise import rho_for_epsilon
from src.partition import certified_partition_dp
from src.planner import plan
p=argparse.ArgumentParser();p.add_argument('--n',type=int,default=8);p.add_argument('--output',required=True);p.add_argument('--queries',type=int,default=100);p.add_argument('--delay-ms',type=float,default=0);p.add_argument('--rate-bytes-s',type=float,default=0);p.add_argument('--hotspot',action='store_true');p.add_argument('--epochs',type=int,default=41);p.add_argument('--noise-kind',choices=['signature-cycle','signature-complete','independent','unaware-cycle','certified-partition','robust-fixed-sdp'],default='signature-cycle');p.add_argument('--order',choices=['metadata','signature','interleaved'],default='metadata');p.add_argument('--gamma-min',type=float,default=.05);p.add_argument('--edge-cost',type=float,default=.01);p.add_argument('--dataset',choices=['electricity','intel'],default='electricity');p.add_argument('--retry-after-abort',action='store_true');p.add_argument('--numerical-rescale',action='store_true');p.add_argument('--near',action='store_true');p.add_argument('--workload-shift',action='store_true');args=p.parse_args()
n=args.n;W,names,kinds=workload(n,8,'hotspot' if args.hotspot else 'group');base=W.copy()
if args.near:base*=1+.01*(np.arange(n)%3)[None,:]
W=np.vstack([base[j%len(base)] for j in range(args.queries)]);design=grouped_design(W,'complete' if args.noise_kind=='signature-complete' else 'cycle') if args.noise_kind in ['signature-cycle','signature-complete'] else None;groups=[{'id':j,'leader':g[j%len(g)],'members':g} for j,g in enumerate(signature_groups(W))]
if args.noise_kind=='certified-partition':
    order=list(range(n)) if args.order=='metadata' else sorted(range(n),key=lambda i:tuple(W[:,i]))
    if args.order=='interleaved':order=sorted(range(n),key=lambda i:(i%8,i//8))
    design=certified_partition_dp(W,order,f=1,gamma_min=args.gamma_min,edge_cost=args.edge_cost)
    groups=plan(W,noise_groups=[b['members'] for b in design['blocks']])['groups']
if args.noise_kind=='independent':design={'a':np.ones(n)*(1+1e-7),'edges':[],'w':np.array([]),'certificate':{'passed':True,'worst_rho_upper':.5/(1+1e-7),'f':1,'global_scenarios_covered':n+1,'global_honest_coordinate_constraints_covered':n*n}}
if args.noise_kind=='unaware-cycle':
    d=uniform_tuned(np.ones((1,n)),'cycle');e=support(n,'cycle');design={'a':np.full(n,d['a']),'edges':e,'w':np.full(len(e),d['w']),'certificate':dict(d['certificate'],worst_rho_upper=d['worst_inverse']/2)}
if args.noise_kind=='robust-fixed-sdp':
    from src.baselines import robust_fixed_blocks
    design=robust_fixed_blocks(W,'complete')
if args.workload_shift:
    shifted=np.vstack([base,(np.arange(n)%3==0).astype(float)])
    W=np.vstack([shifted[j%len(shifted)] for j in range(args.queries)])
    groups=plan(W,noise_groups=[b['members'] for b in design['blocks']] if args.noise_kind=='certified-partition' else None)['groups']
with open('data/processed/electricity_kwh_clipped.f32','rb') as f:f.seek(100000*370*4);s=struct.unpack('<370f',f.read(370*4))
delta_l2=1.;report_dimension=1;intel_meta=None
if args.dataset=='intel':
    from src.intel import dataset as intel_dataset
    _,contributions,_,intel_meta=intel_dataset()
    if n>54:raise ValueError('Intel requires the declared public sensor roster; no synthetic replicas')
    s=contributions[0,:n].tolist();delta_l2=intel_meta['sensitivity']['delta_l2'];report_dimension=2
rho_total=rho_for_epsilon(1.,1e-6);rho=rho_total/args.epochs;noise_scale=.5/rho*delta_l2**2;peers=[]
for i in range(n):
    neighbors={str(v if u==i else u):float(w*noise_scale) for (u,v),w in zip(design['edges'],design['w']) if u==i or v==i}
    peers.append({'id':i,'n':n,'a':float(design['a'][i]*noise_scale),'s':s[i%len(s)],'neighbors':neighbors,'rho_per_release':rho,'rho_total':rho_total,'W':W.tolist(),'groups':groups,'delay_ms':args.delay_ms if i%4==0 else 0,'rate_bytes_s':args.rate_bytes_s if i%4==0 else 0})
if args.dataset=='intel':
    for peer in peers:peer.update(report_dimension=2,delta_l2=delta_l2,clip_interval=intel_meta['clip_interval'],encoding='availability_value')
certificate=dict(design['certificate'],base_certificate_rho=.5,rho_target=rho,worst_rho_upper=design['certificate']['worst_rho_upper']*delta_l2**2/noise_scale,uniform_noise_scale=noise_scale)
out={'visibility':'internal input fixture; per-peer inputs not received by protocol planner','noise_kind':args.noise_kind,'peers':peers,'certificate':certificate,'accountant':{'eps_total_bound':1.,'delta':1e-6,'rho_total':rho_total,'max_release_epochs':args.epochs,'rho_per_release':rho,'failures':'all exposed releases charged; failed query returns no result'},'input_label':'real first n UCI clients, row100000' if n<=370 else 'synthetic scale-up of 370 real client readings','query_label':'synthetic public ID workloads; repeat common subexpressions over one report vector','impairment':{'type':'application-level delay/rate emulation on every fourth peer','delay_ms':args.delay_ms,'rate_bytes_s':args.rate_bytes_s},'W':W.tolist()}
out.update(batch_remote=True,local_peer_count=min(8,n//2),dataset=args.dataset,retry_after_abort=args.retry_after_abort)
out['workload_variant']='near public coefficients' if args.near else 'workload shift with fixed previous noise plan' if args.workload_shift else 'hotspot' if args.hotspot else 'group'
if args.workload_shift:out['shift_scope']='new public modulo3 query, previous noise design unchanged, routes refined for current coefficients before fixed-epoch release; no dynamic/Byzantine claim'
if args.dataset=='intel':
    out['input_label']='real first n declared Intel sensor IDs on first public holdout day; unavailable entries included'
    out['missingness']='private availability/value pair; fixed public sensor-day membership'
    out['public_roster']={'sensor_ids':intel_meta['public_roster']['sensor_ids'][:n],'day':intel_meta['evaluation_days'][0],'calendar':intel_meta['public_roster']['days']}
    out['encoding']=intel_meta['sensitivity'];out['report_dimension']=report_dimension
    out['accountant']['joint_release']='two independent coordinate Gaussian masks/local noises with common spatial covariance; one joint L2 privacy charge'
if args.noise_kind=='certified-partition':
    out['noise_blocks']=[dict(b,a=b['a']*noise_scale,w=b['w']*noise_scale) for b in design['blocks']]
    out['partition_metadata']={k:v for k,v in design.items() if k not in ['a','edges','w','blocks']}
    out['public_order_source']=args.order
if args.numerical_rescale:
    from src.noise import certify
    history=[];edges=design['edges'];scale_used=1.
    for attempt in range(3):
        aa=np.asarray([p['a'] for p in peers]);ww=np.asarray([peers[u]['neighbors'][str(v)] for u,v in edges])
        c=certify(aa,edges,ww,delta_l2,rho,1)
        history.append({'attempt':attempt,'worst_rho_upper':c['worst_rho_upper'],'passed':c['passed'],'cumulative_noise_scale':scale_used})
        if c['passed']:break
        t=c['worst_rho_upper']/rho*(1+1e-6);scale_used*=t
        for peer in peers:
            peer['a']*=t;peer['neighbors']={j:w*t for j,w in peer['neighbors'].items()}
        for block in out.get('noise_blocks',[]):block['a']*=t;block['w']*=t
    else:raise ValueError('bounded numerical rescaling failed; no configuration released')
    out['numerical_rescaling']={'history':history,'factor':scale_used,'actual_query_variance_per_coordinate':float(__import__('src.noise',fromlist=['loss']).loss(W,aa,edges,ww)),'reason':'conservative residual/inverse gate with identical threat and rho; all variances increased together'}
    out['certificate']=c
out['peer_common']={'W':W.tolist(),'groups':groups}
for peer in peers:
    peer.pop('W');peer.pop('groups')
out['config_format']='compact common public workload/routing; expands to identical per-peer configurations'
pathlib.Path(args.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'n':n,'queries':len(W),'edges':len(design['edges']),'path':args.output,'rho_per_release':rho}))
