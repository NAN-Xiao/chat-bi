"""Authenticated attribution context and connection timezone requirements."""
import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import sqlglot
from sqlglot import exp
from apps.dashboard.crud.path_execution_contract import metadata_digest, _key
from apps.dashboard.crud.attribution_sql_compiler import GUARD_COLUMN

MARKER = re.compile(r"/\* attribution-contract-v1:([A-Za-z0-9_=-]+)\.([0-9a-f]{64}) \*/")

def attribution_tree(sql, dialect):
    text = re.sub(r"\{\{(dashboard_[a-z_]+)\}\}", r":\1", MARKER.sub("", sql))
    trees = [t for t in sqlglot.parse(text,read=dialect) if t is not None]
    if len(trees) != 1 or not isinstance(trees[0],exp.Query): raise ValueError("归因 SQL 必须是单条只读查询。")
    for node in trees[0].walk(): node.comments = None
    return trees[0]

def bounds(tree):
    nodes = [n for n in tree.find_all(exp.CTE) if n.alias == 'attribution_parameter_bounds']
    if len(nodes) != 1 or not isinstance(nodes[0].this,exp.Select): raise ValueError("归因日期边界缺失。")
    node = nodes[0].this
    if len(node.selects) != 2 or any(v for k,v in node.args.items() if k != 'expressions'): raise ValueError("归因日期边界无效。")
    for i,n in enumerate(node.selects):
        if n.alias != ('range_start','range_end')[i] or any(isinstance(v,(exp.Query,exp.Column)) for v in n.walk()):
            raise ValueError("归因日期参数无效。")
    return node

def fingerprint(sql,dialect):
    tree = attribution_tree(sql,dialect)
    bounds(tree).set('expressions',[exp.alias_(exp.Literal.number(0),n) for n in ('range_start','range_end')])
    return hashlib.sha256(tree.sql(dialect=dialect).encode()).hexdigest()

def attach_attribution_contract(sql,plan,*,tenant_id,datasource_id,tracking_metadata):
    contract = {'kind':'attribution','version':1,'dialect':plan.dialect,'tenant_id':tenant_id,'datasource_id':int(datasource_id),
        'columns':list(plan.required_columns),'parameter_type':plan.time.parameter_type,
        'business_timezone':plan.time.business_timezone,'naive_timezones':list(plan.time.naive_timezones),
        'mysql_utc':plan.time.mysql_utc,'mysql_timezones':list(plan.time.mysql_timezones),
        'window_seconds':plan.window_seconds,'metadata_digest':metadata_digest(tracking_metadata),'fingerprint':fingerprint(sql,plan.dialect)}
    payload = base64.urlsafe_b64encode(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).decode()
    signature = hmac.new(_key(),payload.encode(),hashlib.sha256).hexdigest()
    return f'/* attribution-contract-v1:{payload}.{signature} */\n{sql}'

def read_attribution_contract(sql):
    matches = list(MARKER.finditer(sql or ''))
    if not matches:
        if re.search(r'attribution-contract-v1|\battribution_parameter_bounds\b|\b__attribution_data_error\b',sql or '',re.I):
            raise ValueError('归因执行协议缺失或损坏，请重新生成 SQL。')
        return None
    if len(matches) != 1: raise ValueError('归因执行协议重复。')
    payload,signature = matches[0].groups()
    if not hmac.compare_digest(signature,hmac.new(_key(),payload.encode(),hashlib.sha256).hexdigest()): raise ValueError('归因执行协议签名无效。')
    contract = json.loads(base64.urlsafe_b64decode(payload))
    if contract.get('kind') != 'attribution' or contract.get('version') != 1: raise ValueError('归因执行协议版本不支持。')
    if fingerprint(sql,contract['dialect']) != contract['fingerprint']: raise ValueError('归因 SQL 已偏离已验证配置，请重新生成。')
    return contract

def date_range(sql,contract):
    dates = []
    for n in bounds(attribution_tree(sql,contract['dialect'])).selects:
        value = n.this.unnest()
        if isinstance(value,exp.Cast): value = value.this.unnest()
        parameter = contract['parameter_type']
        if not isinstance(value,exp.Literal) or value.is_string == (parameter == 'yyyymmdd_number'):
            raise ValueError('归因日期范围必须是对应类型的日期常量。')
        dates.append(datetime.strptime(str(value.this),'%Y%m%d') if parameter.startswith('yyyymmdd') else datetime.fromisoformat(str(value.this)))
    if contract['parameter_type'] != 'timestamp': dates[1] += timedelta(days=1)
    if dates[1] <= dates[0]: raise ValueError('归因日期范围无效。')
    return dates

def validate_attribution_workspace_contract(session,current_user,datasource_id,sql,expected=None):
    contract = read_attribution_contract(sql)
    if expected is not None and contract != expected: raise ValueError('归因执行协议与 SQL 不一致。')
    if not contract: return None
    from apps.system.crud.tracking_config import get_tracking_config
    from apps.system.schemas.access_context import require_current_tenant_id
    from common.core.config import settings
    tenant = require_current_tenant_id(current_user)
    if tenant != contract['tenant_id'] or int(datasource_id) != contract['datasource_id']: raise ValueError('归因 SQL 与当前工作空间或数据源不一致。')
    tracking = get_tracking_config(session,tenant,int(datasource_id),include_legacy=False)
    if metadata_digest(tracking) != contract['metadata_digest']: raise ValueError('工作空间元数据已变更，请重新生成归因 SQL。')
    if settings.DASHBOARD_BUSINESS_TIMEZONE != contract['business_timezone']: raise ValueError('业务时区已变更，请重新生成归因 SQL。')
    start,end = date_range(sql,contract)
    business = ZoneInfo(contract['business_timezone'])
    start = start.replace(tzinfo=business).astimezone(timezone.utc)-timedelta(seconds=contract['window_seconds'])
    stop = end.replace(tzinfo=business).astimezone(timezone.utc)-timedelta(microseconds=1)
    for name in contract['naive_timezones']:
        zone = ZoneInfo(name); point = start; offset = (point-timedelta(microseconds=1)).astimezone(zone).utcoffset()
        while point <= stop:
            if point.astimezone(zone).utcoffset() != offset: raise ValueError('归因范围包含源无时区时间的夏令时切换，请使用绝对时间字段。')
            if point == stop: break
            point = min(point+timedelta(hours=6),stop)
    return contract

def validate_attribution_execution_result(result,contract):
    if not contract or result.get('status') == 'failed': return result
    if result.get('fields') != [*contract['columns'],GUARD_COLUMN]: raise ValueError('归因结果缺少固定业务列或数据校验列。')
    from common.core.config import settings
    if len(result.get('data') or []) > max(1,int(settings.SHUZHI_QUERY_RESULT_MAX_ROWS)):
        raise ValueError('归因结果超过行数限制，请缩小范围或减少分组；不会返回截断结果。')
    rows = []
    for row in result.get('data') or []:
        guard = row.get(GUARD_COLUMN)
        if type(guard) not in (int,float) or guard not in (0,1): raise ValueError('归因数据校验返回非法值。')
        if guard == 1: raise ValueError('ATTRIBUTION_DATA_CONFLICT：事件时间或首次/末次排序键为空或重复，请修正元数据及源数据。')
        if set(row) != set(result['fields']): raise ValueError('归因结果字段不完整。')
        rows.append({k:row[k] for k in contract['columns']})
    return {**result,'fields':contract['columns'],'data':rows}
