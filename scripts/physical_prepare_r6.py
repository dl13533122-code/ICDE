"""Frozen B6 public planning and configs, never inspecting private s for costs."""
import copy,datetime,hashlib,itertools,json,pathlib,sys,time,tracemalloc
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
from fractions import Fraction as F
from src.physical import *
from src.protocol import wire_fraction
from src.release_gate import validate_peer_config,rigorous_finite_certificate
from src.finite_reports import public_bound,public_preflight
from src.noise import rho_for_epsilon
ROOT=pathlib.Path(__file__).resolve().parents[1]

def save(path,data):pathlib.Path(path).write_text(json.dumps(data,indent=2,default=lambda x:str(x) if isinstance(x,F) else x.tolist() if isinstance(x,np.ndarray) else x)+'\n')

def response_sizes(W,n,d):
    rational=F(0)
    sizes=[]
    for i in range(n):
        ans={str(q):rational if d==1 else [rational]*d for q in range(i,len(W),n)}
        b=len((json.dumps({'answers':ans},separators=(',',':'),default=wire_fraction)+'\n').encode())
        sizes.append(((b+511)//512)*512)
    return sizes

def lzero(W,host_map,d):
    sizes=response_sizes(W,len(host_map),d);hosts=sorted(set(host_map));v=[5888+s for s in sizes]
    loads=[sum(v[i] for i,h in enumerate(host_map) if h==host) for host in hosts]
    loads[hosts.index('fu')]+=sum(v) # Controller sees only noisy reports/outputs.
    return tuple(loads),sizes

def fixed_design_plan(W,host_map,peers,noise_groups=None,l0=(0,0)):
    # Keep baseline mechanism; route with same intragroup-only sharing frames.
    groups=noise_groups or [list(range(len(peers)))]
    plans=[]
    for members in groups:
        pos={v:i for i,v in enumerate(members)}
        edges=[(pos[i],pos[int(j)]) for i in members for j in peers[i]['neighbors'] if i<int(j)]
        choices=[public_plan(W,members,host_map,h,edges) for h in sorted(set(host_map))]
        plans.append(choices)
    # Routing choices for a fixed mechanism also have additive resource
    # vectors; exact nondominated labels avoid enumerating 2**group_count.
    cs=[Candidate(i,i+1,str(j),F(0),p['loads'],p) for i,choices in enumerate(plans) for j,p in enumerate(choices)]
    out=resource_partition(len(plans),cs)
    x=min(out['frontier'],key=lambda a:(max(a.loads[h]+l0[h] for h in range(2)),sum(a.loads),a.loads))
    pp=[]
    while x.candidate:pp.append(x.candidate.payload);x=x.previous
    pp.reverse()
    routing=[]
    for p in pp:
        for g in p['groups']:routing.append(dict(id=len(routing),**g))
    return routing,tuple(sum(p['loads'][h] for p in pp) for h in range(2)),pp

def stats(out,l0,caps,peak):
    return dict(feasible=out['feasible'],error_exact=out['error'],analytic_error=float(out['error']) if out['error'] is not None else None,
      loads=list(out['loads']),total_loads=[x+y for x,y in zip(out['loads'],l0)] if out['feasible'] else None,
      rounded_loads=out['rounded_loads'],l0=l0,caps=caps,planning_seconds=out['planning_seconds'],peak_tracemalloc_bytes=peak,
      extensions=out['extensions'],labels_per_prefix=out['labels_per_prefix'],max_labels=out['max_labels'],H=out['H'],
      selected=[c.key for c in out['selected']],comparison=out['comparison'],scope=out['scope'])

def configure(base,W,groups,host_map,sizes,tag,design=None,public=None):
    cfg=copy.deepcopy(base);n=len(cfg['peers']);common=cfg['peer_common'];peers=[dict(common,**p) for p in cfg['peers']]
    common.update(W=np.asarray(W).tolist(),groups=groups);cfg['W']=np.asarray(W).tolist()
    for p in peers:p.update(W=common['W'],groups=groups,physical_frames=True)
    if design is not None:
        for i,p in enumerate(peers):
            p['a']=float(design['a'][i]);p['neighbors']={str(v if u==i else u):float(w) for (u,v),w in zip(design['edges'],design['w']) if u==i or v==i}
        cfg['noise_blocks']=design['blocks']
    cfg['certificate']=validate_peer_config(peers,cfg.get('noise_blocks'))
    cfg['rigorous_ideal_certificate']=rigorous_finite_certificate(peers)
    cfg['finite_proof']=public_bound(peers,common['finite_parameters'],cfg['accountant']['eps_total_bound'],22,cfg['accountant']['delta'])
    cfg['finite_arithmetic_preflight']=public_preflight(peers)
    if not cfg['finite_proof']['passed']:raise ValueError('unchanged finite parameters fail public bound')
    common['physical_frames']=True
    cfg['peers']=[{k:v for k,v in p.items() if k not in common} for p in peers]
    cfg.update(noise_kind=tag.split('_')[1],physical_frames=True,physical_control_response_bytes=sizes,routing_modes=['sharing'],local_peer_count=4,physical_plan_public=public,
               host_identity_evidence=['evidence/resources_r6_local.json','evidence/resources_r6_fy1.json'])
    save('experiments/protocol_config_'+tag+'.json',cfg)

if __name__=='__main__':
    freeze=json.loads(pathlib.Path('experiments/EVALUATION_FREEZE_r6.json').read_text());summary=[]
    for dataset,basepath in freeze['dataset_configs'].items():
        base=json.loads(pathlib.Path(basepath).read_text());n=len(base['peers']);W=np.array(base['peer_common']['W']);hosts=['fu']*4+['fy1']*(n-4);d=base.get('report_dimension',1);l0,sizes=lzero(W,hosts,d)
        peers=[dict(base['peer_common'],**p) for p in base['peers']];blocks=[b['members'] for b in base['noise_blocks']]
        # B5 keeps its original scalar partition and original leader choices.
        orig=[];calls=[]
        for group in base['peer_common']['groups']:
            g=group['members'];leader=group['leader'];orig.append(group)
            calls.extend((leader,i,'report') for i in g if i!=leader)
            calls.extend((o,leader,'partial') for o in sorted({qi%n for qi,row in enumerate(W) if row[g[0]]}) if o!=leader)
        calls.extend((i,int(j),'mask') for i,p in enumerate(peers) for j in p['neighbors'] if i<int(j))
        node=[0]*n
        for u,v,op in calls:node[u]+=sum(FRAME_BYTES[op]);node[v]+=sum(FRAME_BYTES[op])
        b5loads=tuple(sum(node[i] for i,h in enumerate(hosts) if h==host) for host in sorted(set(hosts)))
        b5total=tuple(x+y for x,y in zip(b5loads,l0));b5max=max(b5total)
        commonpublic=dict(host_map=hosts,hosts=sorted(set(hosts)),overlay_links=[['fu','fy1']],l0=l0,
            frame_bytes=FRAME_BYTES,control_response_bytes=sizes,cap_scope='fixed scientific application frames TX+RX at peers plus controller; TLS handshakes/SSH/TCP/monitoring measured overhead',
            public_order=list(range(n)),max_interval=8,gamma_min=.05,scenario_seed=20261006)
        commonpublic['b5_loads']=b5loads;commonpublic['b5_total_loads']=b5total
        configure(base,W,orig,hosts,sizes,dataset+'_b5_r6',public=commonpublic)
        tracemalloc.start();t0=time.perf_counter()
        cs=candidate_family(W,hosts,rho=base['accountant']['rho_per_release'],delta=peers[0].get('delta_l2',1.),max_interval=8,allowed_host_links=[('fu','fy1')])
        familytime=time.perf_counter()-t0
        independent=[c for c in cs if c.end-c.start==1];indout=resource_partition(n,independent)
        indtotal=tuple(x+y for x,y in zip(indout['loads'],l0))
        capslist={'balanced':tuple(F(4,5)*b5max for _ in range(2)), 'skew':(F(7,10)*b5total[0],F(21,20)*b5total[1]),'tight-independent':indtotal,'infeasible':l0}
        outputs={}
        for scenario,caps in capslist.items():
            out=resource_partition(n,cs,caps,l0,(4096,4096));peak=tracemalloc.get_traced_memory()[1]
            row=dict(dataset=dataset,scenario=scenario,candidate_count=len(cs),candidate_build_seconds=familytime,**stats(out,l0,caps,peak));summary.append(row);outputs[scenario]=out
            print(json.dumps(dict(dataset=dataset,scenario=scenario,feasible=out['feasible'],labels=out['max_labels'],seconds=out['planning_seconds'])),flush=True)
        chosen=outputs['balanced']
        if not chosen['feasible']:
            # Frozen alternate is full frontier, minimum maximum normalized load.
            ff=resource_partition(n,cs);chosenlabel=min(ff['frontier'],key=lambda a:(max((a.loads[h]+l0[h])/b5max for h in range(2)),a.error))
            selected=[];x=chosenlabel
            while x.candidate:selected.append(x.candidate);x=x.previous
            selected.reverse();chosen=dict(ff,selected=selected,error=chosenlabel.error,loads=chosenlabel.loads)
            summary.append(dict(dataset=dataset,scenario='full-frontier-minmax',**stats(chosen,l0,None,tracemalloc.get_traced_memory()[1])))
        design=assemble(chosen['selected'],n)
        selected_public=dict(commonpublic,selected=[c.key for c in chosen['selected']],predicted_loads=chosen['loads'],caps=capslist['balanced'] if outputs['balanced']['feasible'] else None)
        configure(base,W,design['groups'],hosts,sizes,dataset+'_b6_r6',design,selected_public)
        # Predetermined bad order; and old selected mechanism under shifted W.
        badorder=sorted(range(n),key=lambda i:(i%8,i//8))
        badcs=candidate_family(W,hosts,order=badorder,rho=base['accountant']['rho_per_release'],delta=peers[0].get('delta_l2',1.),max_interval=8,allowed_host_links=[('fu','fy1')])
        bad=resource_partition(n,badcs,capslist['balanced'],l0,(4096,4096));summary.append(dict(dataset=dataset,scenario='bad-order',**stats(bad,l0,capslist['balanced'],tracemalloc.get_traced_memory()[1])))
        shifted=np.vstack([W,(np.arange(n)%3==0).astype(float)]);shiftload=tuple(sum(public_plan(shifted,c.payload['members'],hosts,c.payload['plan']['leader_host'],robust_cycle_power(len(c.payload['members']),1) if c.payload['noise'].w else [])['loads'][h] for c in chosen['selected']) for h in range(2))
        shift_error=sum((error_exact(shifted,c.payload['members'],c.payload['noise'].a,robust_cycle_power(len(c.payload['members']),1) if c.payload['noise'].w else [],c.payload['noise'].w) for c in chosen['selected']),F(0))
        sd0,_=lzero(shifted,hosts,d);summary.append(dict(dataset=dataset,scenario='workload-shift-fixed-design',loads=shiftload,l0=sd0,total_loads=tuple(x+y for x,y in zip(shiftload,sd0)),analytic_error=float(shift_error),note='fixed selected covariance evaluated on shifted public workload; no optimum claim'))
        tracemalloc.stop()
        baseline_paths={'independent':f'experiments/protocol_config_{dataset}_independent_finite_r5'+('_retry1' if dataset=='electricity' else '')+'.json','signature':f'experiments/protocol_config_{dataset}_signature_cycle_finite_r5.json','sdp':f'experiments/protocol_config_{dataset}_robust_fixed_sdp_finite_r5.json'}
        for name,path in baseline_paths.items():
            cb=json.loads(pathlib.Path(path).read_text());pb=[dict(cb['peer_common'],**p) for p in cb['peers']]
            assert cb['peer_common']['W']==W.tolist() and [p['s'] for p in pb]==[p['s'] for p in peers]
            gg,ll,pp=fixed_design_plan(W,hosts,pb,[b['members'] for b in cb['noise_blocks']] if cb.get('noise_blocks') else None)
            configure(cb,W,gg,hosts,sizes,dataset+'_'+name+'_r6',public=dict(commonpublic,predicted_loads=ll))
        # Public workload-unaware full cycle construction, same finite rho and sensitivity.
        from src.partition import uniform_group_noise
        noise=uniform_group_noise(n,1,.05,rho=base['accountant']['rho_per_release'],delta=peers[0].get('delta_l2',1.))
        ud=dict(a=np.full(n,noise['a']),edges=noise['edges'],w=np.full(len(noise['edges']),noise['w']),blocks=[dict(members=list(range(n)),a=noise['a'],w=noise['w'],f=1)])
        pp=public_plan(W,list(range(n)),hosts,'fu',noise['edges'])
        gg=[dict(id=i,**g) for i,g in enumerate(pp['groups'])]
        configure(base,W,gg,hosts,sizes,dataset+'_unaware_r6',ud,dict(commonpublic,predicted_loads=pp['loads']))
        save('evidence/planning_r6.json',summary)
    save('evidence/planning_r6.json',summary)
