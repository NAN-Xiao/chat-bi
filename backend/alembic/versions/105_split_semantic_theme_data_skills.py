"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f64b1e9c2a75"
down_revision = "e42f8b6c1d9a"
branch_labels = None
depends_on = None


PLATFORM_THEMES: tuple[dict[str, Any], ...] = (
    {
        "slug": "growth-activity",
        "title": "增长活跃与时间窗口",
        "description": "从旧版 SaaS 术语和 SQL 示例抽取，覆盖新增、活跃、回流、分层和观察窗口。",
        "term_words": ("DAU", "新增用户", "回流用户", "活跃用户分层"),
        "sql_keywords": ("DAU", "新增用户"),
        "usage": (
            "先确定统计对象、行为事实、去重粒度和观察基准日。",
            "最近 N 天优先使用当前分析表的最大业务日期作为截止日。",
            "活跃、新增、回流和分层是不同指标，不要互相替代。",
        ),
    },
    {
        "slug": "retention-lifecycle",
        "title": "留存与生命周期",
        "description": "从旧版 SaaS 术语和 SQL 示例抽取，覆盖 cohort、成熟窗口、留存和生命周期曲线。",
        "term_words": ("次日留存", "留存率"),
        "sql_keywords": ("留存",),
        "usage": (
            "cohort 分母必须固定，不能在按 lifecycle_day 分组后重新计算分母。",
            "未成熟生命周期天返回 NULL 或标注未成熟，不要当作 0。",
            "精确日留存、连续留存、滚动留存和回流不是同一个口径。",
        ),
    },
    {
        "slug": "revenue-payment-ltv",
        "title": "收入付费与 LTV",
        "description": "从旧版 SaaS 术语和 SQL 示例抽取，覆盖收入、付费、转化、商品结构、人均值和 LTV。",
        "term_words": (
            "流水",
            "付费用户",
            "付费率",
            "ARPU",
            "ARPPU",
            "LTV",
            "首付成功",
            "付费留存",
            "生命周期日付费率",
            "累计付费转化",
            "首日付费用户复购留存",
            "商品付费结构",
        ),
        "sql_keywords": ("流水", "ARPU", "ARPPU", "付费", "LTV", "商品", "礼包", "复购", "转化"),
        "usage": (
            "收入必须使用成功交易和有效金额字段，不能把原始订单金额直接当净收入。",
            "ARPU、ARPPU、付费率、累计转化、复购留存和 LTV 要先区分分母。",
            "总量、均值和比率不要全部放进同一同轴图。",
        ),
    },
    {
        "slug": "funnel-behavior",
        "title": "漏斗转化与行为路径",
        "description": "从旧版 SaaS 术语和 SQL 示例抽取，覆盖漏斗、步骤转化、节点流失和教程行为。",
        "term_words": ("漏斗分析", "新手教程步骤"),
        "sql_keywords": ("漏斗", "流失", "教程"),
        "usage": (
            "漏斗必须先构造玩家或实体级状态表，再计算每一步完成人数。",
            "主漏斗 users 应是完成当前步骤且完成所有前序步骤的去重实体数。",
            "事件次数、事件人数和漏斗用户数必须分别命名。",
        ),
    },
    {
        "slug": "report-chart-prediction",
        "title": "报表图表与预测规范",
        "description": "从旧版 SaaS 术语和 SQL 示例抽取，覆盖百分比、混合图表、SQL 输出字段和预测表达。",
        "term_words": ("百分比指标", "混合指标图表", "预测分析"),
        "sql_keywords": ("预测",),
        "usage": (
            "百分比字段输出 0-100 的数值型结果，图表层再格式化百分号。",
            "趋势、维度对比、漏斗、指标卡和混合图要使用不同字段结构。",
            "预测类结果应区分 actual_value、benchmark_value、predicted_value 和 confidence。",
        ),
    },
)


