"""Validate the tracked AI dashboard question banks in this directory."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent

BANKS = {
    "gig-ai-dashboard-100-questions-20260817.json": {
        "workspace": "gig",
        "tenant_id": "7493272549510352896",
        "datasource_id": 12,
        "dashboard_count": 10,
        "auditable": True,
    },
    "unicorn-ai-dashboard-100-questions-20260817.json": {
        "workspace": "unicorn",
        "tenant_id": "7493583885482070016",
        "datasource_id": 9,
        "dashboard_count": 10,
        "auditable": True,
    },
    "j2000-ai-dashboard-100-questions-20260817.json": {
        "workspace": "j2000",
        "tenant_id": "7493583991958671360",
        "datasource_id": 11,
        "dashboard_count": 10,
        "auditable": True,
    },
    "lds-ai-dashboard-100-questions-20260817.json": {
        "workspace": "lds",
        "tenant_id": "7493272675721154560",
        "datasource_id": 10,
        "dashboard_count": 10,
        "auditable": True,
    },
    "flam-ai-dashboard-100-questions-2026-08-02.json": {
        "workspace": "flam",
        "tenant_id": "7477202383789887488",
        "datasource_id": 3,
        "dashboard_count": 14,
        "auditable": False,
    },
    "xiuxian-ai-dashboard-100-questions-2026-08-02.json": {
        "workspace": "修仙",
        "tenant_id": "7482727237662281728",
        "datasource_id": 6,
        "dashboard_count": 10,
        "auditable": False,
    },
    "sample-workspace-ai-dashboard-100-questions-20260811.json": {
        "workspace": "示例工作空间",
        "tenant_id": "7473600346187632640",
        "datasource_id": 1,
        "dashboard_count": 13,
        "auditable": False,
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_bank(filename: str, expected: dict[str, object]) -> dict[str, object]:
    path = ROOT / filename
    items = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(items, list), f"{filename}: root must be a list")
    require(len(items) == 100, f"{filename}: expected 100 questions, got {len(items)}")
    require(
        [item.get("id") for item in items] == list(range(1, 101)),
        f"{filename}: ids must be continuous from 1 to 100",
    )

    questions = [str(item.get("question", "")).strip() for item in items]
    require(all(questions), f"{filename}: question text must not be empty")
    require(
        len(set(questions)) == 100,
        f"{filename}: question text must be unique within the bank",
    )

    for item in items:
        question_id = item["id"]
        require(
            item.get("workspace") == expected["workspace"],
            f"{filename}#{question_id}: workspace mismatch",
        )
        require(
            item.get("datasource_id") == expected["datasource_id"],
            f"{filename}#{question_id}: datasource mismatch",
        )
        require(item.get("independent") is True, f"{filename}#{question_id}: not independent")
        for field in (
            "dashboard_id",
            "dashboard_name",
            "topic",
            "time_scope",
            "expected_answer_kind",
        ):
            require(bool(item.get(field)), f"{filename}#{question_id}: missing {field}")

    dashboard_counts = Counter(str(item["dashboard_id"]) for item in items)
    require(
        len(dashboard_counts) == expected["dashboard_count"],
        f"{filename}: dashboard count mismatch",
    )

    if expected["auditable"]:
        require(
            set(dashboard_counts.values()) == {10},
            f"{filename}: each recommended dashboard must provide 10 questions",
        )
        selected_count = 0
        for item in items:
            question_id = item["id"]
            require(
                str(item.get("tenant_id")) == expected["tenant_id"],
                f"{filename}#{question_id}: tenant mismatch",
            )
            source_charts = item.get("source_charts")
            require(
                isinstance(source_charts, list) and bool(source_charts),
                f"{filename}#{question_id}: source_charts must not be empty",
            )
            selected_count += item.get("selected_for_test") is True
        require(selected_count == 20, f"{filename}: expected 20 selected questions")

    return {
        "questions": len(items),
        "unique_questions": len(set(questions)),
        "dashboards": len(dashboard_counts),
        "datasource_id": expected["datasource_id"],
        "tenant_id": expected["tenant_id"],
        "format": "auditable" if expected["auditable"] else "legacy",
    }


def main() -> None:
    actual_files = {path.name for path in ROOT.glob("*-ai-dashboard-100-questions*.json")}
    require(actual_files == set(BANKS), "question bank file list does not match the manifest")
    report = {
        filename: validate_bank(filename, expected)
        for filename, expected in BANKS.items()
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
