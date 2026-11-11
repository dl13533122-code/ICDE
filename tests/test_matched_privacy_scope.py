"""The matched batch must refuse cumulative history before any sampling."""
import copy
import pytest
from scripts.protocol_run import case_attempt_count


def config():
    return {'accountant':{'max_release_epochs':22},'routing_modes':['sharing'],
            'retry_after_abort':True,'privacy_scope':'single_benchmark_case_transcript',
            'fixture_sensitivity_semantics':'public_research_benchmark_fixture',
            'prior_related_attempts':12,'new_prepared_attempts':12,'related_two_batch_attempts':24,
            'combined_history_epsilon1_delta1e-6_claim':False,
            'production_cross_restart_accountant_certified':False}


def test_individually_scoped_public_case_retains_attempt_limit():
    c=config();before=copy.deepcopy(c)
    assert case_attempt_count(c,10)==12
    assert c==before


def test_cumulative_history_refused_without_resetting_counter():
    c=config();c['privacy_scope']='cumulative_protected_release_history'
    with pytest.raises(ValueError,match='refused before sampling'):
        case_attempt_count(c,10)
    assert c['prior_related_attempts']==12 and c['accountant']['max_release_epochs']==22


@pytest.mark.parametrize('field,value',[
    ('fixture_sensitivity_semantics','protected_production_data'),
    ('combined_history_epsilon1_delta1e-6_claim',True),
    ('production_cross_restart_accountant_certified',True),
    ('related_two_batch_attempts',12),('new_prepared_attempts',10),
    ('routing_modes',['sharing','no_sharing']),('retry_after_abort',False)])
def test_scope_and_provenance_changes_refused(field,value):
    c=config();c[field]=value
    with pytest.raises(ValueError):case_attempt_count(c,10)