TENANT_THEMES: tuple[dict[str, Any], ...] = (
    {
        "slug": "growth-retention",
        "title": "增长留存与会话",
        "description": "覆盖当前工作空间数据源的用户增长、活跃、会话、生命周期和留存问题。",
        "term_words": (
            "DAU",
            "新增用户",
            "回流用户",
            "活跃用户分层",
            "SLG BI Mock数据集",
            "观察基准日",
            "明细表粒度",
            "玩家维表",
            "归因和设备维度",
            "区服和联盟维度",
            "生命周期日",
            "会话分析",
            "流失用户",
            "次日留存",
            "留存率",
            "连续留存",
            "滚动留存",
        ),
        "sql_keywords": ("DAU", "新增用户", "留存"),
        "usage": (
            "先用本 Skill 确定数据集、观察基准日、明细粒度、玩家维度和会话活跃口径。",
            "增长趋势使用 stat_date；生命周期与留存曲线使用 lifecycle_day 和 cohort/install_date。",
            "留存类问题必须固定分母并处理未成熟窗口。",
        ),
    },
    {
        "slug": "revenue-ltv",
        "title": "收入付费与 LTV",
        "description": "覆盖当前工作空间数据源的收入、付费、商品结构、转化、人均值和 LTV 问题。",
        "term_words": (
            "流水",
            "付费用户",
            "付费率",
            "生命周期日付费率",
            "付费留存",
            "累计付费转化",
            "首日付费用户复购留存",
            "商品付费结构",
            "ARPU",
            "ARPPU",
            "LTV",
            "首付成功",
            "订单状态",
            "毛收入和退款",
            "付费相关资源",
            "百分比指标",
            "混合指标图表",
            "预测分析",
        ),
        "sql_keywords": ("流水", "ARPU", "ARPPU", "付费", "LTV", "商品", "礼包", "复购", "转化", "预测"),
        "usage": (
            "收入相关 SQL 必须使用本 Skill 指定的成功订单、净收入、退款和首付字段口径。",
            "付费率、累计转化、复购留存、生命周期日付费率和 LTV 是不同指标。",
            "图表不要把收入总量、均值、人均值和比率全部放到同一同轴图。",
        ),
    },
    {
        "slug": "events-battle-resource-growth",
        "title": "事件战斗资源成长",
        "description": "覆盖当前工作空间数据源的事件、漏斗、战斗、资源、成长、质量和联盟行为问题。",
        "term_words": (
            "漏斗分析",
            "新手教程步骤",
            "事件明细",
            "事件次数和事件人数",
            "买量事件",
            "质量事件",
            "战斗分析",
            "战斗胜率",
            "兵损和战力变化",
            "资源流水",
            "资源产出和消耗",
            "建筑升级",
            "科技研究",
            "士兵训练",
            "加速使用",
            "玩家成长",
            "联盟行为",
        ),
        "sql_keywords": ("漏斗", "流失", "事件", "质量", "战斗", "资源", "建筑", "科技", "练兵", "兵损", "成长消耗"),
        "usage": (
            "事件次数、触发人数、漏斗用户数、战斗次数和战斗人数必须分别计算并清晰命名。",
            "资源、成长、战斗等明细问题优先复用本 Skill 中对应事实表和维表连接方式。",
            "漏斗主图按 step_order、step_name、users 输出；多维拆解另用表格或柱图。",
        ),
    },
)


EXCLUDED_PLATFORM_SQL_KEYWORDS: tuple[str, ...] = (
    "SLG BI Mock 2",
    "Season War",
    "crystal",
)


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    """
    是什么：_has_columns 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return _has_table(table_name) and all(_has_column(table_name, column_name) for column_name in column_names)


def _datasource_ids(value: Any) -> list[int]:
    """
    是什么：_datasource_ids 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [value]
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(result))


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """
    是什么：_contains_any 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _term_line(term: dict[str, Any]) -> str:
    """
    是什么：_term_line 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    synonyms = (term.get("synonyms") or "").strip()
    description = (term.get("description") or "").strip()
    line = f"<!-- legacy-terminology:{term['id']} -->\n- **{term['word']}**"
    if synonyms:
        line += f"（同义词：{synonyms}）"
    if description:
        line += f"：{description}"
    return line


