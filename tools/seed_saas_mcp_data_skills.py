# -*- coding: utf-8 -*-
"""Seed SaaS-level MCP capability Data Skills."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config, export_postgres_compat_env


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"

DB = core_system_db_config()
PLATFORM_TENANT_ID = 1


DATA_SKILLS: list[dict[str, str]] = [
    {
        "name": "SaaS ChatMon MCP 告警过滤项 Skill",
        "description": "平台公共 ChatMon MCP 能力：列出当前工作空间绑定 MCP 可用的告警来源、优先级、风险分类和风险子类过滤项。",
        "prompt": r"""<!-- data-skill-source:saas:mcp:chatmon:alert-filter-options -->
<!-- saas-skill:{
  "id": "saas_chatmon_alert_filter_options",
  "name": "SaaS ChatMon 告警过滤项",
  "description": "调用当前工作空间绑定的 ChatMon MCP，列出告警过滤项。",
  "intent": ["ChatMon 过滤项", "告警过滤项", "舆情风险分类", "有哪些风险分类", "有哪些告警优先级"],
  "match": {
    "block_keywords_any": ["收入", "营收", "付费", "充值", "DAU", "活跃", "留存", "LTV", "ARPU", "ARPPU"],
    "keywords_any": ["过滤项", "风险分类", "风险子类", "优先级", "告警来源", "filter options"]
  },
  "sources": [
    {
      "name": "chatmon_filter_options",
      "type": "external_mcp",
      "tool": "alerts.filter_options",
      "arguments_template": {},
      "field_map": {
        "timezone": "时区",
        "sources": "告警来源",
        "priorities": "优先级",
        "risk_categories": "风险分类",
        "risk_subcategories": "风险子类"
      }
    }
  ],
  "chart": {
    "type": "table",
    "title": "ChatMon 告警过滤项",
    "columns": [
      {"value": "时区"},
      {"value": "告警来源"},
      {"value": "优先级"},
      {"value": "风险分类"},
      {"value": "风险子类"}
    ]
  },
  "analysis": {
    "answer_contract": ["说明这些过滤项来自当前工作空间绑定的 ChatMon MCP", "提示 count/search 可使用返回的风险分类或优先级继续过滤"]
  }
} -->
# SaaS ChatMon MCP 告警过滤项 Skill

## 适用范围
- 平台公共能力，不绑定具体数据源、租户或业务库表。
- 仅当当前工作空间已绑定 ChatMon 类外部 MCP 且当前用户有工作空间访问权限时可执行。
- 用于列出 `alerts.count` / `alerts.search` 支持的稳定过滤项：来源、优先级、风险分类、风险子类。

## 工具说明
- MCP 工具：`alerts.filter_options`
- 时间口径：工具返回的日期/时间过滤项遵循 MCP 服务声明，一般为 Asia/Shanghai。
- 该 Skill 不提供业务指标口径；不能替代工作空间 Data Skill、Schema 或权限配置。
""",
    },
    {
        "name": "SaaS ChatMon MCP 告警数量 Skill",
        "description": "平台公共 ChatMon MCP 能力：统计最近 1-7 天告警总量，并按优先级、风险分类和来源分布展示。",
        "prompt": r"""<!-- data-skill-source:saas:mcp:chatmon:alert-count -->
