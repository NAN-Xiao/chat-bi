import asyncio
from typing import Any

import orjson
from fastapi import HTTPException
from sqlalchemy import and_
from sqlmodel import Session, select

from apps.chat.models.chat_model import ChatFinishStep, ChatQuestion, ChatRecord, QuickCommand
from apps.chat.task.llm import LLMService
from apps.chat.task_events import append_chat_task_event, bind_chat_record_task
from apps.system.crud.tenant import normalize_tenant_role
from apps.system.crud.user import apply_user_role_flags
from apps.system.models.user import UserModel
from apps.system.schemas.system_schema import AssistantHeader, UserInfoDTO
from apps.system.schemas.access_context import require_current_tenant_id
from common.core.db import engine
from common.core.task_queue import current_task_context, current_task_tenant_id, task_handler
from common.utils.command_utils import parse_quick_command


def _error_chunk(message: str) -> str:
    return "data:" + orjson.dumps({"content": message, "type": "error"}).decode() + "\n\n"


def _assistant_from_payload(payload: dict[str, Any]) -> AssistantHeader | None:
    assistant_payload = payload.get("assistant")
    if not assistant_payload:
        return None
    return AssistantHeader(**assistant_payload)


def _parse_finish_step(value: int) -> ChatFinishStep:
    try:
        return ChatFinishStep(value)
    except ValueError as exc:
        allowed = ", ".join(str(step.value) for step in ChatFinishStep)
        raise ValueError(f"finish_step must be one of: {allowed}") from exc


def _find_base_question(record_id: int, session: Session, current_user: UserInfoDTO) -> str:
    stmt = select(ChatRecord.question, ChatRecord.regenerate_record_id).where(
        and_(
            ChatRecord.id == record_id,
            ChatRecord.create_by == current_user.id,
            ChatRecord.tenant_id == require_current_tenant_id(current_user),
        )
    )
    row = session.execute(stmt).fetchone()
    if not row:
        raise ValueError("Cannot find base chat record")
    rec_question, rec_regenerate_record_id = row
    if rec_regenerate_record_id:
        return _find_base_question(rec_regenerate_record_id, session, current_user)
    return rec_question


def _load_task_user(session: Session, payload: dict[str, Any], tenant_id: int) -> UserInfoDTO:
    user_id = int(payload["user_id"])
    db_user = session.get(UserModel, user_id)
    if db_user is None:
        raise ValueError(f"User {user_id} does not exist")

    tenant_role = normalize_tenant_role(payload.get("tenant_role") or "member")
    user_info = UserInfoDTO(
        id=int(db_user.id),
        account=db_user.account,
        name=db_user.name,
        email=db_user.email,
        password=db_user.password,
        status=db_user.status,
        origin=db_user.origin,
        language=db_user.language or payload.get("language") or "zh-CN",
        system_role=db_user.system_role,
        tenant_id=tenant_id,
        tenant_role=tenant_role,
        tenant_ids=[tenant_id],
        tenant_roles={str(tenant_id): tenant_role},
        workspace_role=tenant_role,
        has_workspace=True,
        workspace_status="active",
    )
    return apply_user_role_flags(user_info)