def _sql_block(row: dict[str, Any]) -> str:
    """
    是什么：_sql_block 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    description = (row.get("description") or "").strip()
    return (
        f"<!-- legacy-data-training:{row['id']} -->\n"
        f"### 问题：{row['question']}\n\n"
        f"````sql\n{description}\n````"
    )


def _dedupe_sql_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    是什么：_dedupe_sql_rows 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        question = str(row.get("question") or "").strip()
        if not question or question in seen:
            continue
        seen.add(question)
        result.append(row)
    return result


def _theme_for_term(word: str, themes: tuple[dict[str, Any], ...]) -> str | None:
    """
    是什么：_theme_for_term 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    for theme in themes:
        if word in theme["term_words"]:
            return str(theme["slug"])
    return None


def _theme_for_sql(question: str, description: str, themes: tuple[dict[str, Any], ...]) -> str | None:
    """
    是什么：_theme_for_sql 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    theme_slugs = {str(theme["slug"]) for theme in themes}
    rules = (
        ("report-chart-prediction", ("预测",)),
        ("events-battle-resource-growth", ("漏斗", "流失", "事件", "质量", "教程", "战斗", "资源", "建筑", "科技", "练兵", "兵损", "成长消耗")),
        ("funnel-behavior", ("漏斗", "流失", "教程")),
        ("revenue-ltv", ("流水", "ARPU", "ARPPU", "付费", "LTV", "商品", "礼包", "复购", "转化")),
        ("revenue-payment-ltv", ("流水", "ARPU", "ARPPU", "付费", "LTV", "商品", "礼包", "复购", "转化")),
        ("retention-lifecycle", ("留存",)),
        ("growth-retention", ("DAU", "新增用户", "留存", "会话")),
        ("growth-activity", ("DAU", "新增用户")),
    )
    for text in (question, description):
        for slug, keywords in rules:
            if slug in theme_slugs and _contains_any(text, keywords):
                return slug
    return None


def _fetch_terms(platform: bool) -> list[dict[str, Any]]:
    """
    是什么：_fetch_terms 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移需要的数据找出来，整理成后面好用的样子。
    """
    if not _has_columns(
        "terminology",
        ("id", "tenant_id", "scope", "pid", "word", "description", "specific_ds", "datasource_ids", "enabled"),
    ):
        return []
    scope_operator = "=" if platform else "<>"
    return [
        dict(row)
        for row in op.get_bind().execute(
            sa.text(
                f"""
                SELECT
                    t.id,
                    t.tenant_id,
                    COALESCE(t.scope, 'TENANT') AS scope,
                    COALESCE(t.specific_ds, FALSE) AS specific_ds,
                    COALESCE(t.datasource_ids, '[]'::jsonb) AS datasource_ids,
                    btrim(t.word) AS word,
                    NULLIF(btrim(COALESCE(t.description, '')), '') AS description,
                    COALESCE(
                        string_agg(btrim(child.word), ', ' ORDER BY child.word)
                            FILTER (
                                WHERE child.id IS NOT NULL
                                  AND NULLIF(btrim(child.word), '') IS NOT NULL
                            ),
                        ''
                    ) AS synonyms
                FROM terminology AS t
                LEFT JOIN terminology AS child
                    ON child.pid = t.id
                   AND COALESCE(child.enabled, TRUE) = TRUE
                WHERE t.pid IS NULL
                  AND COALESCE(t.enabled, TRUE) = TRUE
                  AND COALESCE(t.scope, 'TENANT') {scope_operator} 'PLATFORM'
                  AND NULLIF(btrim(t.word), '') IS NOT NULL
                GROUP BY t.id
                ORDER BY t.id
                """
            )
        ).mappings().all()
    ]


def _fetch_sql_rows(platform: bool) -> list[dict[str, Any]]:
    """
    是什么：_fetch_sql_rows 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移需要的数据找出来，整理成后面好用的样子。
    """
    if not _has_columns("data_training", ("id", "tenant_id", "scope", "datasource", "question", "description", "enabled")):
        return []
    scope_operator = "=" if platform else "<>"
    return [
        dict(row)
        for row in op.get_bind().execute(
            sa.text(
                f"""
                SELECT
                    id,
                    tenant_id,
                    COALESCE(scope, 'TENANT') AS scope,
                    datasource::bigint AS datasource_id,
                    btrim(question) AS question,
                    btrim(description) AS description
                FROM data_training
                WHERE COALESCE(enabled, TRUE) = TRUE
                  AND COALESCE(scope, 'TENANT') {scope_operator} 'PLATFORM'
                  AND NULLIF(btrim(question), '') IS NOT NULL
                  AND NULLIF(btrim(COALESCE(description, '')), '') IS NOT NULL
                ORDER BY id
                """
            )
        ).mappings().all()
    ]


def _datasource_and_tenant_maps() -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
    """
    是什么：_datasource_and_tenant_maps 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    datasource_map: dict[int, dict[str, Any]] = {}
    tenant_map: dict[int, str] = {}
    if _has_columns("core_datasource", ("id", "tenant_id", "name")):
        for row in op.get_bind().execute(
            sa.text("SELECT id, tenant_id, name FROM core_datasource ORDER BY id")
        ).mappings().all():
            datasource_map[int(row["id"])] = {
                "tenant_id": int(row["tenant_id"]),
                "name": row["name"] or f"数据源 {row['id']}",
            }
    if _has_columns("sys_tenant", ("id", "name")):
        for row in op.get_bind().execute(
            sa.text("SELECT id, name FROM sys_tenant ORDER BY id")
        ).mappings().all():
            tenant_map[int(row["id"])] = row["name"] or f"工作空间 {row['id']}"
    return datasource_map, tenant_map


