from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import orjson
from langgraph.config import get_stream_writer

from apps.datasource.crud.permission_errors import (
    PERMISSION_DENIED_ERROR_TYPE,
    PERMISSION_DENIED_RESULT_MESSAGE,
)
from common.utils.utils import AppLogUtil


def emit(payload: Any) -> None:
    get_stream_writer()(payload)


def sse(payload: dict[str, Any]) -> str:
    return "data:" + orjson.dumps(payload).decode() + "\n\n"


def emit_stream_text(
    chunks: Iterable[dict[str, Any]],
    *,
    in_chat: bool,
    stream: bool,
    event_type: str,
    emit_plain_text: bool = False,
) -> str:
    full_text = ""
    for chunk in chunks:
        content = chunk.get("content") or ""
        full_text += content
        if in_chat:
            emit(sse({
                "content": content,
                "reasoning_content": chunk.get("reasoning_content"),
                "type": event_type,
            }))
        elif stream and emit_plain_text:
            emit(content)
    return full_text


def emit_markdown_table(
    data: Any,
    fields: Any,
    *,
    empty_message: str,
) -> None:
    if not data or not fields:
        emit(empty_message + "\n\n")
        return

    import pandas as pd

    from common.utils.data_format import DataFormat

    df = pd.DataFrame(data, columns=fields)
    df_safe = DataFormat.safe_convert_to_string(df)
    emit(df_safe.to_markdown(index=False) + "\n\n")


def emit_permission_denied_response(
    *,
    in_chat: bool,
    stream: bool,
    json_result: dict[str, Any],
    sql: str | None = None,
    failed_result: dict[str, Any] | None = None,
    formatted_sql: str | None = None,
    emit_sql: bool = False,
    include_reason: bool = False,
) -> dict[str, Any]:
    if in_chat:
        if emit_sql and formatted_sql:
            emit(sse({"content": formatted_sql, "type": "sql"}))
        payload = {
            "content": "execute-failed",
            "type": "sql-data",
            "status": "failed",
            "error_type": PERMISSION_DENIED_ERROR_TYPE,
            "message": PERMISSION_DENIED_RESULT_MESSAGE,
        }
        if include_reason:
            payload["reason"] = PERMISSION_DENIED_RESULT_MESSAGE
        emit(sse(payload))
        emit(sse({"type": "finish"}))
    elif stream:
        if emit_sql and formatted_sql:
            emit(f"```sql\n{formatted_sql}\n```\n\n")
        emit(f"> {PERMISSION_DENIED_RESULT_MESSAGE}\n")
    else:
        json_result["success"] = False
        if sql is not None:
            json_result["sql"] = sql
        if failed_result is not None:
            json_result["data"] = failed_result
        json_result["message"] = PERMISSION_DENIED_RESULT_MESSAGE
        emit(json_result)

    return json_result


def emit_chart_image(
    *,
    session: Any,
    service: Any,
    chart: dict[str, Any],
    data: dict[str, Any],
    return_img: bool = True,
    json_result: dict[str, Any] | None = None,
    emit_markdown: bool = False,
    emit_error_message: bool = True,
    log_operation: bool = False,
    error_message: str = "generate or fetch chart picture error.\n\n",
) -> str | None:
    if chart.get("type") == "table" or not return_img:
        return None

    from apps.chat.task.llm import request_picture

    end_log_func = None
    operation = None
    if log_operation:
        from apps.chat.curd.chat import end_log, start_log
        from apps.chat.models.chat_model import OperationEnum

        operation = OperationEnum.GENERATE_PICTURE
        service.current_logs[operation] = start_log(
            session=session,
            operate=operation,
            record_id=service.record.id,
            local_operation=True,
        )
        end_log_func = end_log

    try:
        image_url, error = request_picture(
            service.record.chat_id,
            service.record.id,
            chart,
            data,
        )
        AppLogUtil.info(image_url)
        if emit_markdown:
            emit(f'![{chart.get("type")}]({image_url})')
        elif json_result is not None:
            json_result["image_url"] = image_url
        if error is not None:
            raise error
    except Exception:
        if emit_markdown and emit_error_message:
            emit(error_message)
        raise

    if log_operation and operation is not None and end_log_func is not None:
        service.current_logs[operation] = end_log_func(
            session=session,
            log=service.current_logs[operation],
            full_message=image_url,
        )

    return image_url
