"""Server-authenticated path query protocol, shared by every execution surface."""
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

from apps.dashboard.crud.path_sql_compiler import PATH_GUARD_COLUMN as GUARD_COLUMN

MARKER = re.compile(r"/\* path-contract-v1:([A-Za-z0-9_=-]+)\.([0-9a-f]{64}) \*/")


def metadata_digest(value):
    if hasattr(value, "model_dump"): value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value or {}, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _key():
    from common.core.config import settings
    value = settings.SECRET_KEY
    return (value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)).encode()


def path_tree(sql, dialect):
    text = MARKER.sub("", sql)
    text = re.sub(r"\{\{(dashboard_[a-z_]+)\}\}", r":\1", text)
    trees = [t for t in sqlglot.parse(text, read=dialect) if t is not None]
    if len(trees) != 1 or not isinstance(trees[0], exp.Query): raise ValueError("路径 SQL 必须为单条只读查询。")
    for n in trees[0].walk(): n.comments = None
    return trees[0]


def path_fingerprint(sql, dialect):
    tree = path_tree(sql, dialect)
    bounds = [c for c in tree.find_all(exp.CTE) if c.alias == "path_parameter_bounds"]
    if len(bounds) != 1: raise ValueError("路径日期边界结构不完整。")
    select = bounds[0].this
    if not isinstance(select, exp.Select) or len(select.selects) != 2 or set(select.args) - {"expressions"}:
        # SQLGlot may set empty optional keys; only populated clauses matter.
        if not isinstance(select, exp.Select) or len(select.selects) != 2 or any(v for k, v in select.args.items() if k != "expressions"):
            raise ValueError("路径日期边界只能包含两个日期参数。")
    for i, node in enumerate(select.selects):
        if node.alias != ("range_start", "range_end")[i] or any(isinstance(n, (exp.Query, exp.Column)) for n in node.walk()):
            raise ValueError("路径日期参数无效。")
    select.set("expressions", [exp.alias_(exp.Literal.number(0), n) for n in ("range_start", "range_end")])
    return hashlib.sha256(tree.sql(dialect=dialect).encode()).hexdigest()


def attach_path_contract(sql, plan, *, tenant_id, datasource_id, tracking_metadata):
    contract = {"kind": "path", "version": 1, "dialect": plan.dialect, "guard_column": GUARD_COLUMN,
                "columns": list(plan.required_columns), "business_timezone": plan.time.business_timezone,
                "naive_timezones": list(plan.time.naive_timezones), "mysql_utc": plan.time.mysql_utc,
                "mysql_timezones": list(plan.time.mysql_timezones),
                "parameter_type": plan.time.parameter_type, "tenant_id": tenant_id, "datasource_id": int(datasource_id),
                "metadata_digest": metadata_digest(tracking_metadata), "fingerprint": path_fingerprint(sql, plan.dialect)}
    payload = base64.urlsafe_b64encode(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).decode()
    signature = hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"/* path-contract-v1:{payload}.{signature} */\n{sql}"


def read_path_contract(sql):
    matches = list(MARKER.finditer(sql or ""))
    if not matches:
        if re.search(r"\b(?:__path_order_error|path_guard|path_parameter_bounds)\b|path-contract-v1", sql or "", re.I):
            raise ValueError("路径执行协议缺失或损坏，请重新生成 SQL。")
        return None
    if len(matches) != 1: raise ValueError("路径执行协议重复。")
    payload, signature = matches[0].groups()
    if not hmac.compare_digest(signature, hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()):
        raise ValueError("路径执行协议签名无效，请重新生成 SQL。")
    contract = json.loads(base64.urlsafe_b64decode(payload))
    if contract.get("kind") != "path" or contract.get("version") != 1 or contract.get("guard_column") != GUARD_COLUMN:
        raise ValueError("路径执行协议版本不支持。")
    if path_fingerprint(sql, contract["dialect"]) != contract["fingerprint"]:
        raise ValueError("路径 SQL 已偏离已验证配置，请重新生成。")
    return contract


