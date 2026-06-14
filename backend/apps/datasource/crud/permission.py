import datetime
import json
from typing import Any, List, Optional

from sqlalchemy import and_, or_

from apps.datasource.crud.permission_rules import (
    list_permission_records,
    list_rule_records,
    parse_json_list,
    trans_record_to_dto,
)
from apps.datasource.crud.row_permission import transFilterTree
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser, CoreField, CoreTable
from common.core.deps import CurrentUser, SessionDep

PROJECT_ROLE_VIEWER = "viewer"
PROJECT_ROLE_EDITOR = "editor"
PROJECT_ROLE_ADMIN = "admin"
PROJECT_ROLE_ORDER = {
    PROJECT_ROLE_VIEWER: 10,
    PROJECT_ROLE_EDITOR: 20,
    PROJECT_ROLE_ADMIN: 30,
}
PROJECT_ROLE_ALIASES = {
    "project_viewer": PROJECT_ROLE_VIEWER,
    "project_editor": PROJECT_ROLE_EDITOR,
    "project_admin": PROJECT_ROLE_ADMIN,
}


def normalize_project_role(role: str | None) -> str:
    if not role:
        return PROJECT_ROLE_VIEWER
    normalized = PROJECT_ROLE_ALIASES.get(str(role).strip().lower(), str(role).strip().lower())
    return normalized if normalized in PROJECT_ROLE_ORDER else PROJECT_ROLE_VIEWER


def project_role_rank(role: str | None) -> int:
    return PROJECT_ROLE_ORDER.get(normalize_project_role(role), 0)


def _can_satisfy_project_role(actual_role: str | None, required_role: str | None) -> bool:
    return project_role_rank(actual_role) >= project_role_rank(required_role)


def list_datasource_user_ids(session: SessionDep, datasource_id: int) -> list[int]:
    rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource_id).all()
    return [int(row.user_id) for row in rows]


def list_datasource_users(session: SessionDep, datasource_id: int) -> list[dict[str, Any]]:
    rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource_id).all()
    return [
        {
            "user_id": int(row.user_id),
            "role": normalize_project_role(getattr(row, "role", None)),
        }
        for row in rows
    ]


def list_user_datasource_ids(session: SessionDep, user_id: int) -> list[int]:
    rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.user_id == user_id).all()
    return [int(row.ds_id) for row in rows]


def list_user_datasource_roles(session: SessionDep, user_id: int) -> dict[int, str]:
    rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.user_id == user_id).all()
    return {int(row.ds_id): normalize_project_role(getattr(row, "role", None)) for row in rows}


def update_datasource_users(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        user_ids: list[int],
        user_roles: Optional[dict[int, str]] = None
) -> list[dict[str, Any]]:
    user_roles = user_roles or {}
    next_user_ids = {int(user_id) for user_id in user_ids if int(user_id) != 1}
    current_rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == datasource.id).all()
    current_rows_by_user = {int(row.user_id): row for row in current_rows}

    for row in current_rows:
        if int(row.user_id) not in next_user_ids:
            session.delete(row)

    for user_id in next_user_ids:
        next_role = normalize_project_role(user_roles.get(user_id))
        row = current_rows_by_user.get(user_id)
        if row:
            row.role = next_role
            session.add(row)
        else:
            session.add(CoreDatasourceUser(
                ds_id=datasource.id,
                user_id=user_id,
                role=next_role,
                create_by=current_user.id,
                create_time=datetime.datetime.now()
            ))

    session.flush()
    return [
        {"user_id": user_id, "role": normalize_project_role(user_roles.get(user_id))}
        for user_id in sorted(next_user_ids)
    ]


def update_user_datasources(
        session: SessionDep,
        current_user: CurrentUser,
        user_id: int,
        datasource_ids: list[int]
) -> list[int]:
    if int(user_id) == 1:
        return []

    next_datasource_ids = {int(datasource_id) for datasource_id in datasource_ids}
    if next_datasource_ids:
        existing_datasources = session.query(CoreDatasource).filter(
            CoreDatasource.id.in_(next_datasource_ids)
        ).all()
        datasource_map = {int(datasource.id): datasource for datasource in existing_datasources}
        next_datasource_ids = set(datasource_map.keys())
    else:
        datasource_map = {}

    current_rows = session.query(CoreDatasourceUser).filter(CoreDatasourceUser.user_id == user_id).all()
    current_datasource_ids = {int(row.ds_id) for row in current_rows}

    for row in current_rows:
        if int(row.ds_id) not in next_datasource_ids:
            session.delete(row)

    add_datasource_ids = next_datasource_ids - current_datasource_ids
    for datasource_id in add_datasource_ids:
        datasource = datasource_map.get(datasource_id)
        session.add(CoreDatasourceUser(
            ds_id=datasource_id,
            user_id=user_id,
            role=PROJECT_ROLE_VIEWER,
            create_by=current_user.id if current_user else None,
            create_time=datetime.datetime.now()
        ))

    session.flush()
    return sorted(next_datasource_ids)


