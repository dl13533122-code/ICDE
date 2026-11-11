import numpy as np
from src.noise import *
from src.workloads import *

def test_symmetry_certificate_matches_every_coalition():
    for n in [3,8,16]:
        for kind in ['cycle','complete']:
            a=.4;w=2.;e=support(n,kind);c=certify(np.full(n,a),e,np.full(len(e),w),1,100)
            assert np.isclose(c['worst_rho_upper'],uniform_worst(n,a,w,kind)/2,atol=1e-10)

def test_block_coverage_matches_dense():
    W,_,_=workload(16,4);x=grouped_design(W);c=certify(x['a'],x['edges'],x['w'],1,.5)
    assert c['passed'] and c['constraint_count']==256
    assert np.isclose(c['worst_rho_upper'],x['certificate']['worst_rho_upper'],atol=1e-10)
    assert np.allclose(query_covariance(W,x),W@covariance(x['a'],x['edges'],x['w'])[0]@W.T)
