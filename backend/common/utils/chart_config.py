from typing import Any


CHART_TYPES = {
    "table",
    "metric",
    "column",
    "bar",
    "line",
    "area",
    "pie",
    "funnel",
    "heatmap",
    "scatter",
    "sankey",
    "treemap",
}


def _axis_binding_has_distinct_display_name(value: dict[str, Any]) -> bool:
    name = str(value.get("name") or "").strip()
    bound_value = str(value.get("value") or "").strip()
    return bool(name and bound_value and name != bound_value)


def _sanitize_axis_binding(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize_axis_binding(item) for item in value]
    if not isinstance(value, dict):
        return value
    sanitized = {
        key: _sanitize_axis_binding(item)
        for key, item in value.items()
        if key != "name" or _axis_binding_has_distinct_display_name(value)
    }
    return sanitized


def _sanitize_chart_object(chart: dict[str, Any]) -> dict[str, Any]:
    for key in ("columns", "xAxis", "yAxis", "series"):
        if key in chart:
            chart[key] = _sanitize_axis_binding(chart[key])
    axis = chart.get("axis")
    if isinstance(axis, dict):
        for key in ("x", "y", "series", "multi-quota"):
            if key in axis:
                axis[key] = _sanitize_axis_binding(axis[key])
    return chart


def _looks_like_chart_object(value: dict[str, Any]) -> bool:
    if any(key in value for key in ("axis", "xAxis", "yAxis", "series", "multiQuotaName")):
        return True
    return "columns" in value and str(value.get("type") or "").lower() in CHART_TYPES


def sanitize_chart_display_names(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitize_chart_display_names(item) for item in value]
    if not isinstance(value, dict):
        return value

    result = {
        key: sanitize_chart_display_names(item)
        for key, item in value.items()
    }
    if _looks_like_chart_object(result):
        _sanitize_chart_object(result)
    chart = result.get("chart")
    if isinstance(chart, dict):
        _sanitize_chart_object(chart)
    return result