def _render_skill(
        marker: str,
        name: str,
        scope_text: str,
        theme: dict[str, Any],
        terms: list[dict[str, Any]],
        sql_rows: list[dict[str, Any]],
) -> str:
    """
    是什么：_render_skill 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    term_section = "\n".join(_term_line(term) for term in terms) or "- 暂无匹配的旧版术语记录。"
    sql_section = "\n\n".join(_sql_block(row) for row in _dedupe_sql_rows(sql_rows)) or "- 暂无匹配的旧版 SQL 示例记录。"
    usage = "\n".join(f"- {item}" for item in theme["usage"])
    return f"""{marker}
# {name}

本 Skill 由旧版术语和 SQL 示例按主题整理生成；原 terminology 与 data_training 记录保留不删除。它用于问答报表自动理解业务口径、生成 SQL 和选择图表。

## 适用范围
- {scope_text}

## 使用方式
{usage}
- 如果本 Skill 与当前数据库 Schema、数据权限或用户已选数据源冲突，以当前 SaaS 权限、Schema 和已选数据源为准。

## 术语与口径
{term_section}

## SQL 示例
{sql_section}
"""


def _upsert_skill(
        marker: str,
        tenant_id: int,
        visibility_scope: str,
        name: str,
        description: str,
        prompt: str,
        specific_ds: bool,
        datasource_ids: list[int],
) -> None:
    """
    是什么：_upsert_skill 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    bind = op.get_bind()
    update_stmt = sa.text(
        """
        UPDATE custom_prompt
        SET tenant_id = :tenant_id,
            name = :name,
            description = :description,
            target_scope = 'ALL',
            active = TRUE,
            ai_model_id = NULL,
            create_by = NULL,
            visibility_scope = :visibility_scope,
            prompt = :prompt,
            specific_ds = :specific_ds,
            datasource_ids = :datasource_ids
        WHERE type = 'DATA_SKILL'
          AND position(:marker in COALESCE(prompt, '')) > 0
        """
    ).bindparams(sa.bindparam("datasource_ids", type_=postgresql.JSONB))
    result = bind.execute(
        update_stmt,
        {
            "marker": marker,
            "tenant_id": tenant_id,
            "visibility_scope": visibility_scope,
            "name": name[:255],
            "description": description,
            "prompt": prompt.strip(),
            "specific_ds": specific_ds,
            "datasource_ids": datasource_ids,
        },
    )
    if result.rowcount:
        return

    insert_stmt = sa.text(
        """
        INSERT INTO custom_prompt (
            tenant_id,
            type,
            create_time,
            name,
            description,
            target_scope,
            active,
            ai_model_id,
            create_by,
            visibility_scope,
            prompt,
            specific_ds,
            datasource_ids
        )
        VALUES (
            :tenant_id,
            'DATA_SKILL',
            NOW(),
            :name,
            :description,
            'ALL',
            TRUE,
            NULL,
            NULL,
            :visibility_scope,
            :prompt,
            :specific_ds,
            :datasource_ids
        )
        """
    ).bindparams(sa.bindparam("datasource_ids", type_=postgresql.JSONB))
    bind.execute(
        insert_stmt,
        {
            "tenant_id": tenant_id,
            "visibility_scope": visibility_scope,
            "name": name[:255],
            "description": description,
            "prompt": prompt.strip(),
            "specific_ds": specific_ds,
            "datasource_ids": datasource_ids,
        },
    )


