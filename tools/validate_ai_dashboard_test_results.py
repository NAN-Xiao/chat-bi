"""Validate AI dashboard question-bank attempts and collect chart failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "question_id",
    "attempt_id",
    "record_id",
    "finish",
    "has_complete_sql",
    "has_sql_answer",
    "has_chart_answer",
    "chart_rendered",
)
SUCCESS_STATUS = "success"
CHART_NOT_GENERATED_STATUS = "chart_not_generated"
SQL_NOT_GENERATED_STATUS = "sql_not_generated"
CHART_ERROR_STATUS = "chart_error"
RUNTIME_ERROR_STATUS = "runtime_error"
RUNNING_OR_ORPHANED_STATUS = "running_or_orphaned"
CAPABILITY_BOUNDARY_STATUS = "capability_boundary"


def _is_true(value: Any) -> bool:
    """Accept only JSON true for acceptance evidence; strings are invalid evidence."""
    return value is True


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_fields(item: dict[str, Any], index: int) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in item]
    if missing:
        raise ValueError(f"item {index}: missing required fields: {', '.join(missing)}")
    if not _has_text(item.get("question_id")) and not isinstance(item.get("question_id"), (int, float)):
        raise ValueError(f"item {index}: question_id is required")
    if not _has_text(item.get("attempt_id")) and not isinstance(item.get("attempt_id"), (int, float)):
        raise ValueError(f"item {index}: attempt_id is required")


def _failure_reason(item: dict[str, Any], status: str) -> str:
    existing = item.get("chart_not_generated_reason")
    if _has_text(existing):
        return str(existing)
    if status == SQL_NOT_GENERATED_STATUS:
        return "complete SQL was not generated"
    if not _is_true(item.get("has_chart_answer")):
        return "chart answer was not generated"
    if not _is_true(item.get("chart_rendered")):
        return "chart answer exists but was not rendered in the current page"
    return "chart acceptance evidence is incomplete"


def classify_attempt(item: dict[str, Any]) -> dict[str, Any]:
    """Classify one attempt without combining evidence from another attempt."""
    result = dict(item)
    if _is_true(item.get("capability_boundary")):
        status = CAPABILITY_BOUNDARY_STATUS
    elif not _is_true(item.get("finish")):
        task_status = str(item.get("task_status") or "").lower()
        status = (
            RUNNING_OR_ORPHANED_STATUS
            if task_status in {"running", "pending", "queued"} or not _has_text(str(item.get("error") or ""))
            else RUNTIME_ERROR_STATUS
        )
    elif not _is_true(item.get("has_complete_sql")) or not _is_true(item.get("has_sql_answer")):
        status = SQL_NOT_GENERATED_STATUS
    elif not _is_true(item.get("has_chart_answer")):
        status = CHART_NOT_GENERATED_STATUS
    elif not _is_true(item.get("chart_rendered")):
        status = CHART_ERROR_STATUS
    elif _has_text(item.get("error")) or _has_text(item.get("error_type")):
        status = RUNTIME_ERROR_STATUS
    else:
        status = SUCCESS_STATUS

    result["status"] = status
    result["success"] = status == SUCCESS_STATUS
    result["chart_not_generated"] = bool(
        _is_true(item.get("has_sql_answer"))
        and (
            not _is_true(item.get("has_chart_answer"))
            or not _is_true(item.get("chart_rendered"))
        )
    )
    if result["chart_not_generated"]:
        result["chart_not_generated_reason"] = _failure_reason(item, status)
    return result


def validate_results(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validated: list[dict[str, Any]] = []
    chart_failures: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"item {index}: result must be an object")
        _require_fields(item, index)
        result = classify_attempt(item)
        validated.append(result)
        if result.get("chart_not_generated"):
            chart_failures.append(result)
    return validated, chart_failures


def _read_items(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("result input must be a JSON array")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AI dashboard question-bank results.")
    parser.add_argument("--input", required=True, type=Path, help="Question-bank attempt result JSON array.")
    parser.add_argument("--output", type=Path, help="Validated result JSON path.")
    parser.add_argument(
        "--chart-failures",
        type=Path,
        help="Output path for attempts without a generated chart.",
    )
    args = parser.parse_args()

    items = _read_items(args.input)
    validated, chart_failures = validate_results(items)
    output_path = args.output or args.input.with_name(f"{args.input.stem}-validated.json")
    failures_path = args.chart_failures or args.input.with_name(f"{args.input.stem}-chart-not-generated.json")
    output_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
    failures_path.write_text(json.dumps(chart_failures, ensure_ascii=False, indent=2), encoding="utf-8")

    success_count = sum(1 for item in validated if item["success"])
    print(f"total={len(validated)} success={success_count} chart_not_generated={len(chart_failures)}")
    print(f"validated_results={output_path}")
    print(f"chart_not_generated={failures_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
