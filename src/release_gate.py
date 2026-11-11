"""Reject graph/covariance changes before participant report release."""
import hashlib,json,time
import numpy as np
from src.noise import certify

def validate_peer_config(peers,noise_blocks=None):
    t=time.perf_counter();n=len(peers);a=np.array([p['a'] for p in peers]);rhos={p['rho_per_release'] for p in peers}
    if len(rhos)!=1 or [p['id'] for p in peers]!=list(range(n)):raise ValueError('ambiguous accountant/membership')
    rho=next(iter(rhos));edges=[];weights=[]
    dimensions={p.get('report_dimension',1) for p in peers}
    deltas={p.get('delta_l2',1.) for p in peers}
    if len(dimensions)!=1 or len(deltas)!=1:raise ValueError('ambiguous joint encoding')
    dimension=next(iter(dimensions));delta=next(iter(deltas))
    if dimension==2:
        from src.vector import availability_value_diameter
        intervals={tuple(p.get('clip_interval',[])) for p in peers}
        if len(intervals)!=1 or len(next(iter(intervals)))!=2:raise ValueError('explicit clip interval required')
        exact=availability_value_diameter(*next(iter(intervals)))['delta_l2']
        if delta!=exact:raise ValueError('joint sensitivity disagrees with exact encoding diameter')
        if any(p.get('encoding')!='availability_value' for p in peers):raise ValueError('unsupported joint encoding')
    elif dimension!=1 or delta!=1.:raise ValueError('unsupported encoding/sensitivity')
    for p in peers:
        i=p['id']
        for jj,w in p['neighbors'].items():
            j=int(jj)
            if not 0<=j<n or i==j or peers[j]['neighbors'].get(str(i))!=w:raise ValueError('asymmetric or invalid peer mask support')
            if i<j:edges.append((i,j));weights.append(w)
    if noise_blocks is not None:
        from src.partition import robust_cycle_power,coalition_certificate
        if sorted(i for b in noise_blocks for i in b['members'])!=list(range(n)):
            raise ValueError('construction blocks must partition membership')
        expected={};checked=[]
        for b in noise_blocks:
            members=b['members'];k=len(members);f=b['f']
            if f!=1:raise ValueError('deployed fixed-epoch scope is f=1 only')
            if any(a[i]!=b['a'] for i in members):raise ValueError('independent variance disagrees with construction')
            local=robust_cycle_power(k,f) if b['w'] else []
            for u,v in local:expected[tuple(sorted((members[u],members[v])))]=b['w']
            certificate=coalition_certificate(k,f,b['a'],b['w'],rho,delta,exhaustive=k<=12)
            if not certificate['passed']:raise ValueError('construction refused before release')
            if k<=12:
                numerical=certify(np.full(k,b['a']),local,np.full(len(local),b['w']),delta,rho,f)
                if not numerical['passed']:raise ValueError('finite-precision inverse verification refused before release')
                certificate['numerical_inverse_guard']=dict(passed=True,worst_rho_upper=numerical['worst_rho_upper'],max_residual=numerical['max_residual'])
            checked.append({'nodes':members,'certificate':certificate})
        if dict(zip(edges,weights))!=expected:raise ValueError('actual mask graph differs from certified construction')
        public={'a':a.tolist(),'edges':edges,'weights':weights,'rho_per_release':rho,'Delta':delta,'report_dimension':dimension,'family':'all empty/singleton coalitions'}
        return {'passed':True,'f':1,'worst_rho_upper':max(b['certificate']['worst_rho_upper'] for b in checked),
            'rho_target':rho,'blocks':checked,'scenario_count':n+1,'constraint_count':n*n,
            'coverage':'verified exact cycle-power support/uniform weights and analytic all-deletion spectral certificate; independent blocks; small blocks additionally factored exhaustively',
            'public_parameter_sha256':hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest(),
            'verification_seconds':time.perf_counter()-t}
    # Public graph components are independent covariance blocks. Certify every
    # local deletion; outside-block coalitions preserve the intact local view.
    adjacency=[set() for _ in range(n)]
    for u,v in edges:adjacency[u].add(v);adjacency[v].add(u)
    todo=set(range(n));blocks=[]
    while todo:
        root=min(todo);component={root};front=[root];todo.remove(root)
        while front:
            u=front.pop()
            for v in adjacency[u]:
                if v in todo:todo.remove(v);component.add(v);front.append(v)
        H=sorted(component);pos={v:i for i,v in enumerate(H)};e=[];w=[]
        for (u,v),value in zip(edges,weights):
            if u in component:e.append((pos[u],pos[v]));w.append(value)
        cycle={tuple(sorted((j,(j+1)%len(H)))) for j in range(len(H))}
        if len(H)>12 and set(e)==cycle and len(set(a[H]))==1 and len(set(w))==1:
            from src.workloads import uniform_worst
            upper=float(np.nextafter(uniform_worst(len(H),a[H][0],w[0],'cycle')*delta**2/2,np.inf))
            local=dict(passed=upper<=rho,worst_rho_upper=upper,f=1,
                coverage='uniform cycle rotation symmetry; intact circulant and every coordinate of singleton-deletion path; rigorous Arb gate additionally required for finite runs')
        else:local=certify(a[H],e,w,delta,rho,1)
        blocks.append({'nodes':H,'certificate':local})
    worst=max(b['certificate']['worst_rho_upper'] for b in blocks)
    c={'passed':all(b['certificate']['passed'] for b in blocks),'worst_rho_upper':worst,'rho_target':rho,'f':1,'scenario_count':n+1,'constraint_count':n*n,'blocks':blocks,'coverage':'all global empty/singleton views via independently factorized components; exhaustive every local deletion and honest coordinate'}
    if not c['passed']:raise ValueError('graph refused before release: worst rho '+str(c['worst_rho_upper'])+' exceeds '+str(rho))
    public={'a':a.tolist(),'edges':edges,'weights':weights,'rho_per_release':rho,'Delta':delta,'report_dimension':dimension,'family':'all empty/singleton coalitions'}
    c['public_parameter_sha256']=hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest();c['verification_seconds']=time.perf_counter()-t
    return c