def _generate_platform_theme_skills() -> None:
    """
    是什么：_generate_platform_theme_skills 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成数据库迁移的结果，比如答案、SQL、图表或建议。
    """
    terms = _fetch_terms(platform=True)
    sql_rows = [
        row
        for row in _fetch_sql_rows(platform=True)
        if not _contains_any(f"{row.get('question', '')}\n{row.get('description', '')}", EXCLUDED_PLATFORM_SQL_KEYWORDS)
    ]

    grouped_terms: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_sql: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for term in terms:
        slug = _theme_for_term(str(term.get("word") or ""), PLATFORM_THEMES)
        if slug:
            grouped_terms[slug].append(term)
    for row in sql_rows:
        slug = _theme_for_sql(str(row.get("question") or ""), str(row.get("description") or ""), PLATFORM_THEMES)
        if slug:
            grouped_sql[slug].append(row)

    for theme in PLATFORM_THEMES:
        slug = str(theme["slug"])
        theme_terms = grouped_terms.get(slug, [])
        theme_sql = grouped_sql.get(slug, [])
        if not theme_terms and not theme_sql:
            continue
        marker = f"<!-- data-skill-source:semantic-theme:saas:{slug} -->"
        name = f"SaaS 数据 Skill：{theme['title']}"
        prompt = _render_skill(
            marker=marker,
            name=name,
            scope_text="SaaS 全局通用；不绑定具体数据源。",
            theme=theme,
            terms=theme_terms,
            sql_rows=theme_sql,
        )
        _upsert_skill(
            marker=marker,
            tenant_id=1,
            visibility_scope="PLATFORM_PUBLIC",
            name=name,
            description=str(theme["description"]),
            prompt=prompt,
            specific_ds=False,
            datasource_ids=[],
        )


