"""Authenticated ranking SQL and atomic attribute-cardinality checks."""
import base64
import hashlib
import hmac
import json
import re
from datetime import datetime

import sqlglot
from sqlglot import exp

from apps.dashboard.crud.path_execution_contract import metadata_digest, _key
from apps.dashboard.crud.ranking_sql_compiler import GUARD_COLUMN

MARKER = re.compile(r"/\* ranking-contract-v1:([A-Za-z0-9_=-]+)\.([0-9a-f]{64}) \*/")


def ranking_tree(sql, dialect):
    text = re.sub(r"\{\{(dashboard_[a-z_]+)\}\}", r":\1", MARKER.sub("", sql))
    statements = [t for t in sqlglot.parse(text, read=dialect) if t is not None]
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError("排行榜 SQL 必须为单条只读查询。")
    for node in statements[0].walk():
        node.comments = None
    return statements[0]


def parameter_bounds(tree):
    nodes = [n for n in tree.find_all(exp.CTE) if n.alias == "ranking_parameter_bounds"]
    if len(nodes) != 1 or not isinstance(nodes[0].this, exp.Select):
        raise ValueError("排行榜日期边界缺失。")
    node = nodes[0].this
    if len(node.selects) != 2 or any(v for k,v in node.args.items() if k != "expressions"):
        raise ValueError("排行榜日期边界结构无效。")
    for i, value in enumerate(node.selects):
        if value.alias != ("range_start", "range_end")[i] or any(isinstance(n, (exp.Query, exp.Column)) for n in value.walk()):
            raise ValueError("排行榜日期参数无效。")
    return node


def fingerprint(sql, dialect):
    tree = ranking_tree(sql, dialect)
    parameter_bounds(tree).set("expressions", [exp.alias_(exp.Literal.number(0), name) for name in ("range_start", "range_end")])
    return hashlib.sha256(tree.sql(dialect=dialect).encode()).hexdigest()


def attach_ranking_contract(sql, plan, *, tenant_id, datasource_id, tracking_metadata):
    contract = {"kind": "ranking", "version": 1, "dialect": plan.dialect, "tenant_id": tenant_id,
        "datasource_id": int(datasource_id), "columns": list(plan.required_columns), "parameter_type": plan.parameter_type,
        "business_timezone": plan.business_timezone, "mysql_utc": False, "mysql_timezones": list(plan.mysql_timezones),
        "metadata_digest": metadata_digest(tracking_metadata), "fingerprint": fingerprint(sql, plan.dialect)}
    payload = base64.urlsafe_b64encode(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).decode()
    signature = hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"/* ranking-contract-v1:{payload}.{signature} */\n{sql}"


def read_ranking_contract(sql):
    matches = list(MARKER.finditer(sql or ""))
    if not matches:
        if re.search(r"ranking-contract-v1|\branking_parameter_bounds\b|\b__ranking_property_error\b", sql or "", re.I):
            raise ValueError("排行榜执行协议缺失或损坏，请重新生成 SQL。")
        return None
    if len(matches) != 1:
        raise ValueError("排行榜执行协议重复。")
    payload, signature = matches[0].groups()
    if not hmac.compare_digest(signature, hmac.new(_key(), payload.encode(), hashlib.sha256).hexdigest()):
        raise ValueError("排行榜执行协议签名无效。")
    contract = json.loads(base64.urlsafe_b64decode(payload))
    if contract.get("kind") != "ranking" or contract.get("version") != 1:
        raise ValueError("排行榜执行协议版本不支持。")
    if fingerprint(sql, contract["dialect"]) != contract["fingerprint"]:
        raise ValueError("排行榜 SQL 已偏离已验证配置，请重新生成。")
    return contract


