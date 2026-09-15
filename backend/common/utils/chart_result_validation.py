from datetime import date, datetime

from common.error import SingleMessageError
from common.utils.sql_date_validation import mysql_temporal_result_fields


class ChartResultValidationError(SingleMessageError):
    pass


def _blank(value) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


def validate_trend_dimensions(chart: dict, result: dict) -> None:
    if chart.get('type') not in {'line', 'area'} or not result.get('data'):
        return
    axis = chart.get('axis') or {}
    dimension = axis.get('x') or {}
    field = dimension.get('value') or dimension.get('name')
    if not field or field not in (result.get('fields') or []):
        raise ChartResultValidationError('趋势图缺少有效的横轴字段，请检查图表配置。')
    rows = result['data']
    invalid_count = sum(_blank(row.get(field)) for row in rows)
    if invalid_count:
        raise ChartResultValidationError(
            f'横轴字段“{field}”有 {invalid_count}/{len(rows)} 行为空，无法展示完整趋势。请检查查询结果、日期转换或字段配置。'
        )


def validate_temporal_query_result(sql: str, datasource_type: str | None, result: dict, chart_type: str) -> None:
    if chart_type not in {'line', 'area', 'column', 'grouped_column', 'bar'} or not result.get('data'):
        return
    for field in mysql_temporal_result_fields(sql, datasource_type):
        invalid_count = 0
        for row in result['data']:
            value = row.get(field)
            if isinstance(value, (date, datetime)):
                continue
            text = str(value).strip() if value is not None else ''
            try:
                if len(text) == 8 and text.isdigit():
                    datetime.strptime(text, '%Y%m%d')
                else:
                    datetime.fromisoformat(text.replace('Z', '+00:00'))
            except ValueError:
                invalid_count += 1
        if invalid_count:
            raise ChartResultValidationError(
                f'日期字段“{field}”有 {invalid_count}/{len(result["data"])} 行为空或无效，无法展示完整趋势。'
                '请检查源数据和日期配置；仅凭空值不能确定 SQL 错误，已停止自动改写。'
            )
