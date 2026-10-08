"""The existing editor always serializes optional filters as a structured root."""
from copy import deepcopy
import pytest
from test_interval_sql_plan import config, plan
from apps.dashboard.crud.interval_sql_plan import IntervalConfigurationError
from apps.dashboard.crud.interval_sql_plan import interval_filter_issues

@pytest.mark.parametrize('scope', ['global','start','end'])
@pytest.mark.parametrize('logic', ['and','or'])
def test_editor_empty_root_filters_mean_no_restriction(scope,logic):
    c=config();empty={'logic':logic,'rules':[]}
    if scope=='global':c['filters']=empty
    else:c['interval'][scope+'EventFilters']=empty
    actual=plan(c); expected=plan(config())
    assert (actual.filters,actual.start,actual.end)==(expected.filters,expected.start,expected.end)

@pytest.mark.parametrize('scope',['global','start','end'])
def test_nested_empty_filter_groups_remain_invalid(scope):
    c=config();bad={'logic':'and','rules':[{'type':'group','logic':'or','children':[]}]}
    if scope=='global':c['filters']=bad
    else:c['interval'][scope+'EventFilters']=bad
    with pytest.raises(IntervalConfigurationError):plan(c)

def test_empty_endpoint_filters_preserve_configured_global_filter():
    c=config();c['filters']={'logic':'or','rules':[
        {'field':{'table':'events','field':'category'},'operator':'eq','value':'A'},
        {'field':{'table':'events','field':'category'},'operator':'eq','value':'B'}]}
    expected=plan(c)
    c['interval']['startEventFilters']={'logic':'and','rules':[]}
    c['interval']['endEventFilters']={'logic':'or','rules':[]}
    assert plan(c).filters==expected.filters

def test_optional_root_group_is_empty_but_nested_empty_group_is_invalid():
    c=config();c['filters']={'type':'group','logic':'or','children':[]}
    assert plan(c).filters==plan(config()).filters
    assert interval_filter_issues(c['filters'],'filters',child=True)

@pytest.mark.parametrize('value',[None,[],{'logic':'xor','rules':[]}])
def test_malformed_roots_are_not_treated_as_absent_filters(value):
    assert interval_filter_issues(value,'metadata.table_filters')
