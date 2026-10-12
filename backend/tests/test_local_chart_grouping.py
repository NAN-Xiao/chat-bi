from apps.dashboard.crud.local_chart_grouping import build_local_grouping_plan


def test_plan_maps_generic_dimensions_additive_measures_and_formula_operands():
    plan = build_local_grouping_plan('''
        SELECT day AS date,region AS dimension,SUM(amount) AS value,
        SUM(quantity) AS quantity,SUM(amount)*1.0/NULLIF(SUM(quantity),0) AS price,
        COUNT(DISTINCT user_id) AS people FROM facts GROUP BY day,region
    ''', 'sqlite')
    assert plan['dimensions'] == ['date', 'dimension']
    assert plan['metrics']['value'] == {'kind': 'aggregate', 'aggregation': 'sum'}
    assert plan['metrics']['price']['kind'] == 'formula'
    assert plan['metrics']['price']['expression']['op'] == 'divide'
    assert plan['metrics']['people']['kind'] == 'unavailable'


def test_missing_denominator_and_rounded_source_are_explicitly_unavailable():
    plan = build_local_grouping_plan('''
        SELECT day,region,SUM(amount) AS value,
        ROUND(SUM(amount)*1.0/NULLIF(SUM(quantity),0),2) AS price,
        ROUND(SUM(amount),2) AS rounded FROM facts GROUP BY day,region
    ''', 'sqlite')
    assert plan['metrics']['price']['kind'] == 'unavailable'
    assert plan['metrics']['rounded']['kind'] == 'formula'
    assert plan['metrics']['rounded']['expression']['op'] == 'round'


def test_cte_operands_and_union_summary_marker_are_traced_without_execution():
    plan = build_local_grouping_plan('''
        WITH daily AS (
          SELECT day,region,SUM(amount) AS value,SUM(quantity) AS quantity
          FROM facts GROUP BY day,region
        ), report AS (
          SELECT 1 AS row_kind,day,region,value,quantity FROM daily
          UNION ALL SELECT 0,NULL,NULL,SUM(value),SUM(quantity) FROM daily
        )
        SELECT CASE WHEN row_kind=0 THEN 'total' ELSE day END AS date,
          region AS dimension,value,quantity,
          ROUND(value*1.0/NULLIF(quantity,0),2) AS price FROM report
    ''', 'sqlite')
    assert plan['dimensions'] == ['date', 'dimension']
    assert plan['summary'] == {'field': 'date', 'value': 'total'}
    assert plan['metrics']['value']['aggregation'] == 'sum'
    assert plan['metrics']['price']['kind'] == 'formula'


def test_query_parameters_ordinal_groups_and_average_never_become_naive_means():
    plan = build_local_grouping_plan('''
        SELECT day AS date,region AS dimension,AVG(amount) AS mean
        FROM facts WHERE day BETWEEN {{dashboard_start_date}} AND {{dashboard_end_date}}
        GROUP BY 1,2
    ''', 'sqlite')
    assert plan['dimensions'] == ['date', 'dimension']
    assert plan['metrics']['mean']['kind'] == 'unavailable'


def test_invalid_query_has_visible_reason_and_no_guessed_dimensions():
    plan = build_local_grouping_plan('SELECT * FROM facts', 'sqlite')
    assert plan['dimensions'] == []
    assert plan['reason']


def test_group_aliases_and_hidden_measure_definitions_do_not_use_field_names():
    plan = build_local_grouping_plan('''
        WITH a AS (SELECT day,region,SUM(amount) AS n FROM facts GROUP BY day,region)
        SELECT day AS d,region AS r,COALESCE(n,0) AS m,n*1.0/2 AS half FROM a
    ''', 'sqlite')
    assert plan['dimensions'] == ['d', 'r']
    assert plan['metrics']['m']['kind'] == 'aggregate'
    assert plan['metrics']['half']['kind'] == 'formula'


def test_structural_reader_accepts_quoted_fields_without_loading_datasource_metadata():
    plan = build_local_grouping_plan('SELECT day AS `date`,region AS `dimension`,ROUND(SUM(amount),2) AS `cost` FROM facts GROUP BY day,region')
    assert plan['dimensions'] == ['date', 'dimension']
    assert plan['metrics']['cost'] == {'kind': 'aggregate', 'aggregation': 'sum'}


def test_distinct_sum_is_not_additive_without_original_value_sets():
    plan = build_local_grouping_plan('SELECT day,region,SUM(DISTINCT amount) AS value FROM facts GROUP BY day,region', 'sqlite')
    assert plan['metrics']['value']['kind'] == 'unavailable'


def test_subtotal_union_without_visible_row_kind_disables_ambiguous_regrouping():
    plan = build_local_grouping_plan('''
        WITH daily AS (SELECT day,region,SUM(amount) AS value FROM facts GROUP BY day,region),
        rows AS (SELECT day,region,value FROM daily
                 UNION ALL SELECT day,NULL,SUM(value) FROM daily GROUP BY day)
        SELECT day,region,value FROM rows
    ''', 'sqlite')
    assert plan['dimensions'] == []
    assert plan['reason']


def test_unspecified_division_type_is_unavailable_instead_of_changing_integer_division():
    plan = build_local_grouping_plan('SELECT day,region,SUM(a) AS n,SUM(b) AS d,SUM(a)/SUM(b) AS ratio FROM facts GROUP BY day,region', 'sqlite')
    assert plan['metrics']['ratio']['kind'] == 'unavailable'


def test_each_union_aggregate_branch_requires_its_own_summary_marker():
    plan = build_local_grouping_plan('''
        WITH daily AS(SELECT day,region,SUM(amount) AS n FROM facts GROUP BY day,region),
        mixed AS(SELECT day,region,n FROM daily UNION ALL SELECT day,NULL,SUM(n) FROM daily GROUP BY day),
        report AS(SELECT 1 AS k,day,region,n FROM mixed UNION ALL SELECT 0,NULL,NULL,SUM(n) FROM daily)
        SELECT CASE WHEN k=0 THEN 'total' ELSE day END AS day,region,n FROM report
    ''', 'sqlite')
    assert plan['dimensions'] == []
    assert plan['reason']
