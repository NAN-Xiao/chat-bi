from types import SimpleNamespace

import pytest

from apps.datasource.crud.sql_permission import (
    RowPermissionRelation,
    analyze_row_permission_relation,
)


DATASOURCE = SimpleNamespace(type="mysql")
SERVER_PAY_CONSTRAINTS = [
    {
        "table": "event",
        "deny_sql": "(`event` = 'ServerPayLog')",
    }
]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            "select count(*) from `event` e where e.event = 'ServerPayLog'",
            RowPermissionRelation.OVERLAP,
        ),
        (
            "select count(*) from `event` e "
            "where e.event in ('Login', 'ServerPayLog')",
            RowPermissionRelation.OVERLAP,
        ),
        (
            "select count(*) from `event` e where e.event like '%PayLog%'",
            RowPermissionRelation.OVERLAP,
        ),
        (
            "select count(*) from `event` e where e.event not like 'Login%'",
            RowPermissionRelation.OVERLAP,
        ),
        (
            "select max(case when e.event = 'ServerPayLog' then 1 else 0 end) "
            "from `event` e",
            RowPermissionRelation.OVERLAP,
        ),
        (
            "select count(*) from `event` e where e.event = 'Login'",
            RowPermissionRelation.DISJOINT,
        ),
        (
            "select count(*) from `event` e where e.event in ('Login', 'UserActive')",
            RowPermissionRelation.DISJOINT,
        ),
        (
            "select count(*) from `event` e where e.event <> 'ServerPayLog'",
            RowPermissionRelation.DISJOINT,
        ),
        (
            "select count(*) from `event` e where e.event not like '%ServerPayLog%'",
            RowPermissionRelation.DISJOINT,
        ),
    ],
)
def test_analyze_row_permission_relation_for_discrete_denied_value(sql, expected):
    assert analyze_row_permission_relation(sql, DATASOURCE, SERVER_PAY_CONSTRAINTS) == expected


def test_analyze_row_permission_relation_fails_closed_for_non_finite_rule():
    constraints = [{"table": "event", "deny_sql": "(`event` LIKE '%PayLog%')"}]

    assert (
        analyze_row_permission_relation(
            "select count(*) from `event` where event = 'Login'",
            DATASOURCE,
            constraints,
        )
        == RowPermissionRelation.UNKNOWN
    )
