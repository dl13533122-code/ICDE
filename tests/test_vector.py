import numpy as np
from src.vector import *
from src.noise import covariance,support

def test_vector_recalibration():
    S=histogram([.01,.08,.9]);assert np.all(S.sum(1)==1)
    delta=adjacency_case('histogram_owner_onehot_replace')['delta_l2'];assert np.isclose(delta,np.sqrt(2))
    e=support(3,'complete');a=np.ones(3);w=np.ones(3);z=sample_vector(a,e,w,S,delta,50000,19)
    total=(z-S).sum(1);assert np.allclose(total.var(0),np.full(4,6.),rtol=.04)
    assert adjacency_case('owner_vector_l2_cap1_replace')['delta_l2']==2
