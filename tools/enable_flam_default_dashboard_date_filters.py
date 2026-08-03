# -*- coding: utf-8 -*-
"""为 Flam 默认看板中语义明确的分区日期窗口启用日期表达式。

默认只读预演。``--apply`` 会为每个目标看板生成可恢复快照，并通过行锁和
canvas JSON 的 CAS 条件更新。日快照、实时数据、多窗口及成熟期类 SQL 不在本脚本范围内。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-date-expression-backups"
TENANT_ID = 7477202383789887488
EXCLUDED_DASHBOARD_ID = "6d50bd7dfc9f46ba961d636814c3294d"
EXCLUDED_TITLES = {"活跃用户", "新增用户", "充值人数", "充值总额"}
START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}
CORE_METRIC_EXPRESSION = {"version": 1, "mode": "preset", "preset": "yesterday"}

_PARTITION_RANGE = re.compile(r"\b(?P<alias>[A-Za-z_][\w]*)\.dt\s+BETWEEN\b", re.IGNORECASE)
_CURRENT_DATE = re.compile(r"\bCURDATE\s*\(|\bCURRENT_DATE\b", re.IGNORECASE)
_UNSUPPORTED_SEMANTICS = re.compile(r"\b(?:cohort|retention|ltv|d1|d3|d7|d14|d30)\b|留存|生命周期", re.IGNORECASE)
_BOUNDARY_WORDS = ("AND", "OR", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION")
_MISSING_BOUNDARY_WHITESPACE = re.compile(
    rf"{re.escape(END_TOKEN)}(?P<word>{'|'.join(_BOUNDARY_WORDS)})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateMigrationTarget:
    title: str
    kind: Literal["range", "core_range", "end_anchor", "cohort", "weekly_snapshots", "roi"]
    date_field: str = "dt"


DATE_MIGRATION_TARGETS = {
    ("8f86e50234794606bd2a33ec41ffa660", "b55382d46c664f1dbd465964cc5e8da2"): DateMigrationTarget("各渠道新增留存", "cohort"),
    ("8f86e50234794606bd2a33ec41ffa660", "3bb23e771d584610a2c88a38760163b6"): DateMigrationTarget("各渠道活跃留存", "cohort"),
    ("8f86e50234794606bd2a33ec41ffa660", "2187432754973679616"): DateMigrationTarget("各渠道新增用户次日留存趋势", "cohort"),
    ("5cee4cf41a024c56ac9de0e3aef9aefe", "63e03c7e2ad34ad58321892998497a85"): DateMigrationTarget("各渠道新增留存", "cohort"),
    ("6d50bd7dfc9f46ba961d636814c3294d", "c23c019171804f608e92961dc06ae8b2"): DateMigrationTarget("活跃用户", "core_range"),
    ("6d50bd7dfc9f46ba961d636814c3294d", "d84e234a7f3b4e728a8b02d61911d88f"): DateMigrationTarget("新增用户", "core_range"),
    ("6d50bd7dfc9f46ba961d636814c3294d", "4d250a8575cc4bcd84f7b9514abbf455"): DateMigrationTarget("充值人数", "core_range"),
    ("6d50bd7dfc9f46ba961d636814c3294d", "ba0dc1580f0d43c29c0d6cdf26a6239c"): DateMigrationTarget("充值总额", "core_range"),
    ("bb3ab5f2697a42af98ab90da4679cb77", "f0d759307a304043883a23499a281b97"): DateMigrationTarget("新增用户次日留存", "cohort"),
    ("bb3ab5f2697a42af98ab90da4679cb77", "f784452553f1426ea5097b092deb818a"): DateMigrationTarget("新增首日付费金额", "cohort"),
    ("8c93878ee7af41b9b3832547856d25e6", "77aa7f9c7c2c4eb38d821d10379978e7"): DateMigrationTarget("MAU", "end_anchor"),
    ("8c93878ee7af41b9b3832547856d25e6", "3ea113a229784c6f9c04b2a7b91d65b6"): DateMigrationTarget("活跃用户生命周期构成", "end_anchor"),
    ("259414f219f94aacaa46f4e531646b9d", "f75122a83c84441381fe77a551f69a28"): DateMigrationTarget("付费情况", "range"),
    ("259414f219f94aacaa46f4e531646b9d", "6391d385e5084c0f86351ae088d3c336"): DateMigrationTarget("新增用户30日LTV", "cohort"),
    ("259414f219f94aacaa46f4e531646b9d", "f6ca362eb4274830b3298b0227a8ab88"): DateMigrationTarget("充值用户周累充分布", "weekly_snapshots"),
    ("259414f219f94aacaa46f4e531646b9d", "eabf5e30333342ed8bf47dfcd0898278"): DateMigrationTarget("各等级段人均付费金额", "end_anchor"),
    ("db9df7a9015c4b4bb033810ffc5a84d2", "4608fb0831cd4845ba881678fb778b2f"): DateMigrationTarget("主城平均等级", "end_anchor"),
    ("db9df7a9015c4b4bb033810ffc5a84d2", "1b9eb5aac8224dee9ccdf839d5a3988c"): DateMigrationTarget("各主城等级玩家数", "end_anchor"),
    ("db9df7a9015c4b4bb033810ffc5a84d2", "a547eb9c1a1a4f4eba00191abbd9ac62"): DateMigrationTarget("主城升级漏斗", "end_anchor"),
    ("4bae835c4243481b9963122b5275ed81", "9d4add7a8be048ea9c7beb62a43e50cc"): DateMigrationTarget("出征事件数", "end_anchor"),
    ("4bae835c4243481b9963122b5275ed81", "9325211a9f594376bf818cec639aa103"): DateMigrationTarget("兵种升级事件数", "end_anchor"),
    ("4bae835c4243481b9963122b5275ed81", "440303dfdf39408ba86ffb222f3334f2"): DateMigrationTarget("出征平均战力", "end_anchor"),
    ("4bae835c4243481b9963122b5275ed81", "0b849c96c0a3480c9e940b92995d5e3e"): DateMigrationTarget("荣耀远征事件数", "end_anchor"),
    ("4bae835c4243481b9963122b5275ed81", "344c936b561f44f6bc29cc2663f3f651"): DateMigrationTarget("各英雄出征胜率", "range"),
    ("5cee4cf41a024c56ac9de0e3aef9aefe", "4045ede9004f48de9fb8b8aed5f79287"): DateMigrationTarget("各渠道充值用户周累充分布", "weekly_snapshots"),
    ("29ea652e2969440b91899cfb254dd0ca", "c794f6521d8b44d39f78eabdf109896b"): DateMigrationTarget("各类活动参与率", "range"),
    ("29ea652e2969440b91899cfb254dd0ca", "9684a569ed034fb0b8a106a9817effaa"): DateMigrationTarget("参与新手活动的后续7日留存率", "cohort"),
    ("29ea652e2969440b91899cfb254dd0ca", "095b1cf41cd64844b1f78f07ceccb7bf"): DateMigrationTarget("参与节日活动用户的当日/D7付费率", "cohort"),
    ("2b990d3821fa4c3d97f0dda519b644e8", "98918b6a38b14ca2b3ec63ff4cc8753f"): DateMigrationTarget("ROI总览", "roi"),
    ("2b990d3821fa4c3d97f0dda519b644e8", "7a0cba8a01f045a584e9562338c6e876"): DateMigrationTarget("ROI地区总览", "roi"),
    ("2b990d3821fa4c3d97f0dda519b644e8", "455a872e57764ebeb0dee3a9e9072c41"): DateMigrationTarget("ROI广告地区总览", "roi"),
    ("2b990d3821fa4c3d97f0dda519b644e8", "2196532494151622656"): DateMigrationTarget("安装投放趋势", "roi"),
    ("e423819a72454bc9ab71646d41aa5fd6", "531012d01f104a509da2d1926692ee1d"): DateMigrationTarget("各渠道注册与付费", "range"),
}


def _parameter_date(token: str) -> str:
    return f"STR_TO_DATE(CAST({token} AS CHAR), '%Y%m%d')"


def _replace_once(source: str, old: str, new: str, *, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"{label}的固定日期条件数量异常")
    return source.replace(old, new, 1)


def _non_recursive_day_offsets(column_name: str) -> str:
    return f"""digit_offsets AS (
  SELECT 0 AS digit UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
  UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9
),
day_offsets AS (
  SELECT units.digit + tens.digit * 10 + hundreds.digit * 100 AS {column_name}
  FROM digit_offsets AS units
  CROSS JOIN digit_offsets AS tens
  CROSS JOIN digit_offsets AS hundreds
)"""


def _replace_day_offsets_cte(source: str, *, column_name: str) -> str:
    offsets = re.compile(
        r"day_offsets(?:\s*\([^)]*\))?\s+AS\s*\(.*?\)(?=\s*,\s*calendar\s+AS)",
        re.IGNORECASE | re.DOTALL,
    )
    result, count = offsets.subn(_non_recursive_day_offsets(column_name), source, count=1)
    if count != 1:
        raise ValueError("留存 SQL 未找到可替换的 cohort 日历偏移")
    calendar_from = re.compile(
        rf"(FROM\s+params\s+(?:AS\s+)?p\s+CROSS\s+JOIN\s+day_offsets\s+(?:AS\s+)?d)(\s*\))",
        re.IGNORECASE,
    )
    result, count = calendar_from.subn(
        rf"\1\n  WHERE d.{column_name} <= DATEDIFF(p.end_date, p.start_date)\2",
        result,
        count=1,
    )
    if count != 1:
        raise ValueError("留存 SQL 未找到 cohort 日历的参数范围")
    return result


def migrate_channel_retention_sql(sql: str) -> str:
    """将固定 15 日 cohort 留存窗口改为调用方传入的日期范围。"""
    source = str(sql or "")
    if not re.match(r"^WITH\s", source, re.IGNORECASE):
        raise ValueError("渠道留存 SQL 必须以 WITH 开始")
    start_date = _parameter_date(START_TOKEN)
    end_date = _parameter_date(END_TOKEN)
    result = re.sub(r"^WITH\s+(?:RECURSIVE\s+)?", "WITH\n", source, count=1, flags=re.IGNORECASE)
    result = result.replace("DATE_SUB(CURRENT_DATE, INTERVAL 15 DAY)", start_date)
    result = result.replace("DATE_SUB(CURRENT_DATE, INTERVAL 14 DAY)", start_date)
    result = result.replace("DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY)", end_date)
    for offset in (2, 4, 8):
        old = f"DATE_SUB(CURRENT_DATE, INTERVAL {offset} DAY)"
        new = f"DATE_SUB({end_date}, INTERVAL {offset - 1} DAY)"
        result = result.replace(old, new)

    result = _replace_day_offsets_cte(result, column_name="n")
    if START_TOKEN not in result or END_TOKEN not in result:
        raise ValueError("渠道留存 SQL 未写入日期参数")
    return result


def migrate_active_retention_sql(sql: str) -> str:
    """将固定 14 日活跃 cohort 留存窗口改为调用方传入的日期范围。"""
    source = str(sql or "")
    if not re.match(r"^WITH\s", source, re.IGNORECASE):
        raise ValueError("活跃留存 SQL 必须以 WITH 开始")
    start_date = _parameter_date(START_TOKEN)
    end_date = _parameter_date(END_TOKEN)
    result = re.sub(r"^WITH\s+(?:RECURSIVE\s+)?", "WITH\n", source, count=1, flags=re.IGNORECASE)
    result = result.replace(
        "DATE_SUB(DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY), INTERVAL 14 DAY)",
        start_date,
    )
    result = result.replace(
        "DATE_SUB(DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY), INTERVAL 13 DAY)",
        start_date,
    )
    result = result.replace("DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY)", end_date)
    result = _replace_day_offsets_cte(result, column_name="day_offset")
    if START_TOKEN not in result or END_TOKEN not in result:
        raise ValueError("活跃留存 SQL 未写入日期参数")
    return result


def migrate_next_day_retention_sql(sql: str) -> str:
    """将固定近 30 天新增次留窗口改为传入 cohort 与观察期窗口。"""
    source = str(sql or "")
    start_date = _parameter_date(START_TOKEN)
    end_date = _parameter_date(END_TOKEN)
    result = _replace_once(
        source,
        "DATE_SUB(CURDATE(), INTERVAL 31 DAY)",
        start_date,
        label="注册 cohort 开始",
    )
    result = _replace_once(
        result,
        "DATE_SUB(CURDATE(), INTERVAL 2 DAY)",
        f"DATE_SUB({end_date}, INTERVAL 1 DAY)",
        label="注册 cohort 结束",
    )
    result = _replace_once(
        result,
        "DATE_SUB(CURDATE(), INTERVAL 30 DAY)",
        f"DATE_ADD({start_date}, INTERVAL 1 DAY)",
        label="次日观察开始",
    )
    result = _replace_once(
        result,
        "DATE_SUB(CURDATE(), INTERVAL 1 DAY)",
        end_date,
        label="次日观察结束",
    )
    return result


def migrate_range_sql(sql: str) -> str:
    """将唯一业务 ``dt`` 日期范围替换为看板起止参数。"""
    source = str(sql or "")
    if len(_PARTITION_RANGE.findall(source)) != 1:
        raise ValueError("SQL 不包含唯一业务日期窗口")
    return replace_unique_partition_range(source)


def migrate_parallel_range_sql(sql: str) -> str:
    """将同一指标中并列的多个业务日期范围统一绑定到看板日期。"""
    source = str(sql or "")
    matches = list(_PARTITION_RANGE.finditer(source))
    if not matches:
        raise ValueError("SQL 不包含业务日期窗口")
    result = source
    for match in reversed(matches):
        start_expression = match.end()
        and_index = _find_top_level_word(result, start_expression, ("AND",))
        if and_index < 0:
            raise ValueError("分区日期窗口缺少结束条件")
        end_expression = and_index + 3
        suffix_index = _find_top_level_word(result, end_expression, _BOUNDARY_WORDS)
        if suffix_index < 0:
            suffix_index = result.find(";", end_expression)
        if suffix_index < 0:
            suffix_index = len(result)
        replacement = f"{match.group('alias')}.dt BETWEEN {START_TOKEN} AND {END_TOKEN}"
        suffix = result[suffix_index:]
        separator = " " if suffix and not suffix[0].isspace() else ""
        result = result[:match.start()] + replacement + separator + suffix
    return result


def migrate_activity_d7_cohort_sql(sql: str) -> str:
    """将活动参与 cohort 绑定到日期范围，并保留 D7 观察期。"""
    start_date = _parameter_date(START_TOKEN)
    end_date = _parameter_date(END_TOKEN)
    source = str(sql or "")
    result = source.replace("DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL 34 DAY)", start_date)
    result = result.replace("DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL 7 DAY)", f"DATE_SUB({end_date}, INTERVAL 7 DAY)")
    result = result.replace("DATE_SUB(CURDATE(), INTERVAL 1 DAY)", end_date)
    if START_TOKEN not in result or END_TOKEN not in result or "INTERVAL 7 DAY" not in result:
        raise ValueError("活动 D7 cohort SQL 未完整参数化")
    return result


def migrate_quoted_next_day_retention_sql(sql: str) -> str:
    """将带字符串 interval 的新增次留 SQL 改为 cohort 参数范围。"""
    start_date = _parameter_date(START_TOKEN)
    end_date = _parameter_date(END_TOKEN)
    source = str(sql or "")
    replacements = {
        "DATE_SUB(DATE_SUB(CURRENT_DATE, INTERVAL '1' DAY), INTERVAL '28' DAY)": start_date,
        "DATE_SUB(DATE_SUB(CURRENT_DATE, INTERVAL '1' DAY), INTERVAL '1' DAY)": f"DATE_SUB({end_date}, INTERVAL 1 DAY)",
        "DATE_SUB(DATE_SUB(CURRENT_DATE, INTERVAL '1' DAY), INTERVAL '27' DAY)": f"DATE_ADD({start_date}, INTERVAL 1 DAY)",
        "DATE_SUB(CURRENT_DATE, INTERVAL '1' DAY)": end_date,
    }
    result = source
    for old, new in replacements.items():
        result = result.replace(old, new)
    if START_TOKEN not in result or END_TOKEN not in result or "CURRENT_DATE" in result.upper():
        raise ValueError("新增次留 SQL 未完整参数化")
    return result


def migrate_bounds_cte_sql(sql: str) -> str:
    """将固定日期 bounds CTE 改为看板日期参数。"""
    source = str(sql or "")
    result = re.sub(
        r"CAST\s*\(\s*DATE_FORMAT\s*\(\s*DATE_SUB\s*\(\s*DATE_SUB\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*INTERVAL\s*1\s*DAY\s*\)\s*,\s*INTERVAL\s*\d+\s*DAY\s*\)\s*,\s*'%Y%m%d'\s*\)\s*AS\s*SIGNED\s*\)",
        START_TOKEN,
        source,
        count=1,
        flags=re.I,
    )
    result = re.sub(
        r"CAST\s*\(\s*DATE_FORMAT\s*\(\s*DATE_SUB\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*INTERVAL\s*1\s*DAY\s*\)\s*,\s*'%Y%m%d'\s*\)\s*AS\s*SIGNED\s*\)",
        END_TOKEN,
        result,
        count=1,
        flags=re.I,
    )
    if START_TOKEN not in result or END_TOKEN not in result or _CURRENT_DATE.search(result):
        raise ValueError("bounds CTE 未完整参数化")
    return result


def migrate_channel_registration_payment_sql(sql: str) -> str:
    """将投放注册 cohort、D7 与累计快照边界绑定到看板日期范围。"""
    source = str(sql or "")
    start_date = _parameter_date(START_TOKEN)
    end_date = _parameter_date(END_TOKEN)
    result = source.replace("DATE_SUB(DATE_SUB(CURRENT_DATE, INTERVAL '1' DAY), INTERVAL '29' DAY)", start_date)
    result = result.replace("DATE_SUB(CURRENT_DATE, INTERVAL '24' DAY)", f"DATE_ADD({start_date}, INTERVAL 6 DAY)")
    result = result.replace("DATE_SUB(CURRENT_DATE, INTERVAL '1' DAY)", end_date)
    if START_TOKEN not in result or END_TOKEN not in result or "CURRENT_DATE" in result.upper():
        raise ValueError("投放注册与付费 SQL 未完整参数化")
    return result


def migrate_core_realtime_metric_sql(sql: str) -> str:
    """将核心看板当天实时指标改为历史事件表的日期范围统计。"""
    source = str(sql or "")
    date_label = f"DATE_FORMAT({_parameter_date(END_TOKEN)}, '%Y-%m-%d')"
    result, table_count = re.subn(r"\bFROM\s+event_realtime\b", "FROM event", source, count=1, flags=re.IGNORECASE)
    result, label_count = re.subn(
        r"DATE_FORMAT\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*'%Y-%m-%d'\s*\)",
        date_label,
        result,
        count=1,
        flags=re.IGNORECASE,
    )
    today = re.compile(
        r"\bdt\s*=\s*CAST\s*\(\s*DATE_FORMAT\s*\(\s*CURDATE\s*\(\s*\)\s*,\s*'%Y%m%d'\s*\)\s*AS\s*SIGNED\s*\)",
        re.IGNORECASE,
    )
    result, date_count = today.subn(f"dt BETWEEN {START_TOKEN} AND {END_TOKEN}", result, count=1)
    if table_count != 1 or date_count != 1 or "event_realtime" in result.lower() or _CURRENT_DATE.search(result):
        raise ValueError("核心实时指标 SQL 未完整改为历史日期范围")
    return result


def migrate_end_anchor_metric_sql(sql: str) -> str:
    """将选定日卡片的日环比、周同比锚定到日期控件结束日。"""
    source = str(sql or "")
    end_date = _parameter_date(END_TOKEN)
    current_date = r"(?:CURDATE\s*\(\s*\)|CURRENT_DATE)"
    nested = re.compile(
        rf"DATE_SUB\s*\(\s*DATE_SUB\s*\(\s*{current_date}\s*,\s*INTERVAL\s*1\s*DAY\s*\)\s*,\s*INTERVAL\s*(?P<days>\d+)\s*DAY\s*\)",
        re.IGNORECASE,
    )
    result, nested_count = nested.subn(
        lambda match: f"DATE_SUB({end_date}, INTERVAL {match.group('days')} DAY)",
        source,
    )
    selected_day = re.compile(
        rf"DATE_SUB\s*\(\s*{current_date}\s*,\s*INTERVAL\s*1\s*DAY\s*\)",
        re.IGNORECASE,
    )
    result, selected_count = selected_day.subn(end_date, result)
    if nested_count + selected_count == 0 or _CURRENT_DATE.search(result) or END_TOKEN not in result:
        raise ValueError("结束日锚点 SQL 未完整参数化")
    return result


def migrate_cohort_sql(sql: str) -> str:
    """替换标准 cohort 查询的起止边界，不修改 D1/D7/D30 观察表达式。"""
    source = str(sql or "")
    start_date = _parameter_date(START_TOKEN)
    end_date = _parameter_date(END_TOKEN)
    start_pattern = re.compile(
        r"DATE_SUB\s*\(\s*DATE_SUB\s*\(\s*(?:CURDATE\s*\(\s*\)|CURRENT_DATE)\s*,\s*INTERVAL\s*1\s*DAY\s*\)\s*,\s*INTERVAL\s*\d+\s*DAY\s*\)",
        re.IGNORECASE,
    )
    end_pattern = re.compile(
        r"DATE_SUB\s*\(\s*(?:CURDATE\s*\(\s*\)|CURRENT_DATE)\s*,\s*INTERVAL\s*1\s*DAY\s*\)",
        re.IGNORECASE,
    )
    result, start_count = start_pattern.subn(start_date, source, count=1)
    result, end_count = end_pattern.subn(end_date, result, count=1)
    if start_count != 1 or end_count != 1:
        raise ValueError("cohort SQL 未找到唯一的起止边界")
    return result


def migrate_weekly_snapshots_sql(sql: str) -> str:
    """将固定八周快照计算锚定到日期控件结束日。"""
    source = str(sql or "")
    end_date = _parameter_date(END_TOKEN)
    pattern = re.compile(
        r"DATE_SUB\s*\(\s*(?:CURDATE\s*\(\s*\)|CURRENT_DATE)\s*,\s*INTERVAL\s*1\s*DAY\s*\)",
        re.IGNORECASE,
    )
    result, count = pattern.subn(end_date, source)
    if count == 0 or _CURRENT_DATE.search(result):
        raise ValueError("周快照 SQL 未完整替换结束日锚点")
    return result


def migrate_roi_sql(sql: str) -> str:
    """仅替换 ROI 安装 cohort 的固定日期边界，保留收入周期。"""
    source = str(sql or "")
    current_date = r"(?:CURDATE\s*\(\s*\)|CURRENT_DATE)"
    start = re.compile(
        rf"(?P<field>\b[A-Za-z_][\w]*\.dt)\s*>=\s*CAST\s*\(\s*DATE_FORMAT\s*\(\s*DATE_SUB\s*\(\s*{current_date}\s*,\s*INTERVAL\s*\d+\s*DAY\s*\)\s*,\s*'%Y%m%d'\s*\)\s*AS\s*BIGINT\s*\)",
        re.IGNORECASE,
    )
    end = re.compile(
        rf"(?P<field>\b[A-Za-z_][\w]*\.dt)\s*<=\s*CAST\s*\(\s*DATE_FORMAT\s*\(\s*DATE_SUB\s*\(\s*{current_date}\s*,\s*INTERVAL\s*1\s*DAY\s*\)\s*,\s*'%Y%m%d'\s*\)\s*AS\s*BIGINT\s*\)",
        re.IGNORECASE,
    )
    result, start_count = start.subn(lambda match: f"{match.group('field')} >= {START_TOKEN}", source)
    result, end_count = end.subn(lambda match: f"{match.group('field')} <= {END_TOKEN}", result)
    if start_count == 0 or end_count == 0 or _CURRENT_DATE.search(result):
        raise ValueError("ROI SQL 未完整替换 cohort 日期边界")
    return result


def repair_explicit_retention_sql(sql: str, *, column_name: str) -> str:
    """将已写入的递归 cohort SQL 修复为数据源兼容的数字序列实现。"""
    source = str(sql or "")
    if not source.upper().startswith("WITH RECURSIVE"):
        raise ValueError("SQL 不是待修复的递归 cohort 查询")
    result = re.sub(r"^WITH\s+RECURSIVE\s+", "WITH\n", source, count=1, flags=re.IGNORECASE)
    return _replace_day_offsets_cte(result, column_name=column_name)


EXPLICIT_DATE_VIEW_MIGRATIONS = {
    ("8f86e50234794606bd2a33ec41ffa660", "b55382d46c664f1dbd465964cc5e8da2"): migrate_channel_retention_sql,
    ("5cee4cf41a024c56ac9de0e3aef9aefe", "63e03c7e2ad34ad58321892998497a85"): migrate_channel_retention_sql,
    ("8f86e50234794606bd2a33ec41ffa660", "3bb23e771d584610a2c88a38760163b6"): migrate_active_retention_sql,
    ("8f86e50234794606bd2a33ec41ffa660", "2187432754973679616"): migrate_next_day_retention_sql,
}


def target_migration(target: DateMigrationTarget):
    if target.title in {"参与新手活动的后续7日留存率", "参与节日活动用户的当日/D7付费率"}:
        return migrate_activity_d7_cohort_sql
    if target.title == "新增用户次日留存":
        return migrate_quoted_next_day_retention_sql
    if target.title == "各英雄出征胜率":
        return migrate_bounds_cte_sql
    if target.title == "各渠道注册与付费":
        return migrate_channel_registration_payment_sql
    return {
        "range": migrate_parallel_range_sql,
        "core_range": migrate_core_realtime_metric_sql,
        "end_anchor": migrate_end_anchor_metric_sql,
        "cohort": migrate_cohort_sql,
        "weekly_snapshots": migrate_weekly_snapshots_sql,
        "roi": migrate_roi_sql,
    }[target.kind]


def date_migration_target_by_chart_id(chart_id: str) -> DateMigrationTarget | None:
    matches = [target for (_, target_id), target in DATE_MIGRATION_TARGETS.items() if target_id == chart_id]
    if len(matches) > 1:
        raise RuntimeError(f"图表 ID 在日期迁移清单中不唯一：{chart_id}")
    return matches[0] if matches else None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_hash(value: Any) -> str:
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _is_word_at(value: str, index: int, words: tuple[str, ...]) -> str | None:
    if index > 0 and (value[index - 1].isalnum() or value[index - 1] == "_"):
        return None
    upper = value[index:].upper()
    for word in words:
        if not upper.startswith(word):
            continue
        end = index + len(word)
        if end >= len(value) or not (value[end].isalnum() or value[end] == "_"):
            return word
    return None


def _find_top_level_word(value: str, start: int, words: tuple[str, ...]) -> int:
    depth = 0
    quote = ""
    index = start
    while index < len(value):
        char = value[index]
        if quote:
            if char == "\\" and index + 1 < len(value):
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and _is_word_at(value, index, words):
            return index
        index += 1
    return -1


def is_safe_candidate(sql: str) -> bool:
    source = str(sql or "")
    matches = list(_PARTITION_RANGE.finditer(source))
    return bool(
        len(matches) == 1
        and "{{dashboard_" not in source
        and "event_realtime" not in source.lower()
        and len(_CURRENT_DATE.findall(source)) == 2
        and not _UNSUPPORTED_SEMANTICS.search(source)
    )


def replace_unique_partition_range(sql: str) -> str:
    source = str(sql or "")
    matches = list(_PARTITION_RANGE.finditer(source))
    if len(matches) != 1:
        raise ValueError("SQL 不包含唯一分区日期窗口")
    match = matches[0]
    start_expression = match.end()
    and_index = _find_top_level_word(source, start_expression, ("AND",))
    if and_index < 0:
        raise ValueError("分区日期窗口缺少结束条件")
    end_expression = and_index + 3
    suffix_index = _find_top_level_word(source, end_expression, _BOUNDARY_WORDS)
    if suffix_index < 0:
        suffix_index = source.find(";", end_expression)
    if suffix_index < 0:
        suffix_index = len(source)
    replacement = f"{match.group('alias')}.dt BETWEEN {START_TOKEN} AND {END_TOKEN}"
    suffix = source[suffix_index:]
    separator = " " if suffix and not suffix[0].isspace() else ""
    migrated = source[:match.start()] + replacement + separator + suffix
    if migrated.count(START_TOKEN) != 1 or migrated.count(END_TOKEN) != 1:
        raise ValueError("受控日期参数数量异常")
    return migrated


def _date_field(view: dict[str, Any]) -> str:
    pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
    configured = str(pivot.get("time_field") or "").strip()
    if configured:
        return configured
    chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
    axes = chart.get("xAxis") if isinstance(chart.get("xAxis"), list) else []
    for axis in axes:
        if not isinstance(axis, dict):
            continue
        field = str(axis.get("value") or axis.get("name") or "").strip()
        if field:
            return field
    return "dt"


def configure_explicit_date_view(
    view: dict[str, Any],
    sql: str,
    *,
    expression: dict[str, Any] = DEFAULT_EXPRESSION,
    metric_date_expression_enabled: bool = False,
) -> dict[str, Any]:
    result = copy.deepcopy(view)
    result["sql"] = str(sql or "")
    time_field = _date_field(result)
    source_config = result.setdefault("sourceConfig", {})
    if not isinstance(source_config, dict):
        raise ValueError("sourceConfig 配置无效")
    sql_config = source_config.setdefault("sql", {})
    if not isinstance(sql_config, dict):
        raise ValueError("sourceConfig.sql 配置无效")
    sql_config["sql"] = result["sql"]
    builder = sql_config.setdefault("builder", {})
    if not isinstance(builder, dict):
        raise ValueError("sourceConfig.sql.builder 配置无效")
    builder.update(
        {
            "dateExpressionPickerEnabled": True,
            "metricDateExpressionEnabled": metric_date_expression_enabled,
            "timeField": time_field,
            "timeRange": "expression",
            "timeExpression": copy.deepcopy(expression),
        }
    )
    pivot = result.setdefault("pivot", {})
    if not isinstance(pivot, dict):
        raise ValueError("pivot 配置无效")
    pivot.update(
        {
            "time_field": time_field,
            "range_enabled": True,
            "client_filter_only": False,
            "date_parameter_type": "yyyymmdd_number",
            "date_expression": copy.deepcopy(expression),
        }
    )
    if metric_date_expression_enabled:
        result["configVersion"] = 2
        result["dateFilter"] = {
            "enabled": True,
            "parameterType": "yyyymmdd_number",
            "expression": copy.deepcopy(expression),
        }
    return result


def configure_view(view: dict[str, Any]) -> dict[str, Any]:
    source_sql = str(view.get("sql") or "")
    if not is_safe_candidate(source_sql):
        raise ValueError("SQL 不属于可安全迁移的唯一分区日期窗口")
    return configure_explicit_date_view(view, replace_unique_partition_range(source_sql))


def is_existing_migrated_view_with_missing_boundary_whitespace(view: dict[str, Any]) -> bool:
    """识别仅由本次旧版迁移产生的 ``}}AND`` 损坏态。"""
    sql = str(view.get("sql") or "")
    if sql.count(START_TOKEN) != 1 or sql.count(END_TOKEN) != 1 or not _MISSING_BOUNDARY_WHITESPACE.search(sql):
        return False
    source_config = view.get("sourceConfig") if isinstance(view.get("sourceConfig"), dict) else {}
    sql_config = source_config.get("sql") if isinstance(source_config.get("sql"), dict) else {}
    builder = sql_config.get("builder") if isinstance(sql_config.get("builder"), dict) else {}
    pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
    return (
        builder.get("dateExpressionPickerEnabled") is True
        and builder.get("timeExpression") == DEFAULT_EXPRESSION
        and pivot.get("range_enabled") is True
        and pivot.get("client_filter_only") is False
        and pivot.get("date_parameter_type") == "yyyymmdd_number"
        and pivot.get("date_expression") == DEFAULT_EXPRESSION
    )


def repair_existing_migrated_view(view: dict[str, Any]) -> dict[str, Any]:
    if not is_existing_migrated_view_with_missing_boundary_whitespace(view):
        raise ValueError("图表不属于可安全修复的旧版日期迁移损坏态")
    result = copy.deepcopy(view)
    result["sql"] = _MISSING_BOUNDARY_WHITESPACE.sub(
        lambda match: f"{END_TOKEN} {match.group('word')}",
        str(result.get("sql") or ""),
        count=1,
    )
    return result


def _canvas(raw: str) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("canvas_view_info 不是合法 JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("canvas_view_info 不是对象")
    return result


def _chart_title(view: dict[str, Any], chart_id: str) -> str:
    chart = view.get("chart") if isinstance(view.get("chart"), dict) else {}
    return str(chart.get("title") or view.get("title") or chart_id)


def migrate_canvas(canvas: dict[str, Any], *, dashboard_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    migrated = copy.deepcopy(canvas)
    targets: list[str] = []
    for chart_id, view in canvas.items():
        if not isinstance(view, dict):
            continue
        target_key = (dashboard_id, chart_id)
        explicit_migration = EXPLICIT_DATE_VIEW_MIGRATIONS.get(target_key)
        target = DATE_MIGRATION_TARGETS.get(target_key)
        source_config = view.get("sourceConfig") if isinstance(view.get("sourceConfig"), dict) else {}
        sql_config = source_config.get("sql") if isinstance(source_config.get("sql"), dict) else {}
        builder = sql_config.get("builder") if isinstance(sql_config.get("builder"), dict) else {}
        if explicit_migration:
            sql = str(view.get("sql") or "")
            incompatible_recursive_offsets = "WITH RECURSIVE" in sql.upper()
            if (
                builder.get("dateExpressionPickerEnabled") is not True
                or START_TOKEN not in sql
                or END_TOKEN not in sql
                or incompatible_recursive_offsets
            ):
                targets.append(chart_id)
            continue
        if target:
            sql = str(view.get("sql") or "")
            if builder.get("dateExpressionPickerEnabled") is not True or (
                END_TOKEN not in sql
                or (target.kind in {"range", "core_range", "cohort", "roi"} and START_TOKEN not in sql)
            ) or (
                target.kind == "core_range"
                and (
                    builder.get("metricDateExpressionEnabled") is not True
                    or builder.get("timeExpression") != CORE_METRIC_EXPRESSION
                )
            ):
                targets.append(chart_id)
            continue
        if (
            is_safe_candidate(str(view.get("sql") or ""))
            or is_existing_migrated_view_with_missing_boundary_whitespace(view)
        ):
            targets.append(chart_id)
    unchanged = {
        chart_id: stable_json_hash(view)
        for chart_id, view in canvas.items()
        if chart_id not in targets
    }
    for chart_id in targets:
        source_view = migrated[chart_id]
        explicit_migration = EXPLICIT_DATE_VIEW_MIGRATIONS.get((dashboard_id, chart_id))
        target = DATE_MIGRATION_TARGETS.get((dashboard_id, chart_id))
        if explicit_migration:
            source_sql = str(source_view.get("sql") or "")
            repaired_sql = (
                repair_explicit_retention_sql(
                    source_sql,
                    column_name="day_offset" if explicit_migration is migrate_active_retention_sql else "n",
                )
                if "WITH RECURSIVE" in source_sql.upper()
                else explicit_migration(source_sql)
            )
            migrated[chart_id] = configure_explicit_date_view(
                source_view,
                repaired_sql,
            )
        elif target:
            migrated[chart_id] = configure_explicit_date_view(
                source_view,
                target_migration(target)(str(source_view.get("sql") or "")),
                expression=(
                    CORE_METRIC_EXPRESSION
                    if target.kind == "core_range"
                    else DEFAULT_EXPRESSION
                ),
                metric_date_expression_enabled=target.kind == "core_range",
            )
        else:
            migrated[chart_id] = (
                configure_view(source_view)
                if is_safe_candidate(str(source_view.get("sql") or ""))
                else repair_existing_migrated_view(source_view)
            )
    return migrated, unchanged


def verify_canvas(canvas: dict[str, Any], *, target_ids: list[str], unchanged: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for chart_id in target_ids:
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"读回缺少目标图表：{chart_id}")
        sql = str(view.get("sql") or "")
        source_config = view.get("sourceConfig") if isinstance(view.get("sourceConfig"), dict) else {}
        builder = source_config.get("sql", {}).get("builder", {}) if isinstance(source_config.get("sql"), dict) else {}
        pivot = view.get("pivot") if isinstance(view.get("pivot"), dict) else {}
        target = date_migration_target_by_chart_id(chart_id)
        expected_expression = (
            CORE_METRIC_EXPRESSION
            if target and target.kind == "core_range"
            else DEFAULT_EXPRESSION
        )
        explicit_target = any(chart_id == target_id for _, target_id in EXPLICIT_DATE_VIEW_MIGRATIONS)
        if target and target.kind in {"end_anchor", "weekly_snapshots"}:
            invalid_token_counts = sql.count(START_TOKEN) != 0 or sql.count(END_TOKEN) < 1
        elif explicit_target or (target and target.kind in {"range", "core_range", "cohort", "roi"}):
            invalid_token_counts = sql.count(START_TOKEN) < 1 or sql.count(END_TOKEN) < 1
        else:
            invalid_token_counts = sql.count(START_TOKEN) != 1 or sql.count(END_TOKEN) != 1
        if (
            invalid_token_counts
            or builder.get("dateExpressionPickerEnabled") is not True
            or builder.get("timeExpression") != expected_expression
            or (
                target is not None
                and target.kind == "core_range"
                and builder.get("metricDateExpressionEnabled") is not True
            )
            or pivot.get("range_enabled") is not True
            or pivot.get("client_filter_only") is not False
            or pivot.get("date_parameter_type") != "yyyymmdd_number"
            or pivot.get("date_expression") != expected_expression
        ):
            raise RuntimeError(f"日期配置读回校验失败：{chart_id}")
        result[chart_id] = {"title": _chart_title(view, chart_id), "sql_sha256": sha256_text(sql)}
    for chart_id, expected_hash in unchanged.items():
        if chart_id not in canvas or stable_json_hash(canvas[chart_id]) != expected_hash:
            raise RuntimeError(f"非目标图表发生变化：{chart_id}")
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _backup(row: dict[str, Any], *, new_canvas: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_default_dashboard_date_filters_{row['id']}_{time.time_ns()}.json"
    payload = {
        "dashboard_id": row["id"],
        "tenant_id": row["tenant_id"],
        "old_canvas_sha256": sha256_text(row["canvas_view_info"]),
        "new_canvas_sha256": sha256_text(new_canvas),
        "row": {key: _json_value(value) for key, value in row.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


def _select_dashboards(cur: Any, *, lock: bool) -> list[dict[str, Any]]:
    cur.execute(
        f"""
        SELECT id, tenant_id, name, update_time, canvas_view_info
        FROM public.core_dashboard
        WHERE tenant_id = %s AND type = 'dashboard' AND node_type = 'leaf'
          AND status = 1 AND COALESCE(delete_flag, 0) = 0 AND is_default = 1
        ORDER BY id
        {'FOR UPDATE' if lock else ''}
        """,
        (TENANT_ID,),
    )
    return list(cur.fetchall())


def migrate_default_dashboards(*, apply: bool) -> dict[str, Any]:
    plans: list[tuple[dict[str, Any], str, list[str], dict[str, str]]] = []
    backups: list[str] = []
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for row in _select_dashboards(cur, lock=apply):
                original = _canvas(row["canvas_view_info"])
                migrated, unchanged = migrate_canvas(original, dashboard_id=row["id"])
                target_ids = [chart_id for chart_id, view in migrated.items() if chart_id in original and stable_json_hash(view) != stable_json_hash(original[chart_id])]
                if not target_ids:
                    continue
                new_raw = json.dumps(migrated, ensure_ascii=False, separators=(",", ":"))
                verify_canvas(migrated, target_ids=target_ids, unchanged=unchanged)
                plans.append((row, new_raw, target_ids, unchanged))
            if apply:
                for row, new_raw, _, _ in plans:
                    backups.append(str(_backup(row, new_canvas=new_raw)))
                    cur.execute(
                        """
                        UPDATE public.core_dashboard
                        SET canvas_view_info = %s, update_time = %s
                        WHERE id = %s AND tenant_id = %s AND canvas_view_info = %s
                          AND COALESCE(delete_flag, 0) = 0
                        """,
                        (new_raw, int(time.time()), row["id"], TENANT_ID, row["canvas_view_info"]),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(f"CAS 更新数量异常：{row['id']}")
                conn.commit()
            else:
                conn.rollback()

    verified: dict[str, Any] = {}
    if apply:
        with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                rows = {row["id"]: row for row in _select_dashboards(cur, lock=False)}
                for row, _, target_ids, unchanged in plans:
                    current = rows.get(row["id"])
                    if not current:
                        raise RuntimeError(f"读回缺少目标看板：{row['id']}")
                    verified[row["id"]] = verify_canvas(_canvas(current["canvas_view_info"]), target_ids=target_ids, unchanged=unchanged)
            conn.rollback()
    return {
        "applied": apply,
        "dashboard_count": len(plans),
        "chart_count": sum(len(target_ids) for _, _, target_ids, _ in plans),
        "backups": backups,
        "charts": verified if apply else {row["id"]: target_ids for row, _, target_ids, _ in plans},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="备份后写入候选看板")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(migrate_default_dashboards(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
