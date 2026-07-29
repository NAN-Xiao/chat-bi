"""看板日期筛选 V2 显式迁移工具；默认 scan，不会写入数据库。"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlmodel import Session

from apps.dashboard.crud import dashboard_date_filter_migration as migration
from common.core.db import engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("scan", "apply", "rollback", "count-v1"), default="scan")
    parser.add_argument("--manifest", type=Path, default=migration.default_manifest_path())
    parser.add_argument("--batch-id", default="")
    return parser.parse_args()


def _report_dict(report: migration.ScanReport) -> dict:
    migrated_canvas = migration._migrated_canvas(report.original_canvas, report.target_configs)
    return {
        "tenant_id": report.tenant_id,
        "dashboard_id": report.dashboard_id,
        "original_canvas_sha256": report.original_sha256,
        "classifications": report.classifications,
        "write_required": migrated_canvas != report.original_canvas,
    }


def main() -> None:
    args = parse_args()
    manifest = migration.load_manifest(args.manifest)
    with Session(engine) as session:
        if args.command == "scan":
            result = _report_dict(migration.scan_dashboard(session, tenant_id=manifest.tenant_id, dashboard_id=manifest.dashboard_id, manifest=manifest))
        elif args.command == "count-v1":
            result = {"count_v1": migration.count_v1(session, tenant_id=manifest.tenant_id, dashboard_id=manifest.dashboard_id, manifest=manifest)}
        elif args.command == "apply":
            batch_id = args.batch_id or f"dashboard-date-filter-v2-{uuid.uuid4().hex}"
            result = migration.apply_dashboard(session, tenant_id=manifest.tenant_id, dashboard_id=manifest.dashboard_id, manifest=manifest, batch_id=batch_id).__dict__
        else:
            if not args.batch_id:
                raise SystemExit("rollback 必须提供 --batch-id")
            result = migration.rollback_dashboard(session, batch_id=args.batch_id, dashboard_id=manifest.dashboard_id).__dict__
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
