import pytest
import time
from src.protocol import Peer,gaussian

def fake_peer():
    x=Peer.__new__(Peer);x.i=0;x.cfg={'n':4,'W':[[1,1,1,1]]*12,'groups':[{'id':0,'leader':0,'members':[0,1]},{'id':1,'leader':2,'members':[2,3]}]};x.state='RELEASED';x.z=1.;x.partial={'0':3.};x.phase={};x.calls=[];x.started=time.perf_counter()
    def call(j,msg):
        x.calls.append((j,msg));return {'z':float(j+1),'value':7.}
    x.call=call;return x

def test_query_cache_fair_ablation():
    shared=fake_peer();a=shared.dispatch({'op':'aggregate','mode':'query','sharing':True},'control')
    plain=fake_peer();b=plain.dispatch({'op':'aggregate','mode':'query','sharing':False},'control')
    assert a['answers']==b['answers']=={'0':10.,'4':10.,'8':10.}
    assert len(shared.calls)==1 and len(plain.calls)==3

def test_randomness_not_constant():
    xs=[gaussian() for _ in range(100)]
    assert len(set(xs))==100
