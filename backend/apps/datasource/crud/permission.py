import datetime
import json
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlbot_xpack.permissions.api.permission import transRecord2DTO
from sqlbot_xpack.permissions.models.ds_permission import DsPermission, PermissionDTO
from sqlbot_xpack.permissions.models.ds_rules import DsRules

from apps.datasource.crud.row_permission import transFilterTree
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser, CoreField, CoreTable
from common.core.deps import CurrentUser, SessionDep


def list_datasource_user_ids(session: SessionDep, datasource_id: int) -> list[int]:
    rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource_id).all()
    return [int(row.user_id) for row in rows]


def update_datasource_users(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        user_ids: list[int]
) -> list[int]:
    next_user_ids = {int(user_id) for user_id in user_ids if int(user_id) != 1}
    current_rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource.id).all()
    current_user_ids = {int(row.user_id) for row in current_rows}

    for row in current_rows:
        if int(row.user_id) not in next_user_ids:
            session.delete(row)

    add_user_ids = next_user_ids - current_user_ids
    for user_id in add_user_ids:
        session.add(CoreDatasourceUser(
            ds_id=datasource.id,
            user_id=user_id,
            oid=datasource.oid if datasource.oid is not None else 1,
            create_by=current_user.id,
            create_time=datetime.datetime.now()
        ))

    session.flush()
    return sorted(next_user_ids)


def _parse_json_list(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _same_id(left, right) -> bool:
    return str(left) == str(right)


def _rule_contains_user(rule: DsRules, current_user: CurrentUser) -> bool:
    return any(_same_id(user_id, current_user.id) for user_id in _parse_json_list(rule.user_list))


def _is_datasource_scope_admin(current_user: CurrentUser) -> bool:
    return bool(current_user.isAdmin or current_user.weight > 0)


def get_accessible_datasource_ids(session: SessionDep, current_user: CurrentUser) -> Optional[set[int]]:
    if _is_datasource_scope_admin(current_user):
        return None

    project_users = session.query(CoreDatasourceUser).join(
        CoreDatasource, CoreDatasource.id == CoreDatasourceUser.ds_id
    ).filter(
        CoreDatasourceUser.user_id == current_user.id
    ).all()
    return {int(project_user.ds_id) for project_user in project_users if project_user.ds_id}


def has_datasource_access(session: SessionDep, current_user: CurrentUser, datasource_ids) -> bool:
    if datasource_ids is None or datasource_ids == "":
        return True

    allowed_ids = get_accessible_datasource_ids(session, current_user)
    if allowed_ids is None:
        return True

    if isinstance(datasource_ids, list):
        requested_ids = datasource_ids
    else:
        requested_ids = [datasource_ids]

    try:
        requested_set = {int(datasource_id) for datasource_id in requested_ids}
    except (TypeError, ValueError):
        return False
    return requested_set.issubset(allowed_ids)


def get_row_permission_filters(session: SessionDep, current_user: CurrentUser, ds: CoreDatasource,
                               tables: Optional[list] = None, single_table: Optional[CoreTable] = None):
    if single_table:
        table_list = [session.get(CoreTable, single_table.id)]
    else:
        table_list = session.query(CoreTable).filter(
            and_(CoreTable.ds_id == ds.id, CoreTable.table_name.in_(tables))
        ).all()

    filters = []
    if is_normal_user(current_user):
        contain_rules = get_user_permission_rules(session, current_user, ds.id)
        for table in table_list:
            row_permissions = session.query(DsPermission).filter(
                and_(DsPermission.ds_id == ds.id, DsPermission.table_id == table.id, DsPermission.type == 'row')
            ).all()
            res: List[PermissionDTO] = []
            if row_permissions is not None:
                for permission in row_permissions:
                    # check permission and user in same rules
                    flag = False
                    for r in contain_rules:
                        p_list = _parse_json_list(r.permission_list)
                        u_list = _parse_json_list(r.user_list)
                        if p_list is not None and u_list is not None and permission.id in p_list and (
                                current_user.id in u_list or f'{current_user.id}' in u_list):
                            flag = True
                            break
                    if flag:
                        res.append(transRecord2DTO(session, permission))
            where_str = transFilterTree(session, current_user, res, ds)
            if where_str:
                filters.append({"table": table.table_name, "filter": where_str})
    return filters


def get_column_permission_fields(session: SessionDep, current_user: CurrentUser, table: CoreTable,
                                 fields: list[CoreField], contain_rules: list[DsRules]):
    if is_normal_user(current_user):
        column_permissions = session.query(DsPermission).filter(
            and_(DsPermission.ds_id == table.ds_id, DsPermission.table_id == table.id, DsPermission.type == 'column')
        ).all()
        if column_permissions is not None:
            for permission in column_permissions:
                # check permission and user in same rules
                # obj = session.query(DsRules).filter(
                #     and_(DsRules.permission_list.op('@>')(cast([permission.id], JSONB)),
                #          or_(DsRules.user_list.op('@>')(cast([f'{current_user.id}'], JSONB)),
                #              DsRules.user_list.op('@>')(cast([current_user.id], JSONB))))
                # ).first()
                flag = False
                for r in contain_rules:
                    p_list = _parse_json_list(r.permission_list)
                    u_list = _parse_json_list(r.user_list)
                    if p_list is not None and u_list is not None and permission.id in p_list and (
                            current_user.id in u_list or f'{current_user.id}' in u_list):
                        flag = True
                        break
                if flag:
                    permission_list = json.loads(permission.permissions)
                    fields = filter_list(fields, permission_list)
    return fields


def is_normal_user(current_user: CurrentUser):
    return not _is_datasource_scope_admin(current_user)


def get_user_permission_rules(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: Optional[int] = None
) -> list[DsRules]:
    if not is_normal_user(current_user):
        return []

    oid = current_user.oid if current_user.oid is not None else 1
    rules_query = session.query(DsRules).filter(DsRules.enable.is_(True))
    if hasattr(DsRules, "oid"):
        rules_query = rules_query.filter(or_(DsRules.oid == oid, DsRules.oid.is_(None)))

    if datasource_id is None:
        return [rule for rule in rules_query.all() if _rule_contains_user(rule, current_user)]

    permission_ids = {
        int(permission.id) for permission in session.query(DsPermission).filter(
            and_(DsPermission.enable.is_(True), DsPermission.ds_id == datasource_id)
        ).all()
    }
    if not permission_ids:
        return []

    user_rules = []
    for rule in rules_query.all():
        if not _rule_contains_user(rule, current_user):
            continue
        rule_permission_ids = set()
        for permission_id in _parse_json_list(rule.permission_list):
            try:
                rule_permission_ids.add(int(permission_id))
            except (TypeError, ValueError):
                continue
        if rule_permission_ids & permission_ids:
            user_rules.append(rule)
    return user_rules


def filter_list(list_a, list_b):
    id_to_invalid = {}
    for b in list_b:
        if not b['enable']:
            id_to_invalid[b['field_id']] = True

    return [a for a in list_a if not id_to_invalid.get(a.id, False)]
