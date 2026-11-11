"""Reuse full370 R3 designs; freeze affected finite transport before outcomes."""
import copy,datetime,hashlib,json,pathlib,resource,struct,sys,time,tracemalloc
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from fractions import Fraction as F
from scripts.physical_prepare_r6 import save,lzero,configure,fixed_design_plan,stats
from src.physical import *
from src.planner import plan
from src.workloads import grouped_design

ROOT=pathlib.Path(__file__).resolve().parents[1]
source=pathlib.Path('experiments/partition_utility_r3/results.jsonl');retained={}
for i,line in enumerate(source.open()):
 r=json.loads(line)
 if (r['n'],r['group_size'],r['variant'],r['statistic'],r['eps_total'])==(370,8,'group','scalar',1):
  retained[r['method']]=(r,i+1,hashlib.sha256(line.encode()).hexdigest())
W=np.array(retained['partition-metadata'][0]['W']);n=W.shape[1]
assert W.shape==(55,370)
template=json.loads(pathlib.Path('experiments/protocol_config_electricity_certified_partition_finite_r5.json').read_text())
with pathlib.Path('data/processed/electricity_kwh_clipped.f32').open('rb') as f:f.seek(100000*370*4);s=struct.unpack('<370f',f.read(370*4))
hosts=['fu']*4+['fy1']*366;l0,sizes=lzero(W,hosts,1);rho=template['accountant']['rho_per_release'];scale=.5/rho
provenance=dict(source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),reuse={k:dict(line=v[1],line_sha256=v[2]) for k,v in retained.items()})
designs={name:copy.deepcopy(retained[orig][0]['design']) for name,orig in [('b5','partition-metadata'),('independent','independent'),('sdp','robust-fixed-block-SDP-complete'),('unaware','unaware-cycle-uniform')]}
designs['signature']=grouped_design(W,'cycle')
summary=[];cfgs={}
for name,d in designs.items():
 if name=='unaware':d.update(a=[d['a']]*n,edges=[tuple(sorted((i,(i+1)%n))) for i in range(n)],w=[d['w']]*n)
 a=np.array(d['a'])*scale;ee=d['edges'];ww=np.array(d['w'])*scale
 cfg=copy.deepcopy(template);cfg.pop('noise_blocks',None);cfg.pop('partition_metadata',None)
 cfg['peers']=[dict(template['peers'][0],id=i,n=n,a=float(a[i]),s=s[i],neighbors={str(v if u==i else u):float(w) for (u,v),w in zip(ee,ww) if u==i or v==i}) for i in range(n)]
 cfg['dataset']='electricity_full';cfg['input_label']='All370 original UCI clients, row100000, no replicas';cfg['W']=W.tolist();cfg['peer_common']['W']=W.tolist();cfg['full_roster_reuse']=provenance
 if name=='b5':
  cfg['noise_blocks']=[dict(b,a=b['a']*scale,w=b['w']*scale) for b in d['blocks']]
  gg=plan(W,noise_groups=[b['members'] for b in d['blocks']])['groups']
  # Count original scalar-plan routes without optimizing their leader choices.
  calls=[(i,int(j),'mask') for i,p in enumerate(cfg['peers']) for j in p['neighbors'] if i<int(j)]
  for g in gg:
   calls.extend((g['leader'],i,'report') for i in g['members'] if i!=g['leader'])
   calls.extend((o,g['leader'],'partial') for o in sorted({q%n for q,row in enumerate(W) if row[g['members'][0]]}) if o!=g['leader'])
  node=[0]*n
  for u,v,op in calls:node[u]+=sum(FRAME_BYTES[op]);node[v]+=sum(FRAME_BYTES[op])
  loads=tuple(sum(node[i] for i,h in enumerate(hosts) if h==host) for host in sorted(set(hosts)))
 else:
  groups=[b['members'] for b in d['blocks']] if d.get('blocks') else None
  gg,loads,_=fixed_design_plan(W,hosts,cfg['peers'],groups,l0)
 cfgs[name]=(cfg,gg,loads)
b5total=tuple(x+y for x,y in zip(cfgs['b5'][2],l0));b5max=max(b5total)
public=dict(host_map=hosts,hosts=sorted(set(hosts)),overlay_links=[['fu','fy1']],l0=l0,frame_bytes=FRAME_BYTES,control_response_bytes=sizes,b5_loads=cfgs['b5'][2],b5_total_loads=b5total,public_order=list(range(n)),max_interval=8,scenario_seed=20261006,cap_scope='fixed scientific endpoint application frames TX+RX including output/controller; TLS/SSH overhead measured separately')
for name,(cfg,gg,ll) in cfgs.items():
 configure(cfg,W,gg,hosts,sizes,'electricity_full_'+name+'_r6',public=dict(public,predicted_loads=ll))
 print(json.dumps(dict(config=name,n=n,utc=datetime.datetime.now(datetime.timezone.utc).isoformat())),flush=True)