def validate_ranking_workspace_contract(session, current_user, datasource_id, sql, expected=None):
    contract = read_ranking_contract(sql)
    if expected is not None and contract != expected:
        raise ValueError("排行榜执行协议与 SQL 不一致。")
    if not contract:
        return None
    from apps.system.crud.tracking_config import get_tracking_config
    from apps.system.schemas.access_context import require_current_tenant_id
    from common.core.config import settings
    tenant = require_current_tenant_id(current_user)
    if tenant != contract["tenant_id"] or int(datasource_id) != contract["datasource_id"]:
        raise ValueError("排行榜 SQL 与当前工作空间或数据源不一致。")
    tracking = get_tracking_config(session, tenant, int(datasource_id), include_legacy=False)
    if metadata_digest(tracking) != contract["metadata_digest"]:
        raise ValueError("工作空间元数据已变更，请重新生成排行榜 SQL。")
    if settings.DASHBOARD_BUSINESS_TIMEZONE != contract["business_timezone"]:
        raise ValueError("业务时区已变更，请重新生成排行榜 SQL。")
    dates = []
    parameter = contract["parameter_type"]
    for node in parameter_bounds(ranking_tree(sql, contract["dialect"])).selects:
        value = node.this.unnest()
        if isinstance(value, exp.Cast):
            allowed = {exp.DataType.Type.DATE} if parameter == "date" else {exp.DataType.Type.TIMESTAMP, exp.DataType.Type.DATETIME}
            if parameter.startswith("yyyymmdd") or value.to.this not in allowed:
                raise ValueError("排行榜日期参数转换类型不匹配。")
            value = value.this.unnest()
        elif ((parameter == "date" and isinstance(value, exp.TsOrDsToDate))
              or (parameter == "timestamp" and isinstance(value, exp.Timestamp))):
            if any(v for k, v in value.args.items() if k != "this"):
                raise ValueError("排行榜日期转换只能包含一个日期常量。")
            value = value.this.unnest()
        if not isinstance(value, exp.Literal) or value.is_string == (parameter == "yyyymmdd_number"):
            raise ValueError("排行榜日期范围必须是对应类型的日期常量。")
        parsed = (datetime.strptime(str(value.this), "%Y%m%d") if parameter.startswith("yyyymmdd") else
                  datetime.strptime(str(value.this), "%Y-%m-%d") if parameter == "date" else datetime.fromisoformat(str(value.this)))
        if parsed.tzinfo is not None:
            raise ValueError("排行榜日期范围必须使用业务时区的本地时间。")
        dates.append(parsed)
    if dates[1] < dates[0] or (parameter == "timestamp" and dates[1] == dates[0]):
        raise ValueError("排行榜日期范围无效。")
    return contract


def validate_ranking_execution_result(result, contract):
    if not contract or result.get("status") == "failed":
        return result
    fields = [*contract["columns"], GUARD_COLUMN]
    if result.get("fields") != fields:
        raise ValueError("排行榜结果缺少固定业务列或属性校验列。")
    rows = []
    for row in result.get("data") or []:
        guard = row.get(GUARD_COLUMN)
        if type(guard) not in (int, float) or guard not in (0, 1):
            raise ValueError("排行榜属性校验返回非法值。")
        if guard == 1:
            raise ValueError("RANKING_PROPERTY_CONFLICT：同一排行主体存在多组展示属性，请移除多值属性或修正数据，不能任意选取属性值。")
        if set(row) != set(fields):
            raise ValueError("排行榜结果字段不完整。")
        rows.append({key: row[key] for key in contract["columns"]})
    from common.core.config import settings
    if len(rows) > max(1, int(settings.SHUZHI_QUERY_RESULT_MAX_ROWS)):
        raise ValueError("排行榜结果超过行数限制，请缩小范围；不会返回截断结果。")
    return {**result, "fields": list(contract["columns"]), "data": rows,
            "_ranking_contract": {"version": 1, "guard_status": "passed",
                "fingerprint": contract["fingerprint"], "metadata_digest": contract["metadata_digest"]}}
