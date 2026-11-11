"""Reconcile saved B2 evidence with the owner-specified theorem assumptions."""
import datetime,hashlib,itertools,json,math,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from src.partition import coalition_certificate,uniform_group_noise

sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
p=pathlib.Path('experiments/partition_diagnostics_r3/results.json');d=json.loads(p.read_text())
assert d['code_hashes']['src/partition.py']==sha('evidence/code_revisions/before_intel_roster_r4/src/partition.py')
# No existing scientific experiment is rerun. Counts classify prior exhaustive
# inverses by valid exact-f domain versus software fallback diagnostics.
counts=dict(lower_bound_parameter_cases=0,outside_lower_bound_fallback_parameter_cases=0,nontrivial_parameter_cases=0,boundary_parameter_cases=0)
for k in d['exhaustive']['k']:
    for f in d['exhaustive']['f']:
        key='lower_bound_parameter_cases' if f<=k-1 else 'outside_lower_bound_fallback_parameter_cases'
        counts[key]+=len(d['exhaustive']['gamma'])
        counts['nontrivial_parameter_cases' if k>=f+2 else 'boundary_parameter_cases']+=len(d['exhaustive']['gamma'])
# Direct boundary evidence is small, not a repeat of the prior full diagnostics.
boundaries=[]
for k in range(1,11):
    f=k-1;x=uniform_group_noise(k,f,.05);c=coalition_certificate(k,f,x['a'],x['w'])
    assert x['w']==0 and not x['edges'] and c['passed'] and c['lower_bound_domain'] and not c['nontrivial_hidden_peer_gain']
    outside=coalition_certificate(k,k,x['a'],0.)
    assert not outside['lower_bound_domain']
    boundaries.append(dict(k=k,f=f,a=x['a'],w=x['w'],certificate=c,outside_f_k_lower_bound_domain=outside['lower_bound_domain']))
# Existing partition diagnostics/utility enumerate the declared family only.
assert 'counterexamples' in d and 'complexity' in d
record=dict(status='LOCALLY_VERIFIED',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    command=sys.executable+' scripts/validate_b2_r4.py',script_sha256=sha(__file__),source_path=str(p),source_sha256=sha(p),counts=counts,
    theorem_domain=dict(protocol='ideal continuous-Gaussian fixed-epoch pair masks z=s+nu+Br',coalition='reveals local noise and all incident masks; conditioned covariance diag(a_H)+L_G[H]',
        lower_bound='integer 0<=f<=k-1; homogeneous scalar Delta; every exact-f within-group coalition; h=k-f>=1',
        gain='k>=f+2; uniform a/w cycle power p=f+1; gamma>0, finite w; independent fallback for k<=f+1',
        workload='public W; public disjoint groups; internal group masks only; identical columns required for lower-bound utility factor',
        partition='one public ordered contiguous family and declared public costs/gamma options; numerical DP optimum, not global optimum; max physical congestion is not additive'),
    saved_exhaustive=d['exhaustive'],boundaries=boundaries,
    preserved_negative_results=d['counterexamples'],finite_precision_evidence=d['finite_precision'],
    remaining='web theory/novelty review and finite-precision cryptographic implementation privacy; actual deployments f=1 honest-but-curious only',
    acceptance='no web scientific acceptance or conference acceptance')
pathlib.Path('evidence/b2_assumptions_r4.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(counts))
