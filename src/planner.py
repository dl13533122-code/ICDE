"""Public aggregation plan and explicit RPC-load objective, separate from G_N.

RPC counts are a public cost model, not measured byte/latency claims. Actual
TLS and SSH bytes are measured by src/protocol.py and the network runner.
"""
import itertools, math
import numpy as np
from src.noise import signature_groups

def plan(W,share=True,exact_small=True,noise_groups=None):
    W=np.asarray(W);n=W.shape[1];groups=signature_groups(W)
    if noise_groups is not None:
        flat=[i for g in noise_groups for i in g]
        if sorted(flat)!=list(range(n)):raise ValueError('noise groups must partition participants')
        # A nonidentical-signature noise interval cannot be routed as one
        # unweighted partial. Intersect with exact public signatures instead.
        signatures={i:tuple(W[:,i]) for i in range(n)};groups=[]
        for g in noise_groups:
            pieces={}
            for i in g:pieces.setdefault(signatures[i],[]).append(i)
            groups.extend(pieces.values())
    assignments=[list(x) for x in itertools.product(*groups)] if exact_small and math.prod(len(g) for g in groups)<=4096 else [[g[j%len(g)] for j,g in enumerate(groups)]]
    best=None
    for leaders in assignments:
        tx=np.zeros(n,int);rx=np.zeros(n,int);calls=[]
        if share:
            for g,leader in zip(groups,leaders):
                for i in g:
                    if i!=leader:calls.append((leader,i,'group-report'))
            for owner in range(n):
                queries=W[owner::n]
                for g,leader in zip(groups,leaders):
                    if owner!=leader and np.any(queries[:,g[0]]!=0):calls.append((owner,leader,'partial'))
        else:
            for owner in range(n):
                for i in np.flatnonzero(np.any(W[owner::n]!=0,axis=0)):
                    if i!=owner:calls.append((owner,int(i),'cached-report'))
        for u,v,kind in calls:tx[u]+=1;rx[v]+=1;tx[v]+=1;rx[u]+=1
        score=int(max(tx+rx));candidate={'groups':[{'id':j,'members':g,'leader':leader} for j,(g,leader) in enumerate(zip(groups,leaders))],'query_owner':[j%n for j in range(len(W))],'per_node_rpc_messages_tx':tx.tolist(),'per_node_rpc_messages_rx':rx.tolist(),'max_node_rpc_messages':score,'total_rpc_messages':int(sum(tx)),'share':share,'leader_selection':'exact enumeration' if len(assignments)>1 else 'public deterministic assignment','cost_model':'RPC request+response counts; excludes TLS/SSH/control setup, no measured speed/bytes implied'}
        if best is None or score<best['max_node_rpc_messages']:best=candidate
    return best

def joint_objective(W,design,setup_weight=.01,max_load_weight=.005):
    from src.noise import loss
    n=W.shape[1];P=plan(W);degree=np.zeros(n,int)
    for u,v in design['edges']:degree[u]+=1;degree[v]+=1
    setup_rpc_messages=2*len(design['edges']);max_node=int(max(np.array(P['per_node_rpc_messages_tx'])+np.array(P['per_node_rpc_messages_rx'])+2*degree))
    query_loss=loss(W,design['a'],design['edges'],design['w'])
    return {'objective':query_loss+setup_weight*setup_rpc_messages+max_load_weight*max_node,'variance':query_loss,'setup_rpc_messages':setup_rpc_messages,'max_node_rpc_messages_with_mask_setup':max_node,'weights':{'setup_variance_units_per_rpc_message':setup_weight,'max_load_variance_units_per_rpc_message':max_load_weight},'execution_plan':P}
