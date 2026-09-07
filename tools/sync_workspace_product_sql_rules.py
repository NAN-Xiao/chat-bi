"""Add datasource-scoped product rules to the six configured business workspaces."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config

ROOT = Path(__file__).resolve().parents[1]
PROFILES = [
    (3, 7477202383789887488, "flam", 110000038),
    (6, 7482727237662281728, "\u4fee\u4ed9", 110000047),
    (9, 7493583885482070016, "unicorn", 110000030),
    (10, 7493272675721154560, "lds", 110000039),
    (11, 7493583991958671360, "j2000", 110000034),
    (12, 7493272549510352896, "gig", 110000036),
]
RULE_TEMPLATE = "{name}\u5de5\u4f5c\u7a7a\u95f4\u4ea7\u54c1\u7b5b\u9009\uff08\u5f3a\u5236\uff09\uff1a\u5f53\u524d\u6570\u636e\u6e90\u67e5\u8be2\u4efb\u4f55\u5305\u542b prod \u5b57\u6bb5\u7684\u7269\u7406\u8868\u65f6\uff0c\u5fc5\u987b\u9650\u5b9a prod = {product_id}\u3002\u5f53\u524d\u9002\u7528\u8868\u4e3a event\u3001event_realtime\u3001user\uff1b\u540c\u4e00\u7269\u7406\u8868\u5728\u591a\u4e2a CTE\u3001\u5b50\u67e5\u8be2\u3001UNION \u5206\u652f\u6216 JOIN \u4e2d\u88ab\u8bfb\u53d6\u65f6\uff0c\u6bcf\u6b21\u5f15\u7528\u5747\u987b\u5728\u5176\u6240\u5c5e\u67e5\u8be2\u5757\u7684 WHERE \u6216 JOIN ON \u4e2d\u663e\u5f0f\u5199\u5165\u5bf9\u5e94\u8868\u522b\u540d\u7684 prod = {product_id} \u6761\u4ef6\u3002LEFT JOIN \u53f3\u8868\u7684\u4ea7\u54c1\u6761\u4ef6\u5e94\u5199\u5728\u8be5\u8868\u7684 ON \u6761\u4ef6\u6216\u53f3\u4fa7\u5b50\u67e5\u8be2\u4e2d\uff0c\u4fdd\u7559\u5de6\u8fde\u63a5\u8bed\u4e49\u3002\u4ec5\u5199\u8868\u4e4b\u95f4\u7684 prod \u76f8\u7b49\u5173\u8054\u4e0d\u80fd\u66ff\u4ee3\u56fa\u5b9a\u4ea7\u54c1\u503c\u7b5b\u9009\uff1b\u4e0d\u5f97\u4ee5 SELECT * \u6d3e\u751f\u8868\u5305\u88f9\u4ee3\u66ff\uff0c\u4e5f\u4e0d\u5f97\u4f7f\u7528\u5176\u4ed6\u5de5\u4f5c\u7a7a\u95f4\u7684\u4ea7\u54c1\u503c\u3002\u8be5\u89c4\u5219\u9002\u7528\u4e8e\u5f53\u524d\u5de5\u4f5c\u7a7a\u95f4\u7ed1\u5b9a\u7684\u6570\u636e\u6e90\uff0c\u4e0d\u5f97\u4f20\u64ad\u5230\u5176\u4ed6\u5de5\u4f5c\u7a7a\u95f4\u3002"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    options = "-c statement_timeout=10000 -c lock_timeout=5000"
    if not args.apply:
        options += " -c default_transaction_read_only=on"
    changes = []
    summaries = []
    with psycopg.connect(
        **core_system_db_config(), connect_timeout=8, options=options, row_factory=dict_row
    ) as conn:
        with conn.cursor() as cur:
            for ds_id, tenant_id, name, product_id in PROFILES:
                cur.execute(
                    """SELECT d.name AS datasource_name, t.name AS workspace_name
                       FROM core_datasource d JOIN sys_tenant t ON t.id=d.tenant_id
                       WHERE d.id=%s AND d.tenant_id=%s""" +
                    (" FOR SHARE OF d, t" if args.apply else ""),
                    (ds_id, tenant_id),
                )
                identity = cur.fetchone()
                if not identity or set(identity.values()) != {name}:
                    raise RuntimeError(f"Workspace identity mismatch: {ds_id}")
                cur.execute(
                    """SELECT id, tenant_id, datasource_id, enabled, sql_rules, update_time
                       FROM sys_tenant_tracking_config
                       WHERE tenant_id=%s AND datasource_id=%s""" +
                    (" FOR UPDATE" if args.apply else ""),
                    (tenant_id, ds_id),
                )
                rows = cur.fetchall()
                if len(rows) != 1 or not rows[0]["enabled"]:
                    raise RuntimeError(f"Missing or disabled tracking configuration: {ds_id}")
                before = rows[0]
                cur.execute(
                    """SELECT DISTINCT t.table_name FROM core_field f
                       JOIN core_table t ON t.id=f.table_id AND t.ds_id=f.ds_id
                       WHERE f.ds_id=%s AND f.field_name='prod'""",
                    (ds_id,),
                )
                if {r["table_name"] for r in cur.fetchall()} != {"event", "event_realtime", "user"}:
                    raise RuntimeError(f"Product field table mapping changed: {ds_id}")
                rule = RULE_TEMPLATE.format(name=name, product_id=product_id)
                old_rules = before["sql_rules"] or ""
                changed = rule not in old_rules.splitlines()
                after_rules = rule + ("\n" + old_rules if old_rules else "") if changed else old_rules
                summaries.append(dict(workspace=name, datasource_id=ds_id, product_id=product_id, changed=changed))
                if changed:
                    changes.append(dict(before=before, after_sql_rules=after_rules))

            if args.apply and changes:
                backup_dir = ROOT / ".codex-runtime" / "tracking-dictionary-backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / f"workspace-product-rules-{time.time_ns()}.json"
                with backup.open("x", encoding="utf-8") as handle:
                    json.dump(dict(kind="workspace-product-sql-rules-v1", changes=changes), handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                print(f"BACKUP {backup}")
                for change in changes:
                    before = change["before"]
                    cur.execute(
                        """UPDATE sys_tenant_tracking_config SET sql_rules=%s, update_time=%s
                           WHERE id=%s AND tenant_id=%s AND datasource_id=%s
                           AND sql_rules IS NOT DISTINCT FROM %s
                           AND update_time IS NOT DISTINCT FROM %s""",
                        (change["after_sql_rules"], int(time.time() * 1000), before["id"],
                         before["tenant_id"], before["datasource_id"], before["sql_rules"], before["update_time"]),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(f"Concurrent configuration change: {before['datasource_id']}")
                    cur.execute("SELECT sql_rules FROM sys_tenant_tracking_config WHERE id=%s", (before["id"],))
                    if cur.fetchone()["sql_rules"] != change["after_sql_rules"]:
                        raise RuntimeError("Read-back mismatch")
    print(json.dumps(dict(applied=args.apply, changed_count=len(changes), workspaces=summaries), ensure_ascii=False))


if __name__ == "__main__":
    main()
