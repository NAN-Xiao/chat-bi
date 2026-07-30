"""显式、可审计的看板日期筛选 V2 迁移服务。"""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import update
from sqlmodel import Session, select

from apps.dashboard.crud.dashboard_date_filter import resolve_dashboard_date_expression, validate_dashboard_date_parameter_sql
from apps.dashboard.models.dashboard_date_filter_migration_model import CoreDashboardDateFilterMigrationAudit
from apps.dashboard.models.dashboard_model import CoreDashboard


Classification = Literal["automatic", "approved_repair", "manual_review"]
_PARAMETER_TYPES = {"date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"}


class MigrationError(RuntimeError):
    """迁移前置条件不满足。"""


class CompareAndSwapConflict(MigrationError):
    """看板画布在扫描和写入之间发生变化。"""


class RollbackConflict(MigrationError):
    """当前画布已不再是该批次写入的内容。"""


@dataclass(frozen=True)
class TargetConfig:
    parameter_type: str
    expression: dict[str, Any]


@dataclass(frozen=True)
class Manifest:
    tenant_id: int
    dashboard_id: str
    charts: dict[str, TargetConfig]


@dataclass(frozen=True)
class ScanReport:
    tenant_id: int
    dashboard_id: str
    original_canvas: str
    original_sha256: str
    classifications: dict[str, Classification]
    target_configs: dict[str, TargetConfig]


@dataclass(frozen=True)
class ApplyResult:
    batch_id: str
    dashboard_id: str
    applied: bool
    idempotent: bool
    original_sha256: str
    migrated_sha256: str
    classifications: dict[str, Classification]


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=False, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[4] / "tools" / "dashboard_date_filter_v2_manifests" / "2026-07-29-workspace-7482727237662281728.json"


def load_manifest(path: Path) -> Manifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        charts_raw = raw["charts"]
        charts = {
            str(chart_id): TargetConfig(
                parameter_type=str(config["parameter_type"]),
                expression=copy.deepcopy(config["expression"]),
            )
            for chart_id, config in charts_raw.items()
        }
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"迁移清单无效：{path}") from exc
    manifest = Manifest(tenant_id=int(raw["tenant_id"]), dashboard_id=str(raw["dashboard_id"]), charts=charts)
    for chart_id, config in manifest.charts.items():
        if not chart_id or config.parameter_type not in _PARAMETER_TYPES or not _valid_expression(config.expression):
            raise MigrationError(f"迁移清单图表配置无效：{chart_id}")
    return manifest


def _valid_expression(expression: Any) -> bool:
    try:
        resolve_dashboard_date_expression(expression, today=date(2026, 1, 1))
    except (TypeError, ValueError):
        return False
    return True


def _load_dashboard(session: Session, *, tenant_id: int, dashboard_id: str) -> CoreDashboard:
    dashboard = session.exec(
        select(CoreDashboard).where(
            CoreDashboard.id == dashboard_id,
            CoreDashboard.tenant_id == tenant_id,
            CoreDashboard.delete_flag == 0,
        )
    ).first()
    if dashboard is None or not isinstance(dashboard.canvas_view_info, str):
        raise MigrationError("未找到目标看板，或看板不在指定租户边界内")
    return dashboard


def _parse_canvas(raw: str) -> dict[str, Any]:
    try:
        canvas = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MigrationError("canvas_view_info 不是合法 JSON 对象") from exc
    if not isinstance(canvas, dict):
        raise MigrationError("canvas_view_info 必须是 JSON 对象")
    return canvas


def _legacy_config(view: dict[str, Any]) -> TargetConfig | None:
    pivot = view.get("pivot")
    if not isinstance(pivot, dict):
        return None
    parameter_type = pivot.get("date_parameter_type")
    expression = pivot.get("date_expression")
    if parameter_type not in _PARAMETER_TYPES or not _valid_expression(expression):
        return None
    if validate_dashboard_date_parameter_sql(str(view.get("sql") or ""), parameter_type):
        return None
    return TargetConfig(parameter_type=parameter_type, expression=copy.deepcopy(expression))


def _v2_config(view: dict[str, Any]) -> TargetConfig | None:
    if view.get("configVersion") != 2:
        return None
    config = view.get("dateFilter")
    if config is None:
        config = view.get("date_filter")
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return None
    parameter_type = config.get("parameterType")
    expression = config.get("expression")
    if parameter_type not in _PARAMETER_TYPES or not _valid_expression(expression):
        return None
    if validate_dashboard_date_parameter_sql(str(view.get("sql") or ""), parameter_type):
        return None
    return TargetConfig(parameter_type=parameter_type, expression=copy.deepcopy(expression))


