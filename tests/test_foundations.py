import numpy as np
import pytest
import mpmath as mp
from src.noise import *

def test_negative_principal_submatrix():
    A,H=covariance([1,1],[(0,1)],[9]);hidden,H=covariance([1,1],[(0,1)],[9],(1,))
    assert 0.5/A[0,0]==0.05 and 0.5/hidden[0,0]==0.5
    assert not certify([1,1],[(0,1)],[9],1,.1)['passed']

@pytest.mark.parametrize('k',[2,3,6])
def test_variance(k):
    a=np.arange(k)+1.;e=support(k,'complete');w=np.full(len(e),2.)
    W=np.stack([np.ones(k),np.eye(k)[0],np.arange(k)]);A,H=covariance(a,e,w)
    assert np.isclose(loss(W,a,e,w),np.trace(W@A@W.T))
    z=sample_reports(a,e,w,np.zeros(k),50000,seed=71);v=np.var(z@W.T,axis=0)
    assert np.allclose(v,np.diag(W@A@W.T),rtol=.035)

def test_high_precision_derivative_downdate():
    a=np.array([.3,.7,1.]);e=[(0,1),(1,2),(0,2)];w=np.array([2.,3.,4.]);A,H=covariance(a,e,w)
    X,res=verified_inverse(A);mp.mp.dps=80;Y=np.array((mp.matrix(A.tolist())**-1).tolist(),float)
    assert np.allclose(X,Y,rtol=1e-13,atol=1e-13)
    new,den,der=diagonal_downdate(A,0,1,w[0]);eps=1e-5;B,H=covariance(a,e,w+[eps,0,0]);XX,_=verified_inverse(B)
    assert np.allclose((np.diag(XX)-np.diag(X))/eps,der,atol=1e-5)

@pytest.mark.parametrize('kind',['complete','cycle','regular','random'])
def test_spectral_every_deletion(kind):
    x=spectral_group(8,kind);c=certify(x['a'],x['edges'],x['w'],1,.5)
    assert c['passed'] and c['scenario_count']==9 and c['constraint_count']==64
    assert max(max(q['rho_upper']) for q in c['scenarios']) <= x['bound']/2+1e-10
    # NumPy and Python may sum the same floating-point values in different orders.
    assert np.isclose(loss(np.ones((1,8)),x['a'],x['edges'],x['w']),
                      sum(x['a']), rtol=8*np.finfo(float).eps, atol=0.)

def test_transfer_and_accountant():
    a=np.ones(3);e=support(3,'complete');w=np.ones(3)
    assert transfer_check(a,e,w,a*1.1,e,w*1.1,.2)['passed']
    assert not transfer_check(a,e,w,a*.1,e,w*.1,.2)['passed']
    for eps in [.25,.5,1,2,4,8]:assert np.isclose(epsilon(rho_for_epsilon(eps,1e-6),1e-6),eps)
    assert spectral_group(2,'complete')['edges']==[]

def test_solver_and_public_pipeline():
    W=np.array([[1,1,1],[1,1,0],[0,1,1]],float)
    x=optimize_fixed(W,support(3,'complete'),.5)
    assert x['certificate']['passed']
    y=sparse_candidate(W,.5);assert y['certificate']['passed']
