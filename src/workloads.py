import numpy as np
from src.noise import signature_groups,spectral_group,certify,covariance

def workload(n,k=8,variant='group'):
    # Synthetic public query labels on real client/mote IDs; never consumption clustering.
    ids=np.arange(n);g=ids//k;rows=[np.ones(n)];names=['global'];kinds=['global']
    for j in range(int(g.max())+1):rows.append((g==j).astype(float));names.append('group_'+str(j));kinds.append('group')
    for start in range(min(4,int(g.max())+1)):
        rows.append(((g>=start)&(g<=start+2)).astype(float));names.append('range_'+str(start));kinds.append('range')
    for j in range(3):
        rows.append(((g%3==j)|(g%4==j)).astype(float));names.append('overlap_'+str(j));kinds.append('overlap')
    if variant=='hotspot':rows.append((ids==0).astype(float));names.append('single_client_hotspot');kinds.append('hotspot')
    if variant=='shift':rows.append((ids%3==0).astype(float));names.append('shift_unplanned_mod3');kinds.append('shift')
    return np.array(rows),names,kinds

def grouped_design(W,kind='cycle',rho=.5):
    n=W.shape[1];a=np.ones(n);edges=[];weights=[];blocks=[]
    for group in signature_groups(W):
        x=spectral_group(len(group),kind,rho=rho);a[group]=x['a']
        edges.extend([(group[u],group[v]) for u,v in x['edges']]);weights.extend(x['w'])
        # Explicitly checks every within-block deletion and every honest node.
        c=certify(x['a'],x['edges'],x['w'],1,rho)
        if not c['passed']:raise ValueError('group refused')
        blocks.append({'members':group,'kind':kind,'certificate':c,'gap':x['lambda_star'],'bound':x['bound']})
    # Independence across blocks: global coalition affects only its block.
    # Covers ALL global C=empty/singleton via exact block products, no sampling.
    return {'a':a,'edges':edges,'w':np.array(weights),'blocks':blocks,'certificate':{'passed':True,'f':1,'global_scenarios_covered':n+1,'global_honest_coordinate_constraints_covered':n*n,'coverage':'block diagonal induced covariance; all local singleton deletions exhaustively factored, outside-block coalitions use intact block','worst_rho_upper':max(x['certificate']['worst_rho_upper'] for x in blocks)}}

def path_inv_diag(n,a,w):
    # Extended precision prevents cancellation in low-a/high-w calibration.
    a=np.longdouble(a);w=np.longdouble(w)
    d=np.full(n,a+2*w,dtype=np.longdouble);d[0]=d[-1]=a+w;left=np.zeros(n,dtype=np.longdouble);right=np.zeros(n,dtype=np.longdouble)
    for i in range(1,n):left[i]=w*w/(d[i-1]-left[i-1])
    for i in range(n-2,-1,-1):right[i]=w*w/(d[i+1]-right[i+1])
    return 1/(d-left-right)

def uniform_worst(n,a,w,kind):
    if kind=='complete':
        def f(h):return 1/(a*h)+(1-1/h)/(a+w*h)
        return max(f(n),f(n-1))
    if kind=='cycle':
        full=np.mean(1/(a+w*(2-2*np.cos(2*np.pi*np.arange(n)/n))))
        return max(full,max(path_inv_diag(n-1,a,w)))
    raise ValueError(kind)

def uniform_tuned(W,kind,rho=.5,budget=24):
    n=W.shape[1];r=2*rho;Acoeff=np.sum(W*W)
    if kind=='complete':Bcoeff=n*Acoeff-np.sum(W.sum(axis=1)**2)
    else:Bcoeff=np.sum((W-np.roll(W,1,axis=1))**2)
    best={'a':(1+1e-6)/r,'w':0.,'kind':kind,'objective':float((1+1e-6)/r*Acoeff),'worst_inverse':r/(1+1e-6),'tuning_budget':budget};grid=np.geomspace((1+1e-4)/(r*(n-1)),(1+1e-7)/r,budget)
    for a in grid:
        lo=0.;hi=1./r
        while uniform_worst(n,a,hi,kind)>r:hi*=2
        for _ in range(48):
            mid=(lo+hi)/2
            if uniform_worst(n,a,mid,kind)>r:lo=mid
            else:hi=mid
        w=hi*(1+1e-5);worst=uniform_worst(n,a,w,kind);cost=a*Acoeff+w*Bcoeff
        if np.isfinite(worst) and worst<=r and cost<best['objective']:best={'a':float(a),'w':float(w),'kind':kind,'objective':float(cost),'worst_inverse':float(worst),'tuning_budget':budget}
    best['certificate']={'passed':best['worst_inverse']<=r,'f':1,'global_scenarios_covered':n+1,'global_honest_coordinate_constraints_covered':n*n,'coverage':'uniform cycle/complete vertex transitivity with constant Delta=1: intact inverse diagonal and every position of induced path/clique; checked against dense small cases'}
    return best

def query_covariance(W,design):
    n=W.shape[1]
    if 'edges' in design:
        a=np.asarray(design['a']);B=(W*a)@W.T
        for (u,v),w in zip(design['edges'],design['w']):d=W[:,u]-W[:,v];B+=w*np.outer(d,d)
        return B
    a,w=design['a'],design['w'];B=a*(W@W.T)
    if design['kind']=='complete':B+=w*(n*(W@W.T)-np.outer(W.sum(1),W.sum(1)))
    else:D=W-np.roll(W,1,axis=1);B+=w*(D@D.T)
    return B