def _same_config(left: TargetConfig, right: TargetConfig) -> bool:
    return left.parameter_type == right.parameter_type and left.expression == right.expression


def _in_scope(view: Any, chart_id: str, manifest: Manifest) -> bool:
    if chart_id in manifest.charts or not isinstance(view, dict):
        return chart_id in manifest.charts
    pivot = view.get("pivot")
    return "dateFilter" in view or "date_filter" in view or (
        isinstance(pivot, dict)
        and ("date_parameter_type" in pivot or "date_expression" in pivot)
    )


def scan_dashboard(session: Session, *, tenant_id: int, dashboard_id: str, manifest: Manifest) -> ScanReport:
    if manifest.tenant_id != tenant_id or manifest.dashboard_id != dashboard_id:
        raise MigrationError("迁移清单与请求租户或看板不精确匹配")
    dashboard = _load_dashboard(session, tenant_id=tenant_id, dashboard_id=dashboard_id)
    raw = dashboard.canvas_view_info
    canvas = _parse_canvas(raw)
    classifications: dict[str, Classification] = {}
    target_configs: dict[str, TargetConfig] = {}
    for chart_id, view in canvas.items():
        chart_id = str(chart_id)
        if not _in_scope(view, chart_id, manifest):
            continue
        if not isinstance(view, dict):
            classifications[chart_id] = "manual_review"
            continue
        expected = manifest.charts.get(chart_id)
        current = _v2_config(view) or _legacy_config(view)
        if current is None:
            if (
                expected is not None
                and _valid_expression(expected.expression)
                and validate_dashboard_date_parameter_sql(
                    str(view.get("sql") or ""), expected.parameter_type
                ) is None
            ):
                classifications[chart_id] = "approved_repair"
                target_configs[chart_id] = expected
                continue
            classifications[chart_id] = "manual_review"
            continue
        if expected is not None:
            if not _same_config(current, expected):
                classifications[chart_id] = "manual_review"
                continue
            classifications[chart_id] = "approved_repair"
            target_configs[chart_id] = expected
        else:
            classifications[chart_id] = "automatic"
            target_configs[chart_id] = current
    for chart_id in manifest.charts:
        if chart_id not in canvas:
            classifications[chart_id] = "manual_review"
    return ScanReport(
        tenant_id=tenant_id,
        dashboard_id=dashboard_id,
        original_canvas=raw,
        original_sha256=_sha256(raw),
        classifications=classifications,
        target_configs=target_configs,
    )


def _migrated_canvas(raw: str, target_configs: dict[str, TargetConfig]) -> str:
    canvas = _parse_canvas(raw)
    changed = False
    for chart_id, target in target_configs.items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise MigrationError(f"目标图表配置无效：{chart_id}")
        expected = {
            "enabled": True,
            "parameterType": target.parameter_type,
            "expression": copy.deepcopy(target.expression),
        }
        pivot = view.get("pivot")
        if not isinstance(pivot, dict):
            pivot = {}
            view["pivot"] = pivot
        if view.get("configVersion") != 2:
            view["configVersion"] = 2
            changed = True
        if view.get("dateFilter") != expected:
            view["dateFilter"] = expected
            changed = True
        if "date_filter" in view:
            del view["date_filter"]
            changed = True
        for legacy_key in ("date_parameter_type", "date_expression"):
            if legacy_key in pivot:
                del pivot[legacy_key]
                changed = True
    return _compact_json(canvas) if changed else raw


def _verify_migrated_canvas(raw: str, targets: dict[str, TargetConfig]) -> dict[str, Any]:
    canvas = _parse_canvas(raw)
    verified: dict[str, Any] = {}
    for chart_id, target in targets.items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict) or not _same_config(_v2_config(view) or TargetConfig("", {}), target):
            raise MigrationError(f"写后验证失败：图表 {chart_id} 的 V2 配置不匹配")
        verified[chart_id] = {"parameter_type": target.parameter_type, "expression": target.expression}
    return verified


def _update_canvas_cas(session: Session, *, tenant_id: int, dashboard_id: str, original_canvas: str, migrated_canvas: str) -> int:
    result = session.exec(
        update(CoreDashboard)
        .where(
            CoreDashboard.id == dashboard_id,
            CoreDashboard.tenant_id == tenant_id,
            CoreDashboard.canvas_view_info == original_canvas,
            CoreDashboard.delete_flag == 0,
        )
        .values(canvas_view_info=migrated_canvas, update_time=int(time.time() * 1000))
    )
    return int(result.rowcount or 0)


def get_audit(session: Session, *, batch_id: str, dashboard_id: str) -> CoreDashboardDateFilterMigrationAudit | None:
    return session.exec(
        select(CoreDashboardDateFilterMigrationAudit).where(
            CoreDashboardDateFilterMigrationAudit.batch_id == batch_id,
            CoreDashboardDateFilterMigrationAudit.dashboard_id == dashboard_id,
        )
    ).first()


