import copy,json,pathlib,sys,time,tracemalloc
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.physical_prepare_r6 import *
result=[]
for dataset in ['electricity','intel']:
 base=json.loads(pathlib.Path('experiments/protocol_config_'+dataset+'_b6_r6.json').read_text());common=base['peer_common'];n=len(base['peers']);W=np.array(common['W']);hostmap=base['physical_plan_public']['host_map'];pub=base['physical_plan_public'];l0=tuple(map(F,pub['l0']));p=[dict(common,**v) for v in base['peers']]
 cs=candidate_family(W,hostmap,rho=base['accountant']['rho_per_release'],delta=p[0].get('delta_l2',1.),max_interval=8,allowed_host_links=[('fu','fy1')]);selected=None
 for ratio in [F(85,100),F(9,10),F(95,100),F(1)]:
  cap=(ratio*max(pub['b5_total_loads']),)*2;tracemalloc.start();out=resource_partition(n,cs,cap,l0,(4096,4096));peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
  result.append(dict(dataset=dataset,ratio=str(ratio),**stats(out,l0,cap,peak)))
  if selected is None and out['feasible']:
   selected=out;design=assemble(out['selected'],n);configure(base,W,design['groups'],hostmap,base['physical_control_response_bytes'],dataset+'_cap_r6',design,dict(pub,caps=list(map(str,cap)),predicted_loads=list(map(str,out['loads'])),selected=[c.key for c in out['selected']],grid=4096,rounding_slack_bound=n*4096,selection='first feasible publicly frozen cap ratio'))
 shW=np.vstack([W,(np.arange(n)%3==0).astype(float)]);newgroups,loads,_=fixed_design_plan(shW,hostmap,p,[b['members'] for b in base['noise_blocks']]);sh0,sizes=lzero(shW,hostmap,base.get('report_dimension',1));configure(base,shW,newgroups,hostmap,sizes,dataset+'_shift_r6',public=dict(pub,l0=list(sh0),predicted_loads=loads,caps=None,scenario='public modulo3 row; original minload mechanism unchanged'))
pathlib.Path('evidence/cap_ratios_r6.json').write_text(json.dumps(result,indent=2,default=str)+'\n');print(json.dumps(result,default=str))