<!-- saas-skill:{
  "id": "saas_chatmon_alert_count",
  "name": "SaaS ChatMon 告警数量",
  "description": "调用当前工作空间绑定的 ChatMon MCP，统计最近 N 天告警/舆情/风险反馈数量及分布。",
  "intent": ["告警数量", "舆情数量", "风险反馈数量", "bug 反馈数量", "用户反馈趋势", "ChatMon 告警趋势"],
  "match": {
    "block_keywords_any": ["收入", "营收", "付费", "充值", "DAU", "活跃", "留存", "LTV", "ARPU", "ARPPU"],
    "keywords_any": ["告警", "舆情", "反馈", "风险", "bug", "Bug", "吐槽", "趋势", "数量", "ChatMon", "chatmon"]
  },
  "parameters": {
    "days": {
      "type": "integer",
      "default": 7,
      "min": 1,
      "max": 7,
      "patterns": ["(?:最近|近|过去|last)\\s*(\\d+)\\s*(?:天|日|days?)"]
    },
    "source": {
      "type": "string",
      "patterns": ["(game_chat|external_community|游戏内|游戏聊天|社区|外部社区)"],
      "value_map": {
        "游戏内": "game_chat",
        "游戏聊天": "game_chat",
        "社区": "external_community",
        "外部社区": "external_community"
      }
    },
    "priority_in": {
      "type": "array",
      "patterns": ["((?:P[0-2][,，、/\\s]*)+)"]
    },
    "risk_category": {
      "type": "string",
      "patterns": ["风险分类[:：\\s]+([^,，。\\s]+)", "risk_category[:：=\\s]+([^,，。\\s]+)"]
    },
    "risk_subcategory": {
      "type": "string",
      "patterns": ["风险子类[:：\\s]+([^,，。\\s]+)", "risk_subcategory[:：=\\s]+([^,，。\\s]+)"]
    }
  },
  "sources": [
    {
      "name": "chatmon_alert_count",
      "type": "external_mcp",
      "tool": "alerts.count",
      "arguments_template": {
        "start_date": "{{start_date}}",
        "end_date": "{{end_date}}",
        "source": "{{source}}",
        "priority_in": "{{priority_in}}",
        "risk_category": "{{risk_category}}",
        "risk_subcategory": "{{risk_subcategory}}"
      },
      "field_map": {
        "name": "指标",
        "value": "值",
        "group": "分组",
        "timezone": "时区",
        "total": "告警总数",
        "by_priority": "按优先级",
        "by_risk_category": "按风险分类",
        "by_source": "按来源"
      }
    }
  ],
  "chart": {
    "type": "table",
    "title": "ChatMon 告警数量与分布",
    "columns": [
      {"value": "指标"},
      {"value": "值"},
      {"value": "分组"},
      {"value": "告警总数"},
      {"value": "时区"}
    ]
  },
  "analysis": {
    "answer_contract": ["说明查询日期窗口", "给出总量", "概括 P0/P1/P2、风险分类、来源分布", "提示该工具只返回统计不返回明细证据，明细需使用 alerts.search 或 alerts.get_evidence"]
  }
} -->
# SaaS ChatMon MCP 告警数量 Skill

## 适用范围
- 平台公共能力，不绑定具体数据源、租户或业务库表。
- 仅当当前工作空间已绑定 ChatMon 类外部 MCP 且当前用户有工作空间访问权限时可执行。
- 适用于“最近 N 天告警数量 / 舆情数量 / Bug 反馈数量 / 风险反馈趋势”等问题。

## 工具说明
- MCP 工具：`alerts.count`
- 时间窗口：北京自然日；ChatMon 当前限制单次查询最长 7 天，因此本 Skill 会把用户更长的窗口限制为 7 天。
- 可选过滤：来源 `game_chat` / `external_community`、优先级 `P0/P1/P2`、风险分类、风险子类。
- 输出为统计和分布，不包含告警明细或证据消息；需要明细时使用 `alerts.search`，需要证据时使用 `alerts.get_evidence`。

## 边界
- 该 Skill 只描述 MCP 能力，不定义业务数据库里的收入、活跃、留存等指标。
- 如果用户要求结合业务指标，应同时使用当前工作空间的数据源 Skill / SQL 结果和本 MCP 结果，不要把相关性直接断言为因果。
""",
    },
    {
        "name": "SaaS ChatMon MCP 告警搜索 Skill",
        "description": "平台公共 ChatMon MCP 能力：搜索最近 1-7 天轻量告警明细，返回标题、摘要、优先级、风险分类、UID 和区服等字段。",
        "prompt": r"""<!-- data-skill-source:saas:mcp:chatmon:alert-search -->
