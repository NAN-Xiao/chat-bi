import asyncio
import json
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select

from apps.chat.curd.chat import list_chats, get_chat_with_records, create_chat, save_question, save_answer, rename_chat, \
    delete_chat, list_records
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat, Chat, ChatQuestion
from apps.chat.task.llm import LLMService
from apps.datasource.crud.datasource import get_table_schema
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.system_model import AiModelDetail
from common.core.deps import SessionDep, CurrentUser

router = APIRouter(tags=["Data Q&A"], prefix="/chat")


@router.get("/list")
async def chats(session: SessionDep, current_user: CurrentUser):
    return list_chats(session, current_user)


@router.get("/get/{chart_id}")
async def list_chat(session: SessionDep, current_user: CurrentUser, chart_id: int):
    try:
        return get_chat_with_records(chart_id=chart_id, session=session, current_user=current_user)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/rename")
async def rename(session: SessionDep, chat: RenameChat):
    try:
        return rename_chat(session=session, rename_object=chat)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/delete/{chart_id}")
async def delete(session: SessionDep, chart_id: int):
    try:
        return delete_chat(session=session, chart_id=chart_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/start")
async def start_chat(session: SessionDep, current_user: CurrentUser, create_chat_obj: CreateChat):
    try:
        return create_chat(session, current_user, create_chat_obj)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/question")
async def stream_sql(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion):
    """Stream SQL analysis results
    
    Args:
        session: Database session
        current_user: CurrentUser
        request_question: User question model
        
    Returns:
        Streaming response with analysis results
    """
    question = request_question.question

    chat = session.query(Chat).filter(Chat.id == request_question.chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=400,
            detail=f"Chat with id {request_question.chart_id} not found"
        )

    # Get available datasource
    ds = session.query(CoreDatasource).filter(CoreDatasource.id == chat.datasource).first()
    if not ds:
        raise HTTPException(
            status_code=500,
            detail="No available datasource configuration found"
        )

    request_question.engine = ds.type_name

    # Get available AI model
    aimodel = session.exec(select(AiModelDetail).where(
        AiModelDetail.status == True,
        AiModelDetail.api_key.is_not(None)
    )).first()
    if not aimodel:
        raise HTTPException(
            status_code=500,
            detail="No available AI model configuration found"
        )

    history_records: List[ChatRecord] = list_records(session=session, current_user=current_user,
                                                     chart_id=request_question.chat_id)
    # get schema
    request_question.db_schema = get_table_schema(session=session, ds=ds)
    llm_service = LLMService(request_question, history_records, ds, aimodel)

    llm_service.init_record(session=session, current_user=current_user)

    def run_task():
        sql_res = llm_service.generate_sql(session=session)
        for chunk in sql_res:
            yield json.dumps({'content': chunk, 'type': 'sql'}) + '\n\n'
        yield json.dumps({'type': 'info', 'msg': 'sql generated'}) + '\n\n'

    # async def event_generator():
    #     all_text = ''
    #     try:
    #         async for chunk in llm_service.async_generate(question, request_question.db_schema):
    #             data = json.loads(chunk.replace('data: ', ''))
    #
    #             if data['type'] in ['final', 'tool_result']:
    #                 content = data['content']
    #                 print('--  ' + content)
    #                 all_text += content
    #                 for char in content:
    #                     yield f"data: {json.dumps({'type': 'char', 'content': char})}\n\n"
    #                     await asyncio.sleep(0.05)
    #
    #                 if 'html' in data:
    #                     yield f"data: {json.dumps({'type': 'html', 'content': data['html']})}\n\n"
    #             else:
    #                 yield chunk
    #
    #     except Exception as e:
    #         all_text = 'Exception:' + str(e)
    #         yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    #
    #     try:
    #         save_answer(session=session, id=record.id, answer=all_text)
    #     except Exception as e:
    #         raise HTTPException(
    #             status_code=500,
    #             detail=str(e)
    #         )

    # return EventSourceResponse(event_generator(), headers={"Content-Type": "text/event-stream"})
    return StreamingResponse(run_task(), media_type="text/event-stream")
