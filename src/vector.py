"""Vector Gaussian recalibration, distinct owner/record adjacency."""
import numpy as np
from src.noise import sample_reports

def histogram(values,bins=(0.,.02,.1,.5,1.000001)):
    # One contribution per owner/epoch, public bin edges; replacement between
    # distinct bins has L2 sensitivity sqrt(2), not scalar Delta=1.
    values=np.asarray(values,float)
    if np.any(values<0) or np.any(values>1):raise ValueError('fixed scalar clipping required')
    ids=np.searchsorted(np.asarray(bins),values,side='right')-1
    return np.eye(len(bins)-1)[ids]

def sample_vector(a,edges,w,statistics,delta_l2,rounds,seed=20261005):
    S=np.asarray(statistics,float);d=S.shape[1];scale=delta_l2**2
    columns=[sample_reports(np.asarray(a)*scale,edges,np.asarray(w)*scale,S[:,j],rounds,seed+j*1000003) for j in range(d)]
    return np.stack(columns,axis=-1)

def adjacency_case(kind):
    if kind=='histogram_owner_onehot_replace':return {'delta_l2':float(np.sqrt(2)),'reason':'replace one normalized per-owner reading between public bins'}
    if kind=='owner_vector_l2_cap1_replace':return {'delta_l2':2.,'reason':'arbitrary replacement of two vectors each L2 norm <=1'}
    if kind=='record_histogram_add_remove':return {'delta_l2':1.,'reason':'add/remove one underlying record in one bin; excludes replacement and unlimited-owner changes'}
    if kind=='count_owner_binary_replace':return {'delta_l2':1.,'reason':'replace bounded binary per-owner predicate'}
    raise ValueError('explicit adjacency required')


def availability_value(values, lower=0., upper=1.):
    """Fixed public roster entries: unavailable -> (0,0), available -> (1,clip).

    None/nonfinite readings affect the private contribution, never membership.
    No centering, rescaling or norm clipping is applied to this encoding.
    """
    if not np.isfinite([lower, upper]).all() or lower > upper:
        raise ValueError('finite ordered clip interval required')
    V=np.asarray(values,dtype=float);A=np.isfinite(V)
    clipped=np.clip(np.where(A,V,0.),lower,upper)
    return np.stack([A.astype(float),np.where(A,clipped,0.)],axis=-1)


def availability_value_diameter(lower=0., upper=1.):
    """Exact replace-one L2 diameter of {(0,0)} union {(1,x): L<=x<=U}."""
    if not np.isfinite([lower, upper]).all() or lower > upper:
        raise ValueError('finite ordered clip interval required')
    same=float(upper-lower)
    changed=float(np.hypot(1.,max(abs(lower),abs(upper))))
    return dict(clip_interval=[float(lower),float(upper)],
        same_availability_distance=same,availability_change_distance=changed,
        delta_l2=max(same,changed),delta_l2_squared=max(same**2,1+max(lower**2,upper**2)),
        domain='(0,0) or (1,x), x in [L,U]',
        adjacency='replace one sensor-day bounded contribution; availability may change',
        derivation='same availability: |x-y|<=U-L, achieved at endpoints; availability change: sqrt(1+x^2), achieved at largest absolute endpoint; maximum of both')
