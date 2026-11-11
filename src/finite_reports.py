"""B5 finite report backend: exact dyadic intervals, rigorous Arb, rational fallback.

No primitive is rounded to a point. Only the final input-plus-noise interval
may produce a grid index. Secret coins are never returned in diagnostics.
"""
from fractions import Fraction as F
from functools import lru_cache
import math, secrets
from flint import arb, ctx

VERSION = 'B5-output-interval-v1'
DEFAULT = dict(b=256, u=64, K=10, eta_bits=180, coefficient_bits=220,
               grid_bits=20, arb_bits=512)

def exact(x):
    return x if isinstance(x,F) else F(x)

def bounds(x):
    if not x.is_finite(): raise ArithmeticError('nonfinite rigorous enclosure')
    return F(str(x.lower().fmpq())), F(str(x.upper().fmpq()))

def sqrt_interval(x,bits=220):
    """Integer square root gives a universal, exact rational certificate."""
    x=exact(x)
    if x<0: raise ValueError('negative variance')
    scale=1<<bits; m=math.isqrt((x.numerator*scale*scale)//x.denominator)
    lo=F(m,scale)
    hi=lo if lo*lo==x else F(m+1,scale)
    assert lo*lo<=x<=hi*hi
    return lo,hi

def add(a,b): return a[0]+b[0],a[1]+b[1]
def neg(a): return -a[1],-a[0]
def mul(a,b):
    v=[x*y for x in a for y in b]; return min(v),max(v)

@lru_cache(None)
def constants(K,precision=512):
    with ctx.workprec(precision):
        D=bounds((2*arb.pi()).sqrt()*(arb(K*K)/2).exp())[1]
        density=bounds(1/(2*arb.pi()).sqrt())
        log2=bounds(arb(2).log())[1]
    return D,density,log2

def central(coin,p):
    b,u=p['b'],p['u']
    if not isinstance(coin,int) or not 0<=coin<1<<b: raise ValueError('invalid coin')
    if not 0<u<=b: raise ValueError('invalid tail bits')
    tail=1<<(b-u)
    return tail<=coin and coin+1<=(1<<b)-tail

def draw(p=DEFAULT): return secrets.randbits(p['b'])

def _atan_bounds(q,terms):
    total=F(0); power=F(1,q)
    for j in range(terms):
        total+=(-1 if j%2 else 1)*power/(2*j+1);power/=q*q
    next_term=power/(2*terms+1)
    return (total-next_term,total) if terms%2 else (total,total+next_term)

@lru_cache(None)
def rational_constant(bits):
    """Machin pi, alternating-series remainder, integer-sqrt enclosure."""
    terms=bits//4+8
    a=_atan_bounds(5,terms);b=_atan_bounds(239,terms)
    pi=(16*a[0]-4*b[1],16*a[1]-4*b[0])
    low=sqrt_interval(1/(2*pi[1]),bits)[0]
    high=sqrt_interval(1/(2*pi[0]),bits)[1]
    return low,high

def _outward(a,bits):
    scale=1<<bits
    return F((a[0]*scale).__floor__(),scale), F((a[1]*scale).__ceil__(),scale)

@lru_cache(None)
def fallback_plan(K,eta_bits):
    """Public uniform remainder/roundoff plan; no sensitive values or coins."""
    D=constants(K)[0]; tolerance=F(1,1<<eta_bits)/(32*D)
    R=0; remainder=F(K**3,6)
    while remainder>tolerance/8:
        R+=1
        remainder=F(K**(2*R+3),2**(R+1)*math.factorial(R+1)*(2*R+3))
    Y=F(K*K,2)
    # Horner coefficient and multiply outward-rounding widths <= 3*2^-Q
    # per step. x and x^2/2 are exact dyadics at the bisection precision.
    amp=sum(Y**j for j in range(R+1))
    Q=max(2*(eta_bits+16),512)
    while F(8*K,1<<Q)*amp>tolerance/8: Q+=64
    c=rational_constant(Q)
    abs_sum=sum(F(K**(2*j+1),2**j*math.factorial(j)*(2*j+1)) for j in range(R+1))
    while (c[1]-c[0])*abs_sum>tolerance/8:
        Q+=64;c=rational_constant(Q)
    return dict(R=R,Q=Q,remainder=remainder*c[1],constant=c,
                tolerance=tolerance,D=D,roundoff_upper=F(8*K,1<<Q)*amp,
                constant_error_upper=(c[1]-c[0])*abs_sum)

def certified_cdf(x,plan):
    """Exact rational, bounded-precision interval Horner + Taylor remainder."""
    x=exact(x); y=x*x/2; Q=plan['Q']; value=(F(0),F(0))
    for r in range(plan['R'],-1,-1):
        coefficient=F((-1)**r,math.factorial(r)*(2*r+1))
        value=_outward(add(mul(value,(y,y)),(coefficient,coefficient)),Q)
    value=_outward(mul(mul(value,(x,x)),plan['constant']),Q)
    e=plan['remainder']
    return value[0]+F(1,2)-e,value[1]+F(1,2)+e

def fallback_quantile(prob,p=DEFAULT):
    """Finite deterministic inverse, including an exact median.

    Every overlap maps certified CDF width through D. Fixed bisection cap
    follows from initial width 2K and eta. Failure is an implementation error.
    """
    prob=exact(prob);K=p['K'];eta=F(1,1<<p['eta_bits'])
    if prob==F(1,2): return F(0),F(0)
    tau=F(1,1<<p['u'])
    if not tau<=prob<=1-tau: raise ValueError('noncentral inverse')
    plan=fallback_plan(K,p['eta_bits']);lo,hi=F(-K),F(K)
    steps=p['eta_bits']+(2*K).bit_length()+4
    for _ in range(steps):
        if hi-lo<=eta: return lo,hi
        mid=(lo+hi)/2;cdf=certified_cdf(mid,plan)
        if cdf[1]<prob: lo=mid
        elif cdf[0]>prob: hi=mid
        else:
            radius=plan['D']*max(prob-cdf[0],cdf[1]-prob)
            if 2*radius>eta: raise ArithmeticError('CDF uniform enclosure insufficient')
            return max(lo,mid-radius),min(hi,mid+radius)
    raise ArithmeticError('deterministic inverse did not terminate')

def quantile(prob,p=DEFAULT,force_fallback=False):
    prob=exact(prob);eta=F(1,1<<p['eta_bits'])
    if force_fallback: return fallback_quantile(prob,p)
    with ctx.workprec(p['arb_bits']):
        try:
            # Probability and both endpoints are exact dyadics, no float CDF.
            x=(2*arb(str(prob))-1).erfinv()*arb(2).sqrt()
            result=bounds(x)
            if result[1]-result[0]<=eta: return result
        except (ValueError,ArithmeticError): pass
    return fallback_quantile(prob,p)

def primitive(coin,p=DEFAULT,force_fallback=False):
    if not central(coin,p): return None
    lo=quantile(F(coin,1<<p['b']),p,force_fallback)[0]
    hi=quantile(F(coin+1,1<<p['b']),p,force_fallback)[1]
    if lo>hi: raise ArithmeticError('inverted primitive interval')
    return lo,hi

def encode_report(s,a,masks,p=DEFAULT,force_fallback=False):
    """masks=(coin, variance, sign); a=(local coin, local variance)."""
    value=(exact(s),exact(s)); public_width=F(0)
    primitives=[(a[0],a[1],1),*masks]
    for coin,variance,sign in primitives:
        z=primitive(coin,p,force_fallback)
        if z is None: return None
        c=sqrt_interval(variance,p['coefficient_bits'])
        term=mul(c,z)
        value=add(value,term if sign==1 else neg(term))
        D=constants(p['K'])[0];eta=F(1,1<<p['eta_bits'])
        public_width+=c[1]*(D/F(1<<p['b'])+2*eta)+(c[1]-c[0])*(p['K']+eta)
    if value[1]-value[0]>public_width: raise ArithmeticError('proved width violated')
    g=F(1,1<<p['grid_bits'])
    # Strict cell containment also avoids a tie convention mismatch.
    index=(value[0]/g+F(1,2)).__floor__()
    if not (g*(index-F(1,2))<value[0]<=value[1]<g*(index+F(1,2))): return None
    return index

def public_bound(peers,p=DEFAULT,epsilon=1.,attempts=1,delta_total=1e-6):
    """Conservative upper constants. All Fraction inputs are exact public data."""
    D,density,log2=constants(p['K']);K=p['K'];eta=F(1,1<<p['eta_bits'])
    if K*K<2*p['u']*log2: raise ValueError('K does not certify central quantiles')
    if not 0<p['u']<=p['b']: raise ValueError('invalid public bits')
    d=peers[0].get('report_dimension',1);M=d*(len(peers)+sum(len(x['neighbors']) for x in peers)//2)
    rows=[];beta=2*M*F(1,1<<p['u']);g=F(1,1<<p['grid_bits'])
    for peer in peers:
        variances=[peer['a'],*peer['neighbors'].values()]
        cs=[sqrt_interval(v,p['coefficient_bits']) for v in variances]
        C=sum(v[1] for v in cs);sigma=sqrt_interval(sum(map(exact,variances)),p['coefficient_bits'])[0]
        if sigma<=0: raise ValueError('positive marginal sigma required')
        eta_sum=sum((v[1]-v[0])*(K+eta) for v in cs)
        v=C*(D/F(1<<p['b'])+2*eta)+eta_sum
        R=(2*K*C/g).__ceil__()+2
        term=R*2*v*density[1]/sigma;beta+=d*term
        rows.append(dict(id=peer['id'],C_upper=str(C),sigma_lower=str(sigma),v_upper=str(v),R=R,eta_sum=str(eta_sum)))
    beta=min(F(1),beta)
    with ctx.workprec(512): factor=bounds(1+arb(str(exact(epsilon))).exp())[1]
    numerical_delta=factor*attempts*beta
    return dict(version=VERSION,parameters=dict(p),M=M,coordinates=d*len(peers),attempts=attempts,
                beta_upper_exact=str(beta),beta_upper=float(beta),numerical_delta_upper_exact=str(numerical_delta),
                numerical_delta_upper=float(numerical_delta),delta_total=delta_total,delta_G=delta_total/2,
                passed=numerical_delta<=exact(delta_total)/2,rows=rows,
                eta_sum_derivation='exact rational scaled sums; sqrt interval width <=2^-coefficient_bits times |Z|<=K+eta; no summation roundoff',
                scope='rounded report/abort and coalition coin view; ideal secure channels; computational advantage separate; hardware timing/cache excluded')

def public_preflight(peers,p=DEFAULT,wire_bytes=64):
    """Public central-bin arithmetic and wire bounds, independent of inputs/coins.

    Python integers/Fractions have no fixed-width arithmetic overflow. Only
    serialization is fixed-width. Bound every report, subset partial, row and
    weighted intermediate before sampling; reject unsupported public encodings.
    This does not turn machine resource exhaustion into a numerical TV event.
    """
    for key in DEFAULT:
        if not isinstance(p[key],int) or p[key]<=0:
            raise ValueError('positive integer numerical parameters required')
    if p['b']%8 or not 0<p['u']<=p['b']:
        raise ValueError('invalid fixed-width primitive parameters')
    D,_,log2=constants(p['K'])
    if p['K']**2<2*p['u']*log2:
        raise ValueError('central quantile bracket not certified')
    plan=fallback_plan(p['K'],p['eta_bits'])
    if not 0<plan['constant'][0]<=plan['constant'][1]<1:
        raise ArithmeticError('Horner constant amplification assumption failed')
    # Two Taylor endpoints, the constant enclosure and outward Horner widths.
    cdf_width=2*plan['remainder']+plan['constant_error_upper']+plan['roundoff_upper']
    if cdf_width>plan['tolerance'] or 2*D*cdf_width>F(1,1<<p['eta_bits']):
        raise ArithmeticError('uniform fallback enclosure plan insufficient')
    signed_limit=(1<<(8*wire_bytes-1))-1
    denominator_limit=(1<<(8*wire_bytes))-1
    grid_denominator=1<<p['grid_bits'];eta=F(1,1<<p['eta_bits'])
    indices=[];rows=[]
    for peer in peers:
        d=peer.get('report_dimension',1)
        if d not in (1,2):raise ValueError('unsupported bounded encoding')
        if d==2 and (peer.get('encoding')!='availability_value' or peer.get('clip_interval')!=[0.,1.]):
            raise ValueError('explicit fixed [0,1] vector encoding required')
        cs=[sqrt_interval(v,p['coefficient_bits']) for v in [peer['a'],*peer['neighbors'].values()]]
        if exact(peer['a'])<=0 or any(exact(v)<0 for v in peer['neighbors'].values()):
            raise ValueError('invalid public variances')
        # Frozen scalar [0,1] or vector (a, ax), both coordinate bounds <=1.
        noise_upper=sum(c[1]*(p['K']+eta) for c in cs)
        index_upper=((1+noise_upper)*grid_denominator+F(1,2)).__ceil__()
        indices.append(index_upper)
        rows.append(dict(id=peer['id'],input_coordinate_abs_upper='1',
                         central_noise_abs_upper=str(noise_upper),grid_index_abs_upper=index_upper))
    capacities=[('report',max(indices),grid_denominator),('any subset partial',sum(indices),grid_denominator)]
    W=peers[0].get('W',[])
    if any(peer.get('W',W)!=W for peer in peers):raise ValueError('mixed public workloads')
    for j,row in enumerate(W):
        if len(row)!=len(peers):raise ValueError('workload shape')
        coeff=list(map(exact,row));den=math.lcm(*(c.denominator for c in coeff))
        # This common denominator also bounds all subset/intermediate sums.
        num=sum(abs(c.numerator)*(den//c.denominator)*k for c,k in zip(coeff,indices))
        capacities.append(('query/intermediate '+str(j),num,den*grid_denominator))
    if any(num>signed_limit or den>denominator_limit for _,num,den in capacities):
        raise OverflowError('public central-bin fixed-wire capacity insufficient; no sampling allowed')
    return dict(passed=True,wire_bytes=wire_bytes,rows=rows,
                maximum_numerator_bits=max(num.bit_length() for _,num,_ in capacities),
                maximum_denominator_bits=max(den.bit_length() for _,_,den in capacities),
                fallback_R=plan['R'],fallback_Q=plan['Q'],
                fallback_cdf_width_upper=str(cdf_width),fallback_cdf_tolerance=str(plan['tolerance']),
                fallback_bisection_steps=p['eta_bits']+(2*p['K']).bit_length()+4,
                arithmetic='arbitrary precision integers/rationals; outward Arb512 endpoint enclosures; exact integer sqrt; no input quantization',
                scope='all central bins and bounded inputs, reports and all subset/weighted query intermediates; resource exhaustion is an implementation failure')
