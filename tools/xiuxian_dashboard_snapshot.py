"""修仙推荐看板 SQL 的完整、可验签只读备份。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from seed_xiuxian_data_skills import DATASOURCE_ID, TENANT_ID
from xiuxian_dashboard_skill_catalog import EMPTY_VIEW_ID, EXPECTED_VIEW_IDS


EXPECTED_DASHBOARD_COUNT = 9
EXPECTED_DRAWER_COUNT = 45
EXPECTED_NONEMPTY_DRAWER_COUNT = 44
BACKUP_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = ROOT / ".codex-runtime" / "xiuxian-dashboard-sql-backups"

RECOMMENDED_DASHBOARD_SQL = """
SELECT d.id, d.name, d.tenant_id, d.datasource, d.canvas_view_info
FROM core_dashboard d
JOIN core_dashboard_tree t
  ON t.dashboard_id = d.id AND t.tenant_id = d.tenant_id
WHERE d.tenant_id = %s
  AND d.datasource = %s
  AND t.scope = 'default'
  AND d.node_type = 'leaf'
  AND COALESCE(d.delete_flag, 0) = 0
ORDER BY t.sort, d.id
"""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


@dataclass(frozen=True)
class DrawerSnapshot:
    """单个看板抽屉的原始 SQL 及其摘要。"""

    dashboard_id: str
    dashboard_name: str
    view_id: str
    sql: str
    sql_sha256: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DrawerSnapshot":
        sql = value.get("sql")
        if not isinstance(sql, str):
            raise ValueError("抽屉 SQL 必须是字符串")
        return cls(
            dashboard_id=str(value["dashboard_id"]),
            dashboard_name=str(value["dashboard_name"]),
            view_id=str(value["view_id"]),
            sql=sql,
            sql_sha256=str(value["sql_sha256"]),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "dashboard_id": self.dashboard_id,
            "dashboard_name": self.dashboard_name,
            "view_id": self.view_id,
            "sql": self.sql,
            "sql_sha256": self.sql_sha256,
        }


@dataclass(frozen=True)
class DashboardSnapshot:
    """推荐看板及未格式化重写的完整 canvas_view_info。"""

    id: str
    name: str
    tenant_id: int
    datasource: int
    canvas_view_info: str
    drawers: tuple[DrawerSnapshot, ...]

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "DashboardSnapshot":
        dashboard_id, name, tenant_id, datasource, canvas_value = row
        if isinstance(canvas_value, str):
            raw_canvas = canvas_value
            try:
                canvas = json.loads(canvas_value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"看板 {dashboard_id} 的 canvas_view_info 不是有效 JSON") from exc
        elif isinstance(canvas_value, Mapping):
            canvas = dict(canvas_value)
            raw_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
        else:
            raise ValueError(f"看板 {dashboard_id} 的 canvas_view_info 必须是 JSON 对象")
        if not isinstance(canvas, dict):
            raise ValueError(f"看板 {dashboard_id} 的 canvas_view_info 必须是 JSON 对象")

        drawers: list[DrawerSnapshot] = []
        for view_id, view in canvas.items():
            if not isinstance(view, dict):
                raise ValueError(f"看板 {dashboard_id} 的抽屉 {view_id} 必须是 JSON 对象")
            sql_value = view.get("sql")
            sql = "" if sql_value is None else sql_value
            if not isinstance(sql, str):
                raise ValueError(f"看板 {dashboard_id} 的抽屉 {view_id} SQL 必须是字符串")
            drawers.append(
                DrawerSnapshot(
                    dashboard_id=str(dashboard_id),
                    dashboard_name=str(name),
                    view_id=str(view_id),
                    sql=sql,
                    sql_sha256=_sha256_text(sql),
                )
            )
        return cls(
            id=str(dashboard_id),
            name=str(name),
            tenant_id=int(tenant_id),
            datasource=int(datasource),
            canvas_view_info=raw_canvas,
            drawers=tuple(drawers),
        )

    def to_backup_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tenant_id": self.tenant_id,
            "datasource": self.datasource,
            "canvas_view_info": self.canvas_view_info,
        }


@dataclass(frozen=True)
class BackupManifest:
    """备份数量门禁及文件、SQL 摘要清单。"""

    version: int
    tenant_id: int
    datasource_id: int
    dashboard_count: int
    drawer_count: int
    nonempty_drawer_count: int
    file_sha256: dict[str, str]
    sql_sha256: dict[str, str]
    manifest_payload_sha256: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BackupManifest":
        try:
            file_sha256 = value["file_sha256"]
            sql_sha256 = value["sql_sha256"]
            if not isinstance(file_sha256, dict) or not isinstance(sql_sha256, dict):
                raise TypeError
            return cls(
                version=int(value["version"]),
                tenant_id=int(value["tenant_id"]),
                datasource_id=int(value["datasource_id"]),
                dashboard_count=int(value["dashboard_count"]),
                drawer_count=int(value["drawer_count"]),
                nonempty_drawer_count=int(value["nonempty_drawer_count"]),
                file_sha256={str(key): str(item) for key, item in file_sha256.items()},
                sql_sha256={str(key): str(item) for key, item in sql_sha256.items()},
                manifest_payload_sha256=str(value["manifest_payload_sha256"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("manifest.json 结构无效") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tenant_id": self.tenant_id,
            "datasource_id": self.datasource_id,
            "dashboard_count": self.dashboard_count,
            "drawer_count": self.drawer_count,
            "nonempty_drawer_count": self.nonempty_drawer_count,
            "file_sha256": self.file_sha256,
            "sql_sha256": self.sql_sha256,
            "manifest_payload_sha256": self.manifest_payload_sha256,
        }


def load_recommended_dashboards(connection: Any) -> list[DashboardSnapshot]:
    """仅查询目标租户、数据源下的推荐看板。"""

    with connection.cursor() as cur:
        cur.execute(RECOMMENDED_DASHBOARD_SQL, (TENANT_ID, DATASOURCE_ID))
        return [DashboardSnapshot.from_row(row) for row in cur.fetchall()]


def _drawer_rows(dashboards: Sequence[DashboardSnapshot]) -> list[dict[str, str]]:
    return [drawer.to_dict() for dashboard in dashboards for drawer in dashboard.drawers]


def _drawer_key(drawer: DrawerSnapshot) -> str:
    return f"{drawer.dashboard_id}:{drawer.view_id}"


def _validate_dashboards(dashboards: Sequence[DashboardSnapshot]) -> None:
    if len(dashboards) != EXPECTED_DASHBOARD_COUNT:
        raise ValueError(
            f"看板数量必须为 {EXPECTED_DASHBOARD_COUNT}，实际为 {len(dashboards)}"
        )
    if len({dashboard.id for dashboard in dashboards}) != EXPECTED_DASHBOARD_COUNT:
        raise ValueError("看板 ID 必须唯一")
    if any(
        dashboard.tenant_id != TENANT_ID or dashboard.datasource != DATASOURCE_ID
        for dashboard in dashboards
    ):
        raise ValueError("看板租户或数据源与修仙备份范围不一致")

    drawers = [drawer for dashboard in dashboards for drawer in dashboard.drawers]
    if len(drawers) != EXPECTED_DRAWER_COUNT:
        raise ValueError(f"抽屉数量必须为 {EXPECTED_DRAWER_COUNT}，实际为 {len(drawers)}")
    if len({_drawer_key(drawer) for drawer in drawers}) != EXPECTED_DRAWER_COUNT:
        raise ValueError("抽屉的看板 ID 与 view id 组合必须唯一")

    nonempty = [drawer for drawer in drawers if drawer.sql.strip()]
    if len(nonempty) != EXPECTED_NONEMPTY_DRAWER_COUNT:
        raise ValueError(
            "非空 SQL 数量必须为 "
            f"{EXPECTED_NONEMPTY_DRAWER_COUNT}，实际为 {len(nonempty)}"
        )
    nonempty_view_ids = {drawer.view_id for drawer in nonempty}
    all_view_ids = {drawer.view_id for drawer in drawers}
    if nonempty_view_ids != set(EXPECTED_VIEW_IDS):
        raise ValueError("44 个非空 SQL 的 view id 与 Task 1 目录不一致")
    if all_view_ids != set(EXPECTED_VIEW_IDS) | {EMPTY_VIEW_ID}:
        raise ValueError("45 个抽屉的 view id 与 Task 1 目录不一致")

    for dashboard in dashboards:
        parsed = DashboardSnapshot.from_row(
            (
                dashboard.id,
                dashboard.name,
                dashboard.tenant_id,
                dashboard.datasource,
                dashboard.canvas_view_info,
            )
        )
        if parsed.drawers != dashboard.drawers:
            raise ValueError(f"看板 {dashboard.id} 的完整 canvas 与抽屉清单不一致")
    for drawer in drawers:
        if drawer.sql_sha256 != _sha256_text(drawer.sql):
            raise ValueError(f"抽屉 {_drawer_key(drawer)} 的 SQL 哈希不一致")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _manifest_payload_sha256(manifest: BackupManifest) -> str:
    payload = manifest.to_dict()
    payload.pop("manifest_payload_sha256")
    normalized = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return _sha256_bytes(normalized)


def _write_json(path: Path, value: Any) -> None:
    payload = _json_bytes(value)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取有效 JSON：{path}") from exc


def _build_manifest(target: Path, dashboards: Sequence[DashboardSnapshot]) -> BackupManifest:
    data_files = [target / "drawer_sql.json"] + [
        target / "dashboards" / f"{dashboard.id}.json" for dashboard in dashboards
    ]
    file_sha256 = {
        path.relative_to(target).as_posix(): _sha256_bytes(path.read_bytes())
        for path in data_files
    }
    drawers = [drawer for dashboard in dashboards for drawer in dashboard.drawers]
    manifest = BackupManifest(
        version=BACKUP_VERSION,
        tenant_id=TENANT_ID,
        datasource_id=DATASOURCE_ID,
        dashboard_count=len(dashboards),
        drawer_count=len(drawers),
        nonempty_drawer_count=sum(bool(drawer.sql.strip()) for drawer in drawers),
        file_sha256=file_sha256,
        sql_sha256={_drawer_key(drawer): drawer.sql_sha256 for drawer in drawers},
        manifest_payload_sha256="",
    )
    return replace(
        manifest, manifest_payload_sha256=_manifest_payload_sha256(manifest)
    )


def write_verified_backup(
    dashboards: Sequence[DashboardSnapshot], backup_root: Path, timestamp: str
) -> Path:
    """写入新目录，并通过重新读取校验后返回备份路径。"""

    dashboards = tuple(dashboards)
    _validate_dashboards(dashboards)
    backup_root = Path(backup_root)
    target = backup_root / timestamp
    if target.exists():
        raise FileExistsError(target)
    backup_root.mkdir(parents=True, exist_ok=True)
    staging = backup_root / f".{timestamp}.{uuid4().hex}.staging"
    staging.mkdir(exist_ok=False)
    try:
        dashboards_dir = staging / "dashboards"
        dashboards_dir.mkdir()
        for dashboard in dashboards:
            _write_json(
                dashboards_dir / f"{dashboard.id}.json", dashboard.to_backup_dict()
            )
        _write_json(staging / "drawer_sql.json", _drawer_rows(dashboards))
        _write_json(
            staging / "manifest.json", _build_manifest(staging, dashboards).to_dict()
        )
        verify_backup(staging)
        if target.exists():
            raise FileExistsError(target)
        staging.replace(target)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return target


def verify_backup(path: Path) -> BackupManifest:
    """重新读取所有文件并严格校验数量、文件哈希与原 SQL 哈希。"""

    path = Path(path)
    manifest_path = path / "manifest.json"
    manifest_value = _read_json(manifest_path)
    if not isinstance(manifest_value, dict):
        raise ValueError("manifest.json 结构无效")
    manifest = BackupManifest.from_dict(manifest_value)
    if manifest_path.read_bytes() != _json_bytes(manifest.to_dict()):
        raise ValueError("manifest.json 不是规范化的完整文件")
    if manifest.manifest_payload_sha256 != _manifest_payload_sha256(manifest):
        raise ValueError("manifest payload 哈希不一致")
    if (
        manifest.version != BACKUP_VERSION
        or manifest.tenant_id != TENANT_ID
        or manifest.datasource_id != DATASOURCE_ID
    ):
        raise ValueError("manifest 版本、租户或数据源不匹配")

    actual_files = {
        item.relative_to(path).as_posix()
        for item in path.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    }
    if actual_files != set(manifest.file_sha256):
        raise ValueError("备份文件清单与 manifest 不一致")
    for relative_path, expected_hash in manifest.file_sha256.items():
        actual_hash = _sha256_bytes((path / relative_path).read_bytes())
        if actual_hash != expected_hash:
            raise ValueError(f"文件哈希不一致：{relative_path}")

    dashboard_paths = sorted((path / "dashboards").glob("*.json"))
    dashboards: list[DashboardSnapshot] = []
    for dashboard_path in dashboard_paths:
        value = _read_json(dashboard_path)
        if not isinstance(value, dict):
            raise ValueError(f"看板备份结构无效：{dashboard_path.name}")
        try:
            dashboard = DashboardSnapshot.from_row(
                (
                    value["id"],
                    value["name"],
                    value["tenant_id"],
                    value["datasource"],
                    value["canvas_view_info"],
                )
            )
        except KeyError as exc:
            raise ValueError(f"看板备份缺少字段：{dashboard_path.name}") from exc
        if dashboard_path.stem != dashboard.id:
            raise ValueError(f"看板文件名与 ID 不一致：{dashboard_path.name}")
        dashboards.append(dashboard)
    _validate_dashboards(dashboards)

    drawer_values = _read_json(path / "drawer_sql.json")
    if not isinstance(drawer_values, list):
        raise ValueError("drawer_sql.json 必须是数组")
    drawers = [DrawerSnapshot.from_dict(value) for value in drawer_values]
    expected_drawers = [drawer for dashboard in dashboards for drawer in dashboard.drawers]
    if sorted(drawers, key=_drawer_key) != sorted(expected_drawers, key=_drawer_key):
        raise ValueError("drawer_sql.json 与完整 canvas 中的原 SQL 不一致")

    actual_sql_hashes: dict[str, str] = {}
    for drawer in drawers:
        actual_hash = _sha256_text(drawer.sql)
        if drawer.sql_sha256 != actual_hash:
            raise ValueError(f"抽屉 {_drawer_key(drawer)} 的 SQL 哈希不一致")
        actual_sql_hashes[_drawer_key(drawer)] = actual_hash
    if actual_sql_hashes != manifest.sql_sha256:
        raise ValueError("SQL 哈希清单与 manifest 不一致")

    expected_counts = (
        EXPECTED_DASHBOARD_COUNT,
        EXPECTED_DRAWER_COUNT,
        EXPECTED_NONEMPTY_DRAWER_COUNT,
    )
    manifest_counts = (
        manifest.dashboard_count,
        manifest.drawer_count,
        manifest.nonempty_drawer_count,
    )
    if manifest_counts != expected_counts:
        raise ValueError("manifest 的 9/45/44 数量门禁不匹配")
    return manifest


def _print_result(path: Path, manifest: BackupManifest) -> None:
    print(path.resolve())
    print(
        f"dashboards={manifest.dashboard_count} drawers={manifest.drawer_count} "
        f"nonempty={manifest.nonempty_drawer_count} verified=true"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup", help="从系统库只读生成备份")
    backup_parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    backup_parser.add_argument("--timestamp")
    verify_parser = subparsers.add_parser("verify", help="重新校验已有备份")
    verify_parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    if args.command == "verify":
        manifest = verify_backup(args.path)
        _print_result(args.path, manifest)
        return 0

    # 现场执行时显式启用只读事务，模块导入和 verify 均不会连接数据库。
    import psycopg

    from core_system_db import core_system_db_config

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    with psycopg.connect(**core_system_db_config()) as connection:
        connection.read_only = True
        dashboards = load_recommended_dashboards(connection)
    path = write_verified_backup(dashboards, args.backup_root, timestamp)
    _print_result(path, verify_backup(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
