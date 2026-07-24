"""定向修复修仙核心看板的真实交易 SQL。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

import psycopg
from psycopg.types.json import Jsonb

try:
    from .core_system_db import core_system_db_config
except ImportError:  # 支持直接执行 tools 下的脚本。
    from core_system_db import core_system_db_config


TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
DASHBOARD_ID = "afe201c9762c448aa0495f3508c01793"
DATA_SKILL_NAME = "修仙 ServerPayLog 收入与 ARPU/ARPPU"
DATA_SKILL_SOURCE_SHA256 = "714771270144e40ab7f872d7a3668c6278e84b8a1db61167690b51fde62fb15f"


class SourceSqlChangedError(ValueError):
    """目标抽屉 SQL 已偏离审核版本，拒绝覆盖。"""


class SourcePromptChangedError(ValueError):
    """目标 Data Skill 已偏离审核版本，拒绝覆盖。"""


class DashboardCasConflictError(RuntimeError):
    """读取后看板被其他操作修改，CAS 更新被拒绝。"""


class DataSkillCasConflictError(RuntimeError):
    """读取后 Data Skill 被其他操作修改，CAS 更新被拒绝。"""


@dataclass(frozen=True)
class ViewRepair:
    """单个抽屉的审核源哈希和替换 SQL。"""

    view_id: str
    source_sha256: str
    sql: str


@dataclass(frozen=True)
class RepairReport:
    """一次修补执行的最小结果。"""

    dashboard_id: str
    updated: bool
    view_ids: tuple[str, ...]


@dataclass(frozen=True)
class DataSkillRepairReport:
    """一次 Data Skill SQL 块替换的最小结果。"""

    skill_id: int
    updated: bool


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


SQL_ARPU_ARPPU = """
WITH daily_pay AS (
    SELECT
        e.dt,
        ROUND(
            SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))),
            2
        ) AS pay_amount,
        COUNT(DISTINCT e.uid) AS pay_users
    FROM `event` e
    WHERE e.dt BETWEEN
          CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 28 DAY), '%Y%m%d') AS SIGNED)
      AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000047
      AND e.event = 'ServerPayLog'
    GROUP BY e.dt
),
daily_active AS (
    SELECT
        e.dt,
        COUNT(DISTINCT e.uid) AS active_users
    FROM `event` e
    WHERE e.dt BETWEEN
          CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 28 DAY), '%Y%m%d') AS SIGNED)
      AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000047
      AND e.event = 'UserActive'
    GROUP BY e.dt
)
SELECT
    DATE_FORMAT(STR_TO_DATE(CAST(d.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS dt,
    ROUND(COALESCE(p.pay_amount, 0) / NULLIF(d.active_users, 0), 2) AS `ARPU`,
    ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`
FROM daily_active d
LEFT JOIN daily_pay p ON p.dt = d.dt
ORDER BY d.dt;
""".strip()


SQL_NEW_USER_ARPU_ARPPU = """
WITH new_users AS (
    SELECT
        e.dt,
        e.uid
    FROM `event` e
    WHERE e.dt BETWEEN
          CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
      AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000047
      AND e.event = 'UserRegister'
    GROUP BY e.dt, e.uid
),
new_user_payment AS (
    SELECT
        n.dt,
        n.uid,
        COALESCE(
            CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.pay, '$.pay1')), '') AS DECIMAL(18, 4)),
            0
        ) AS first_day_payment
    FROM new_users n
    JOIN `user` u
      ON u.prod = 110000047
     AND u.dt = n.dt
     AND u.uid = n.uid
     AND CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')), '') AS SIGNED) = n.dt
),
daily_metrics AS (
    SELECT
        dt,
        COUNT(DISTINCT uid) AS new_users,
        COUNT(DISTINCT CASE WHEN first_day_payment > 0 THEN uid END) AS new_pay_users,
        ROUND(SUM(first_day_payment), 2) AS new_pay_amount
    FROM new_user_payment
    GROUP BY dt
)
SELECT
    DATE_FORMAT(STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS `日期`,
    new_users AS `新增用户数`,
    new_pay_users AS `新增付费用户数`,
    COALESCE(new_pay_amount, 0) AS `新增首日付费金额`,
    ROUND(COALESCE(new_pay_amount, 0) / NULLIF(new_users, 0), 2) AS `新增用户ARPU`,
    ROUND(COALESCE(new_pay_amount, 0) / NULLIF(new_pay_users, 0), 2) AS `新增用户ARPPU`
FROM daily_metrics
ORDER BY dt;
""".strip()


REPAIRS: dict[str, ViewRepair] = {
    "22d89d4a69224e53994d21fb44b376aa": ViewRepair(
        view_id="22d89d4a69224e53994d21fb44b376aa",
        source_sha256="9222861c2af9e08a6ed5debe1a11728de84b97c9d303505cf3ae9b8a619ee8c0",
        sql=SQL_ARPU_ARPPU,
    ),
    "2192510609759838208": ViewRepair(
        view_id="2192510609759838208",
        source_sha256="5a23757f3ab4a4f4c69f2b55646faaa8fa16e6dce2c72593e38a63a32e7734ee",
        sql=SQL_NEW_USER_ARPU_ARPPU,
    ),
}


def apply_repairs_to_canvas(
    canvas: dict[str, Any],
    *,
    repairs: Mapping[str, ViewRepair] | None = None,
) -> dict[str, Any]:
    """在内存中验证并替换两个受限抽屉的双份 SQL。"""

    effective_repairs = REPAIRS if repairs is None else repairs
    repaired = copy.deepcopy(canvas)
    for view_id, repair in effective_repairs.items():
        view = repaired.get(view_id)
        if not isinstance(view, dict):
            raise ValueError(f"缺少目标抽屉: {view_id}")
        source_sql = view.get("sql")
        if not isinstance(source_sql, str):
            raise ValueError(f"抽屉 SQL 必须是字符串: {view_id}")
        if _sha256_text(source_sql) != repair.source_sha256:
            raise SourceSqlChangedError(f"抽屉 {view_id} 的 SQL 已偏离审核版本")
        source_config = view.get("sourceConfig")
        source_sql_config = source_config.get("sql") if isinstance(source_config, dict) else None
        if not isinstance(source_sql_config, dict):
            raise ValueError(f"抽屉缺少 sourceConfig.sql: {view_id}")
        if source_sql_config.get("sql") != source_sql:
            raise ValueError(f"抽屉 SQL 副本不一致: {view_id}")
        view["sql"] = repair.sql
        source_sql_config["sql"] = repair.sql
    return repaired


def apply_repairs_to_data_skill_prompt(
    prompt: str,
    *,
    repairs: Mapping[str, ViewRepair] | None = None,
    expected_source_sha256: str = DATA_SKILL_SOURCE_SHA256,
) -> str:
    """仅替换指定 dashboard-sql 标记后的 SQL 代码块。"""

    if _sha256_text(prompt) != expected_source_sha256:
        raise SourcePromptChangedError("修仙收入 Data Skill 已偏离审核版本")
    effective_repairs = REPAIRS if repairs is None else repairs
    repaired = prompt
    for view_id, repair in effective_repairs.items():
        pattern = re.compile(
            rf"(<!-- dashboard-sql:{re.escape(view_id)} -->\s*```sql\s*)(.*?)(\s*```)",
            re.DOTALL,
        )
        repaired, replaced = pattern.subn(
            lambda match: f"{match.group(1)}{repair.sql}{match.group(3)}",
            repaired,
            count=1,
        )
        if replaced != 1:
            raise ValueError(f"Data Skill 缺少或重复 SQL 代码块: {view_id}")
    return repaired


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def repair_dashboard(connection: Any, *, apply: bool) -> RepairReport:
    """以原始 canvas 为 CAS 条件修补指定修仙核心看板。"""

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, canvas_view_info
            FROM core_dashboard
            WHERE id = %s
              AND tenant_id = %s
              AND datasource = %s
              AND COALESCE(delete_flag, 0) = 0
            FOR UPDATE
            """,
            (DASHBOARD_ID, TENANT_ID, DATASOURCE_ID),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("未找到修仙核心看板")
        dashboard_id, original_canvas = row
        if not isinstance(original_canvas, str):
            original_canvas = _canonical_json(original_canvas)
        canvas = json.loads(original_canvas)
        if not isinstance(canvas, dict):
            raise ValueError("核心看板 canvas_view_info 必须是 JSON 对象")
        repaired_canvas = apply_repairs_to_canvas(canvas)
        if not apply:
            return RepairReport(str(dashboard_id), False, tuple(REPAIRS))
        cur.execute(
            """
            UPDATE core_dashboard
            SET canvas_view_info = %s
            WHERE id = %s
              AND tenant_id = %s
              AND datasource = %s
              AND canvas_view_info = %s
            """,
            (
                _canonical_json(repaired_canvas),
                dashboard_id,
                TENANT_ID,
                DATASOURCE_ID,
                original_canvas,
            ),
        )
        if cur.rowcount != 1:
            raise DashboardCasConflictError("看板在读取后已被其他操作修改")
    connection.commit()
    return RepairReport(str(dashboard_id), True, tuple(REPAIRS))


def repair_data_skill(
    connection: Any,
    *,
    apply: bool,
    repairs: Mapping[str, ViewRepair] | None = None,
    source_sha256: str | None = None,
) -> DataSkillRepairReport:
    """以原始 prompt 为 CAS 条件更新修仙收入 Skill 的嵌入 SQL。"""

    effective_repairs = REPAIRS if repairs is None else repairs
    expected_source_sha256 = (
        DATA_SKILL_SOURCE_SHA256 if source_sha256 is None else source_sha256
    )
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, prompt
            FROM custom_prompt
            WHERE tenant_id = %s
              AND type = 'DATA_SKILL'
              AND specific_ds = TRUE
              AND datasource_ids = %s::jsonb
              AND name = %s
            FOR UPDATE
            """,
            (TENANT_ID, Jsonb([DATASOURCE_ID]), DATA_SKILL_NAME),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("未找到修仙收入 Data Skill")
        skill_id, source_prompt = row
        if not isinstance(source_prompt, str):
            raise ValueError("修仙收入 Data Skill prompt 必须是字符串")
        repaired_prompt = apply_repairs_to_data_skill_prompt(
            source_prompt,
            repairs=effective_repairs,
            expected_source_sha256=expected_source_sha256,
        )
        if not apply:
            return DataSkillRepairReport(int(skill_id), False)
        cur.execute(
            """
            UPDATE custom_prompt
            SET prompt = %s
            WHERE id = %s
              AND tenant_id = %s
              AND type = 'DATA_SKILL'
              AND specific_ds = TRUE
              AND datasource_ids = %s::jsonb
              AND name = %s
              AND prompt = %s
            """,
            (
                repaired_prompt,
                skill_id,
                TENANT_ID,
                Jsonb([DATASOURCE_ID]),
                DATA_SKILL_NAME,
                source_prompt,
            ),
        )
        if cur.rowcount != 1:
            raise DataSkillCasConflictError("Data Skill 在读取后已被其他操作修改")
    connection.commit()
    return DataSkillRepairReport(int(skill_id), True)


def main() -> None:
    parser = argparse.ArgumentParser(description="修复修仙核心看板真实交易 SQL")
    parser.add_argument("--apply", action="store_true", help="执行数据库更新；默认仅 dry-run")
    args = parser.parse_args()
    with psycopg.connect(**core_system_db_config()) as connection:
        report = repair_dashboard(connection, apply=args.apply)
    print(
        f"dashboard_id={report.dashboard_id} updated={report.updated} "
        f"view_ids={','.join(report.view_ids)}"
    )


if __name__ == "__main__":
    main()
