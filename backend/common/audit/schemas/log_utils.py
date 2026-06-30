"""
脚本说明：这个脚本定义操作日志的输入输出结构，帮接口和业务代码统一数据格式。
"""
from sqlalchemy import select, func
from sqlalchemy.sql import Select
from sqlalchemy import String, column, table, union_all

from apps.chat.models.chat_model import Chat
from apps.dashboard.models.dashboard_model import CoreDashboard
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.system_model import AiModelDetail, ApiKeyModel
from apps.system.models.user import UserModel
from apps.system.models.system_model import AssistantModel

from sqlalchemy import literal_column


def build_resource_union_query() -> Select:
    """
    是什么：build_resource_union_query 是一个可以复用的小步骤，负责操作日志相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存操作日志需要的东西，让后续流程能继续往下走。
    """
    # 创建各个子查询，每个查询都包含模块字段

    # AI 模型表查询
    ai_model_query = select(
        func.cast(AiModelDetail.id, String).label("id"),
        AiModelDetail.name.label("name"),
        literal_column("'ai_model'").label("module")
    ).select_from(AiModelDetail)

    # 聊天表查询（使用摘要作为名称）
    chat_query = select(
        func.cast(Chat.id, String).label("id"),
        Chat.brief.label("name"),
        literal_column("'chat'").label("module")
    ).select_from(Chat)

    # 仪表盘表查询
    dashboard_query = select(
        func.cast(CoreDashboard.id, String).label("id"),
        CoreDashboard.name.label("name"),
        literal_column("'dashboard'").label("module")
    ).select_from(CoreDashboard)

    # 数据源表查询
    datasource_query = select(
        func.cast(CoreDatasource.id, String).label("id"),
        CoreDatasource.name.label("name"),
        literal_column("'datasource'").label("module")
    ).select_from(CoreDatasource)

    # 自定义提示词表查询
    custom_prompt_table = table(
        "custom_prompt",
        column("id"),
        column("name"),
    )
    custom_prompt_query = select(
        func.cast(custom_prompt_table.c.id, String).label("id"),
        custom_prompt_table.c.name.label("name"),
        literal_column("'prompt_words'").label("module")
    ).select_from(custom_prompt_table)

    ds_permission_table = table(
        "ds_permission",
        column("id"),
        column("name"),
    )
    ds_rules_table = table(
        "ds_rules",
        column("id"),
        column("name"),
    )

    # 数据源权限表查询
    ds_permission_query = select(
        func.cast(ds_permission_table.c.id, String).label("id"),
        ds_permission_table.c.name.label("name"),
        literal_column("'permission'").label("module")
    ).select_from(ds_permission_table)

    # 数据源规则表查询
    ds_rules_query = select(
        func.cast(ds_rules_table.c.id, String).label("id"),
        ds_rules_table.c.name.label("name"),
        literal_column("'rules'").label("module")
    ).select_from(ds_rules_table)

    # 系统用户表查询
    user_query = select(
        func.cast(UserModel.id, String).label("id"),
        UserModel.name.label("name"),
        literal_column("'user'").label("module")
    ).select_from(UserModel)

    # 系统用户表查询
    member_query = select(
        func.cast(UserModel.id, String).label("id"),
        UserModel.name.label("name"),
        literal_column("'member'").label("module")
    ).select_from(UserModel)

    # 系统助手表查询
    sys_assistant_query = select(
        func.cast(AssistantModel.id, String).label("id"),
        AssistantModel.name.label("name"),
        literal_column("'application'").label("module")
    ).select_from(AssistantModel)

    # 系统 API 密钥表查询
    sys_apikey_query = select(
        func.cast(ApiKeyModel.id, String).label("id"),
        ApiKeyModel.access_key.label("name"),
        literal_column("'api_key'").label("module")
    ).select_from(ApiKeyModel)

    # 使用 union_all() 方法连接所有查询
    union_query = union_all(
        ai_model_query,
        chat_query,
        dashboard_query,
        datasource_query,
        custom_prompt_query,
        ds_permission_query,
        ds_rules_query,
        user_query,
        member_query,
        sys_assistant_query,
        sys_apikey_query
    )

    # 返回查询，包含所有字段
    return select(union_query.c.id, union_query.c.name, union_query.c.module)
