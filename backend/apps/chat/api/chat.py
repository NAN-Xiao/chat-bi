import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from apps.chat.curd.chat import list_chats, get_chat_with_records, create_chat, rename_chat, \
    delete_chat, get_chat_chart_data, get_chat_predict_data
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat, ChatQuestion
from apps.chat.task.llm import LLMService, run_task, run_analysis_or_predict_task, run_recommend_questions_task
from common.core.deps import CurrentAssistant, SessionDep, CurrentUser

router = APIRouter(tags=["Data Q&A"], prefix="/chat")


@router.get("/list")
async def chats(session: SessionDep, current_user: CurrentUser):
    return list_chats(session, current_user)


@router.get("/get/{chart_id}")
async def get_chat(session: SessionDep, current_user: CurrentUser, chart_id: int):
    try:
        return get_chat_with_records(chart_id=chart_id, session=session, current_user=current_user)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/record/get/{chart_record_id}/data")
async def chat_record_data(session: SessionDep, chart_record_id: int):
    try:
        return get_chat_chart_data(chart_record_id=chart_record_id, session=session)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/record/get/{chart_record_id}/predict_data")
async def chat_predict_data(session: SessionDep, chart_record_id: int):
    try:
        return get_chat_predict_data(chart_record_id=chart_record_id, session=session)
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
            status_code=500,
            detail=str(e)
        )
        
@router.post("/assistant/start")
async def start_chat(session: SessionDep, current_user: CurrentUser):
    try:
        return create_chat(session, current_user, CreateChat(), False)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/recommend_questions/{chat_record_id}")
async def recommend_questions(session: SessionDep, current_user: CurrentUser, chat_record_id: int, current_assistant: CurrentAssistant):
    try:
        record = session.query(ChatRecord).get(chat_record_id)
        if not record:
            raise HTTPException(
                status_code=400,
                detail=f"Chat record with id {chat_record_id} not found"
            )
        request_question = ChatQuestion(chat_id=record.chat_id, question=record.question if record.question else '')

        llm_service = LLMService(session, current_user, request_question, current_assistant)
        llm_service.set_record(record)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    return StreamingResponse(run_recommend_questions_task(llm_service), media_type="text/event-stream")


@router.post("/question")
async def stream_sql(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion, current_assistant: CurrentAssistant):
    """Stream SQL analysis results
    
    Args:
        session: Database session
        current_user: CurrentUser
        request_question: User question model
        
    Returns:
        Streaming response with analysis results
    """

    try:
        llm_service = LLMService(session, current_user, request_question, current_assistant)
        llm_service.init_record()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    return StreamingResponse(run_task(llm_service), media_type="text/event-stream")


@router.post("/record/{chat_record_id}/{action_type}")
async def analysis_or_predict(session: SessionDep, current_user: CurrentUser, chat_record_id: int, action_type: str, current_assistant: CurrentAssistant):
    if action_type != 'analysis' and action_type != 'predict':
        raise HTTPException(
            status_code=404,
            detail="Not Found"
        )

    record = session.query(ChatRecord).get(chat_record_id)
    if not record:
        raise HTTPException(
            status_code=400,
            detail=f"Chat record with id {chat_record_id} not found"
        )

    if not record.chart:
        raise HTTPException(
            status_code=500,
            detail=f"Chat record with id {chat_record_id} has not generated chart, do not support to analyze it"
        )

    request_question = ChatQuestion(chat_id=record.chat_id, question='')

    try:
        llm_service = LLMService(session, current_user, request_question, current_assistant)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    return StreamingResponse(run_analysis_or_predict_task(llm_service, action_type, record),
                             media_type="text/event-stream")
