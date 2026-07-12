# -*- coding: utf-8 -*-
"""修复 First Zombie 已审计副本看板的语义 SQL。

该脚本只迁移 datasource=3 中已审计的组件。每个目标必须同时匹配
看板 ID、组件 ID、旧标题和旧 SQL 指纹，避免覆盖用户后续编辑的同名图表。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from core_system_db import core_system_db_config
from flam_first_zombie_core_dashboard_sql import CORE_DASHBOARD_VIEW_SQL
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID, VIEW_SQL
from flam_first_zombie_remaining_dashboard_sql import REMAINING_VIEW_SQL
from repair_flam_first_zombie_realtime_dashboard import (
    REALTIME_VIEW_FIELDS,
    build_fixed_realtime_sql,
    load_flam_mysql_config,
)


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"
SYSTEM_DB = core_system_db_config()
UPDATE_BY = "codex"


@dataclass(frozen=True)
class TargetView:
    dashboard_id: str
    view_id: str
    title: str
    legacy_sql_sha256: str
    source_key: str


@dataclass(frozen=True)
class ViewDefinition:
    title: str
    chart_type: str
    fields: tuple[str, ...]
    x_axis: tuple[str, ...]
    y_axis: tuple[str, ...]
    columns: tuple[str, ...]
    sql: str
    series_axis: tuple[str, ...] = ()
    pivot: dict[str, Any] | None = None
    y_axis_semantics: dict[str, dict[str, str]] | None = None


def sql_fingerprint(sql: str) -> str:
    """规范化 SQL 空白后生成迁移保护指纹。"""
    normalized = " ".join((sql or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _definition_from_spec(spec: Any) -> ViewDefinition:
    return ViewDefinition(
        title=spec.title,
        chart_type=spec.chart_type,
        fields=tuple(spec.fields),
        x_axis=tuple(spec.x_axis),
        y_axis=tuple(spec.y_axis),
        columns=tuple(spec.columns),
        sql=spec.sql,
        series_axis=tuple(getattr(spec, "series_axis", ())),
        pivot=getattr(spec, "pivot", None),
        y_axis_semantics=getattr(spec, "y_axis_semantics", None),
    )


def _realtime_definition(view_id: str, sql: str) -> ViewDefinition:
    fields = REALTIME_VIEW_FIELDS[view_id]
    return ViewDefinition(
        title=fields["y_name"],
        chart_type="line",
        fields=(fields["x_value"], fields["y_value"]),
        x_axis=(fields["x_value"],),
        y_axis=(fields["y_value"],),
        columns=(fields["x_value"], fields["y_value"]),
        sql=sql,
    )


def definition_for(source_key: str, realtime_sql: dict[str, str] | None = None) -> ViewDefinition:
    source_type, view_id = source_key.split(":", 1)
    if source_type == "dashboard":
        return _definition_from_spec(VIEW_SQL[view_id])
    if source_type == "core":
        return _definition_from_spec(CORE_DASHBOARD_VIEW_SQL[view_id])
    if source_type == "remaining":
        return _definition_from_spec(REMAINING_VIEW_SQL[view_id])
    if source_type == "realtime":
        if realtime_sql is None or view_id not in realtime_sql:
            raise ValueError(f"缺少实时看板 SQL: {view_id}")
        return _realtime_definition(view_id, realtime_sql[view_id])
    raise ValueError(f"未知 SQL 来源: {source_key}")


def _axis(field: str) -> dict[str, str]:
    return {"name": field, "value": field}


def _clear_result(view: dict[str, Any], fields: tuple[str, ...]) -> None:
    data = view.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        view["data"] = data
    data["fields"] = list(fields)
    data["data"] = []
    data.pop("source_fields", None)
    data.pop("source_data", None)
    data["snapshotRefreshedAt"] = 0
    view["fields"] = list(fields)
    view["status"] = "success"
    view["message"] = ""
    view["dataState"] = "ready"
    view["loadingProgress"] = 100
    view["snapshotRefreshedAt"] = 0


def _apply_definition(view: dict[str, Any], definition: ViewDefinition) -> None:
    chart = view.setdefault("chart", {})
    chart["type"] = definition.chart_type
    chart["title"] = definition.title
    chart["xAxis"] = [_axis(field) for field in definition.x_axis]
    chart["yAxis"] = [_axis(field) for field in definition.y_axis]
    if definition.y_axis_semantics:
        for item in chart["yAxis"]:
            if semantics := definition.y_axis_semantics.get(item["value"]):
                item.update(semantics)
    if definition.series_axis:
        chart["series"] = [_axis(field) for field in definition.series_axis]
    else:
        chart.pop("series", None)
    chart["columns"] = [_axis(field) for field in (definition.columns or definition.fields)]
    if definition.pivot is not None:
        view["pivot"] = definition.pivot
    else:
        view.pop("pivot", None)
    view["datasource"] = DATASOURCE_ID
    view["sql"] = definition.sql.strip()
    _clear_result(view, definition.fields)


def repair_view(
    view: dict[str, Any],
    target: TargetView,
    realtime_sql: dict[str, str] | None = None,
) -> bool:
    """仅在标题和旧 SQL 指纹都匹配时更新一个已审计组件。"""
    chart = view.get("chart") or {}
    if chart.get("title") != target.title:
        return False
    if sql_fingerprint(str(view.get("sql") or "")) != target.legacy_sql_sha256:
        return False
    _apply_definition(view, definition_for(target.source_key, realtime_sql))
    return True


def _target(
    dashboard_id: str,
    view_id: str,
    title: str,
    legacy_sql_sha256: str,
    source_key: str,
) -> TargetView:
    return TargetView(dashboard_id, view_id, title, legacy_sql_sha256, source_key)


# 这些 ID 和指纹来自 datasource=3 的修复前只读审计。不要用标题模糊匹配扩展范围。
TARGET_VIEWS: tuple[TargetView, ...] = (
    _target("4bae835c4243481b9963122b5275ed81", "440303dfdf39408ba86ffb222f3334f2", "竞技场/出征平均战力", "c54f5f773a5dd944b50f90f504ee48d61d3f0eebaed759cb7fb4514027600635", "remaining:440303dfdf39408ba86ffb222f3334f2"),
    _target("4bae835c4243481b9963122b5275ed81", "440303dfdf39408ba86ffb222f3334f2", "竞技场/出征平均战力", "a09d1afa778f1ea1f239b7bcb4de3a7583cc73a79381f17f018439512253ff2b", "remaining:440303dfdf39408ba86ffb222f3334f2"),
    _target("4bae835c4243481b9963122b5275ed81", "61c21b5974844638a3d7370971de58c9", "各主城等级参与演习次数", "4b0ab0d149dbb2a46d75debb78c633968a9232a69aa7c95cb1752444e13cc500", "remaining:61c21b5974844638a3d7370971de58c9"),
    _target("6881ed3756dc44df8a62569f9a040573", "79b4f9c8dfab4368813ff2233d470490", "竞技场/出征平均战力", "c54f5f773a5dd944b50f90f504ee48d61d3f0eebaed759cb7fb4514027600635", "remaining:440303dfdf39408ba86ffb222f3334f2"),
    _target("6881ed3756dc44df8a62569f9a040573", "bbbc8c3ad71f4267b569f3e9f7ada648", "各主城等级参与演习次数", "4b0ab0d149dbb2a46d75debb78c633968a9232a69aa7c95cb1752444e13cc500", "remaining:61c21b5974844638a3d7370971de58c9"),
    _target("259414f219f94aacaa46f4e531646b9d", "f75122a83c84441381fe77a551f69a28", "付费情况", "1420ff56cd3fbd85473dbb2edfb036fc958426db587b43224a7895777d0ee8c4", "dashboard:f75122a83c84441381fe77a551f69a28"),
    _target("259414f219f94aacaa46f4e531646b9d", "bb9fbc7502af455cbea246821e180c72", "近7日累充排名", "59b74adfc87f8090ec2f22bde9dcd438e58d99531830d30d7b994d2c2dea2217", "dashboard:bb9fbc7502af455cbea246821e180c72"),
    _target("259414f219f94aacaa46f4e531646b9d", "20a42bea9bcf4bc5b1bddfff187a874d", "日充值总次数", "a49151544075fc0da8846859f63d57932246d4b9a5886303a07aaf8e78004c2e", "dashboard:20a42bea9bcf4bc5b1bddfff187a874d"),
    _target("259414f219f94aacaa46f4e531646b9d", "01b402cb5b5f4c95bc457cf505a2ecc7", "日充值用户数", "2c4a1db55c0e6164cdc7781e8a4da0fa542a146a0d4d93b879ca979707309151", "dashboard:01b402cb5b5f4c95bc457cf505a2ecc7"),
    _target("259414f219f94aacaa46f4e531646b9d", "fdb8f135e2644bcb80b7634882809f7e", "付费事件分布", "828447a3aa97978dae03c2f69718456a1fe15e1b28fc2855f6dab3b0d7905def", "remaining:fdb8f135e2644bcb80b7634882809f7e"),
    _target("259414f219f94aacaa46f4e531646b9d", "6391d385e5084c0f86351ae088d3c336", "新增用户30日LTV", "4eaf27eb0daeb4bab17c366fd70077edc2146c70d925b0762cf02f4dc1e87349", "dashboard:6391d385e5084c0f86351ae088d3c336"),
    _target("8342496ba7f94c298855feb849666bbf", "648e0a1ddba4469e999c4847e927da58", "付费情况", "1420ff56cd3fbd85473dbb2edfb036fc958426db587b43224a7895777d0ee8c4", "dashboard:f75122a83c84441381fe77a551f69a28"),
    _target("8342496ba7f94c298855feb849666bbf", "b460f216de0f4f7f80534e677d8fdea5", "近7日累充排名", "59b74adfc87f8090ec2f22bde9dcd438e58d99531830d30d7b994d2c2dea2217", "dashboard:bb9fbc7502af455cbea246821e180c72"),
    _target("8342496ba7f94c298855feb849666bbf", "eff38b01f94c43bc8ba3ae7525868ae4", "日充值总次数", "a49151544075fc0da8846859f63d57932246d4b9a5886303a07aaf8e78004c2e", "dashboard:20a42bea9bcf4bc5b1bddfff187a874d"),
    _target("8342496ba7f94c298855feb849666bbf", "5eb3c7801cf94b42af3ce966deb1c035", "日充值用户数", "2c4a1db55c0e6164cdc7781e8a4da0fa542a146a0d4d93b879ca979707309151", "dashboard:01b402cb5b5f4c95bc457cf505a2ecc7"),
    _target("8342496ba7f94c298855feb849666bbf", "4c12af6ec087441a9aa8da7e48b66eec", "付费事件分布", "828447a3aa97978dae03c2f69718456a1fe15e1b28fc2855f6dab3b0d7905def", "remaining:fdb8f135e2644bcb80b7634882809f7e"),
    _target("8342496ba7f94c298855feb849666bbf", "0580ec26ab84452a8c5638eaa1128a44", "新增用户30日LTV", "4eaf27eb0daeb4bab17c366fd70077edc2146c70d925b0762cf02f4dc1e87349", "dashboard:6391d385e5084c0f86351ae088d3c336"),
    _target("6d50bd7dfc9f46ba961d636814c3294d", "6fce0cfb227b47828b41fd3c5cc736d5", "ARPU与ARPPU", "d0c0c718d43fd423da7c9e478c9a45ead0c6c87b679b351efc29a5c3ca3853e7", "core:6fce0cfb227b47828b41fd3c5cc736d5"),
    _target("9a2e6390b3f74f8b876f16de0726121c", "1a9d207abeb84aa7972f4562060d7219", "ARPU与ARPPU", "d0c0c718d43fd423da7c9e478c9a45ead0c6c87b679b351efc29a5c3ca3853e7", "core:6fce0cfb227b47828b41fd3c5cc736d5"),
    _target("dd8b7f58951346d1b2399f056c52559d", "46c00da0841e469dba5036aec7068d34", "ARPU与ARPPU", "d0c0c718d43fd423da7c9e478c9a45ead0c6c87b679b351efc29a5c3ca3853e7", "core:6fce0cfb227b47828b41fd3c5cc736d5"),
    _target("e146aa12aed74c429a1f558f7bd672cf", "41d7bb63038547bbae66aba3dc6b62be", "ARPU与ARPPU", "d0c0c718d43fd423da7c9e478c9a45ead0c6c87b679b351efc29a5c3ca3853e7", "core:6fce0cfb227b47828b41fd3c5cc736d5"),
    _target("5cee4cf41a024c56ac9de0e3aef9aefe", "24a51da63ed84379adbec45927500dce", "付费用户数（按渠道）", "bde3ffd4e38ab6916a3573c689b3c3520d89732080ea71228ddde3d3dc616514", "dashboard:24a51da63ed84379adbec45927500dce"),
    _target("5cee4cf41a024c56ac9de0e3aef9aefe", "8b1c7fa28da041afaf91d4a834a9a84a", "付费金额（按渠道）", "1ba283b4f3e9a8464738a71d8e3a78915073b16ffee762991b311c02de796833", "dashboard:8b1c7fa28da041afaf91d4a834a9a84a"),
    _target("78dc3256d7634085ab5d3701a5ce9cd0", "184e82d45d7a484eb4c7fbe2cd8b8e53", "付费用户数（按渠道）", "bde3ffd4e38ab6916a3573c689b3c3520d89732080ea71228ddde3d3dc616514", "dashboard:24a51da63ed84379adbec45927500dce"),
    _target("78dc3256d7634085ab5d3701a5ce9cd0", "35db1e9a802645cca6536d610c594034", "付费金额（按渠道）", "1ba283b4f3e9a8464738a71d8e3a78915073b16ffee762991b311c02de796833", "dashboard:8b1c7fa28da041afaf91d4a834a9a84a"),
    _target("30816a8c70ac450aade76e831a6fe56b", "e25a1967c7a94f16a01f2e6a07bd6d64", "实时付费事件次数", "666b4e3e9a5db4b5fb4663ecfc404c9a94a759beff60c36e643538c7a78a040a", "realtime:4fc570b4be7d406c9f648d9088f760bb"),
    _target("30816a8c70ac450aade76e831a6fe56b", "ad8550d28b574d73986d492e8cb7f07b", "累计付费事件次数", "c05efc799ba1806bf17d256b3416a318ead36de499a8efb53c2162cdb4bb850b", "realtime:2149b7abbc6c4cd7ad6f52379e69b15a"),
    _target("760150000bdc4abbb740880d494f5a5a", "4fc570b4be7d406c9f648d9088f760bb", "实时付费事件次数", "666b4e3e9a5db4b5fb4663ecfc404c9a94a759beff60c36e643538c7a78a040a", "realtime:4fc570b4be7d406c9f648d9088f760bb"),
    _target("760150000bdc4abbb740880d494f5a5a", "2149b7abbc6c4cd7ad6f52379e69b15a", "累计付费事件次数", "c05efc799ba1806bf17d256b3416a318ead36de499a8efb53c2162cdb4bb850b", "realtime:2149b7abbc6c4cd7ad6f52379e69b15a"),
    _target("db9df7a9015c4b4bb033810ffc5a84d2", "82f560ee39f2409485e7270d2c9db26c", "各建筑升级次数", "093f097a3cf22ee698b56653b38ddb2fe84a47616a8d62f1bbd836285afaabc7", "remaining:82f560ee39f2409485e7270d2c9db26c"),
    _target("db9df7a9015c4b4bb033810ffc5a84d2", "3a46d6c112284ee98373dbe53baa6290", "各主城等级建筑升级次数", "4a38e6d7698d0b1a1820018e04728e15f22056592a297e0299f19bf76ea4bbc7", "remaining:3a46d6c112284ee98373dbe53baa6290"),
    _target("db9df7a9015c4b4bb033810ffc5a84d2", "1c5f7aa5ae6f47ecb3dcfab37ee5e34e", "各类型加速情况", "23a3f9e6074050ade18ae7dd1e347ac7bdbf9387b1081e153b9568a5dbcb1188", "remaining:1c5f7aa5ae6f47ecb3dcfab37ee5e34e"),
    _target("ec29c0cb00d343f6928c3fa549af58ae", "7ff32974b9794b03b18531ec2de19930", "各建筑升级次数", "093f097a3cf22ee698b56653b38ddb2fe84a47616a8d62f1bbd836285afaabc7", "remaining:82f560ee39f2409485e7270d2c9db26c"),
    _target("ec29c0cb00d343f6928c3fa549af58ae", "1f760d0b2c1a4cdd8b2029ab7e0bedf3", "各主城等级建筑升级次数", "4a38e6d7698d0b1a1820018e04728e15f22056592a297e0299f19bf76ea4bbc7", "remaining:3a46d6c112284ee98373dbe53baa6290"),
    _target("ec29c0cb00d343f6928c3fa549af58ae", "aeeaf866526042a09812e355d0851034", "各类型加速情况", "23a3f9e6074050ade18ae7dd1e347ac7bdbf9387b1081e153b9568a5dbcb1188", "remaining:1c5f7aa5ae6f47ecb3dcfab37ee5e34e"),
    _target("29ea652e2969440b91899cfb254dd0ca", "9684a569ed034fb0b8a106a9817effaa", "参与新手活动的后续7日留存率", "ada62e0a5c2689f564dc19d5466b6aec6496b88eb67e9df97a03f59eb7414964", "remaining:9684a569ed034fb0b8a106a9817effaa"),
    _target("29ea652e2969440b91899cfb254dd0ca", "095b1cf41cd64844b1f78f07ceccb7bf", "参与节日活动的后续7日付费留存率", "79baccc6a160d5810325309a5799a1d6b99c56974bba0aef268fe998356a4706", "remaining:095b1cf41cd64844b1f78f07ceccb7bf"),
    _target("0431e8aa54d5444f9de8aef574e21881", "15da41b65ee64aba854e2de701a728bc", "购买新手礼包用户复购率", "5258b32bfbe0f288a693175c7dfa5ca5c1b63482633b970ea7ad65f39282bf0e", "remaining:15da41b65ee64aba854e2de701a728bc"),
    _target("0431e8aa54d5444f9de8aef574e21881", "f113ac14e8994d12814452040b702424", "购买月卡用户的30日留存", "3bd247bd47314024274a339d9fabde1adde5bfc7a44f29723cc5d962011744e6", "remaining:f113ac14e8994d12814452040b702424"),
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _backup_dashboard(row: dict[str, Any], backup_path: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if backup_path.exists():
        existing = json.loads(backup_path.read_text(encoding="utf-8"))
    existing.append({key: _json_value(value) for key, value in row.items()})
    backup_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def repair_dashboards(conn: Any, *, apply: bool) -> dict[str, list[str]]:
    targets_by_dashboard: dict[str, list[TargetView]] = {}
    for target in TARGET_VIEWS:
        targets_by_dashboard.setdefault(target.dashboard_id, []).append(target)

    realtime_targets = [target for target in TARGET_VIEWS if target.source_key.startswith("realtime:")]
    realtime_sql: dict[str, str] | None = None
    if realtime_targets:
        with conn.cursor() as cur:
            datasource_conf = load_flam_mysql_config(cur)
        realtime_sql = build_fixed_realtime_sql({}, datasource_conf)

    backup_path = BACKUP_DIR / f"flam_semantic_dashboards_before_repair_{time.time_ns()}.json"
    result: dict[str, list[str]] = {
        "updated": [],
        "would_update": [],
        "skipped_stale": [],
        "missing": [],
    }
    lock_clause = "FOR UPDATE" if apply else ""
    with conn.cursor() as cur:
        for dashboard_id, targets in targets_by_dashboard.items():
            cur.execute(
                f"""
                SELECT id, name, datasource, tenant_id, canvas_view_info
                FROM public.core_dashboard
                WHERE id = %s
                  AND tenant_id = %s
                  AND datasource = %s
                  AND COALESCE(delete_flag, 0) = 0
                  AND type = 'dashboard'
                {lock_clause}
                """,
                (dashboard_id, TENANT_ID, DATASOURCE_ID),
            )
            row = cur.fetchone()
            if not row:
                result["missing"].append(dashboard_id)
                continue

            stored_id, name, datasource, tenant_id, canvas_view_info_text = row
            canvas = json.loads(canvas_view_info_text or "{}")
            touched: list[str] = []
            targets_by_view_id: dict[str, list[TargetView]] = {}
            for target in targets:
                targets_by_view_id.setdefault(target.view_id, []).append(target)
            for view_id, candidates in targets_by_view_id.items():
                view = canvas.get(view_id)
                if not isinstance(view, dict):
                    result["missing"].append(f"{dashboard_id}:{view_id}")
                    continue
                if any(repair_view(view, target, realtime_sql) for target in candidates):
                    touched.append(view_id)
                else:
                    result["skipped_stale"].append(f"{dashboard_id}:{view_id}")

            if not touched:
                continue
            if apply:
                _backup_dashboard(
                    {
                        "id": stored_id,
                        "name": name,
                        "datasource": datasource,
                        "tenant_id": tenant_id,
                        "canvas_view_info": canvas_view_info_text,
                    },
                    backup_path,
                )
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                       SET canvas_view_info = %s,
                           update_time = %s,
                           update_by = %s
                     WHERE id = %s
                       AND tenant_id = %s
                       AND datasource = %s
                    """,
                    (
                        json.dumps(canvas, ensure_ascii=False, separators=(",", ":")),
                        int(time.time()),
                        UPDATE_BY,
                        stored_id,
                        TENANT_ID,
                        DATASOURCE_ID,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"更新看板失败: {stored_id}, rows={cur.rowcount}")
                result["updated"].extend(f"{dashboard_id}:{view_id}" for view_id in touched)
            else:
                result["would_update"].extend(f"{dashboard_id}:{view_id}" for view_id in touched)

    result["backup"] = [str(backup_path)] if result["updated"] else []
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="修复已审计的 First Zombie 看板副本语义 SQL")
    parser.add_argument("--apply", action="store_true", help="实际写入系统库；缺省仅执行只读演练")
    args = parser.parse_args()
    with psycopg.connect(**SYSTEM_DB) as conn:
        with conn.transaction():
            repair_dashboards(conn, apply=args.apply)


if __name__ == "__main__":
    main()