def rigorous_finite_certificate(peers):
    """Rigorous inverse-diagonal check of exact public IEEE-dyadic variances.

    Each connected component and every empty/singleton local coalition is
    checked. This is not a claim of scientific theorem acceptance.
    """
    from flint import arb,arb_mat,ctx
    from fractions import Fraction
    t=time.perf_counter();n=len(peers);adj=[set() for _ in peers]
    for p in peers:
        for j in p['neighbors']:adj[p['id']].add(int(j))
    todo=set(range(n));components=[]
    while todo:
        comp={min(todo)};todo-=comp;front=list(comp)
        while front:
            u=front.pop()
            for v in adj[u]&todo:todo.remove(v);comp.add(v);front.append(v)
        components.append(sorted(comp))
    upper=0.;constraints=0;scenarios=0
    with ctx.workprec(512):
        for members in components:
            # A uniform simple cycle is invariant under rotation. Every
            # singleton deletion yields the same path, with endpoint degree
            # one in the HIDDEN induced graph. Exact dyadic Arb arithmetic
            # encloses its diagonal via left/right tridiagonal elimination.
            k=len(members);pos={i:j for j,i in enumerate(members)}
            es={tuple(sorted((pos[i],pos[int(j)]))) for i in members for j in peers[i]['neighbors']}
            cycle={tuple(sorted((j,(j+1)%k))) for j in range(k)}
            av={peers[i]['a'] for i in members};wv={w for i in members for w in peers[i]['neighbors'].values()}
            if k>12 and es==cycle and len(av)==len(wv)==1:
                a=arb(str(Fraction(next(iter(av)))));w=arb(str(Fraction(next(iter(wv)))))
                intact=sum((1/(a+w*(2-2*(2*arb.pi()*j/k).cos())) for j in range(k)),arb(0))/k
                h=k-1;diagonal=[a+w if j in (0,h-1) else a+2*w for j in range(h)]
                left=[arb(0) for _ in range(h)];right=[arb(0) for _ in range(h)]
                for j in range(1,h):left[j]=w*w/(diagonal[j-1]-left[j-1])
                for j in range(h-2,-1,-1):right[j]=w*w/(diagonal[j+1]-right[j+1])
                vals=[intact]+[1/(diagonal[j]-left[j]-right[j]) for j in range(h)]
                delta2=2 if peers[members[0]].get('report_dimension',1)==2 else 1
                for invdiag in vals:
                    value=invdiag*delta2/2
                    if not value.upper()<=arb(str(Fraction(peers[members[0]]['rho_per_release']))):
                        raise ValueError('rigorous uniform cycle privacy certificate failed')
                    upper=max(upper,float(value.upper()))
                scenarios+=k+1;constraints+=k*k
                continue
            for corrupt in [None,*members]:
                H=[i for i in members if i!=corrupt]
                if not H:continue
                pos={i:j for j,i in enumerate(H)};A=[[arb(0) for j in H] for i in H]
                for i in H:
                    j=pos[i];A[j][j]+=arb(str(Fraction(peers[i]['a'])))
                    for vv,w in peers[i]['neighbors'].items():
                        v=int(vv)
                        if v in pos:
                            weight=arb(str(Fraction(w)));A[j][j]+=weight;A[j][pos[v]]-=weight
                inv=arb_mat(A).inv();scenarios+=1
                for i in H:
                    # Fixed [0,1] joint availability report has exact Delta^2=2.
                    delta2=2 if peers[i].get('report_dimension',1)==2 else 1
                    value=inv[pos[i],pos[i]]*delta2/2
                    if not value.upper()<=arb(str(Fraction(peers[i]['rho_per_release']))):
                        raise ValueError('rigorous ideal privacy certificate failed')
                    upper=max(upper,float(value.upper()));constraints+=1
    return dict(passed=True,method='Arb512 exact rational covariance; every induced empty/singleton view per component; uniform cycles use rotation symmetry, circulant spectrum and induced-path elimination',worst_rho_upper=upper,component_sizes=list(map(len,components)),scenarios=scenarios,constraints=constraints,verification_seconds=time.perf_counter()-t)