def apply_dashboard(session: Session, *, tenant_id: int, dashboard_id: str, manifest: Manifest, batch_id: str) -> ApplyResult:
    report = scan_dashboard(session, tenant_id=tenant_id, dashboard_id=dashboard_id, manifest=manifest)
    if any(value == "manual_review" for value in report.classifications.values()):
        raise MigrationError("存在 manual_review 图表，拒绝自动写入")
    migrated_canvas = _migrated_canvas(report.original_canvas, report.target_configs)
    migrated_sha256 = _sha256(migrated_canvas)
    existing = get_audit(session, batch_id=batch_id, dashboard_id=dashboard_id)
    if report.original_sha256 == migrated_sha256:
        return ApplyResult(batch_id, dashboard_id, False, True, report.original_sha256, migrated_sha256, report.classifications)
    if existing is not None:
        if existing.migrated_canvas_sha256 == migrated_sha256:
            return ApplyResult(batch_id, dashboard_id, False, True, report.original_sha256, migrated_sha256, report.classifications)
        raise MigrationError("同一批次已记录不同的迁移结果")
    if _update_canvas_cas(
        session,
        tenant_id=tenant_id,
        dashboard_id=dashboard_id,
        original_canvas=report.original_canvas,
        migrated_canvas=migrated_canvas,
    ) != 1:
        session.rollback()
        raise CompareAndSwapConflict("CAS 冲突：看板画布已发生变化，未写入")
    verification = _verify_migrated_canvas(migrated_canvas, report.target_configs)
    session.add(
        CoreDashboardDateFilterMigrationAudit(
            id=uuid.uuid4().hex,
            batch_id=batch_id,
            tenant_id=tenant_id,
            dashboard_id=dashboard_id,
            chart_ids=_compact_json(sorted(report.target_configs)),
            classification_json=_compact_json(report.classifications),
            original_canvas=report.original_canvas,
            original_canvas_sha256=report.original_sha256,
            migrated_canvas=migrated_canvas,
            migrated_canvas_sha256=migrated_sha256,
            verification_json=_compact_json(verification),
            created_time=int(time.time() * 1000),
        )
    )
    session.commit()
    readback = _load_dashboard(session, tenant_id=tenant_id, dashboard_id=dashboard_id).canvas_view_info
    if _sha256(readback) != migrated_sha256:
        raise MigrationError("写后验证失败：看板画布哈希不匹配")
    _verify_migrated_canvas(readback, report.target_configs)
    return ApplyResult(batch_id, dashboard_id, True, False, report.original_sha256, migrated_sha256, report.classifications)


def rollback_dashboard(session: Session, *, batch_id: str, dashboard_id: str) -> ApplyResult:
    audit = get_audit(session, batch_id=batch_id, dashboard_id=dashboard_id)
    if audit is None:
        raise MigrationError("未找到指定批次和看板的迁移审计记录")
    dashboard = _load_dashboard(session, tenant_id=audit.tenant_id, dashboard_id=dashboard_id)
    current = dashboard.canvas_view_info
    if _sha256(current) != audit.migrated_canvas_sha256:
        raise RollbackConflict("回滚 CAS 冲突：当前画布不是该批次迁移结果")
    if _update_canvas_cas(
        session,
        tenant_id=audit.tenant_id,
        dashboard_id=dashboard_id,
        original_canvas=current,
        migrated_canvas=audit.original_canvas,
    ) != 1:
        session.rollback()
        raise RollbackConflict("回滚 CAS 冲突：看板画布已发生变化，未写入")
    audit.status = "rolled_back"
    audit.rolled_back_time = int(time.time() * 1000)
    session.add(audit)
    session.commit()
    readback = _load_dashboard(session, tenant_id=audit.tenant_id, dashboard_id=dashboard_id).canvas_view_info
    if _sha256(readback) != audit.original_canvas_sha256:
        raise MigrationError("回滚读回验证失败：画布哈希不匹配")
    return ApplyResult(batch_id, dashboard_id, True, False, audit.migrated_canvas_sha256, audit.original_canvas_sha256, json.loads(audit.classification_json))


def count_v1(session: Session, *, tenant_id: int, dashboard_id: str, manifest: Manifest) -> int:
    report = scan_dashboard(session, tenant_id=tenant_id, dashboard_id=dashboard_id, manifest=manifest)
    canvas = _parse_canvas(report.original_canvas)
    return sum(
        1
        for chart_id in report.target_configs
        if _v2_config(canvas.get(chart_id, {})) is None
        and _legacy_config(canvas.get(chart_id, {})) is not None
    )
