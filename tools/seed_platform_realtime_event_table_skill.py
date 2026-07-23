"""发布平台通用的实时事件表与历史事件表选表 Data Skill。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


SKILL_MARKER = (
    "<!-- data-skill-source:platform:realtime-event-table-selection -->"
)
PLATFORM_TENANT_ID = 1
VISIBILITY_SCOPE = "PLATFORM_PUBLIC"
SPECIFIC_DS = False

SKILL = {
    "name": "平台通用 Data Skill：当天实时事件与完整历史事件选表",
    "description": (
        "当当前授权数据源同时存在 event_realtime 与 event 时，"
        "区分今天、当天、截至目前、实时、按分钟或按小时查询与完整历史查询。"
    ),
    "prompt": f"""{SKILL_MARKER}
# 平台通用 Data Skill：当天实时事件与完整历史事件选表

## 适用前提

- 仅当当前会话已明确选择一个已授权数据源，且当前实时 Schema 或工作空间元数据确认同时存在 `event_realtime` 和 `event` 时生效。
- 工作空间 Data Skill、事件字典或字段元数据必须已经提供问题所需的事件语义、主体键和指标字段。本 Skill 只决定选表，不定义业务口径。
- 当前数据源权限、实时 Schema 和工作空间配置优先级高于本 Skill；本 Skill 不得扩大任何数据访问范围。

## 选表规则

- 未完成当日：问题包含“今天”“当天”“今日”“截至目前”“当前”“实时”，或要求今天按分钟、按小时统计时，必须查询 `event_realtime`，并直接限制当前业务日分区。
- 完整历史日：问题指定“昨天”“截至昨天”、某个已经结束的日期、完整自然日，或只分析完整历史分区时，查询 `event`。
- 多日趋势：不包含今天的多日趋势查询使用 `event`。
- 包含今天的跨日窗口：已完成历史日期读取 `event`，今天读取 `event_realtime`。只有工作空间口径确认两表字段语义一致且允许合并时，才可使用 `UNION ALL`，并在外层统一聚合，避免重复计算。
- 用户明确指定表名时，仍须验证当前数据源权限、实时 Schema 和工作空间配置。

## 禁止静默回退

- 当 `event_realtime` 不存在、无权限、缺少所需字段或工作空间未配置业务口径时，不得静默改查 `event`、第一张事件表或相似表名。
- 必须明确说明缺少的 Schema、权限或工作空间语义配置，并要求用户切换数据源、申请权限或补充配置。
- 不得根据其他数据源、历史问答或相似字段名推断当前数据源的事件名、主体键、金额字段或产品过滤条件。
""",
}


@dataclass(frozen=True)
class TargetSnapshot:
    skill_id: int | None
    row: Mapping[str, Any] | None


@dataclass(frozen=True)
class AppliedState:
    skill_id: int
    created: bool


@dataclass(frozen=True)
class PublishReport:
    mode: str
    skill_id: int | None
    updated: bool
    embedding_verified: bool
    backup_path: str | None = None


class PublishBackend(Protocol):
    def acquire_lock(self) -> None: ...

    def release_lock(self) -> None: ...

    def inspect(self, marker: str) -> TargetSnapshot: ...

    def backup(self, snapshot: TargetSnapshot) -> Any: ...

    def upsert(
        self,
        skill: Mapping[str, str],
        snapshot: TargetSnapshot,
    ) -> AppliedState: ...

    def refresh_embedding(self, skill_id: int) -> None: ...

    def verify(
        self,
        skill: Mapping[str, str],
        state: AppliedState,
    ) -> None: ...

    def restore(self, backup: Any, state: AppliedState) -> None: ...


def publish_skill(backend: PublishBackend, *, apply: bool) -> PublishReport:
    """只读预检或发布唯一目标 Skill，并在发布失败时恢复目标记录。"""

    if not apply:
        snapshot = backend.inspect(SKILL_MARKER)
        return PublishReport(
            mode="dry-run",
            skill_id=snapshot.skill_id,
            updated=False,
            embedding_verified=False,
        )

    state: AppliedState | None = None
    backup: Any = None
    backend.acquire_lock()
    try:
        snapshot = backend.inspect(SKILL_MARKER)
        backup = backend.backup(snapshot)
        state = backend.upsert(SKILL, snapshot)
        backend.refresh_embedding(state.skill_id)
        backend.verify(SKILL, state)
        return PublishReport(
            mode="apply",
            skill_id=state.skill_id,
            updated=True,
            embedding_verified=True,
            backup_path=str(backup) if backup is not None else None,
        )
    except BaseException:
        if state is not None:
            backend.restore(backup, state)
        raise
    finally:
        backend.release_lock()
