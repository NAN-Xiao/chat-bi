"""Server-authenticated interval query protocol, shared by every execution surface."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import sqlglot
from sqlglot import exp

from apps.dashboard.crud.interval_sql_compiler import GUARD_COLUMN

MARKER = re.compile(r"/\* interval-contract-v1:([A-Za-z0-9_=-]+)\.([0-9a-f]{64}) \*/")


def metadata_digest(value):
    if hasattr(value, "model_dump"): value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value or {}, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _key():
    from common.core.config import settings
    value = settings.SECRET_KEY
    return (value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)).encode()


def interval_tree(sql, dialect):
    text = MARKER.sub("", sql)
    text = re.sub(r"\{\{(dashboard_[a-z_]+)\}\}", r":\1", text)
    trees = [t for t in sqlglot.parse(text, read=dialect) if t is not None]
    if len(trees) != 1 or not isinstance(trees[0], exp.Query): raise ValueError("间隔 SQL 必须为单条只读查询。")
    for n in trees[0].walk(): n.comments = None
    return trees[0]


def interval_fingerprint(sql, dialect):
    tree = interval_tree(sql, dialect)
    bounds = [c for c in tree.find_all(exp.CTE) if c.alias == "interval_parameter_bounds"]
    if len(bounds) != 1: raise ValueError("间隔日期边界结构不完整。")
    select = bounds[0].this
    if not isinstance(select, exp.Select) or len(select.selects) != 2 or set(select.args) - {"expressions"}:
        # SQLGlot may set empty optional keys; only populated clauses matter.
        if not isinstance(select, exp.Select) or len(select.selects) != 2 or any(v for k, v in select.args.items() if k != "expressions"):
            raise ValueError("间隔日期边界只能包含两个日期参数。")
    for i, node in enumerate(select.selects):
        if node.alias != ("range_start", "range_end")[i] or any(isinstance(n, (exp.Query, exp.Column)) for n in node.walk()):
            raise ValueError("间隔日期参数无效。")
    select.set("expressions", [exp.alias_(exp.Literal.number(0), n) for n in ("range_start", "range_end")])
    return hashlib.sha256(tree.sql(dialect=dialect).encode()).hexdigest()


def attach_interval_contract(sql, plan, *, tenant_id, datasource_id, tracking_metadata):
    contract = {"kind": "interval", "version": 1, "dialect": plan.dialect, "guard_column": GUARD_COLUMN,
                "columns": list(plan.required_columns), "business_timezone": plan.time.business_timezone,
                "naive_timezones": list(plan.time.naive_timezones), "mysql_utc": plan.time.mysql_utc,
                "mysql_timezones": list(plan.time.mysql_timezones),
                "parameter_type": plan.time.parameter_type, "tenant_id": tenant_id, "datasource_id": int(datasource_id),
                "metadata_digest": metadata_digest(tracking_metadata), "fingerprint": interval_fingerprint(sql, plan.dialect)}
    payload = base64.urlsafe_b64encode(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).decode()
    signature = hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"/* interval-contract-v1:{payload}.{signature} */\n{sql}"


def read_interval_contract(sql):
    matches = list(MARKER.finditer(sql or ""))
    if not matches:
        if re.search(r"\b(?:__interval_order_error|interval_guard|interval_parameter_bounds)\b|interval-contract-v1", sql or "", re.I):
            raise ValueError("间隔执行协议缺失或损坏，请重新生成 SQL。")
        return None
    if len(matches) != 1: raise ValueError("间隔执行协议重复。")
    payload, signature = matches[0].groups()
    if not hmac.compare_digest(signature, hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()):
        raise ValueError("间隔执行协议签名无效，请重新生成 SQL。")
    contract = json.loads(base64.urlsafe_b64decode(payload))
    if contract.get("kind") != "interval" or contract.get("version") != 1 or contract.get("guard_column") != GUARD_COLUMN:
        raise ValueError("间隔执行协议版本不支持。")
    if interval_fingerprint(sql, contract["dialect"]) != contract["fingerprint"]:
        raise ValueError("间隔 SQL 已偏离已验证配置，请重新生成。")
    return contract


def interval_date_range(sql, contract):
    tree = interval_tree(sql, contract["dialect"])
    bounds = next(c for c in tree.find_all(exp.CTE) if c.alias == "interval_parameter_bounds")
    dates = []
    for node in bounds.this.selects:
        literals = list(node.find_all(exp.Literal))
        if len(literals) != 1: raise ValueError("间隔日期参数尚未解析。")
        value = str(literals[0].this)
        dates.append(datetime.strptime(value, "%Y%m%d") if contract["parameter_type"].startswith("yyyymmdd") else datetime.fromisoformat(value))
    if contract["parameter_type"] != "timestamp": dates[1] += timedelta(days=1)
    return tuple(dates)


def validate_interval_execution_context(contract, date_range, datasource_capabilities=None):
    from common.core.config import settings
    if contract["business_timezone"] != settings.DASHBOARD_BUSINESS_TIMEZONE:
        raise ValueError("业务时区已变更，请重新生成间隔 SQL。")
    start, end = (datetime.fromisoformat(v) if isinstance(v, str) else v for v in date_range)
    if end <= start: raise ValueError("间隔日期范围无效。")
    for zone_name in contract["naive_timezones"]:
        zone = ZoneInfo(zone_name)
        business = ZoneInfo(contract["business_timezone"])
        point = start.replace(tzinfo=business).astimezone(timezone.utc)
        stop = end.replace(tzinfo=business).astimezone(timezone.utc) - timedelta(microseconds=1)
        offset = (point - timedelta(microseconds=1)).astimezone(zone).utcoffset()
        if point.astimezone(zone).utcoffset() != offset:
            raise ValueError("INTERVAL_TIME_AMBIGUOUS：无时区事件时间的查询起点落在夏令时切换，请使用绝对时间字段。")
        while point < stop:
            point = min(point + timedelta(hours=6), stop)
            next_offset = point.astimezone(zone).utcoffset()
            if next_offset != offset:
                raise ValueError("INTERVAL_TIME_AMBIGUOUS：无时区事件时间的查询范围覆盖夏令时切换，请使用绝对时间字段。")
            offset = next_offset


def validate_interval_execution_result(result, contract):
    if not contract or result.get("status") == "failed": return result
    fields = result.get("fields") or []
    if fields != [*contract["columns"], GUARD_COLUMN]:
        raise ValueError("间隔结果缺少固定业务列或排序校验列。")
    from common.core.config import settings
    limit = max(1, int(settings.SHUZHI_QUERY_RESULT_MAX_ROWS))
    if len(result.get("data") or []) > limit:
        raise ValueError(f"间隔结果超过 {limit} 行，请缩小日期范围或减少分组；不会返回被截断的日期结果。")
    rows = []
    for row in result.get("data") or []:
        value = row.get(GUARD_COLUMN)
        if type(value) not in (int, float) or value not in (0, 1): raise ValueError("间隔排序校验返回了非法值。")
        if value == 1: raise ValueError("INTERVAL_ORDER_DATA_CONFLICT：事件时间或排序键为空或重复，请修正事件排序元数据及源数据。")
        if set(row) != set(fields): raise ValueError("间隔结果字段不完整。")
        rows.append({key: row[key] for key in contract["columns"]})
    return {**result, "fields": list(contract["columns"]), "data": rows,
            "_interval_contract": {"guard_status": "passed", "version": 1, "fingerprint": contract["fingerprint"], "metadata_digest": contract["metadata_digest"]}}


def require_interval_contract(sql, expected=None):
    contract = read_interval_contract(sql)
    if expected is not None and expected != contract:
        raise ValueError("间隔图表的执行协议与 SQL 不一致，请重新生成。")
    return contract


def validate_interval_workspace_contract(session, current_user, datasource_id, sql, expected=None):
    contract = require_interval_contract(sql, expected)
    if not contract: return None
    from apps.system.crud.tracking_config import get_tracking_config
    from apps.system.schemas.access_context import require_current_tenant_id
    tenant = require_current_tenant_id(current_user)
    if contract["tenant_id"] != tenant or contract["datasource_id"] != int(datasource_id):
        raise ValueError("间隔 SQL 与当前工作空间或数据源不一致，请重新生成。")
    tracking = get_tracking_config(session, tenant, int(datasource_id), include_legacy=False)
    if contract["metadata_digest"] != metadata_digest(tracking):
        raise ValueError("工作空间元数据已变更，请重新生成间隔 SQL。")
    validate_interval_execution_context(contract, interval_date_range(sql, contract))
    return contract