<!-- saas-skill:{
  "id": "saas_chatmon_alert_search",
  "name": "SaaS ChatMon 告警搜索",
  "description": "调用当前工作空间绑定的 ChatMon MCP，搜索最近 N 天告警/舆情/风险反馈明细摘要。",
  "intent": ["告警明细", "舆情明细", "风险反馈明细", "搜索告警", "查看用户反馈明细", "ChatMon 告警列表"],
  "match": {
    "block_keywords_any": ["收入", "营收", "付费", "充值", "DAU", "活跃", "留存", "LTV", "ARPU", "ARPPU"],
    "keywords_any": ["明细", "列表", "搜索", "查看", "告警ID", "alert_id", "search"]
  },
  "parameters": {
    "days": {
      "type": "integer",
      "default": 7,
      "min": 1,
      "max": 7,
      "patterns": ["(?:最近|近|过去|last)\\s*(\\d+)\\s*(?:天|日|days?)"]
    },
    "limit": {
      "type": "integer",
      "default": 20,
      "min": 1,
      "max": 100,
      "patterns": ["(?:返回|展示|看|查)\\s*(\\d+)\\s*(?:条|个|rows?|items?)"]
    },
    "source": {
      "type": "string",
      "patterns": ["(game_chat|external_community|游戏内|游戏聊天|社区|外部社区)"],
      "value_map": {
        "游戏内": "game_chat",
        "游戏聊天": "game_chat",
        "社区": "external_community",
        "外部社区": "external_community"
      }
    },
    "priority_in": {
      "type": "array",
      "patterns": ["((?:P[0-2][,，、/\\s]*)+)"]
    },
    "risk_category": {
      "type": "string",
      "patterns": ["风险分类[:：\\s]+([^,，。\\s]+)", "risk_category[:：=\\s]+([^,，。\\s]+)"]
    },
    "risk_subcategory": {
      "type": "string",
      "patterns": ["风险子类[:：\\s]+([^,，。\\s]+)", "risk_subcategory[:：=\\s]+([^,，。\\s]+)"]
    }
  },
  "sources": [
    {
      "name": "chatmon_alert_search",
      "type": "external_mcp",
      "tool": "alerts.search",
      "arguments_template": {
        "start_date": "{{start_date}}",
        "end_date": "{{end_date}}",
        "source": "{{source}}",
        "priority_in": "{{priority_in}}",
        "risk_category": "{{risk_category}}",
        "risk_subcategory": "{{risk_subcategory}}",
        "limit": "{{limit}}"
      },
      "result_path": "items",
      "field_map": {
        "alert_id": "告警ID",
        "occurred_at": "发生时间",
        "priority": "优先级",
        "risk_category": "风险分类",
        "risk_subcategory": "风险子类",
        "title": "标题",
        "summary": "摘要",
        "source": "来源",
        "uids": "UID列表",
        "server_ids": "区服列表",
        "evidence_message_count": "证据消息数"
      }
    }
  ],
  "chart": {
    "type": "table",
    "title": "ChatMon 告警明细摘要",
    "columns": [
      {"value": "告警ID"},
      {"value": "发生时间"},
      {"value": "优先级"},
      {"value": "风险分类"},
      {"value": "风险子类"},
      {"value": "标题"},
      {"value": "摘要"},
      {"value": "来源"},
      {"value": "UID列表"},
      {"value": "区服列表"},
      {"value": "证据消息数"}
    ]
  },
  "analysis": {
    "answer_contract": ["说明查询日期窗口和返回条数", "按优先级/风险分类概括明细", "保留告警ID以便继续查询证据", "不要声称已经读取证据原文，除非用户继续调用 evidence Skill"]
  }
} -->
# SaaS ChatMon MCP 告警搜索 Skill

## 适用范围
- 平台公共能力，不绑定具体数据源、租户或业务库表。
- 仅当当前工作空间已绑定 ChatMon 类外部 MCP 且当前用户有工作空间访问权限时可执行。
- 适用于查看最近 N 天告警、舆情、风险反馈的轻量明细摘要。

## 工具说明
- MCP 工具：`alerts.search`
- 时间窗口：北京自然日；ChatMon 当前限制单次查询最长 7 天。
- 默认返回 20 条，最多 100 条。
- 返回摘要字段和 `evidence_message_count`，不返回证据消息原文；证据需用 `alerts.get_evidence` 按告警 ID 继续查询。
""",
    },
    {
        "name": "SaaS ChatMon MCP 告警证据 Skill",
        "description": "平台公共 ChatMon MCP 能力：按 alerts.search 返回的告警 ID 查询证据消息，最多返回 30 条。",
        "prompt": r"""<!-- data-skill-source:saas:mcp:chatmon:alert-evidence -->
<!-- saas-skill:{
  "id": "saas_chatmon_alert_evidence",
  "name": "SaaS ChatMon 告警证据",
  "description": "调用当前工作空间绑定的 ChatMon MCP，按告警 ID 查询证据消息。",
  "intent": ["告警证据", "查看证据消息", "告警原文", "聊天证据", "alerts.get_evidence"],
  "match": {
    "block_keywords_any": ["收入", "营收", "付费", "充值", "DAU", "活跃", "留存", "LTV", "ARPU", "ARPPU"],
    "keywords_any": ["证据", "原文", "消息", "evidence", "告警ID", "alert_id"]
  },
  "parameters": {
    "alert_id": {
      "type": "string",
      "required": true,
      "patterns": ["(alert-[A-Za-z0-9._:-]+)", "告警(?:ID|id)?[:：\\s]+([A-Za-z0-9._:-]+)", "alert_id[:：=\\s]+([A-Za-z0-9._:-]+)"]
    },
    "limit": {
      "type": "integer",
      "default": 10,
      "min": 1,
      "max": 30,
      "patterns": ["(?:返回|展示|看|查)\\s*(\\d+)\\s*(?:条|个|rows?|items?)"]
    }
  },
  "sources": [
    {
      "name": "chatmon_alert_evidence",
      "type": "external_mcp",
      "tool": "alerts.get_evidence",
      "arguments_template": {
        "alert_id": "{{alert_id}}",
        "limit": "{{limit}}"
      },
      "result_path": "messages",
      "field_map": {
        "message_id": "消息ID",
        "sent_at": "发送时间",
        "uid": "UID",
        "server_id": "区服ID",
        "channel": "频道",
        "original_text": "原文",
        "translated_text_zh": "中文翻译",
        "is_evidence": "是否证据"
      }
    }
  ],
  "chart": {
    "type": "table",
    "title": "ChatMon 告警证据消息",
    "columns": [
      {"value": "消息ID"},
      {"value": "发送时间"},
      {"value": "UID"},
      {"value": "区服ID"},
      {"value": "频道"},
      {"value": "原文"},
      {"value": "中文翻译"},
      {"value": "是否证据"}
    ]
  },
  "analysis": {
    "answer_contract": ["说明告警 ID", "摘要证据消息中反复出现的问题", "区分原文和中文翻译", "不要输出超出 MCP 返回内容的聊天记录或附件"]
  }
} -->
# SaaS ChatMon MCP 告警证据 Skill

