import importlib.util
import json
from pathlib import Path

import pytest

from apps.chat.task.llm import _data_skill_sql_validation_violation


SKILL = '<!-- data-skill-sql-validation: {"required_zero_fill":true,"message":"必须补零"} -->'


@pytest.mark.parametrize('projection', ['COALESCE(f.amount, 0)', 'COALESCE(COUNT(DISTINCT f.uid), 0)',
                                        'COALESCE(SUM(f.amount), 0.0)', 'ROUND(COALESCE(AVG(f.amount),0),2)'])
def test_zero_fill_accepts_projected_metric_expressions(projection):
    sql=f'SELECT d.day, {projection} AS metric FROM days d LEFT JOIN facts f ON f.day=d.day GROUP BY d.day'
    assert _data_skill_sql_validation_violation('统计',sql,SKILL) is None


@pytest.mark.parametrize('sql', [
    'SELECT SUM(amount) AS metric FROM facts',
    'SELECT COALESCE(SUM(amount), 1) AS metric FROM facts',
    'SELECT COALESCE(123, 0) AS metric FROM facts',
    'SELECT COALESCE(COUNT(*),0) AS metric FROM days LEFT JOIN facts ON 1=1',
    'WITH unused AS (SELECT COALESCE(amount,0) FROM facts) SELECT amount FROM facts',
    "SELECT 'COALESCE(amount,0)' AS metric FROM facts",
])
def test_zero_fill_rejects_missing_or_ineffective_projection(sql):
    assert _data_skill_sql_validation_violation('统计',sql,SKILL) is not None


def test_zero_fill_follows_projected_cte_metric_through_window_calculation():
    sql='WITH daily AS (SELECT d.day,COALESCE(f.users,0) AS users FROM days d LEFT JOIN facts f ON f.day=d.day) SELECT day, users, LAG(users) OVER (ORDER BY day) AS previous FROM daily'
    assert _data_skill_sql_validation_violation('统计',sql,SKILL) is None


def test_migration_changes_only_platform_zero_fill_rules_and_is_idempotent():
    path=Path(__file__).parents[1]/'alembic/versions/167_platform_zero_fill_expression.py'
    spec=importlib.util.spec_from_file_location('zero_fill_migration',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt='前言\n<!-- platform-foundation-skill:sql-date-grouping:v1 -->\n<!-- data-skill-sql-validation: '+json.dumps([
        {'required_sql_patterns':[module.LEGACY_PATTERN,r'\bleft\s+join\b'],'message':'补零'},
        {'required_sql_patterns':['CUSTOM'],'message':'其它规则'},
    ])+' -->\n尾部'
    updated=module.upgrade_prompt(prompt)
    assert module.upgrade_prompt(updated)==updated
    assert '前言' in updated and '尾部' in updated
    assert 'CUSTOM' in updated
    assert 'required_zero_fill' in updated
    assert _data_skill_sql_validation_violation('统计','SELECT COALESCE(COUNT(f.uid),0) FROM days d LEFT JOIN facts f ON f.day=d.day',updated.replace('CUSTOM','SELECT')) is None


def test_hour_scaffold_contract_does_not_depend_on_the_cte_name():
    path=Path(__file__).parents[1]/'alembic/versions/167_platform_zero_fill_expression.py'
    spec=importlib.util.spec_from_file_location('hour_contract_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rule={'required_sql_patterns':[r'\b(?:hour_offsets?|hour_series|hour_spine|hour_calendar|hour_numbers|hours)\b|\b(?:generate_series|sequence)\s*\(']}
    prompt='<!-- data-skill-sql-validation: '+json.dumps(rule)+' -->'
    fixed=module.upgrade_prompt(prompt)
    values=' UNION ALL '.join(f'SELECT {i} AS hour' for i in range(24))
    sql=f'WITH arbitrary_slots AS ({values}) SELECT hour FROM arbitrary_slots'
    assert _data_skill_sql_validation_violation('每小时',sql,fixed) is None
    assert _data_skill_sql_validation_violation('每小时','SELECT hour FROM facts',fixed) is not None


def test_downgrade_restores_legacy_checks_instead_of_leaving_unknown_flags():
    path=Path(__file__).parents[1]/'alembic/versions/167_platform_zero_fill_expression.py'
    spec=importlib.util.spec_from_file_location('zero_fill_rollback',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original={'required_sql_patterns':[module.LEGACY_PATTERN,module.LEGACY_HOUR_PATTERN,'CUSTOM'],'message':'保留其它规则'}
    prompt='<!-- data-skill-sql-validation: '+json.dumps(original)+' -->'
    restored=module.downgrade_prompt(module.upgrade_prompt(prompt))
    from apps.chat.task.llm import _extract_data_skill_sql_validation_rules
    rule=_extract_data_skill_sql_validation_rules(restored)[0]
    assert set(rule['required_sql_patterns'])==set(original['required_sql_patterns'])
    assert 'required_zero_fill' not in rule and 'required_hour_sequence' not in rule
