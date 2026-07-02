"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
# 作者：Junjun
# 日期：2025/6/25

from typing import List, Dict, Any

from apps.datasource.models.datasource import CoreField, CoreDatasource
from apps.db.constant import DB
from apps.system.models.system_variable_model import SystemVariable
from common.core.deps import SessionDep, CurrentUser


_SYSTEM_VARIABLE_USER_FIELDS = {
    "id": "id",
    "user_id": "id",
    "account": "account",
    "email": "email",
    "name": "name",
    "tenant_id": "tenant_id",
}


def _escape_sql_value(value: str, ds_type: str | None = None) -> str:
    """
    是什么：_escape_sql_value 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if value is None:
        return value
    # 标准 SQL 转义：将嵌入的单引号加倍。
    escaped = str(value).replace("'", "''")
    # 只有保留 C 风格反斜杠字符串转义的方言需要再加倍反斜杠；
    # PostgreSQL/SQL Server 标准字符串下反斜杠是普通字符，不能无条件改写。
    if str(ds_type or "").strip().lower() in {"mysql", "doris", "starrocks", "ck", "clickhouse", "hive"}:
        escaped = escaped.replace("\\", "\\\\")
    return escaped


def _invalid_filter(message: str, strict: bool) -> None:
    """
    是什么：_invalid_filter 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if strict:
        raise ValueError(message)


def _sql_server_nchar(ds: CoreDatasource, field: CoreField) -> bool:
    """
    是什么：_sql_server_nchar 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return ds.type == 'sqlServer' and field.field_type in ('nchar', 'NCHAR', 'nvarchar', 'NVARCHAR')


def _quoted_value(ds: CoreDatasource, field: CoreField, value: Any) -> str:
    """
    是什么：_quoted_value 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    escaped = _escape_sql_value(value, ds.type)
    if _sql_server_nchar(ds, field):
        return f"N'{escaped}'"
    return f"'{escaped}'"


def _list_values(value: Any) -> list[Any]:
    """
    是什么：_list_values 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return str(value).split(",")


def _single_value(value: Any) -> Any:
    """
    是什么：_single_value 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _where_value_for_term(
        ds: CoreDatasource,
        field: CoreField,
        term: str,
        values: Any,
        strict: bool,
) -> str | None:
    """
    是什么：_where_value_for_term 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if term in ('null', 'not_null'):
        return ''
    if term in ('empty', 'not_empty'):
        return "''"
    if term in ('in', 'not in'):
        items = _list_values(values)
        if not items:
            _invalid_filter("行权限过滤条件缺少 IN 值", strict)
            return None
        return "(" + ", ".join(_quoted_value(ds, field, item) for item in items) + ")"
    if term in ('like', 'not like'):
        value = _single_value(values)
        if value is None or value == "":
            _invalid_filter("行权限过滤条件缺少 LIKE 值", strict)
            return None
        escaped = _escape_sql_value(value, ds.type)
        if _sql_server_nchar(ds, field):
            return f"N'%{escaped}%'"
        return f"'%{escaped}%'"
    if term == 'between':
        items = _list_values(values)
        if len(items) < 2:
            _invalid_filter("行权限过滤条件缺少 BETWEEN 边界值", strict)
            return None
        return f"{_quoted_value(ds, field, items[0])} AND {_quoted_value(ds, field, items[1])}"

    value = _single_value(values)
    if value is None or value == "":
        _invalid_filter("行权限过滤条件缺少比较值", strict)
        return None
    return _quoted_value(ds, field, value)


def transFilterTree(session: SessionDep, current_user: CurrentUser, tree_list: List[any],
                    ds: CoreDatasource, deny_mode: bool = False, strict: bool = False) -> str | None:
    """
    是什么：transFilterTree 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if tree_list is None:
        return None
    res: List[str] = []
    for dto in tree_list:
        tree = dto.tree
        if tree is None:
            _invalid_filter("行权限过滤树为空", strict)
            continue
        tree_exp = transTreeToWhere(
            session,
            current_user,
            tree,
            ds,
            table_id=getattr(dto, "table_id", None),
            strict=strict,
        )
        if tree_exp is not None:
            res.append(f"NOT ({tree_exp})" if deny_mode else tree_exp)
    return " AND ".join(res)


_VALID_LOGIC_OPS = {"AND", "OR"}


