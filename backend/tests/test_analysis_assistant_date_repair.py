from importlib import import_module

import pytest

from common.utils.sql_date_validation import SqlDateConversionError, validate_sql_date_conversions


assistant = import_module('apps.analysis_assistant.api.analysis_assistant')


@pytest.mark.parametrize('repair_succeeds', [True, False])
def test_proven_date_conflict_uses_existing_single_repair(monkeypatch, repair_succeeds):
    broken = "SELECT STR_TO_DATE(DATE_FORMAT(created_at, '%Y%m%d'), '%Y-%m-%d') AS day FROM orders"
    corrected = "SELECT STR_TO_DATE(DATE_FORMAT(created_at, '%Y%m%d'), '%Y%m%d') AS day FROM orders"
    errors = []
    prepared = []

    def prepare(*args, **kwargs):
        prepared.append(args[4])
        validate_sql_date_conversions(args[4], 'mysql')
        return args[4]

    def repair(*args, **kwargs):
        errors.append(str(args[4]))
        return corrected if repair_succeeds else broken

    monkeypatch.setattr(assistant, '_prepare_sql_for_execution', prepare)
    monkeypatch.setattr(assistant, '_repair_sql', repair)
    arguments = dict(
        llm=None, session=None, current_user=None, datasource=None,
        raw_query={'sql': broken}, question='daily trend', schema='', sample_data='',
        data_profile='', custom_agent='', tracking_context='', data_skill='',
        allowed_tables=['orders'], time_resolution=None, schema_time_fields={}, dialect='mysql',
    )
    if repair_succeeds:
        assert assistant._prepare_time_safe_query_sql(**arguments) == corrected
    else:
        with pytest.raises(SqlDateConversionError):
            assistant._prepare_time_safe_query_sql(**arguments)
    assert len(prepared) == 2
    assert len(errors) == 1
    assert '%Y%m%d' in errors[0] and '%Y-%m-%d' in errors[0]
