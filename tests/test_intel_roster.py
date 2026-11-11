import itertools,math,threading,time
import numpy as np
import pytest
from src.vector import availability_value,availability_value_diameter
from src.intel import dataset,public_roster
from src.partition import certified_partition_dp,uniform_group_noise,coalition_certificate
from src.release_gate import validate_peer_config
from src.protocol import Peer,blank,weighted_reports

@pytest.mark.parametrize('L,U',[(0,1),(-1,1),(-3,-2),(2,2),(-.2,.3)])
def test_exact_diameter_includes_both_replace_one_cases(L,U):
    d=availability_value_diameter(L,U)
    vertices=availability_value([None,L,U],L,U)
    exact=max(np.linalg.norm(x-y) for x,y in itertools.product(vertices,repeat=2))
    assert d['delta_l2']==pytest.approx(exact)
    assert d['same_availability_distance']==U-L
    assert d['availability_change_distance']==math.hypot(1,max(abs(L),abs(U)))
    assert d['delta_l2_squared']==pytest.approx(exact**2)
    assert np.array_equal(availability_value([None,-1e5,1e5],L,U),vertices)

def test_fixed_roster_includes_sensor_quality_and_calendar_absence():
    name,S,_,meta=dataset();r=public_roster()
    assert len(r['days'])==38 and len(r['sensor_ids'])==54
    assert S.shape==(12,54,2) and len(meta['evaluation_days'])==12
    assert np.isfinite(S).all() and set(np.unique(S[:,:,0]))<={0.,1.}
    assert np.all(S[:,:,1]>=0) and np.all(S[:,:,1]<=S[:,:,0])
    assert np.all(S[:,[4,27]]==0)
    assert np.all(S[-1]==0)  # Day dropped by previous quality-filtered calendar.
    assert public_roster()==r
    assert availability_value([0,None]).tolist()==[[1.,0.],[0.,0.]]

def test_joint_gate_rejects_scalar_calibration_and_checks_actual_induced_views():
    W=np.ones((1,6));d=certified_partition_dp(W);delta=math.sqrt(2)
    def fixture(scale):
        return [dict(id=i,a=float(d['a'][i])*scale,report_dimension=2,delta_l2=delta,
            clip_interval=[0.,1.],encoding='availability_value',rho_per_release=.5,
            neighbors={str(v if u==i else u):float(w)*scale for (u,v),w in zip(d['edges'],d['w']) if i in (u,v)}) for i in range(6)]
    blocks=[dict(b,a=b['a']*2,w=b['w']*2) for b in d['blocks']]
    assert validate_peer_config(fixture(2),blocks)['passed']
    with pytest.raises(ValueError):validate_peer_config(fixture(1),d['blocks'])
    wrong=fixture(2);wrong[0]['delta_l2']=1
    with pytest.raises(ValueError):validate_peer_config(wrong,blocks)

def test_joint_peer_masks_cancel_and_budget_charged_once(monkeypatch):
    monkeypatch.setattr('src.protocol.gaussian',lambda:0.)
    x=Peer.__new__(Peer);x.i=0;x.cfg=dict(s=[1.,.7],a=2.,report_dimension=2,rho_per_release=.3,rho_total=.6,neighbors={'1':2.})
    x.lock=threading.RLock();x.state='IDLE';x.history=[];x.rho_spent=0.;x.metrics=blank()
    x.dispatch(dict(op='prepare',epoch='joint'),'control');x.masks={1:[8.,-12.]}
    x.dispatch(dict(op='release'),'control')
    assert x.z==[9.,-11.3] and x.rho_spent==.3
    assert weighted_reports([1,1],[x.z,[-8.,12.]],2)==pytest.approx([1.,.7])
    x.dispatch(dict(op='abort'),'control')
    x.dispatch(dict(op='prepare',epoch='retry'),'control');x.masks={1:[1.,2.]}
    x.dispatch(dict(op='release'),'control');assert x.rho_spent==.6
    x.dispatch(dict(op='abort'),'control');x.dispatch(dict(op='prepare',epoch='third'),'control');x.masks={1:[0.,0.]}
    with pytest.raises(ValueError,match='budget'):x.dispatch(dict(op='release'),'control')

def test_vector_query_sharing_has_correct_coefficients_and_empty_queries():
    x=Peer.__new__(Peer);x.i=0;x.cfg=dict(n=2,report_dimension=2,W=[[2,2],[0,0],[0,0]],groups=[dict(id=0,leader=0,members=[0,1])])
    x.z=[1,3];x.partial={'0':[5,10]};x.phase={};x.state='RELEASED';x.started=time.perf_counter()
    x.call=lambda j,msg:dict(z=[4,7])
    a=x.dispatch(dict(op='aggregate',mode='query',sharing=True),'control')['answers']
    b=x.dispatch(dict(op='aggregate',mode='query',sharing=False),'control')['answers']
    assert a==b=={'0':[10.,20.],'2':[0.,0.]}

@pytest.mark.parametrize('k,f',[(1,0),(2,1),(3,2),(5,4),(1,2)])
def test_b2_nontrivial_gain_boundary(k,f):
    d=uniform_group_noise(k,f,.05)
    assert d['w']==0 and d['edges']==[] and d['a']>=1
    c=coalition_certificate(k,f,d['a'],d['w'],exhaustive=True)
    assert c['passed'] and c['h_min']==1
    with pytest.raises(ValueError,match='fallback'):coalition_certificate(k,f,d['a'],1.)


def test_legacy_scalar_dataset_entrypoint_cannot_restore_intel_membership_strata():
    from scripts.full_utility import datasets
    names=[name for name,_,_,_ in datasets()]
    assert names==['electricity-full-370']
