# -*- coding: utf-8 -*-
"""First Zombie 历史看板 SQL 日期表达式。

数据源会在业务日结束后完成日分区，因此历史看板以自然日前一天作为
最近完整业务日，避免扫描 ADS 事件视图计算 MAX(dt)。
"""

from __future__ import annotations


def complete_business_date_expr() -> str:
    """返回最近完整业务日的 SQL 日期表达式。"""
    return "DATE_SUB(CURDATE(), INTERVAL 1 DAY)"


def complete_business_dt_expr(days_ago: int = 0) -> str:
    """返回相对最近完整业务日的 yyyyMMdd 分区表达式。"""
    date_expr = complete_business_date_expr()
    if days_ago > 0:
        date_expr = f"DATE_SUB({date_expr}, INTERVAL {days_ago} DAY)"
    return f"CAST(DATE_FORMAT({date_expr}, '%Y%m%d') AS SIGNED)"