def _same_explicit_tenant(left, right) -> bool:
    """
    是什么：_same_explicit_tenant 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if left in (None, "") or right in (None, ""):
        return False
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return False


def transTreeToWhere(
        session: SessionDep,
        current_user: CurrentUser,
        tree: any,
        ds: CoreDatasource,
        table_id: int | None = None,
        strict: bool = False,
) -> str | None:
    """
    是什么：transTreeToWhere 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not isinstance(tree, dict):
        _invalid_filter("行权限过滤树格式无效", strict)
        return None
    logic = str(tree.get('logic') or '').upper()
    # 校验逻辑操作符，防止通过该字段注入。
    if logic not in _VALID_LOGIC_OPS:
        _invalid_filter("行权限逻辑操作符无效", strict)
        return None

    items = tree.get('items')
    if not isinstance(items, list) or len(items) == 0:
        _invalid_filter("行权限过滤树缺少条件项", strict)
        return None
    expressions: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            _invalid_filter("行权限过滤项格式无效", strict)
            continue
        exp: str = None
        if item.get('type') == 'item':
            exp = transTreeItem(session, current_user, item, ds, table_id=table_id, strict=strict)
        elif item.get('type') == 'tree':
            exp = transTreeToWhere(
                session,
                current_user,
                item.get('sub_tree'),
                ds,
                table_id=table_id,
                strict=strict,
            )
        else:
            _invalid_filter("行权限过滤项类型无效", strict)

        if exp is not None:
            expressions.append(exp)
    if not expressions:
        _invalid_filter("行权限过滤树未生成有效条件", strict)
        return None
    return '(' + f' {logic} '.join(expressions) + ')'


def transTreeItem(
        session: SessionDep,
        current_user: CurrentUser,
        item: Dict,
        ds: CoreDatasource,
        table_id: int | None = None,
        strict: bool = False,
) -> str | None:
    """
    是什么：transTreeItem 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    res: str = None
    try:
        field_id = int(item.get('field_id'))
    except (TypeError, ValueError):
        _invalid_filter("行权限过滤字段无效", strict)
        return None
    field = session.query(CoreField).filter(CoreField.id == field_id).first()
    if field is None:
        _invalid_filter("行权限过滤字段不存在", strict)
        return None
    if str(field.ds_id) != str(ds.id) or (table_id is not None and str(field.table_id) != str(table_id)):
        _invalid_filter("行权限过滤字段不属于当前数据表", strict)
        return None

    term = item.get('term')
    whereTerm = transFilterTerm(term)
    if whereTerm == "":
        _invalid_filter("行权限过滤操作符无效", strict)
        return None

    db = DB.get_db(ds.type)
    whereName = db.prefix + field.field_name + db.suffix

    if item.get('filter_type') == 'enum':
        enum_values = item.get('enum_value') or []
        if len(enum_values) > 0:
            whereValue = _where_value_for_term(ds, field, 'in', enum_values, strict)
            if whereValue is not None:
                res = "(" + whereName + " IN " + whereValue + ")"
        else:
            _invalid_filter("行权限枚举过滤条件缺少枚举值", strict)
    else:
        # if system variable, do check and get value
        # 新字段：取值类型（变量或普通值）和变量 ID。
        value_type = item.get('value_type')
        if value_type and value_type == 'variable':
            # 获取系统变量
            variable_id = item.get('variable_id')
            if variable_id is not None:
                sys_variable = session.query(SystemVariable).filter(SystemVariable.id == variable_id).first()
                if sys_variable is None:
                    _invalid_filter("行权限系统变量不存在", strict)
                    return None
                if (
                        sys_variable.type not in ('system', 'platform')
                        and not _same_explicit_tenant(sys_variable.tenant_id, ds.tenant_id)
                ):
                    _invalid_filter("行权限系统变量不属于当前工作空间", strict)
                    return None

                # 处理内置系统变量
                if sys_variable.type == 'system':
                    whereValue = getSysVariableValue(sys_variable, current_user, ds, field, item)
                    if whereValue is None:
                        _invalid_filter("行权限系统变量值为空", strict)
                        return None
                    res = whereName + whereTerm + whereValue
                else:
                    # 检查用户变量
                    user_variables = getattr(current_user, "system_variables", None)
                    if user_variables is None or len(user_variables) == 0 or not userHaveVariable(user_variables,
                                                                                                  sys_variable):
                        _invalid_filter("当前用户缺少行权限变量值", strict)
                        return None
                    else:
                        # 获取用户变量
                        u_variable = None
                        for u in user_variables:
                            if u.get('variableId') == sys_variable.id:
                                u_variable = u
                                break
                        if u_variable is None:
                            _invalid_filter("当前用户缺少行权限变量值", strict)
                            return None

                        # 检查取值
                        values = u_variable.get('variableValues')
                        if sys_variable.var_type == 'text':
                            set_sys = set(sys_variable.value)
                            values = [x for x in values if x in set_sys]
                            if values is None or len(values) == 0:
                                _invalid_filter("当前用户行权限变量值不在允许范围内", strict)
                                return None
                        elif sys_variable.var_type == 'number':
                            if (sys_variable.value[0] is not None and values[0] < sys_variable.value[0]) or (
                                    sys_variable.value[1] is not None and values[0] > sys_variable.value[1]):
                                _invalid_filter("当前用户行权限变量值不在允许范围内", strict)
                                return None
                        elif sys_variable.var_type == 'datetime':
                            if (sys_variable.value[0] is not None and values[0] < sys_variable.value[0]) or (
                                    sys_variable.value[1] is not None and values[0] > sys_variable.value[1]):
                                _invalid_filter("当前用户行权限变量值不在允许范围内", strict)
                                return None

                        whereValue = _where_value_for_term(ds, field, term, values, strict)
                        if whereValue is None:
                            return None

                        res = whereName + whereTerm + whereValue
            else:
                _invalid_filter("行权限变量 ID 为空", strict)
                return None
        else:
            whereValue = _where_value_for_term(ds, field, term, item.get('value'), strict)
            if whereValue is None:
                return None

            res = whereName + whereTerm + whereValue
    return res


def transFilterTerm(term: str) -> str:
    """
    是什么：transFilterTerm 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if term == "eq":
        return " = "
    if term == "not_eq":
        return " <> "
    if term == "lt":
        return " < "
    if term == "le":
        return " <= "
    if term == "gt":
        return " > "
    if term == "ge":
        return " >= "
    if term == "in":
        return " IN "
    if term == "not in":
        return " NOT IN "
    if term == "like":
        return " LIKE "
    if term == "not like":
        return " NOT LIKE "
    if term == "null":
        return " IS NULL "
    if term == "not_null":
        return " IS NOT NULL "
    if term == "empty":
        return " = "
    if term == "not_empty":
        return " <> "
    if term == "between":
        return " BETWEEN "
    return ""