def _same_id(left, right) -> bool:
    return str(left) == str(right)


def _rule_contains_user(rule: Any, current_user: CurrentUser) -> bool:
    return any(_same_id(user_id, current_user.id) for user_id in parse_json_list(rule.user_list))


def _rule_contains_permission(rule: Any, permission_id) -> bool:
    return any(_same_id(item, permission_id) for item in parse_json_list(rule.permission_list))


def _is_datasource_scope_admin(current_user: CurrentUser) -> bool:
    return bool(current_user.isAdmin)


def get_datasource_role(session: SessionDep, current_user: CurrentUser, datasource_id) -> str | None:
    if datasource_id is None or datasource_id == "":
        return None
    if _is_datasource_scope_admin(current_user):
        return PROJECT_ROLE_ADMIN
    try:
        datasource_id = int(datasource_id)
    except (TypeError, ValueError):
        return None

    datasource = session.get(CoreDatasource, datasource_id)
    if datasource and str(datasource.create_by) == str(current_user.id):
        return PROJECT_ROLE_ADMIN

    row = session.query(CoreDatasourceUser).filter(
        CoreDatasourceUser.ds_id == datasource_id,
        CoreDatasourceUser.user_id == current_user.id,
    ).first()
    if row is None:
        return None
    return normalize_project_role(getattr(row, "role", None))


def has_datasource_role(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_ids,
        min_role: str = PROJECT_ROLE_VIEWER
) -> bool:
    if datasource_ids is None or datasource_ids == "":
        return False

    if isinstance(datasource_ids, list):
        requested_ids = datasource_ids
    else:
        requested_ids = [datasource_ids]

    try:
        requested_set = {int(datasource_id) for datasource_id in requested_ids}
    except (TypeError, ValueError):
        return False

    return all(
        _can_satisfy_project_role(get_datasource_role(session, current_user, datasource_id), min_role)
        for datasource_id in requested_set
    )


def get_accessible_datasource_ids(session: SessionDep, current_user: CurrentUser) -> Optional[set[int]]:
    if _is_datasource_scope_admin(current_user):
        return None

    project_ids = session.query(CoreDatasource.id).outerjoin(
        CoreDatasourceUser,
        and_(
            CoreDatasource.id == CoreDatasourceUser.ds_id,
            CoreDatasourceUser.user_id == current_user.id,
        )
    ).filter(
        or_(
            CoreDatasourceUser.user_id == current_user.id,
            CoreDatasource.create_by == current_user.id,
        )
    ).all()
    return {int(row[0] if isinstance(row, tuple) else row) for row in project_ids if row is not None}


def has_datasource_access(session: SessionDep, current_user: CurrentUser, datasource_ids) -> bool:
    if datasource_ids is None or datasource_ids == "":
        return True

    return has_datasource_role(session, current_user, datasource_ids, PROJECT_ROLE_VIEWER)


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
            row_permissions = list_permission_records(
                session,
                ds_id=ds.id,
                table_id=table.id,
                permission_type='row',
                enable=True,
            )
            res: List[Any] = []
            if row_permissions is not None:
                for permission in row_permissions:
                    # check permission and user in same rules
                    flag = False
                    for r in contain_rules:
                        if _rule_contains_permission(r, permission.id) and _rule_contains_user(r, current_user):
                            flag = True
                            break
                    if flag:
                        res.append(trans_record_to_dto(session, permission))
            where_str = transFilterTree(session, current_user, res, ds)
            if where_str:
                filters.append({"table": table.table_name, "filter": where_str})
    return filters


def get_column_permission_fields(session: SessionDep, current_user: CurrentUser, table: CoreTable,
                                 fields: list[CoreField], contain_rules: list[Any]):
    if is_normal_user(current_user):
        column_permissions = list_permission_records(
            session,
            ds_id=table.ds_id,
            table_id=table.id,
            permission_type='column',
            enable=True,
        )
        if column_permissions is not None:
            for permission in column_permissions:
                # check permission and user in same rules
                flag = False
                for r in contain_rules:
                    if _rule_contains_permission(r, permission.id) and _rule_contains_user(r, current_user):
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
) -> list[Any]:
    if not is_normal_user(current_user):
        return []

    rules = list_rule_records(session, enable=True)

    if datasource_id is None:
        return [rule for rule in rules if _rule_contains_user(rule, current_user)]

    permission_ids = {
        int(permission.id) for permission in list_permission_records(
            session,
            ds_id=datasource_id,
            enable=True,
        )
    }
    if not permission_ids:
        return []

    user_rules = []
    for rule in rules:
        if not _rule_contains_user(rule, current_user):
            continue
        rule_permission_ids = set()
        for permission_id in parse_json_list(rule.permission_list):
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
            id_to_invalid[str(b['field_id'])] = True

    return [a for a in list_a if not id_to_invalid.get(str(a.id), False)]
