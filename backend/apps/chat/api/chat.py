import traceback

import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from apps.chat.curd.chat import list_chats, get_chat_with_records, create_chat, rename_chat, \
    delete_chat
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat, ChatQuestion
from apps.chat.task.llm import LLMService, run_task
from common.core.deps import SessionDep, CurrentUser

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

    try:
        llm_service = LLMService(session, current_user, request_question)
        llm_service.init_record()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    return StreamingResponse(run_task(llm_service, session), media_type="text/event-stream")


@router.post("/record/{chart_record_id}/{action_type}")
async def analysis_or_predict(session: SessionDep, current_user: CurrentUser, chart_record_id: int, action_type: str):
    if action_type != 'analysis' and action_type != 'predict':
        raise HTTPException(
            status_code=404,
            detail="Not Found"
        )

    record = session.query(ChatRecord).get(chart_record_id)
    if not record:
        raise HTTPException(
            status_code=400,
            detail=f"Chat record with id {chart_record_id} not found"
        )

    if not record.chart:
        raise HTTPException(
            status_code=500,
            detail=f"Chat record with id {chart_record_id} has not generated chart, do not support to analyze it"
        )

    request_question = ChatQuestion(chat_id=record.chat_id, question='')

    llm_service = LLMService(session, current_user, request_question)
    llm_service.set_record(record)

    def run_task():
        try:
            if action_type == 'analysis':
                # generate analysis
                analysis_res = llm_service.generate_analysis(session=session)
                for chunk in analysis_res:
                    yield orjson.dumps({'content': chunk, 'type': 'analysis-result'}).decode() + '\n\n'
                yield orjson.dumps({'type': 'info', 'msg': 'analysis generated'}).decode() + '\n\n'

                yield orjson.dumps({'type': 'analysis_finish'}).decode() + '\n\n'

            elif action_type == 'predict':
                # generate predict
                analysis_res = llm_service.generate_predict()
                full_text = ''
                for chunk in analysis_res:
                    yield orjson.dumps({'content': chunk, 'type': 'predict-result'}).decode() + '\n\n'
                    full_text += chunk
                yield orjson.dumps({'type': 'info', 'msg': 'predict generated'}).decode() + '\n\n'

                _data = llm_service.check_save_predict_data(res=full_text)
                yield orjson.dumps({'type': 'predict', 'content': _data}).decode() + '\n\n'

                yield orjson.dumps({'type': 'predict_finish'}).decode() + '\n\n'


        except Exception as e:
            traceback.print_exc()
            # llm_service.save_error(session=session, message=str(e))
            yield orjson.dumps({'content': str(e), 'type': 'error'}).decode() + '\n\n'

    return StreamingResponse(run_task(), media_type="text/event-stream")