def _resolve_chat_question(session: Session, current_user: UserInfoDTO, payload: dict[str, Any]) -> ChatQuestion:
    question = ChatQuestion(
        chat_id=int(payload["chat_id"]),
        question=str(payload.get("question") or ""),
        custom_prompt_id=payload.get("custom_prompt_id"),
        data_skill_id=payload.get("data_skill_id"),
    )
    if payload.get("regenerate_record_id"):
        question.regenerate_record_id = int(payload["regenerate_record_id"])
        return question
    command, text_before_command, record_id, _warning_info = parse_quick_command(question.question)
    if not command:
        return question

    if command in {QuickCommand.ANALYSIS, QuickCommand.PREDICT_DATA}:
        raise ValueError(f"Command: {command.value} temporary not supported")

    tenant_id = require_current_tenant_id(current_user)
    rec_id = record_id
    rec_regenerate_record_id = None
    if rec_id is not None:
        stmt = select(
            ChatRecord.id,
            ChatRecord.chat_id,
            ChatRecord.analysis_record_id,
            ChatRecord.predict_record_id,
            ChatRecord.regenerate_record_id,
            ChatRecord.first_chat,
        ).where(
            and_(
                ChatRecord.id == rec_id,
                ChatRecord.create_by == current_user.id,
                ChatRecord.tenant_id == tenant_id,
            )
        ).order_by(ChatRecord.create_time.desc())
        row = session.execute(stmt).fetchone()
        if not row:
            raise ValueError(f"Record id: {rec_id} does not exist")
        (
            _record_id,
            rec_chat_id,
            rec_analysis_record_id,
            rec_predict_record_id,
            rec_regenerate_record_id,
            rec_first_chat,
        ) = row
        if rec_chat_id != question.chat_id:
            raise ValueError(f"Record id: {rec_id} does not belong to this chat")
        if rec_first_chat:
            raise ValueError(f"Record id: {rec_id} does not support this operation")
        if rec_analysis_record_id:
            raise ValueError("Analysis record does not support this operation")
        if rec_predict_record_id:
            raise ValueError("Predict data record does not support this operation")
    else:
        stmt = select(
            ChatRecord.id,
            ChatRecord.chat_id,
            ChatRecord.regenerate_record_id,
        ).where(
            and_(
                ChatRecord.chat_id == question.chat_id,
                ChatRecord.create_by == current_user.id,
                ChatRecord.tenant_id == tenant_id,
                ChatRecord.first_chat == False,
                ChatRecord.analysis_record_id.is_(None),
                ChatRecord.predict_record_id.is_(None),
            )
        ).order_by(ChatRecord.create_time.desc()).limit(1)
        row = session.execute(stmt).fetchone()
        if not row:
            raise ValueError("You have not ask any question")
        rec_id, _rec_chat_id, rec_regenerate_record_id = row

    if not rec_regenerate_record_id:
        rec_regenerate_record_id = rec_id
    base_question_text = _find_base_question(rec_regenerate_record_id, session, current_user)
    question.question = text_before_command + ("\n" if text_before_command else "") + base_question_text
    question.regenerate_record_id = rec_id
    return question


def _load_task_record(session: Session, current_user: UserInfoDTO, payload: dict[str, Any]) -> ChatRecord | None:
    record_id = payload.get("record_id")
    if not record_id:
        return None
    record = session.get(ChatRecord, int(record_id))
    if (
        record is None
        or int(record.create_by) != int(current_user.id)
        or int(record.tenant_id) != require_current_tenant_id(current_user)
    ):
        raise ValueError(f"Chat record {record_id} does not exist or is not accessible")
    return record


@task_handler("chat.smart_qa")
async def smart_qa_task(payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    task = current_task_context()
    task_id = str(task.get("id")) if task else str(payload.get("task_id") or "")

    try:
        with Session(engine) as session:
            current_user = _load_task_user(session, payload, tenant_id)
            current_assistant = _assistant_from_payload(payload)
            question = _resolve_chat_question(session, current_user, payload)
            finish_step = _parse_finish_step(
                int(payload.get("finish_step") or ChatFinishStep.GENERATE_CHART.value)
            )

            llm_service = await LLMService.create(
                session,
                current_user,
                question,
                current_assistant,
                embedding=bool(payload.get("embedding", True)),
            )
            record = _load_task_record(session, current_user, payload)
            if record is None:
                record = llm_service.init_record(session=session)
                session.commit()
            else:
                llm_service.set_record(record)
            await bind_chat_record_task(tenant_id, record.id, task_id)

            for chunk in llm_service.run_task(
                in_chat=True,
                stream=True,
                finish_step=finish_step,
                return_img=bool(payload.get("return_img", True)),
            ):
                await append_chat_task_event(tenant_id, task_id, chunk)
                await asyncio.sleep(0)

            return {"record_id": getattr(record, "id", None), "tenant_id": tenant_id}
    except Exception as exc:
        message = exc.detail if isinstance(exc, HTTPException) else str(exc)
        await append_chat_task_event(tenant_id, task_id, _error_chunk(str(message)))
        raise
