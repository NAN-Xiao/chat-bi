"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import datetime
import json
from types import SimpleNamespace
from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, MetaData, String, Table, Text
from sqlalchemy import and_, delete, insert, or_, select, update

from apps.datasource.models.datasource import CoreDatasource, CoreTable
from apps.system.models.user import UserModel
from common.core.deps import SessionDep


_metadata = MetaData()
DEFAULT_RULE_TENANT_ID = 1
RULE_SCOPE_TENANT = "TENANT"
RULE_SCOPE_PLATFORM = "PLATFORM"
RULE_SCOPES = {RULE_SCOPE_TENANT, RULE_SCOPE_PLATFORM}

ds_rules_table = Table(
    "ds_rules",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("enable", Boolean, nullable=False),
    Column("name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("tenant_id", BigInteger, nullable=False, default=DEFAULT_RULE_TENANT_ID),
    Column("scope", String(32), nullable=False, default=RULE_SCOPE_TENANT),
    Column("permission_list", Text, nullable=True),
    Column("user_list", Text, nullable=True),
    Column("white_list_user", Text, nullable=True),
    Column("create_time", DateTime(timezone=False), nullable=True),
)

ds_permission_table = Table(
    "ds_permission",
    _metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", String, nullable=True),
    Column("enable", Boolean, nullable=False),
    Column("auth_target_type", String, nullable=True),
    Column("auth_target_id", BigInteger, nullable=True),
    Column("type", String, nullable=False),
    Column("ds_id", BigInteger, nullable=True),
    Column("table_id", BigInteger, nullable=True),
    Column("expression_tree", Text, nullable=True),
    Column("permissions", Text, nullable=True),
    Column("white_list_user", Text, nullable=True),
    Column("create_time", DateTime(timezone=False), nullable=True),
)


def _now() -> datetime.datetime:
    """
    是什么：_now 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return datetime.datetime.now()


def _row_to_obj(row: Any) -> SimpleNamespace | None:
    """
    是什么：_row_to_obj 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if row is None:
        return None
    return SimpleNamespace(**dict(row))


def _parse_json(value: Any, fallback: Any) -> Any:
    """
    是什么：_parse_json 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def parse_json_list(value: Any) -> list:
    """
    是什么：parse_json_list 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    parsed = _parse_json(value, [])
    return parsed if isinstance(parsed, list) else []


def _json_text(value: Any, fallback: Any) -> str:
    """
    是什么：_json_text 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parsed = _parse_json(value, fallback)
    return json.dumps(parsed, ensure_ascii=False)


def normalize_rule_scope(value: Any) -> str:
    """
    是什么：normalize_rule_scope 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    normalized = str(value or RULE_SCOPE_TENANT).strip().upper()
    return normalized if normalized in RULE_SCOPES else RULE_SCOPE_TENANT


def _rule_tenant_id(value: Any) -> int:
    """
    是什么：_rule_tenant_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return int(value or DEFAULT_RULE_TENANT_ID)
    except (TypeError, ValueError):
        return DEFAULT_RULE_TENANT_ID


def _int_list(value: Any) -> list[int]:
    """
    是什么：_int_list 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    result: list[int] = []
    for item in parse_json_list(value):
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _id_text(value: Any) -> str | None:
    """
    是什么：_id_text 把用户 ID 转成适合 JSON 往返的字符串。
    谁调用：权限规则保存/返回用户列表时会调用它。
    做了什么：避免 64 位用户 ID 被浏览器当作 Number 后丢失低位精度。
    """
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def _id_string_list(value: Any) -> list[str]:
    """
    是什么：_id_string_list 提取用户 ID 列表并保持字符串形态。
    谁调用：权限规则的 user_list / white_list_user 保存和 DTO 返回会调用它。
    做了什么：去掉空值和重复项，但不把用户 ID 转成数字。
    """
    result: list[str] = []
    seen: set[str] = set()
    for item in parse_json_list(value):
        text = _id_text(item)
        if text is None or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _rule_values(rule_data: dict[str, Any], permission_ids: list[int]) -> dict[str, Any]:
    """
    是什么：_rule_values 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    scope = normalize_rule_scope(rule_data.get("scope"))
    tenant_id = DEFAULT_RULE_TENANT_ID if scope == RULE_SCOPE_PLATFORM else _rule_tenant_id(rule_data.get("tenant_id"))
    return {
        "enable": bool(rule_data.get("enable", True)),
        "name": rule_data.get("name") or "",
        "description": rule_data.get("description") or "",
        "tenant_id": tenant_id,
        "scope": scope,
        "permission_list": json.dumps(permission_ids, ensure_ascii=False),
        "user_list": json.dumps(
            _id_string_list(rule_data.get("users", rule_data.get("user_list"))),
            ensure_ascii=False,
        ),
        "white_list_user": json.dumps(_id_string_list(rule_data.get("white_list_user")), ensure_ascii=False),
    }


def _permission_values(permission_data: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：_permission_values 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    permission_type = permission_data.get("type") or "row"
    return {
        "name": permission_data.get("name") or "",
        "enable": bool(permission_data.get("enable", True)),
        "auth_target_type": permission_data.get("auth_target_type") or "user",
        "auth_target_id": permission_data.get("auth_target_id"),
        "type": permission_type,
        "ds_id": permission_data.get("ds_id"),
        "table_id": permission_data.get("table_id"),
        "expression_tree": _json_text(permission_data.get("expression_tree"), {}),
        "permissions": _json_text(permission_data.get("permissions"), []),
        "white_list_user": json.dumps(_id_string_list(permission_data.get("white_list_user")), ensure_ascii=False),
    }


def list_permission_records(
    session: SessionDep,
    *,
    ids: list[int] | None = None,
    ds_id: int | None = None,
    table_id: int | None = None,
    permission_type: str | None = None,
    enable: bool | None = None,
) -> list[SimpleNamespace]:
    """
    是什么：list_permission_records 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    conditions = []
    if ids is not None:
        if not ids:
            return []
        conditions.append(ds_permission_table.c.id.in_(ids))
    if ds_id is not None:
        conditions.append(ds_permission_table.c.ds_id == ds_id)
    if table_id is not None:
        conditions.append(ds_permission_table.c.table_id == table_id)
    if permission_type is not None:
        conditions.append(ds_permission_table.c.type == permission_type)
    if enable is not None:
        conditions.append(ds_permission_table.c.enable.is_(enable))

    stmt = select(ds_permission_table)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    rows = session.execute(stmt.order_by(ds_permission_table.c.id)).mappings().all()
    return [_row_to_obj(row) for row in rows]


def list_rule_records(
    session: SessionDep,
    *,
    enable: bool | None = None,
    tenant_id: int | None = None,
    include_platform: bool = False,
    scope: str | None = None,
) -> list[SimpleNamespace]:
    """
    是什么：list_rule_records 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    stmt = select(ds_rules_table)
    conditions = []
    if enable is not None:
        conditions.append(ds_rules_table.c.enable.is_(enable))
    if scope:
        conditions.append(ds_rules_table.c.scope == normalize_rule_scope(scope))
    elif tenant_id is not None:
        tenant_conditions = [
            and_(
                ds_rules_table.c.tenant_id == int(tenant_id),
                or_(
                    ds_rules_table.c.scope == RULE_SCOPE_TENANT,
                    ds_rules_table.c.scope.is_(None),
                ),
            )
        ]
        if include_platform:
            tenant_conditions.append(ds_rules_table.c.scope == RULE_SCOPE_PLATFORM)
        conditions.append(or_(*tenant_conditions))
    if conditions:
        stmt = stmt.where(and_(*conditions))
    rows = session.execute(stmt.order_by(ds_rules_table.c.id)).mappings().all()
    return [_row_to_obj(row) for row in rows]


def get_rule_record(session: SessionDep, rule_id: int) -> SimpleNamespace | None:
    """
    是什么：get_rule_record 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    row = session.execute(
        select(ds_rules_table).where(ds_rules_table.c.id == rule_id)
    ).mappings().first()
    return _row_to_obj(row)


def _existing_permission_ids(session: SessionDep, ids: list[int]) -> set[int]:
    """
    是什么：_existing_permission_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not ids:
        return set()
    rows = session.execute(
        select(ds_permission_table.c.id).where(ds_permission_table.c.id.in_(ids))
    ).all()
    return {int(row[0]) for row in rows}


def trans_record_to_dto(session: SessionDep, record: SimpleNamespace) -> SimpleNamespace:
    """
    是什么：trans_record_to_dto 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    dto = permission_record_to_dict(session, record)
    return SimpleNamespace(**dto)


def permission_record_to_dict(session: SessionDep, record: SimpleNamespace) -> dict[str, Any]:
    """
    是什么：permission_record_to_dict 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource = session.get(CoreDatasource, record.ds_id) if record.ds_id else None
    table = session.get(CoreTable, record.table_id) if record.table_id else None
    permission_list = parse_json_list(record.permissions)
    tree = _parse_json(record.expression_tree, {})
    return {
        "id": record.id,
        "name": record.name,
        "enable": record.enable,
        "auth_target_type": record.auth_target_type,
        "auth_target_id": record.auth_target_id,
        "type": record.type,
        "ds_id": record.ds_id,
        "table_id": record.table_id,
        "expression_tree": tree,
        "permissions": permission_list,
        "white_list_user": _id_string_list(record.white_list_user),
        "create_time": record.create_time,
        "tree": tree,
        "permission_list": permission_list,
        "ds_name": datasource.name if datasource else None,
        "table_name": table.table_name if table else None,
    }


def rule_record_to_dict(session: SessionDep, rule: SimpleNamespace) -> dict[str, Any]:
    """
    是什么：rule_record_to_dict 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    permission_ids = _int_list(rule.permission_list)
    permission_records = list_permission_records(session, ids=permission_ids)
    permission_map = {int(permission.id): permission for permission in permission_records}
    permissions = [
        permission_record_to_dict(session, permission_map[permission_id])
        for permission_id in permission_ids
        if permission_id in permission_map
    ]
    users = _id_string_list(rule.user_list)
    return {
        "id": rule.id,
        "enable": rule.enable,
        "name": rule.name,
        "description": rule.description,
        "tenant_id": _rule_tenant_id(getattr(rule, "tenant_id", None)),
        "scope": normalize_rule_scope(getattr(rule, "scope", None)),
        "permission_list": permission_ids,
        "user_list": users,
        "white_list_user": _id_string_list(rule.white_list_user),
        "create_time": rule.create_time,
        "permissions": permissions,
        "users": users,
    }


def list_rule_dtos(session: SessionDep) -> list[dict[str, Any]]:
    """
    是什么：list_rule_dtos 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    return [rule_record_to_dict(session, rule) for rule in list_rule_records(session)]


def get_rule_dto(session: SessionDep, rule_id: int) -> dict[str, Any] | None:
    """
    是什么：get_rule_dto 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    rule = get_rule_record(session, rule_id)
    if rule is None:
        return None
    return rule_record_to_dict(session, rule)


def save_rule_dto(session: SessionDep, rule_data: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：save_rule_dto 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    rule_id = rule_data.get("id")
    old_rule = get_rule_record(session, int(rule_id)) if rule_id else None
    old_permission_ids = _int_list(old_rule.permission_list) if old_rule else []
    submitted_permissions = rule_data.get("permissions") or []
    submitted_ids = []
    for permission in submitted_permissions:
        try:
            submitted_ids.append(int(permission.get("id")))
        except (TypeError, ValueError):
            continue
    old_permission_id_set = set(old_permission_ids)
    existing_ids = _existing_permission_ids(
        session,
        [permission_id for permission_id in submitted_ids if permission_id in old_permission_id_set],
    )

    next_permission_ids: list[int] = []
    for permission in submitted_permissions:
        values = _permission_values(permission)
        permission_id = permission.get("id")
        try:
            permission_id_int = int(permission_id)
        except (TypeError, ValueError):
            permission_id_int = None

        if permission_id_int in existing_ids:
            session.execute(
                update(ds_permission_table)
                .where(ds_permission_table.c.id == permission_id_int)
                .values(**values)
            )
            next_permission_ids.append(permission_id_int)
            continue

        inserted_id = session.execute(
            insert(ds_permission_table)
            .values(**values, create_time=_now())
            .returning(ds_permission_table.c.id)
        ).scalar_one()
        next_permission_ids.append(int(inserted_id))

    remove_ids = set(old_permission_ids) - set(next_permission_ids)
    if remove_ids:
        session.execute(delete(ds_permission_table).where(ds_permission_table.c.id.in_(remove_ids)))

    values = _rule_values(rule_data, next_permission_ids)
    if old_rule is None:
        saved_rule_id = session.execute(
            insert(ds_rules_table)
            .values(**values, create_time=_now())
            .returning(ds_rules_table.c.id)
        ).scalar_one()
    else:
        session.execute(
            update(ds_rules_table)
            .where(ds_rules_table.c.id == int(old_rule.id))
            .values(**values)
        )
        saved_rule_id = int(old_rule.id)

    session.flush()
    return get_rule_dto(session, int(saved_rule_id))


def delete_rule_dto(session: SessionDep, rule_id: int) -> None:
    """
    是什么：delete_rule_dto 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源不再需要的数据、缓存或临时内容清理掉。
    """
    rule = get_rule_record(session, rule_id)
    if rule is None:
        return
    permission_ids = _int_list(rule.permission_list)
    session.execute(delete(ds_rules_table).where(ds_rules_table.c.id == rule_id))
    if permission_ids:
        session.execute(delete(ds_permission_table).where(ds_permission_table.c.id.in_(permission_ids)))
    session.flush()


def delete_permission_records_for_datasources(
    session: SessionDep,
    datasource_ids: list[int],
    *,
    tenant_id: int | None = None,
) -> None:
    """
    是什么：delete_permission_records_for_datasources 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源不再需要的数据、缓存或临时内容清理掉。
    """
    ids = [int(datasource_id) for datasource_id in datasource_ids if datasource_id is not None]
    if not ids:
        return

    permission_rows = session.execute(
        select(ds_permission_table.c.id).where(ds_permission_table.c.ds_id.in_(ids))
    ).all()
    permission_ids = {int(row[0]) for row in permission_rows if row[0] is not None}
    if not permission_ids:
        return

    rules = (
        list_rule_records(session, tenant_id=int(tenant_id), include_platform=False)
        if tenant_id is not None
        else list_rule_records(session)
    )
    for rule in rules:
        rule_permission_ids = _int_list(rule.permission_list)
        next_permission_ids = [
            permission_id for permission_id in rule_permission_ids if permission_id not in permission_ids
        ]
        if not next_permission_ids:
            session.execute(delete(ds_rules_table).where(ds_rules_table.c.id == int(rule.id)))
            continue
        if len(next_permission_ids) != len(rule_permission_ids):
            session.execute(
                update(ds_rules_table)
                .where(ds_rules_table.c.id == int(rule.id))
                .values(permission_list=json.dumps(next_permission_ids, ensure_ascii=False))
            )

    referenced_permission_ids: set[int] = set()
    for rule in list_rule_records(session):
        referenced_permission_ids.update(_int_list(rule.permission_list))
    orphan_permission_ids = permission_ids - referenced_permission_ids
    if orphan_permission_ids:
        session.execute(delete(ds_permission_table).where(ds_permission_table.c.id.in_(orphan_permission_ids)))
    session.flush()


def list_rule_user_ids(session: SessionDep, rule: SimpleNamespace) -> list[str]:
    """
    是什么：list_rule_user_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    return _id_string_list(rule.user_list)


def list_users_by_ids(session: SessionDep, user_ids: list[int]) -> list[UserModel]:
    """
    是什么：list_users_by_ids 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if not user_ids:
        return []
    return session.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
