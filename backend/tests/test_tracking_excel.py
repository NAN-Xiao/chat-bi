"""
脚本说明：验证项目数据字典 Excel 可以作为埋点和语义配置的维护入口。
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from apps.chat.models.chat_model import AiModelQuestion
from apps.system.crud.tracking_config import build_tracking_prompt_context
from apps.system.crud.tracking_excel import (
    PhysicalFieldInfo,
    PhysicalTableInfo,
    parse_tracking_excel,
    tracking_config_excel,
)
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingFieldDTO,
    TenantTrackingTableDTO,
)


def _physical_schema() -> dict[str, PhysicalTableInfo]:
    return {
        "event_log": PhysicalTableInfo(
            table_name="event_log",
            table_comment="事件明细表",
            fields=[
                PhysicalFieldInfo("uid", "varchar", "用户ID"),
                PhysicalFieldInfo("event_name", "varchar", "事件名"),
                PhysicalFieldInfo("event_time", "timestamp", "事件时间"),
                PhysicalFieldInfo("event_props", "jsonb", "事件属性"),
            ],
        ),
        "user_profile": PhysicalTableInfo(
            table_name="user_profile",
            table_comment="用户属性表",
            fields=[
                PhysicalFieldInfo("uid", "varchar", "用户ID"),
                PhysicalFieldInfo("country", "varchar", "注册国家"),
            ],
        ),
    }


def _event_physical_schema() -> dict[str, PhysicalTableInfo]:
    return {
        "event": PhysicalTableInfo(
            table_name="event",
            table_comment="事件明细表",
            fields=[
                PhysicalFieldInfo("uid", "varchar", "用户ID"),
                PhysicalFieldInfo("event", "varchar", "事件名"),
                PhysicalFieldInfo("time", "bigint", "事件时间"),
                PhysicalFieldInfo("ext", "json", "事件属性"),
            ],
        ),
    }


def _tracking_config() -> TenantTrackingConfigDTO:
    return TenantTrackingConfigDTO(
        tenant_id=2001,
        enabled=True,
        default_event_table="event_log",
        default_subject_field="uid",
        default_event_name_field="event_name",
        default_event_time_field="event_time",
        field_role_mappings=[{"field_role": "subject_id", "description": "主体用户字段"}],
        sql_rules="支付金额统一使用 event_props.amount；活跃用户按 uid 去重。",
        notes="当前项目以 Excel 维护事件、公共属性、用户属性。",
        tables=[
            TenantTrackingTableDTO(
                tenant_id=2001,
                table_name="event_log",
                table_comment="事件明细表",
                table_role="event_fact",
                aliases=["事件明细"],
            ),
            TenantTrackingTableDTO(
                tenant_id=2001,
                table_name="user_profile",
                table_comment="用户属性表",
                table_role="user_profile",
                aliases=["用户属性"],
            ),
        ],
        fields=[
            TenantTrackingFieldDTO(
                tenant_id=2001,
                table_name="event_log",
                field_name="uid",
                field_comment="用户唯一标识",
                field_role="subject_id",
                semantic_type="identifier",
                aliases=["用户ID"],
            ),
            TenantTrackingFieldDTO(
                tenant_id=2001,
                table_name="event_log",
                field_name="event_name",
                field_comment="业务事件名",
                field_role="event_name",
                semantic_type="text",
                aliases=["事件名"],
            ),
            TenantTrackingFieldDTO(
                tenant_id=2001,
                table_name="event_log",
                field_name="event_props.amount",
                field_comment="支付金额",
                field_role="json_path_metric",
                semantic_type="number",
                source_field="event_props",
                json_path="$.amount",
                aliases=["支付金额"],
                expression="NULLIF((\"event_log\".\"event_props\"::jsonb #>> '{amount}'), '')::numeric",
            ),
            TenantTrackingFieldDTO(
                tenant_id=2001,
                table_name="event_log",
                field_name="event_props.battleResult",
                field_comment="战斗结果",
                field_role="json_path_dimension",
                semantic_type="text",
                source_field="event_props",
                json_path="$.battleResult",
                aliases=["战斗结果"],
                value_mappings=[
                    {"value": "1", "display_name": "胜利", "category": "战斗结果", "description": "战斗胜利", "aliases": ["win"]},
                    {"value": "3", "display_name": "失败", "category": "战斗结果"},
                ],
            ),
            TenantTrackingFieldDTO(
                tenant_id=2001,
                table_name="user_profile",
                field_name="country",
                field_comment="注册国家",
                field_role="profile_dimension",
                semantic_type="text",
                aliases=["注册国家"],
                value_mappings=[
                    {"value": "US", "display_name": "美国", "category": "北美", "description": "美国用户"},
                    {"value": "CN", "display_name": "中国", "category": "东亚"},
                ],
            ),
        ],
        event_name_mappings=[
            {
                "event_name": "login",
                "event_display_name": "登录",
                "event_category": "基础事件",
                "collect_side": "client",
                "description": "用户登录事件",
                "aliases": ["登录事件"],
                "properties": [
                    {
                        "property_name": "duration",
                        "property_display_name": "停留时长",
                        "property_type": "数值",
                        "source_field": "event_props",
                        "json_path": "$.duration",
                        "description": "本次停留秒数",
                    }
                ],
            },
            {
                "metric": "付费相关事件",
                "events": ["pay_success", "refund_success"],
                "description": "付费与退款事件",
            },
        ],
    )


def _headers(workbook_bytes: bytes, sheet_name: str) -> list[str]:
    workbook = load_workbook(BytesIO(workbook_bytes), read_only=True, data_only=True)
    sheet = workbook[sheet_name]
    return [str(cell or "") for cell in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True))]


def _sheet_rows(workbook_bytes: bytes, sheet_name: str) -> list[tuple[object, ...]]:
    workbook = load_workbook(BytesIO(workbook_bytes), read_only=True, data_only=True)
    sheet = workbook[sheet_name]
    return list(sheet.iter_rows(min_row=2, values_only=True))


def test_tracking_excel_uses_physical_table_sheets_and_roundtrips_to_prompt_context() -> None:
    """
    是什么：验证导出的 Excel 以物理表 sheet 作为唯一主维护入口，且能导入回项目语义。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：导出、检查 sheet/表头/行类型，再导入并生成 agent prompt context。
    """
    config = _tracking_config()
    workbook_bytes = tracking_config_excel(config, physical_schema=_physical_schema()).getvalue()

    workbook = load_workbook(BytesIO(workbook_bytes), read_only=True, data_only=True)
    assert workbook.sheetnames == [
        "_说明",
        "_表映射",
        "event_log",
        "user_profile",
        "_SQL规则",
    ]
    assert _headers(workbook_bytes, "event_log")[:13] == [
        "行类型",
        "字段名",
        "字段显示名",
        "字段类型",
        "字段角色",
        "语义类型",
        "来源字段",
        "JSON 路径",
        "字段表达式",
        "是否必填",
        "字段/事件取值",
        "取值显示名",
        "取值标签",
    ]

    physical_event_rows = _sheet_rows(workbook_bytes, "event_log")
    event_field_row = next(row for row in physical_event_rows if row[1] == "event_name" and row[0] == "physical_field")
    assert event_field_row[3] == "varchar"
    assert event_field_row[4] == "event_name"
    assert event_field_row[5] == "text"
    assert any(row[0] == "event_value" and row[1] == "event_name" and row[10] == "login" for row in physical_event_rows)
    assert any(not row[0] and not row[1] and row[10] == "pay_success" for row in physical_event_rows)
    assert any(row[0] == "dictionary_field" and row[1] == "event_props.amount" and row[6] == "event_props" and row[7] == "$.amount" for row in physical_event_rows)
    battle_row_index = next(
        index
        for index, row in enumerate(physical_event_rows)
        if not row[0] and row[1] == "event_props.battleResult" and row[7] == "$.battleResult"
    )
    assert physical_event_rows[battle_row_index + 1][0] == "field_value"
    assert physical_event_rows[battle_row_index + 1][1] == "event_props.battleResult"
    assert physical_event_rows[battle_row_index + 1][10] == "1"
    assert not physical_event_rows[battle_row_index + 2][0]
    assert not physical_event_rows[battle_row_index + 2][1]
    assert physical_event_rows[battle_row_index + 2][10] == "3"

    user_rows = _sheet_rows(workbook_bytes, "user_profile")
    assert any(row[0] == "field_value" and row[1] == "country" and row[10] == "US" and row[11] == "美国" for row in user_rows)

    parsed = parse_tracking_excel(
        workbook_bytes,
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema=_physical_schema(),
        datasource_type="postgresql",
    )
    assert parsed.profile == "shuzhi_generic_v1"
    assert not parsed.warnings
    assert parsed.editor.default_event_table == "event_log"
    assert parsed.editor.default_subject_field == "uid"
    assert parsed.editor.notes == "当前项目以 Excel 维护事件、公共属性、用户属性。"
    assert {"field_role": "subject_id", "description": "主体用户字段"} in parsed.editor.field_role_mappings
    assert any(table.table_name == "event_log" and "事件明细" in table.aliases for table in parsed.editor.tables)
    assert any(field.table_name == "event_log" and field.field_name == "event_props.amount" for field in parsed.editor.fields)
    assert any(field.table_name == "event_log" and field.field_name == "event_props.duration" for field in parsed.editor.fields)
    assert any(event.get("event_name") == "pay_success" for event in parsed.editor.event_name_mappings if isinstance(event, dict))
    login_event = next(event for event in parsed.editor.event_name_mappings if isinstance(event, dict) and event.get("event_name") == "login")
    assert "登录事件" in login_event.get("aliases", [])
    assert any(prop.get("source_field") == "event_props" and prop.get("json_path") == "$.duration" for prop in login_event.get("properties", []))
    battle_result = next(field for field in parsed.editor.fields if field.table_name == "event_log" and field.field_name == "event_props.battleResult")
    assert {"value": "1", "display_name": "胜利", "category": "战斗结果", "description": "战斗胜利", "aliases": ["win"]} in battle_result.value_mappings
    assert {"value": "3", "display_name": "失败", "category": "战斗结果"} in battle_result.value_mappings
    country = next(field for field in parsed.editor.fields if field.table_name == "user_profile" and field.field_name == "country")
    assert "注册国家" in country.aliases
    assert {"value": "US", "display_name": "美国", "category": "北美", "description": "美国用户"} in country.value_mappings

    context, summary = build_tracking_prompt_context(parsed.editor)
    assert "<Workspace-Tracking-Rules>" in context
    assert "event_log.event_props.amount" in context
    assert "pay_success" in context
    assert "支付金额统一使用 event_props.amount" in context
    assert any("event_props.amount" in item for item in summary)


def test_event_sheet_event_value_rows_can_roundtrip_event_dictionary() -> None:
    """
    是什么：验证只维护物理表 sheet 里的 event_value 行，也能导入为事件值字典。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：删除兼容事件 sheet 和枚举 sheet，确保 event_log sheet 仍可回填事件定义。
    """
    config = _tracking_config()
    workbook_bytes = tracking_config_excel(config, physical_schema=_physical_schema()).getvalue()
    workbook = load_workbook(BytesIO(workbook_bytes))
    for sheet_name in list(workbook.sheetnames):
        if sheet_name not in {"_表映射", "event_log"}:
            del workbook[sheet_name]
    output = BytesIO()
    workbook.save(output)

    parsed = parse_tracking_excel(
        output.getvalue(),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema=_physical_schema(),
        datasource_type="postgresql",
    )

    assert any(event.get("event_name") == "login" for event in parsed.editor.event_name_mappings if isinstance(event, dict))
    assert any(event.get("event_name") == "pay_success" for event in parsed.editor.event_name_mappings if isinstance(event, dict))


def test_compact_event_value_rows_inherit_previous_context() -> None:
    """
    是什么：验证 Excel 里后续 event_value 行省略上下文字段时，也不会被导入跳过。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：模拟用户粘贴的 compact 形态，只有第一行写 row_type/field_name。
    """
    config = _tracking_config()
    workbook_bytes = tracking_config_excel(config, physical_schema=_physical_schema()).getvalue()
    workbook = load_workbook(BytesIO(workbook_bytes))
    sheet = workbook["event_log"]
    for row_index in range(2, sheet.max_row + 1):
        if sheet.cell(row_index, 1).value == "event_value" and sheet.cell(row_index, 11).value != "login":
            for col_index in (1, 2, 4, 5, 6):
                sheet.cell(row_index, col_index).value = None
    output = BytesIO()
    workbook.save(output)

    parsed = parse_tracking_excel(
        output.getvalue(),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema=_physical_schema(),
        datasource_type="postgresql",
    )

    assert any(event.get("event_name") == "login" for event in parsed.editor.event_name_mappings if isinstance(event, dict))
    assert any(event.get("event_name") == "pay_success" for event in parsed.editor.event_name_mappings if isinstance(event, dict))


def test_compact_json_field_value_rows_inherit_nested_context() -> None:
    """
    是什么：验证 ext 这类 JSON 嵌套字段也能按父子分组维护取值。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：模拟 ext.battleResult 下 1/3/4 枚举省略字段上下文，导入后仍形成字段值语义。
    """
    workbook_bytes = tracking_config_excel(
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema=_event_physical_schema(),
        template_only=True,
    ).getvalue()
    workbook = load_workbook(BytesIO(workbook_bytes))
    sheet = workbook["event"]
    for row_index in range(sheet.max_row, 1, -1):
        sheet.delete_rows(row_index, 1)
    sheet.append(["physical_field", "ext", "事件参数", "json", "", "json"])
    sheet.append(["dictionary_field", "ext.battleResult", "战斗结果", "text", "json_path_dimension", "text", "ext", "$.battleResult"])
    sheet.append(["field_value", "", "", "", "", "", "", "", "", "", "1", "胜利", "战斗结果", "", "", "", "", "", "胜利时上报", "", "win"])
    sheet.append(["", "", "", "", "", "", "", "", "", "", "3", "失败", "战斗结果", "", "", "", "", "", "失败时上报", "", "lose"])
    sheet.append(["", "", "", "", "", "", "", "", "", "", "4", "平局", "战斗结果"])
    output = BytesIO()
    workbook.save(output)

    parsed = parse_tracking_excel(
        output.getvalue(),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema=_event_physical_schema(),
        datasource_type="mysql",
    )

    battle_result = next(field for field in parsed.editor.fields if field.table_name == "event" and field.field_name == "ext.battleResult")
    assert battle_result.source_field == "ext"
    assert battle_result.json_path == "$.battleResult"
    assert {"value": "1", "display_name": "胜利", "category": "战斗结果", "description": "胜利时上报", "aliases": ["win"]} in battle_result.value_mappings
    assert {"value": "3", "display_name": "失败", "category": "战斗结果", "description": "失败时上报", "aliases": ["lose"]} in battle_result.value_mappings
    assert {"value": "4", "display_name": "平局", "category": "战斗结果"} in battle_result.value_mappings


def test_single_event_sheet_can_maintain_event_values_and_defaults() -> None:
    """
    是什么：验证真实 event 表只保留 event sheet 时，也能维护事件值字典。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：删除所有辅助 sheet，只导入 event sheet，检查默认事件表/事件名字段和事件值。
    """
    base = _tracking_config()
    config = base.model_copy(
        update={
            "default_event_table": "event",
            "default_event_name_field": "event",
            "default_event_time_field": "time",
            "tables": [
                TenantTrackingTableDTO(
                    tenant_id=2001,
                    table_name="event",
                    table_comment="事件明细表",
                    table_role="event_fact",
                )
            ],
            "fields": [
                TenantTrackingFieldDTO(
                    tenant_id=2001,
                    table_name="event",
                    field_name="uid",
                    field_comment="用户唯一标识",
                    field_role="subject_id",
                    semantic_type="identifier",
                ),
                TenantTrackingFieldDTO(
                    tenant_id=2001,
                    table_name="event",
                    field_name="event",
                    field_comment="业务事件名",
                    field_role="event_name",
                    semantic_type="text",
                ),
                TenantTrackingFieldDTO(
                    tenant_id=2001,
                    table_name="event",
                    field_name="ext.duration",
                    field_comment="停留时长",
                    field_role="json_path_metric",
                    semantic_type="number",
                    source_field="ext",
                    json_path="$.duration",
                ),
            ],
        }
    )
    workbook_bytes = tracking_config_excel(config, physical_schema=_event_physical_schema()).getvalue()
    workbook = load_workbook(BytesIO(workbook_bytes))
    for sheet_name in list(workbook.sheetnames):
        if sheet_name != "event":
            del workbook[sheet_name]
    output = BytesIO()
    workbook.save(output)

    parsed = parse_tracking_excel(
        output.getvalue(),
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema=_event_physical_schema(),
        datasource_type="mysql",
    )

    assert parsed.editor.default_event_table == "event"
    assert parsed.editor.default_event_name_field == "event"
    assert any(field.table_name == "event" and field.field_name == "ext.duration" for field in parsed.editor.fields)
    assert any(event.get("event_name") == "login" for event in parsed.editor.event_name_mappings if isinstance(event, dict))
    assert any(event.get("event_name") == "pay_success" for event in parsed.editor.event_name_mappings if isinstance(event, dict))


def test_export_infers_event_values_when_default_event_table_is_missing() -> None:
    """
    是什么：验证旧默认事件表未保存时，导出仍能按当前数据源 event 表输出事件取值。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：只保留字段角色和事件值配置，不填 default_event_table，再检查 event sheet。
    """
    base = _tracking_config()
    config = base.model_copy(
        update={
            "default_event_table": None,
            "default_subject_field": None,
            "default_event_name_field": None,
            "default_event_time_field": None,
            "tables": [],
            "fields": [
                TenantTrackingFieldDTO(
                    tenant_id=2001,
                    table_name="event",
                    field_name="event",
                    field_comment="业务事件名",
                    field_role="event_name",
                    semantic_type="text",
                ),
                TenantTrackingFieldDTO(
                    tenant_id=2001,
                    table_name="event",
                    field_name="uid",
                    field_comment="用户唯一标识",
                    field_role="subject_id",
                    semantic_type="identifier",
                ),
            ],
        }
    )

    workbook_bytes = tracking_config_excel(config, physical_schema=_event_physical_schema()).getvalue()
    event_rows = _sheet_rows(workbook_bytes, "event")
    table_rows = _sheet_rows(workbook_bytes, "_表映射")
    info_rows = _sheet_rows(workbook_bytes, "_说明")

    assert any(row[0] == "event_value" and row[1] == "event" and row[10] == "login" for row in event_rows)
    assert any(not row[0] and not row[1] and row[10] == "pay_success" for row in event_rows)
    assert any(row[1] == "event" and row[4] == "uid" and row[5] == "event" for row in table_rows)
    assert any(row[0] == "当前默认" and "事件名字段=event" in str(row[1]) for row in info_rows)


def test_template_contains_datasource_aligned_examples() -> None:
    """
    是什么：验证模板不是空壳，事件表 sheet 会给出可照着改的事件值和 JSON 子字段样例。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：按真实 event 表生成模板，并检查样例使用当前数据源里的 event/ext 字段。
    """
    workbook_bytes = tracking_config_excel(
        TenantTrackingConfigDTO(tenant_id=2001, enabled=True),
        physical_schema=_event_physical_schema(),
        template_only=True,
    ).getvalue()

    event_rows = _sheet_rows(workbook_bytes, "event")

    assert any(row[0] == "physical_field" and row[1] == "event" for row in event_rows)
    assert any(row[0] == "event_value" and row[1] == "event" and row[10] == "login" for row in event_rows)
    assert any(row[0] == "dictionary_field" and row[1] == "ext.battleResult" and row[6] == "ext" and row[7] == "$.battleResult" for row in event_rows)


def test_import_excel_replaces_previous_tracking_config() -> None:
    """
    是什么：验证 Excel 是维护源，导入不会把 Excel 已删除的旧事件/字段悄悄合并回来。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：从导出中删掉 pay_success，再用带旧事件的 existing 导入，确认旧事件消失。
    """
    config = _tracking_config()
    workbook_bytes = tracking_config_excel(config, physical_schema=_physical_schema()).getvalue()
    workbook = load_workbook(BytesIO(workbook_bytes))
    sheet = workbook["event_log"]
    for row_index in range(sheet.max_row, 1, -1):
        if sheet.cell(row_index, 11).value in {"pay_success", "refund_success"}:
            sheet.delete_rows(row_index, 1)
    output = BytesIO()
    workbook.save(output)

    existing = config.model_copy(
        update={
            "event_name_mappings": [
                {"event_name": "legacy_event", "event_display_name": "旧事件"},
                *config.event_name_mappings,
            ],
        }
    )
    parsed = parse_tracking_excel(
        output.getvalue(),
        existing,
        physical_schema=_physical_schema(),
        datasource_type="postgresql",
    )
    event_names = {
        event.get("event_name")
        for event in parsed.editor.event_name_mappings
        if isinstance(event, dict)
    }

    assert "login" in event_names
    assert "pay_success" not in event_names
    assert "legacy_event" not in event_names


def test_chart_analysis_and_predict_prompts_share_tracking_semantics() -> None:
    """
    是什么：验证图表生成、分析和预测 Agent 都能看到同一份项目数据字典语义。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：构造问题对象，检查各类 prompt 都包含 tracking_config 与 Data Skill。
    """
    question = AiModelQuestion(
        question="看付费金额趋势",
        sql="select 1",
        fields="[]",
        data="[]",
        tracking_config="<Workspace-Tracking-Rules>支付金额字段 event_props.amount</Workspace-Tracking-Rules>",
        data_skill="Data Skill: 付费金额按事件 pay_success 统计。",
    )

    assert "event_props.amount" in question.chart_user_question()
    assert "pay_success" in question.chart_user_question()
    assert "event_props.amount" in question.analysis_sys_question()
    assert "pay_success" in question.analysis_sys_question()
    assert "event_props.amount" in question.predict_sys_question()
    assert "pay_success" in question.predict_sys_question()


def test_event_name_field_is_text_in_tracking_prompt_context() -> None:
    """
    是什么：验证旧配置里事件名字段若误标为 category，agent 语义出口仍按文本字段表达。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：构造旧库形态的 event_name 字段，检查 prompt 不再输出 type=category。
    """
    config = _tracking_config()
    for field in config.fields:
        if field.field_role == "event_name":
            field.semantic_type = "category"

    context, summary = build_tracking_prompt_context(config)

    assert "`event_log.event_name`; role=event_name; type=text" in context
    assert "role=event_name; type=category" not in context
    assert any("`event_log.event_name`; role=event_name; type=text" in item for item in summary)
