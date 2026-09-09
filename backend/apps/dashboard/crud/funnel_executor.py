"""Deterministic funnel execution from a scoped event result."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class FunnelStep:
    order: int
    event_name: str
    name: str


def _value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _time_value(value: Any) -> int | float | datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float, datetime)):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _duration_seconds(window: dict[str, Any] | None) -> int:
    config = window if isinstance(window, dict) else {}
    mode = str(config.get("mode") or "duration").strip().lower()
    if mode == "same_day":
        return 24 * 60 * 60
    try:
        value = int(config.get("value") or 1)
    except (TypeError, ValueError):
        value = 1
    unit = str(config.get("unit") or "day").strip().lower()
    factor = {"day": 86400, "hour": 3600, "minute": 60, "second": 1}.get(unit)
    if factor is None or value <= 0:
        raise ValueError("漏斗窗口期必须是正数，并使用 day/hour/minute/second")
    return value * factor


def _time_delta_seconds(later: Any, earlier: Any) -> float | None:
    later_value = _time_value(later)
    earlier_value = _time_value(earlier)
    if later_value is None or earlier_value is None:
        return None
    if isinstance(later_value, datetime) and isinstance(earlier_value, datetime):
        return (later_value - earlier_value).total_seconds()
    delta = float(later_value) - float(earlier_value)
    # Event tables commonly store epoch milliseconds. Detect the unit from the
    # timestamp magnitude rather than from the delta (a seven-day delta in
    # seconds is also larger than 10,000).
    if abs(float(later_value)) >= 100_000_000_000 or abs(float(earlier_value)) >= 100_000_000_000:
        return delta / 1000
    return delta


def compute_funnel(
    rows: Iterable[dict[str, Any]],
    steps: Iterable[dict[str, Any]],
    *,
    window: dict[str, Any] | None = None,
    entity_key: str = "entity_id",
    event_key: str = "event_name",
    time_key: str = "event_time",
    date_key: str = "event_date_key",
    group_keys: Iterable[str] = (),
    related_key: str | None = None,
) -> list[dict[str, Any]]:
    """Compute cumulative funnel counts from normalized event rows.

    Each entity contributes at most once per step. The first valid occurrence of each
    subsequent step must follow the prior step and remain inside the window from step 1.
    """
    normalized_steps: list[FunnelStep] = []
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise ValueError("漏斗步骤配置无效")
        event = raw.get("event")
        if isinstance(event, dict):
            event_name = event.get("eventName") or event.get("event_name")
        else:
            event_name = event or raw.get("event_name")
        event_name = str(event_name or "").strip()
        if not event_name:
            raise ValueError(f"漏斗第 {index + 1} 步缺少事件")
        name = str(raw.get("alias") or raw.get("name") or event_name).strip()
        normalized_steps.append(FunnelStep(index + 1, event_name, name))
    if not normalized_steps:
        raise ValueError("漏斗至少需要一个步骤")

    group_key_list = [str(key).strip() for key in group_keys if str(key).strip()]
    by_entity: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        entity = _value(row, entity_key, "uid", "entity_id")
        event_name = _value(row, event_key, "event", "event_name")
        event_time = _value(row, time_key, "time", "event_time")
        if entity is None or event_name is None or event_time is None:
            continue
        group = tuple(_value(row, key, key.split(".")[-1]) for key in group_key_list)
        related = _value(row, related_key, "related_value") if related_key else None
        if related_key and related is None:
            continue
        by_entity.setdefault((entity, *group, related), []).append(row)

    window_config = window if isinstance(window, dict) else {}
    window_mode = str(window_config.get("mode") or "duration").strip().lower()
    window_seconds = _duration_seconds(window)
    if window_mode == "same_day" and not any(
        _value(row, date_key, "event_date", "dt") is not None
        for rows_for_entity in by_entity.values()
        for row in rows_for_entity
    ):
        raise ValueError("同日漏斗计算需要基础数据包含日期字段")
    completed_entities: dict[tuple[Any, ...], list[set[Any]]] = {}
    for entity_rows in by_entity.values():
        ordered = sorted(
            entity_rows,
            key=lambda item: (_time_value(_value(item, time_key, "time", "event_time")) is None,
                              _time_value(_value(item, time_key, "time", "event_time")) or 0),
        )
        completed = 0
        previous_time: Any = None
        first_time: Any = None
        first_date: Any = None
        group = tuple(_value(ordered[0], key, key.split(".")[-1]) for key in group_key_list)
        for step in normalized_steps:
            candidate = None
            candidate_date = None
            for row in ordered:
                if str(_value(row, event_key, "event", "event_name") or "") != step.event_name:
                    continue
                current_time = _value(row, time_key, "time", "event_time")
                if candidate is None and (previous_time is None or (_time_delta_seconds(current_time, previous_time) or -1) >= 0):
                    if first_time is None:
                        candidate = current_time
                        candidate_date = _value(row, date_key, "event_date", "dt")
                    else:
                        elapsed = _time_delta_seconds(current_time, first_time)
                        same_day = _value(row, date_key, "event_date", "dt") == first_date
                        valid_window = same_day if window_mode == "same_day" else (
                            elapsed is not None and 0 <= elapsed <= window_seconds
                        )
                        if valid_window:
                            candidate = current_time
                            candidate_date = _value(row, date_key, "event_date", "dt")
                if candidate is not None:
                    break
            if candidate is None:
                break
            completed += 1
            previous_time = candidate
            first_time = first_time or candidate
            if first_date is None:
                first_date = candidate_date
        if completed:
            bucket = completed_entities.setdefault(group, [set() for _ in normalized_steps])
            entity = _value(ordered[0], entity_key, "uid", "entity_id")
            for index in range(completed):
                bucket[index].add(entity)

    output: list[dict[str, Any]] = []
    for group, bucket in completed_entities.items() or [(tuple(), [set() for _ in normalized_steps])]:
        counts = [len(values) for values in bucket]
        first_count = counts[0]
        for index, step in enumerate(normalized_steps):
            current = counts[index]
            previous = counts[index - 1] if index else None
            row: dict[str, Any] = {
                "step_order": step.order,
                "step_name": step.name,
                "step_count": current,
                "step_rate": round(current / first_count, 4) if first_count else None,
                "step_conversion_rate": round(current / previous, 4) if previous else None,
                "step_dropoff_rate": round((previous - current) / previous, 4) if previous else None,
            }
            for key, value in zip(group_key_list, group):
                row[key] = value
            output.append(row)
    return output