def _generate_tenant_theme_skills() -> None:
    """
    是什么：_generate_tenant_theme_skills 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成数据库迁移的结果，比如答案、SQL、图表或建议。
    """
    terms = _fetch_terms(platform=False)
    sql_rows = _fetch_sql_rows(platform=False)
    datasource_map, tenant_map = _datasource_and_tenant_maps()
    if not datasource_map:
        return

    datasources_by_tenant: dict[int, list[int]] = defaultdict(list)
    for ds_id, info in datasource_map.items():
        datasources_by_tenant[int(info["tenant_id"])].append(ds_id)

    grouped_terms: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    grouped_sql: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)

    for term in terms:
        tenant_id = int(term["tenant_id"])
        ds_ids = _datasource_ids(term.get("datasource_ids"))
        if not ds_ids and not term.get("specific_ds"):
            ds_ids = datasources_by_tenant.get(tenant_id, [])
        slug = _theme_for_term(str(term.get("word") or ""), TENANT_THEMES)
        if not slug:
            continue
        for ds_id in ds_ids:
            if ds_id in datasource_map:
                grouped_terms[(tenant_id, int(ds_id), slug)].append(term)

    for row in sql_rows:
        tenant_id = int(row["tenant_id"])
        datasource_id = row.get("datasource_id")
        ds_ids = [int(datasource_id)] if datasource_id is not None else datasources_by_tenant.get(tenant_id, [])
        slug = _theme_for_sql(str(row.get("question") or ""), str(row.get("description") or ""), TENANT_THEMES)
        if not slug:
            continue
        for ds_id in ds_ids:
            if ds_id in datasource_map:
                grouped_sql[(tenant_id, int(ds_id), slug)].append(row)

    for ds_id, ds_info in datasource_map.items():
        tenant_id = int(ds_info["tenant_id"])
        tenant_name = (tenant_map.get(tenant_id) or f"工作空间 {tenant_id}").strip()
        for theme in TENANT_THEMES:
            slug = str(theme["slug"])
            key = (tenant_id, int(ds_id), slug)
            theme_terms = grouped_terms.get(key, [])
            theme_sql = grouped_sql.get(key, [])
            if not theme_terms and not theme_sql:
                continue
            marker = f"<!-- data-skill-source:semantic-theme:tenant:{tenant_id}:{int(ds_id)}:{slug} -->"
            name = f"{tenant_name} 空间数据 Skill：{theme['title']}"
            prompt = _render_skill(
                marker=marker,
                name=name,
                scope_text=f"工作空间「{tenant_name}」的数据源「{ds_info['name']}」。",
                theme=theme,
                terms=theme_terms,
                sql_rows=theme_sql,
            )
            _upsert_skill(
                marker=marker,
                tenant_id=tenant_id,
                visibility_scope="ADMIN_PUBLIC",
                name=name,
                description=(
                    f"{theme['description']} 由旧版术语和 SQL 示例按主题生成；"
                    f"适用于数据源「{ds_info['name']}」。原始记录保留不删除。"
                ),
                prompt=prompt,
                specific_ds=True,
                datasource_ids=[int(ds_id)],
            )


def _disable_old_generated_semantic_skills() -> None:
    """
    是什么：_disable_old_generated_semantic_skills 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_columns("custom_prompt", ("type", "prompt", "active")):
        return
    op.execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET active = FALSE
            WHERE type = 'DATA_SKILL'
              AND (
                position('<!-- data-skill-source:legacy-semantic:' in COALESCE(prompt, '')) > 0
                OR position('<!-- data-skill-source:terminology:' in COALESCE(prompt, '')) > 0
                OR position('<!-- data-skill-source:data-training:' in COALESCE(prompt, '')) > 0
                OR position('<!-- data-skill-source:custom-prompt-generate-sql:' in COALESCE(prompt, '')) > 0
              )
            """
        )
    )


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_columns(
        "custom_prompt",
        (
            "tenant_id",
            "type",
            "create_time",
            "name",
            "description",
            "target_scope",
            "active",
            "ai_model_id",
            "create_by",
            "visibility_scope",
            "prompt",
            "specific_ds",
            "datasource_ids",
        ),
    ):
        return
    _generate_platform_theme_skills()
    _generate_tenant_theme_skills()
    _disable_old_generated_semantic_skills()


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    pass
