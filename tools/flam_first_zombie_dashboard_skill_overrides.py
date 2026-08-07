"""将 Flam 推荐看板最新目录差异应用到 Data Skill 种子。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

OVERRIDES_PATH = Path(__file__).with_name(
    "flam_first_zombie_dashboard_skill_overrides.json"
)
BLOCK_PATTERN = re.compile(
    r"<!-- dashboard-sql:(?P<view_id>[^ ]+?) -->\s*```sql\s*\n"
    r"(?P<sql>[\s\S]*?)\n```"
)


def _load_overrides() -> dict[str, Any]:
    value = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    required = {
        "version",
        "expected_block_count",
        "remove_view_ids",
        "new_view_owners",
        "sql_overrides",
    }
    if not isinstance(value, dict) or set(value) != required or value["version"] != 1:
        raise ValueError("Flam 推荐看板 Skill 覆盖清单结构无效")
    return value


def _source_marker(prompt: str) -> str:
    for line in prompt.splitlines()[:4]:
        if "data-skill-source:flam:first-zombie:" in line:
            return line.strip()
    raise ValueError("Flam Data Skill 缺少 source marker")


def _sql_block(view_id: str, sql: str) -> str:
    return f"<!-- dashboard-sql:{view_id} -->\n```sql\n{sql.strip()}\n```"


def _view_pattern(view_id: str) -> re.Pattern[str]:
    return re.compile(
        rf"<!-- dashboard-sql:{re.escape(view_id)} -->\s*```sql\s*\n"
        r"(?P<sql>[\s\S]*?)\n```"
    )


def _canonical_sql_overrides() -> dict[str, str]:
    """返回代码目录中已验证的静态 JSON Path 看板 SQL。"""

    # 延迟导入，避免种子模块加载时引入不必要的看板依赖。
    from flam_first_zombie_remaining_dashboard_sql import REMAINING_VIEW_SQL

    return {
        view_id: REMAINING_VIEW_SQL[view_id].sql.strip()
        for view_id in (
            "59a8dfd8d6e341988edfbf1666872aae",
            "344c936b561f44f6bc29cc2663f3f651",
        )
    }


def apply_dashboard_skill_overrides(
    skills: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """返回与当前 Flam 推荐看板目录一致的 Skill 定义。"""

    config = _load_overrides()
    sql_overrides = {
        str(view_id): str(sql)
        for view_id, sql in config["sql_overrides"].items()
    }
    sql_overrides.update(_canonical_sql_overrides())
    result = [dict(skill) for skill in skills]
    prompts = {index: str(skill.get("prompt") or "") for index, skill in enumerate(result)}
    marker_to_index = {
        _source_marker(prompt): index for index, prompt in prompts.items()
    }
    if len(marker_to_index) != len(result):
        raise ValueError("Flam Data Skill source marker 重复")

    remove_ids = {str(view_id) for view_id in config["remove_view_ids"]}
    for index, prompt in prompts.items():
        prompts[index] = BLOCK_PATTERN.sub(
            lambda match: "" if match.group("view_id") in remove_ids else match.group(0),
            prompt,
        ).strip()

    new_owners = {
        str(view_id): str(owner)
        for view_id, owner in config["new_view_owners"].items()
    }
    for view_id, sql in sql_overrides.items():
        view_id = str(view_id)
        pattern = _view_pattern(view_id)
        matches = [
            (index, match)
            for index, prompt in prompts.items()
            for match in pattern.finditer(prompt)
        ]
        replacement = _sql_block(view_id, str(sql))
        if len(matches) == 1:
            index, _match = matches[0]
            prompts[index] = pattern.sub(
                lambda _current, value=replacement: value,
                prompts[index],
                count=1,
            )
            continue
        if matches:
            raise ValueError(f"Flam 推荐看板 SQL 块重复: {view_id}")
        owner = new_owners.get(view_id)
        if owner is None or owner not in marker_to_index:
            raise ValueError(f"Flam 新增推荐看板 SQL 块缺少 owner: {view_id}")
        index = marker_to_index[owner]
        prompts[index] = (
            prompts[index].rstrip()
            + "\n\n## 当前推荐看板补充 SQL\n\n"
            + replacement
        )

    blocks: dict[str, str] = {}
    for index, prompt in prompts.items():
        result[index]["prompt"] = prompt.strip()
        for match in BLOCK_PATTERN.finditer(prompt):
            view_id = match.group("view_id")
            if view_id in blocks:
                raise ValueError(f"Flam 推荐看板 SQL 块重复: {view_id}")
            blocks[view_id] = match.group("sql")
    expected_count = int(config["expected_block_count"])
    if len(blocks) != expected_count:
        raise ValueError(
            f"Flam 推荐看板 SQL 块必须为 {expected_count} 个，实际 {len(blocks)}"
        )
    if remove_ids.intersection(blocks):
        raise ValueError("Flam 已下线推荐看板 SQL 块仍然存在")
    for view_id, sql in sql_overrides.items():
        if blocks.get(str(view_id)) != str(sql).strip():
            raise ValueError(f"Flam 推荐看板 SQL 覆盖失败: {view_id}")
    return result
