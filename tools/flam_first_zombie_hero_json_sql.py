"""Build static JSON-path SQL fragments for First Zombie hero arrays."""

from __future__ import annotations

HERO_SLOT_COUNT = 10


def hero_slot_select_list(*, source_alias: str = "e", indent: str = "        ") -> str:
    return ",\n".join(
        f"{indent}JSON_UNQUOTE(JSON_EXTRACT("
        f"{source_alias}.personal, '$.ed_myTeamHeroList[{index}].heroId')) AS hero_{index}"
        for index in range(HERO_SLOT_COUNT)
    )


def hero_slot_union(
    *,
    source_name: str,
    dimensions: tuple[str, ...],
    indent: str = "    ",
) -> str:
    dimension_sql = ", ".join(dimensions)
    return "\n    UNION ALL\n".join(
        f"{indent}SELECT {dimension_sql}, hero_{index} AS hero_id\n"
        f"{indent}FROM {source_name}\n"
        f"{indent}WHERE hero_{index} IS NOT NULL AND hero_{index} <> ''"
        for index in range(HERO_SLOT_COUNT)
    )
