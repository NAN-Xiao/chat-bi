"""Normalize broad SLG BI Mock workspace skills after splitting business skills.

The dashboard/business skills are intentionally independent. This script keeps
the older broad event-funnel skill focused on generic event dictionary and
funnel validation rules, so tutorial/onboarding retrieval goes to the dedicated
dashboard skill.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from core_system_db import core_system_db_config, export_postgres_compat_env


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"

DB = core_system_db_config()
TENANT_ID = 7473600346187632640
DATASOURCE_ID = 1

EVENT_FUNNEL_NAME = "SLG BI Mock 空间 Skill：事件漏斗与埋点核对"
EVENT_FUNNEL_DESCRIPTION = (
    "定义 fact_events、dim_event_name、event_name、attributes JSON、PV/UV、事件字典核对、"
    "通用事件顺序校验和埋点排查规则；新手引导、教程、付费、活动、主城等具体业务漏斗必须使用独立业务 Skill。"
)
EVENT_FUNNEL_PROMPT = """<!-- data-skill-source:workspace:slg-bi-mock -->
# SLG BI Mock 空间 Skill：事件漏斗与埋点核对

本 Skill 只适用于 slg_bi_mock 工作空间绑定的 SLG BI Mock 数据源（core_datasource.id = 1，tenant_id = 7473600346187632640）。生成 SQL 前必须确认当前会话已选择并授权该工作空间/数据源；如果当前上下文不是这个数据源，不得套用这里的表名、字段名、事件名、指标口径或业务枚举。

## 空间级数据字典规则
- 以系统库中该工作空间/数据源的 core_table、core_field、表注释、字段注释和空间级 Skill 为准。
- 业务库可按只读处理；表字段说明、打点规则和查询口径属于工作空间元数据，不要求写回业务库。
- 如果本 Skill 与实时可见 Schema、权限或更具体的用户私有 Skill 冲突，优先使用当前 Schema、权限和更具体配置。

## 职责边界
- 本 Skill 只负责通用事件字典、事件明细、PV/UV、事件属性 JSON、通用漏斗顺序校验和埋点排查。
- 具体业务漏斗必须使用独立业务 Skill，例如新手引导、活动参与、礼包复购、主城升级等，不要把业务口径沉淀在本 Skill。
- 如果用户提到“新手任务”“新手引导”“新手教程”“tutorial_step”“完成教程后付费”“首次付费转化”，必须使用新手引导独立业务 Skill 的 cohort、步骤和付费口径；本 Skill 不能提供这些问题的默认 SQL 或示例口径。
- 若用户问具体业务名，优先召回对应独立业务 Skill；本 Skill 仅补充事件表通用规则。

## 当前数据源规则
- 事件明细使用 `fact_events`，一行代表一次上报事件。
- 事件唯一键是 `event_uid`；事件名字段是 `event_name`，它是工作空间内的业务事件标识，不是全局平台 ID。
- 事件中文名和说明优先关联 `dim_event_name.event_name`，使用 `event_cn_name`、`description`、`required_attrs` 辅助理解。
- PV/事件次数使用 `count(*)` 或 `count(distinct event_uid)`；UV/触发用户数使用 `count(distinct player_id)`；不要混用。
- `attributes` 是 JSONB，只有在事件字典或业务 Skill 明确属性名时才提取，例如 `attributes->>'xxx'`。
- 事件发生日期优先使用 `event_date` 或 `event_time::date`；客户端时间、接收时间、入库时间只在排查延迟/时区问题时使用。
- 事件上下文维度可使用 `platform`, `channel`, `campaign`, `country`, `device_tier`, `network_type`, `app_build`, `event_schema_version`。

## 通用漏斗校验
- 漏斗必须先构造玩家级或主体级明细，一行一个主体，再用前序条件逐步汇总。
- 后序步骤人数必须满足前序步骤条件；如果后序人数大于前序人数，应检查去重主体、事件时间顺序和步骤条件。
- 漏斗输出字段优先为 `step_order`, `step_name`, `users`, `conversion_from_start_pct`, `conversion_from_prev_pct`, `drop_off_users`。
- 需要事件时间顺序时，使用每个主体每个步骤的首次 `event_time`，并要求后一步时间不早于前一步。

## 埋点排查输出
- 字典核对：`event_name`, `event_cn_name`, `event_category`, `required_attrs`。
- 上报量趋势：`event_date`, `event_name`, `events`, `users`。
- 属性完整性：`event_name`, `attr_name`, `missing_events`, `missing_rate_pct`。
"""


def _save_embeddings(ids: list[int], tenant_id: int) -> int:
    if not ids:
        return 0
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy.orm import scoped_session, sessionmaker

    from apps.chat.curd.custom_prompt_embedding import save_custom_prompt_skill_embedding
    from common.core.db import engine

    session_maker = scoped_session(sessionmaker(bind=engine))
    return save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=tenant_id)


def main() -> None:
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE custom_prompt
                SET description = %s,
                    prompt = %s,
                    target_scope = 'ALL',
                    active = TRUE,
                    visible = TRUE,
                    specific_ds = TRUE,
                    datasource_ids = '[1]'::jsonb,
                    embedding = NULL,
                    embedding_signature = NULL
                WHERE type = 'DATA_SKILL'
                  AND tenant_id = %s
                  AND name = %s
                  AND (datasource_ids::text LIKE %s OR specific_ds = TRUE)
                RETURNING id
                """,
                (EVENT_FUNNEL_DESCRIPTION, EVENT_FUNNEL_PROMPT.strip(), TENANT_ID, EVENT_FUNNEL_NAME, f"%{DATASOURCE_ID}%"),
            )
            ids = [int(row[0]) for row in cur.fetchall()]
        conn.commit()

    saved = _save_embeddings(ids, TENANT_ID)
    print(f"Normalized base event skills: {ids}")
    print(f"Embedding refreshed: {saved}")


if __name__ == "__main__":
    main()
