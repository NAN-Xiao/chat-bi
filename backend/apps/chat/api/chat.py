from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select

from apps.chat.curd.chat import list_chats, get_chat_with_records, create_chat, save_question, save_answer, rename_chat, \
    delete_chat
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat, Chat
from apps.chat.schemas.chat_base_schema import LLMConfig
from apps.chat.schemas.chat_schema import ChatQuestion
from apps.chat.schemas.llm import AgentService
from apps.datasource.crud.datasource import get_table_obj_by_ds
from apps.datasource.models.datasource import CoreDatasource
from apps.system.models.system_model import AiModelDetail
from common.core.deps import SessionDep, CurrentUser
import json
import asyncio

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

    record: ChatRecord
    try:
        record = save_question(session=session, current_user=current_user, question=request_question)
    except Exception as e1:
        raise HTTPException(
            status_code=400,
            detail=str(e1)
        )

    # Get available AI model
    aimodel = session.exec(select(AiModelDetail).where(
        AiModelDetail.status == True,
        AiModelDetail.api_key.is_not(None)
    )).first()
    if not aimodel:
        raise HTTPException(
            status_code=400,
            detail="No available AI model configuration found"
        )

    # Use Tongyi Qianwen
    tongyi_config = LLMConfig(
        model_type="openai",
        model_name=aimodel.name,
        api_key=aimodel.api_key,
        api_base_url=aimodel.endpoint,
        additional_params={"temperature": aimodel.temperature}
    )
    # llm_service = LLMService(tongyi_config)
    llm_service = AgentService(tongyi_config, ds)

    # Use Custom VLLM model
    """ vllm_config = LLMConfig(
        model_type="vllm",
        model_name="your-model-path",
        additional_params={
            "max_new_tokens": 200,
            "temperature": 0.3
        }
    )
    vllm_service = LLMService(vllm_config) """
    """ result = llm_service.generate_sql(question)
    return result """

    # get schema
    schema_str = ""
    table_objs = get_table_obj_by_ds(session=session, ds=ds)
    db_name = table_objs[0].schema
    schema_str += f"【DB_ID】 {db_name}\n【Schema】\n"
    for obj in table_objs:
        schema_str += f"# Table: {db_name}.{obj.table.table_name}"
        table_comment = ''
        if obj.table.custom_comment:
            table_comment = obj.table.custom_comment.strip()
        if table_comment == '':
            schema_str += '\n[\n'
        else:
            schema_str += f", {table_comment}\n[\n"

        field_list = []
        for field in obj.fields:
            field_comment = ''
            if field.custom_comment:
                field_comment = field.custom_comment.strip()
            if field_comment == '':
                field_list.append(f"({field.field_name}:{field.field_type})")
            else:
                field_list.append(f"({field.field_name}:{field.field_type}, {field_comment})")
        schema_str += ",\n".join(field_list)
        schema_str += '\n]\n'

    print(schema_str)

    async def event_generator():
        all_text = ''
        try:
            async for chunk in llm_service.async_generate(question, schema_str):
                data = json.loads(chunk.replace('data: ', ''))

                if data['type'] in ['final', 'tool_result']:
                    content = data['content']
                    print('--  ' + content)
                    all_text += content
                    for char in content:
                        yield f"data: {json.dumps({'type': 'char', 'content': char})}\n\n"
                        await asyncio.sleep(0.05)

                    if 'html' in data:
                        yield f"data: {json.dumps({'type': 'html', 'content': data['html']})}\n\n"
                else:
                    yield chunk

        except Exception as e:
            all_text = 'Exception:' + str(e)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        try:
            save_answer(session=session, id=record.id, answer=all_text)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=str(e)
            )

    # return EventSourceResponse(event_generator(), headers={"Content-Type": "text/event-stream"})
    return StreamingResponse(event_generator(), media_type="text/event-stream")