def path_date_range(sql, contract):
    tree = path_tree(sql, contract["dialect"])
    bounds = next(c for c in tree.find_all(exp.CTE) if c.alias == "path_parameter_bounds")
    dates = []
    for node in bounds.this.selects:
        value_node = node.this.unnest()
        parameter = contract["parameter_type"]
        if isinstance(value_node, exp.Cast):
            allowed = {exp.DataType.Type.DATE} if parameter == "date" else {exp.DataType.Type.TIMESTAMP, exp.DataType.Type.DATETIME}
            if parameter.startswith("yyyymmdd") or value_node.to.this not in allowed:
                raise ValueError("路径日期参数转换类型不匹配。")
            value_node = value_node.this.unnest()
        if not isinstance(value_node, exp.Literal) or value_node.is_string == (parameter == "yyyymmdd_number"):
            raise ValueError("路径日期参数必须是对应类型的日期常量，不能包含计算表达式。")
        value = str(value_node.this)
        parsed = (datetime.strptime(value, "%Y%m%d") if parameter.startswith("yyyymmdd") else
                  datetime.strptime(value, "%Y-%m-%d") if parameter == "date" else datetime.fromisoformat(value))
        if parsed.tzinfo is not None: raise ValueError("路径日期参数必须使用业务时区的本地时间。")
        dates.append(parsed)
    if contract["parameter_type"] != "timestamp": dates[1] += timedelta(days=1)
    return tuple(dates)


def validate_path_execution_context(contract, date_range, datasource_capabilities=None):
    from common.core.config import settings
    if contract["business_timezone"] != settings.DASHBOARD_BUSINESS_TIMEZONE:
        raise ValueError("业务时区已变更，请重新生成路径 SQL。")
    start, end = (datetime.fromisoformat(v) if isinstance(v, str) else v for v in date_range)
    if end <= start: raise ValueError("路径日期范围无效。")
    for zone_name in contract["naive_timezones"]:
        zone = ZoneInfo(zone_name)
        business = ZoneInfo(contract["business_timezone"])
        point = start.replace(tzinfo=business).astimezone(timezone.utc)
        stop = end.replace(tzinfo=business).astimezone(timezone.utc) - timedelta(microseconds=1)
        offset = (point - timedelta(microseconds=1)).astimezone(zone).utcoffset()
        if point.astimezone(zone).utcoffset() != offset:
            raise ValueError("PATH_TIME_AMBIGUOUS：无时区事件时间的查询起点落在夏令时切换，请使用绝对时间字段。")
        while point < stop:
            point = min(point + timedelta(hours=6), stop)
            next_offset = point.astimezone(zone).utcoffset()
            if next_offset != offset:
                raise ValueError("PATH_TIME_AMBIGUOUS：无时区事件时间的查询范围覆盖夏令时切换，请使用绝对时间字段。")
            offset = next_offset


def validate_path_execution_result(result, contract):
    if not contract or result.get("status") == "failed": return result
    fields = result.get("fields") or []
    if fields != [*contract["columns"], GUARD_COLUMN]:
        raise ValueError("路径结果缺少固定业务列或排序校验列。")
    from common.core.config import settings
    limit = max(1, int(settings.SHUZHI_QUERY_RESULT_MAX_ROWS))
    if len(result.get("data") or []) > limit:
        raise ValueError(f"路径结果超过 {limit} 行，请缩小日期范围或减少分组；不会返回被截断的路径结果。")
    rows = []
    for row in result.get("data") or []:
        value = row.get(GUARD_COLUMN)
        if type(value) not in (int, float) or value not in (0, 1): raise ValueError("路径排序校验返回了非法值。")
        if value == 1: raise ValueError("PATH_ORDER_DATA_CONFLICT：事件时间或排序键为空或重复，请修正事件排序元数据及源数据。")
        if set(row) != set(fields): raise ValueError("路径结果字段不完整。")
        rows.append({key: row[key] for key in contract["columns"]})
    return {**result, "fields": list(contract["columns"]), "data": rows,
            "_path_contract": {"guard_status": "passed", "version": 1, "fingerprint": contract["fingerprint"], "metadata_digest": contract["metadata_digest"]}}


def require_path_contract(sql, expected=None):
    contract = read_path_contract(sql)
    if expected is not None and expected != contract:
        raise ValueError("路径图表的执行协议与 SQL 不一致，请重新生成。")
    return contract


def validate_path_workspace_contract(session, current_user, datasource_id, sql, expected=None):
    contract = require_path_contract(sql, expected)
    if not contract: return None
    from apps.system.crud.tracking_config import get_tracking_config
    from apps.system.schemas.access_context import require_current_tenant_id
    tenant = require_current_tenant_id(current_user)
    if contract["tenant_id"] != tenant or contract["datasource_id"] != int(datasource_id):
        raise ValueError("路径 SQL 与当前工作空间或数据源不一致，请重新生成。")
    tracking = get_tracking_config(session, tenant, int(datasource_id), include_legacy=False)
    if contract["metadata_digest"] != metadata_digest(tracking):
        raise ValueError("工作空间元数据已变更，请重新生成路径 SQL。")
    validate_path_execution_context(contract, path_date_range(sql, contract))
    return contract