base=cfgs['b5'][0]
tracemalloc.start();t0=time.perf_counter();cs=candidate_family(W,hosts,rho=rho,max_interval=8,allowed_host_links=[('fu','fy1')]);build=time.perf_counter()-t0
ff=None;chosen=None
capslist={'balanced':(F(4,5)*b5max,)*2,'skew':(F(7,10)*b5total[0],F(21,20)*b5total[1]),'infeasible':l0}
for scenario,caps in capslist.items():
 out=resource_partition(n,cs,caps,l0,(4096,4096));summary.append(dict(dataset='electricity_full',scenario=scenario,candidate_count=len(cs),candidate_build_seconds=build,**stats(out,l0,caps,tracemalloc.get_traced_memory()[1])))
 if scenario=='balanced' and out['feasible']:chosen=out
 print(json.dumps(dict(scenario=scenario,feasible=out['feasible'],labels=out['max_labels'],seconds=out['planning_seconds'])),flush=True)
if chosen is None:
 ff=resource_partition(n,cs);x=min(ff['frontier'],key=lambda a:(max(a.loads[h]+l0[h] for h in range(2)),a.error,a.loads));sel=[];p=x
 while p.candidate:sel.append(p.candidate);p=p.previous
 sel.reverse();chosen=dict(ff,selected=sel,error=x.error,loads=x.loads,rounded_loads=x.loads)
 summary.append(dict(dataset='electricity_full',scenario='full-frontier-minmax',**stats(chosen,l0,None,tracemalloc.get_traced_memory()[1])))
 dd=assemble(sel,n)
else:dd=assemble(chosen['selected'],n)
configure(base,W,dd['groups'],hosts,sizes,'electricity_full_b6_r6',dd,dict(public,predicted_loads=chosen['loads'],caps=capslist['balanced'] if summary[0]['feasible'] else None))
capchosen=None;capratio=None
for ratio in [F(85,100),F(9,10),F(95,100),F(1)]:
 caps=(ratio*b5max,)*2;out=resource_partition(n,cs,caps,l0,(4096,4096));summary.append(dict(dataset='electricity_full',scenario='cap-ratio-'+str(ratio),**stats(out,l0,caps,tracemalloc.get_traced_memory()[1])))
 if out['feasible'] and capchosen is None:capchosen=out;capratio=ratio
if capchosen:
 cd=assemble(capchosen['selected'],n);configure(base,W,cd['groups'],hosts,sizes,'electricity_full_cap_r6',cd,dict(public,predicted_loads=capchosen['loads'],caps=(capratio*b5max,)*2,cap_ratio=capratio))
badorder=sorted(range(n),key=lambda i:(i%8,i//8));bc=candidate_family(W,hosts,order=badorder,rho=rho,max_interval=8,allowed_host_links=[('fu','fy1')]);bad=resource_partition(n,bc,capslist['balanced'],l0,(4096,4096));summary.append(dict(dataset='electricity_full',scenario='bad-order',**stats(bad,l0,capslist['balanced'],tracemalloc.get_traced_memory()[1])))
shift=np.vstack([W,(np.arange(n)%3==0).astype(float)]);shift0,ss=lzero(shift,hosts,1);sg=[];sl=[0,0]
for c in chosen['selected']:
 p=c.payload;pp=public_plan(shift,p['members'],hosts,p['plan']['leader_host'],robust_cycle_power(len(p['members']),1) if p['noise'].w else [])
 for g in pp['groups']:sg.append(dict(id=len(sg),**g))
 for h in range(2):sl[h]+=pp['loads'][h]
configure(base,shift,sg,hosts,ss,'electricity_full_shift_r6',dd,dict(public,l0=shift0,predicted_loads=sl,caps=None,shift_scope='fixed chosen noise design; public routing refined for added modulo3 query'))
shift_error=sum((error_exact(shift,c.payload['members'],c.payload['noise'].a,robust_cycle_power(len(c.payload['members']),1) if c.payload['noise'].w else [],c.payload['noise'].w) for c in chosen['selected']),F(0))
summary.append(dict(dataset='electricity_full',scenario='workload-shift-fixed-design',loads=sl,l0=shift0,total_loads=[a+b for a,b in zip(sl,shift0)],analytic_error=float(shift_error),note='same public fixed design; no carried cap claim'))
tracemalloc.stop()
save('evidence/planning_full_roster_r6.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,source_reuse=provenance,rows=summary,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,grid=4096,capratio=capratio))
print(json.dumps(dict(candidate_build_seconds=build,candidates=len(cs),cap_ratio=str(capratio),done=True)),flush=True)
