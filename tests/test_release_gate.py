import pytest
from src.release_gate import validate_peer_config

def test_changed_graph_refused():
    # Edge cannot protect a target when its only peer is the allowed colluder.
    p=[{'id':0,'a':.1,'rho_per_release':.5,'neighbors':{'1':100.}},{'id':1,'a':.1,'rho_per_release':.5,'neighbors':{'0':100.}}]
    with pytest.raises(ValueError,match='refused'):validate_peer_config(p)
    for x in p:x['a']=1.00001
    c=validate_peer_config(p);assert c['passed'] and c['constraint_count']==4
    p[0]['neighbors']['1']=90
    with pytest.raises(ValueError,match='asymmetric'):validate_peer_config(p)
