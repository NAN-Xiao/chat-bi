"""为数据源级 Data Skill 追加统一的 AI 看板日期输出契约。"""
from __future__ import annotations


DASHBOARD_DATE_CONTRACT_MARKER = "<!-- managed:dashboard-date-contract:v1 -->"
DASHBOARD_DATE_CONTRACT = f"""{DASHBOARD_DATE_CONTRACT_MARKER}
## AI 看板日期输出契约

- 固定语义 `metric` 保留问题自身日期，但不得返回 `date_filter` 或看板日期 token。
- 其他包含日期字段的图表必须返回 `date_filter`，SQL 使用 `{{{{dashboard_start_yyyymmdd}}}}` 与 `{{{{dashboard_end_yyyymmdd}}}}`。
- `time_field` 必须对应 SQL 中实际参数化字段，`date_parameter_type` 必须与 token 家族一致。
- 返回 `date_filter` 时不得使用 `CURDATE()`、`CURRENT_DATE`、`NOW()` 或同类数据库当前时间函数。
""".strip()


def append_dashboard_date_contract(prompt: str) -> str:
    """幂等地把日期输出契约放在 prompt 末尾，使其覆盖前文历史示例。"""
    normalized = str(prompt or "").rstrip()
    if DASHBOARD_DATE_CONTRACT_MARKER in normalized:
        return normalized
    return f"{normalized}\n\n{DASHBOARD_DATE_CONTRACT}"
