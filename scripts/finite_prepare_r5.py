"""Public-only recalibration BEFORE finite coins or real data reports."""
import argparse,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from src.noise import rho_for_epsilon
from src.release_gate import validate_peer_config,rigorous_finite_certificate
from src.finite_reports import DEFAULT,public_bound,public_preflight
p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');args=p.parse_args()
cfg=json.loads(pathlib.Path(args.input).read_text());common=cfg['peer_common'];peers=[dict(common,**v) for v in cfg['peers']];oldrho=cfg['accountant']['rho_total'];a=cfg['accountant'];newrho=rho_for_epsilon(a['eps_total_bound'],a['delta']/2)*(1-1e-9);factor=oldrho/newrho
for pp in peers:
    pp['a']*=factor;pp['neighbors']={j:w*factor for j,w in pp['neighbors'].items()}
    pp['rho_total']=newrho;pp['rho_per_release']=newrho/a['max_release_epochs'];pp['finite_parameters']=DEFAULT
    pp['max_prepared_attempts']=a['max_release_epochs']
for b in cfg.get('noise_blocks',[]):b['a']*=factor;b['w']*=factor
cfg['certificate']=validate_peer_config(peers,cfg.get('noise_blocks'))
t=time.perf_counter();cfg['rigorous_ideal_certificate']=rigorous_finite_certificate(peers)
proof=public_bound(peers,epsilon=a['eps_total_bound'],attempts=a['max_release_epochs'],delta_total=a['delta'])
if not proof['passed']:raise ValueError('public numerical budget does not pass; no data run')
cfg['finite_arithmetic_preflight']=public_preflight(peers)
proof['evaluation_seconds']=time.perf_counter()-t;cfg['finite_proof']=proof
cfg['peers']=[{k:v for k,v in pp.items() if k not in common} for pp in peers]
# Common public precision ensures peers cannot silently select different samplers.
cfg['peer_common']['finite_parameters']=dict(DEFAULT)
for pp in cfg['peers']:pp.pop('finite_parameters')
a.update(rho_total=newrho,rho_per_release=newrho/a['max_release_epochs'],delta_G=a['delta']/2,delta_numerical_reserved=a['delta']/2,numerical_delta_bound=proof['numerical_delta_upper'],attempt_charging='every prepared attempt, including all sampled/exposed aborts and retries')
cfg['noise_reserve_factor']=factor
pathlib.Path(args.output).write_text(json.dumps(cfg,indent=2)+'\n')
print(json.dumps({'output':args.output,'beta':proof['beta_upper'],'delta_numerical':proof['numerical_delta_upper'],'M':proof['M'],'reserve_factor':factor,'rigorous_certificate':cfg['rigorous_ideal_certificate']}))