def userHaveVariable(user_variables: List, sys_variable: SystemVariable):
    """
    是什么：userHaveVariable 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    for u in user_variables:
        if sys_variable.id == u.get('variableId'):
            return True
    return False


def getSysVariableValue(sys_variable: SystemVariable, current_user: CurrentUser, ds: CoreDatasource, field: CoreField,
                        item: Dict, ):
    """
    是什么：getSysVariableValue 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if not isinstance(sys_variable.value, list) or not sys_variable.value:
        return None
    variable_key = str(sys_variable.value[0] or "").strip()
    user_attr = _SYSTEM_VARIABLE_USER_FIELDS.get(variable_key)
    if not user_attr:
        return None
    v = getattr(current_user, user_attr, None)
    if v is None:
        return None

    escaped_v = _escape_sql_value(v, ds.type) if v is not None else v

    whereValue = ''
    if item['term'] == 'null':
        whereValue = ''
    elif item['term'] == 'not_null':
        whereValue = ''
    elif item['term'] == 'empty':
        whereValue = "''"
    elif item['term'] == 'not_empty':
        whereValue = "''"
    elif item['term'] == 'in' or item['term'] == 'not in':
        if ds.type == 'sqlServer' and (
                field.field_type == 'nchar' or field.field_type == 'NCHAR' or field.field_type == 'nvarchar' or field.field_type == 'NVARCHAR'):
            whereValue = f"(N'{escaped_v}')"
        else:
            whereValue = f"('{escaped_v}')"
    elif item['term'] == 'like' or item['term'] == 'not like':
        if ds.type == 'sqlServer' and (
                field.field_type == 'nchar' or field.field_type == 'NCHAR' or field.field_type == 'nvarchar' or field.field_type == 'NVARCHAR'):
            whereValue = f"N'%{escaped_v}%'"
        else:
            whereValue = f"'%{escaped_v}%'"
    else:
        if ds.type == 'sqlServer' and (
                field.field_type == 'nchar' or field.field_type == 'NCHAR' or field.field_type == 'nvarchar' or field.field_type == 'NVARCHAR'):
            whereValue = f"N'{escaped_v}'"
        else:
            whereValue = f"'{escaped_v}'"

    return whereValue