## 适用范围
- 平台公共能力，不绑定具体数据源、租户或业务库表。
- 仅当当前工作空间已绑定 ChatMon 类外部 MCP 且当前用户有工作空间访问权限时可执行。
- 适用于用户拿到 `alerts.search` 的告警 ID 后继续查看证据消息。

## 工具说明
- MCP 工具：`alerts.get_evidence`
- 必填参数：`alert_id`。
- 默认返回 10 条证据消息，最多 30 条。
- 返回内容必须受 MCP 服务授权和脱敏边界约束；不要绕过 MCP 去读取未授权原始聊天导出。
""",
    },
]


def _prompt(skill: dict[str, str]) -> str:
    return (skill["prompt"] or "").strip()


def _upsert_skill(cur, *, skill: dict[str, str], now: dt.datetime) -> int:
    prompt = _prompt(skill)
    marker = prompt.splitlines()[0].strip()
    cur.execute(
        """
        SELECT id
        FROM custom_prompt
        WHERE type = 'DATA_SKILL'
          AND visibility_scope = 'PLATFORM_PUBLIC'
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (marker,),
    )
    row = cur.fetchone()
    values = (
        PLATFORM_TENANT_ID,
        skill["name"][:255],
        skill["description"],
        prompt,
        Jsonb([]),
    )
    if row:
        skill_id = int(row[0])
        cur.execute(
            """
            UPDATE custom_prompt
            SET tenant_id = %s,
                name = %s,
                description = %s,
                target_scope = 'ALL',
                active = TRUE,
                visible = TRUE,
                ai_model_id = NULL,
                visibility_scope = 'PLATFORM_PUBLIC',
                create_by = NULL,
                prompt = %s,
                specific_ds = FALSE,
                datasource_ids = %s,
                embedding = NULL,
                embedding_signature = NULL
            WHERE id = %s
            """,
            (*values, skill_id),
        )
        return skill_id

    cur.execute(
        """
        INSERT INTO custom_prompt (
            tenant_id,
            type,
            create_time,
            name,
            description,
            target_scope,
            active,
            visible,
            ai_model_id,
            create_by,
            visibility_scope,
            prompt,
            specific_ds,
            datasource_ids,
            embedding,
            embedding_signature
        )
        VALUES (%s, 'DATA_SKILL', %s, %s, %s, 'ALL', TRUE, TRUE, NULL, NULL, 'PLATFORM_PUBLIC', %s, FALSE, %s, NULL, NULL)
        RETURNING id
        """,
        (PLATFORM_TENANT_ID, now, skill["name"][:255], skill["description"], prompt, Jsonb([])),
    )
    return int(cur.fetchone()[0])


def _save_embeddings(ids: list[int]) -> int:
    if not ids:
        return 0
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy.orm import scoped_session, sessionmaker

    from apps.chat.curd.custom_prompt_embedding import save_custom_prompt_skill_embedding
    from common.core.db import engine

    session_maker = scoped_session(sessionmaker(bind=engine))
    return save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=PLATFORM_TENANT_ID)


def main() -> None:
    now = dt.datetime.now()
    ids: list[int] = []
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            for skill in DATA_SKILLS:
                ids.append(_upsert_skill(cur, skill=skill, now=now))
        conn.commit()
    saved = _save_embeddings(ids)
    print(f"Upserted SaaS MCP data skills: {ids}; embeddings saved: {saved}")


if __name__ == "__main__":
    main()
