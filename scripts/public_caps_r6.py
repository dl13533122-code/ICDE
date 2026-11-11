import sys,pathlib,json,tracemalloc,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from src.physical import *
from src.noise import loss
results=[]
planning=json.loads(pathlib.Path('evidence/planning_r6.json').read_text())
for dataset in ['electricity','intel']:
 cfg=json.loads(pathlib.Path('experiments/protocol_config_'+dataset+'_b6_r6.json').read_text());common=cfg['peer_common'];peers=[dict(common,**p) for p in cfg['peers']];W=np.array(common['W']);public=cfg['physical_plan_public'];n=len(peers);hosts=public['host_map'];l0=tuple(map(F,public['l0']))
 cs=candidate_family(W,hosts,rho=cfg['accountant']['rho_per_release'],delta=peers[0].get('delta_l2',1.),max_interval=8,allowed_host_links=[('fu','fy1')])
 for scenario in ['balanced','skew','tight-independent']:
  row=next(r for r in planning if r['dataset']==dataset and r['scenario']==scenario);caps=tuple(map(F,row['caps']));tracemalloc.start();out=resource_partition(n,cs,caps,l0);peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
  results.append(dict(dataset=dataset,scenario=scenario,exact_feasible=out['feasible'],grid_feasible=row['feasible'],exact_error=float(out['error']) if out['error'] is not None else None,planning_seconds=out['planning_seconds'],max_labels=out['max_labels'],peak_bytes=peak,caps=list(map(str,caps))))
 # Minimal public endpoint caps supporting the frozen deployed min-load plan.
 cap=tuple(F(l)+b for l,b in zip(public['predicted_loads'],l0));out=resource_partition(n,cs,cap,l0)
 results.append(dict(dataset=dataset,scenario='deployed-minload-caps',caps=list(map(str,cap)),feasible=out['feasible'],error=float(out['error']),all_independent=all(c.payload['noise'].w==0 for c in out['selected']),b5_overloaded=any(F(a)>b for a,b in zip(public['b5_total_loads'],cap)),max_labels=out['max_labels'],planning_seconds=out['planning_seconds'],note='public costs only; cap-feasibility diagnostic of frozen deployed full-frontier choice; no new result-dependent deployment'))
 # Repair only erroneous placeholder in initial shifted error summary.
 sh=next(r for r in planning if r['dataset']==dataset and r['scenario']=='workload-shift-fixed-design');WW=np.vstack([W,(np.arange(n)%3==0).astype(float)]);edges=[(i,int(j)) for i,p in enumerate(peers) for j in p['neighbors'] if i<int(j)];ws=[peers[i]['neighbors'][str(j)] for i,j in edges]
 sh['analytic_error']=loss(WW,[p['a'] for p in peers],edges,ws);sh['note']='mechanically evaluated fixed covariance under shifted public workload; no optimization claim'
pathlib.Path('evidence/public_caps_r6.json').write_text(json.dumps(results,indent=2)+'\n');pathlib.Path('evidence/planning_r6.json').write_text(json.dumps(planning,indent=2)+'\n');print(json.dumps(results))
