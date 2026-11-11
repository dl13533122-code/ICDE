"""Recover and verify existing finite cases without generating private reports."""
import datetime,hashlib,json,pathlib,platform,sys
from fractions import Fraction as F
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from flint import arb,ctx
from src.finite_reports import public_bound,public_preflight,bounds
from src.protocol import read_fraction,weighted_reports
OUT=pathlib.Path('evidence/finite_transcript_r5b');OUT.mkdir(exist_ok=True)
checks=[]
for path in sorted(pathlib.Path('experiments/protocol').glob('*finite_r5*/manifest.json')):
    raw=path.read_bytes();m=json.loads(raw,object_hook=read_fraction)
    cp=pathlib.Path(m['internal_fixture_path']);cfg=json.loads(cp.read_text());common=cfg['peer_common']
    peers=[dict(common,**p) for p in cfg['peers']];a=cfg['accountant'];p=common['finite_parameters']
    assert hashlib.sha256(cp.read_bytes()).hexdigest()==m['config_sha256']
    assert all(0<=F(v)<=1 for pp in peers for v in ([pp['s']] if pp.get('report_dimension',1)==1 else pp['s']))
    if cfg.get('report_dimension',1)==2:
        assert cfg['public_roster']['sensor_ids']==list(range(1,55))
        assert all(pp['encoding']=='availability_value' and pp['delta_l2']**2>1.999999999999 for pp in peers)
        assert all(pp['s'][0] in (0,1) and (pp['s'][0]!=0 or pp['s'][1]==0) for pp in peers)
    proof=public_bound(peers,p,a['eps_total_bound'],a['max_release_epochs'],a['delta'])
    assert proof['passed'] and proof['beta_upper_exact']==cfg['finite_proof']['beta_upper_exact']
    capacity=public_preflight(peers,p)
    with ctx.workprec(512):
        rho=arb(str(F(peers[0]['rho_per_release'])*a['max_release_epochs']))
        deltaG=arb(str(F(a['delta'])/2))
        epsilon=rho+2*(rho*(1/deltaG).log()).sqrt()
        assert epsilon.upper()<=arb(str(F(a['eps_total_bound'])))
        totaldelta=F(a['delta'])/2+F(proof['numerical_delta_upper_exact'])
        assert totaldelta<=F(a['delta'])
        epsupper=str(bounds(epsilon)[1])
    for pp in peers:
        for j,w in pp['neighbors'].items():assert peers[int(j)]['neighbors'][str(pp['id'])]==w
    edgecount=sum(len(pp['neighbors']) for pp in peers)//2
    assert proof['M']==(len(peers)+edgecount)*cfg.get('report_dimension',1)
    for tr in m['trials']:
        if tr.get('status')=='ABORT':continue
        for j,row in enumerate(common['W']):
            assert weighted_reports(row,tr['public_reports'],cfg.get('report_dimension',1))==tr['answers'][str(j)]
    retry=m['fresh_retry_after_abort'];assert retry and retry['arithmetic_max_error']==0
    assert all(m['epoch_reuse_refused'])
    for node in retry['metrics']:
        h=node['history'];assert len(h)==22 and len({x['epoch'] for x in h})==22
        assert h[-2]['state']=='ABORTED' and h[-1]['state']=='FINISHED'
        # Finite backend charges prepared attempts, including unexposed peers.
        for j,x in enumerate(h):assert abs(x['rho_spent_cumulative']-(j+1)*peers[node['id']]['rho_per_release'])<1e-14
    scratch=pathlib.Path('/home/fu/.local/state/server-history-codex/tmp/B-fuyue-20261005-v1/peers')/m['tag']
    staged={}
    for source,name in [('src/protocol.py','protocol.py'),('src/finite_reports.py','finite_reports.py')]:
        value=hashlib.sha256((scratch/name).read_bytes()).hexdigest()
        assert value==m['code_sha256'][source];staged[source]=value
    row=dict(tag=m['tag'],status='LOCALLY_VERIFIED',raw_path=str(path),raw_sha256=hashlib.sha256(raw).hexdigest(),config_sha256=m['config_sha256'],
             staged_code_sha256=staged,trials=len(m['trials']),attempts=22,exposed_aborts=1,fresh_retries=1,
             epsilon_total=a['eps_total_bound'],ideal_epsilon_upper_exact=epsupper,
             delta_total=a['delta'],delta_G=a['delta']/2,numerical_delta_upper=proof['numerical_delta_upper'],
             total_delta_upper_exact=str(totaldelta),M=proof['M'],beta_upper_exact=proof['beta_upper_exact'],
             arithmetic_preflight=capacity,pre_exposure_wire_gate_recorded=(path.parent/'finite_arithmetic_preflight.json').exists(),
             transcript='all complete grid reports and any prefix, fixed-form abort/ready bits, coalition finite bins (including own node and incident edges), fixed public roster/workload/schedule; ideal secure channels',
             ideal_reference='postprocess full ideal incident Gaussian view into floor(2^b Phi(Z)) bins and complete-report grid outputs; continuous mask disclosures are not the compared digital transcript',
             excluded='internal fixtures, keys, honest hidden coins, internal numerical diagnostics/CPU/RSS/timing logs; wall-clock/cache/hardware/scheduler side channels',
             computational_assumptions='TLS security and OS CSPRNG distinguishing advantage separate from statistical delta',
             scientific_acceptance='NOT_REVIEWED')
    checks.append(row);(OUT/(m['tag']+'.json')).write_text(json.dumps(row,indent=2)+'\n')
result=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),python=platform.python_version(),runs=checks,
            all_passed=True,uniform_bound_derivation='web B5 bridge; interval/remainder proofs and exact arithmetic, not empirical sampler tests; retrospective public capacity proof for seven predecessor cases, enforced before missing case',
            theory_status='web theorem review pending; local checks establish configured hypotheses, not scientific acceptance')
(OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(runs=len(checks),trials=sum(x['trials'] for x in checks),attempts=sum(x['attempts'] for x in checks),all_passed=True)))
