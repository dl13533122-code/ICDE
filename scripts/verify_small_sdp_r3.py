"""Read stored rational certificates; independently check primal and dual bounds."""
import datetime,hashlib,itertools,json,pathlib
from fractions import Fraction as F
SOURCE=pathlib.Path('experiments/small_sdp_certificates_r3/results.json')
x=json.loads(SOURCE.read_text());count=0;constraints=0;summary={}
def read(v):return F(*v)
def positive_ldl(M):
    A=[row[:] for row in M]
    for j in range(len(A)):
        assert A[j][j]>0
        pivot=A[j][j]
        for u in range(j+1,len(A)):
            for v in range(u,len(A)):
                A[u][v]-=A[u][j]*A[v][j]/pivot;A[v][u]=A[u][v]
def gram(Q):
    return [[sum((u*v for u,v in zip(row,col)),F(0)) for col in Q] for row in Q]
for name,result in x['cases'].items():
    W=result['W'];n=3;ca=[sum(F(row[i])**2 for row in W) for i in range(n)]
    lowers=[];uppers=[];supports=set()
    for case in result['supports']:
        edges=[tuple(e) for e in case['edges']];supports.add(tuple(edges));count+=1
        a=list(map(read,case['primal_a']));w=list(map(read,case['primal_w']))
        assert all(v>0 for v in a) and all(v>=0 for v in w)
        cw=[sum(F(row[u]-row[v])**2 for row in W) for u,v in edges]
        ga=[F(0)]*3;gw=[F(0)]*len(edges);constant=F(0);views=set()
        for record in case['dual_factors']:
            C=tuple(record['coalition']);H=[i for i in range(n) if i not in C];i=record['target'];m=len(H)
            assert H==record['honest'] and i in H and len(C)<=1
            views.add((C,i));constraints+=1
            Q=[[read(v) for v in row] for row in record['factor_Q']]
            assert len(Q)==m+1 and all(len(row)==m+1 for row in Q)
            Z=gram(Q);A=[[a[H[u]] if u==v else F(0) for v in range(m)] for u in range(m)]
            for j,node in enumerate(H):ga[node]+=Z[j][j]
            for j,((u,v),weight) in enumerate(zip(edges,w)):
                if u not in H or v not in H:continue
                p,q=H.index(u),H.index(v)
                A[p][p]+=weight;A[q][q]+=weight;A[p][q]-=weight;A[q][p]-=weight
                gw[j]+=Z[p][p]+Z[q][q]-2*Z[p][q]
            M=[row+[F(H[u]==i)] for u,row in enumerate(A)]+[[F(v==i) for v in H]+[F(1)]]
            positive_ldl(M);constant-=2*Z[H.index(i)][m]+Z[m][m]
        expected={(C,i) for C in [(),(0,),(1,),(2,)] for i in range(3) if i not in C}
        assert views==expected
        scale=read(case['dual_scale']);assert scale>0
        assert [c-scale*g for c,g in zip(ca,ga)]==list(map(read,case['dual_a_slack']))
        assert [c-scale*g for c,g in zip(cw,gw)]==list(map(read,case['dual_w_slack']))
        assert all(c-scale*g>=0 for c,g in zip(ca,ga)) and all(c-scale*g>=0 for c,g in zip(cw,gw))
        lower=scale*constant;upper=sum(c*v for c,v in zip(ca,a))+sum(c*v for c,v in zip(cw,w))
        assert lower==read(case['lower']) and upper==read(case['upper']) and lower<=upper
        lowers.append(lower);uppers.append(upper)
    assert len(supports)==8
    assert min(lowers)==read(result['all_support_infimum_interval'][0]) and min(uppers)==read(result['all_support_infimum_interval'][1])
    summary[name]=dict(lower=float(min(lowers)),upper=float(min(uppers)),absolute_gap=float(min(uppers)-min(lowers)),
        maximum_fixed_support_gap=max(c['absolute_gap'] for c in result['supports']))
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='LOCALLY_VERIFIED',
    command='python3 scripts/verify_small_sdp_r3.py',checker_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
    raw_path=str(SOURCE),raw_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),supports=count,primal_view_LMIs=constraints,
    results=summary,scope='exact Fraction arithmetic; PSD dual factorization and strict primal LDL checks; positive-width objective intervals, not exact optima or broader mechanism optimality')
pathlib.Path('experiments/small_sdp_certificates_r3/verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
