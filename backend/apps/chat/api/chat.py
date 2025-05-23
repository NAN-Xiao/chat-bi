from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select

from apps.chat.curd.chat import list_chats, get_chat_with_records, create_chat, save_question, save_answer, rename_chat, \
    delete_chat
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat
from apps.chat.schemas.chat_base_schema import LLMConfig
from apps.chat.schemas.chat_schema import ChatQuestion
from apps.chat.schemas.llm import AgentService
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

    # Get available AI model
    aimodel = session.exec(select(AiModelDetail).where(
        AiModelDetail.status == True,
        AiModelDetail.api_key.is_not(None)
    )).first()

    # Get available datasource
    ds = session.exec(select(CoreDatasource).where(
        CoreDatasource.status == 'Success'
    )).first()

    if not aimodel:
        raise HTTPException(
            status_code=400,
            detail="No available AI model configuration found"
        )

    if not ds:
        raise HTTPException(
            status_code=400,
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

    async def event_generator():
        all_text = ''
        try:
            async for chunk in llm_service.async_generate(question):
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
