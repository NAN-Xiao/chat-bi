"""修复“我的看板”中误挂推荐看板源 id 的历史数据。

默认仅 dry-run 扫描候选记录；传入 --apply 才会创建独立副本并回写
core_dashboard_tree(scope='my')。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlmodel import Session, select
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import aliased

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from core_system_db import core_system_db_config, export_postgres_compat_env  # noqa: E402

export_postgres_compat_env(core_system_db_config())

from common.core.db import engine  # noqa: E402
from apps.dashboard.crud.dashboard_service import repair_my_tree_default_dashboard_copies  # noqa: E402
from apps.dashboard.models.dashboard_model import CoreDashboard, CoreDashboardTree  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="修复我的看板误挂推荐看板源 id 的历史数据")
    parser.add_argument("--tenant-id", type=int, required=True, help="要修复的工作空间/租户 id")
    parser.add_argument("--user-id", type=int, required=True, help="执行修复的用户 id，需具备对应看板创建权限")
    parser.add_argument("--tenant-role", default="owner", help="执行用户在该工作空间的角色，默认 owner")
    parser.add_argument("--apply", action="store_true", help="实际写库；不传时仅扫描候选记录")
    return parser.parse_args()


def _candidate_rows(session: Session, tenant_id: int):
    default_tree = aliased(CoreDashboardTree)
    default_position_exists = exists().where(
        and_(
            default_tree.tenant_id == tenant_id,
            default_tree.scope == "default",
            default_tree.dashboard_id == CoreDashboard.id,
        )
    )
    return session.exec(
        select(CoreDashboardTree, CoreDashboard)
        .join(CoreDashboard, CoreDashboardTree.dashboard_id == CoreDashboard.id)
        .where(
            and_(
                CoreDashboardTree.tenant_id == tenant_id,
                CoreDashboardTree.scope == "my",
                CoreDashboard.tenant_id == tenant_id,
                CoreDashboard.node_type == "leaf",
                or_(CoreDashboard.delete_flag == 0, CoreDashboard.delete_flag.is_(None)),
                or_(CoreDashboard.is_default == 1, default_position_exists),
            )
        )
        .order_by(CoreDashboardTree.sort.asc(), CoreDashboard.create_time.asc())
    ).all()


def _dump_backup(candidates: list[tuple[Any, Any]], tenant_id: int) -> Path:
    backup_dir = ROOT / ".codex-runtime" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"dashboard_default_copy_repair_{tenant_id}_{int(time.time())}.json"
    payload = [
        {
            "tree": {
                "id": tree_row.id,
                "tenant_id": tree_row.tenant_id,
                "scope": tree_row.scope,
                "dashboard_id": tree_row.dashboard_id,
                "parent_id": tree_row.parent_id,
                "sort": tree_row.sort,
                "create_time": tree_row.create_time,
                "create_by": tree_row.create_by,
                "update_time": tree_row.update_time,
                "update_by": tree_row.update_by,
            },
            "dashboard": {
                "id": dashboard.id,
                "tenant_id": dashboard.tenant_id,
                "name": dashboard.name,
                "pid": dashboard.pid,
                "datasource": dashboard.datasource,
                "external_mcp_server_id": dashboard.external_mcp_server_id,
                "org_id": dashboard.org_id,
                "level": dashboard.level,
                "node_type": dashboard.node_type,
                "type": dashboard.type,
                "canvas_style_data": dashboard.canvas_style_data,
                "component_data": dashboard.component_data,
                "canvas_view_info": dashboard.canvas_view_info,
                "mobile_layout": dashboard.mobile_layout,
                "status": dashboard.status,
                "self_watermark_status": dashboard.self_watermark_status,
                "is_default": dashboard.is_default,
                "sort": dashboard.sort,
                "create_time": dashboard.create_time,
                "create_by": dashboard.create_by,
                "update_time": dashboard.update_time,
                "update_by": dashboard.update_by,
                "remark": dashboard.remark,
                "source": dashboard.source,
                "delete_flag": dashboard.delete_flag,
                "version": dashboard.version,
                "content_id": dashboard.content_id,
                "check_version": dashboard.check_version,
            },
        }
        for tree_row, dashboard in candidates
    ]
    backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return backup_path


def main() -> int:
    args = _parse_args()
    with Session(engine) as session:
        candidates = _candidate_rows(session, args.tenant_id)
        print(f"候选误挂记录数: {len(candidates)}")
        for tree_row, dashboard in candidates:
            print(
                f"- tree_id={tree_row.id} dashboard_id={dashboard.id} "
                f"name={dashboard.name} parent_id={tree_row.parent_id} sort={tree_row.sort}"
            )
        if not args.apply:
            print("dry-run 完成；如需写库，请追加 --apply。")
            return 0

        backup_path = _dump_backup(candidates, args.tenant_id)
        print(f"修复前备份: {backup_path}")
        user = SimpleNamespace(
            id=args.user_id,
            isAdmin=False,
            tenant_id=args.tenant_id,
            tenant_role=args.tenant_role,
        )
        repaired = repair_my_tree_default_dashboard_copies(session, user)
        print(f"已修复记录数: {len(repaired)}")
        for record in repaired:
            print(f"- new_dashboard_id={record.id} name={record.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
