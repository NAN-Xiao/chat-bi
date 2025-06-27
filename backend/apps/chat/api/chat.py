import traceback
from typing import List

import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select

from apps.chat.curd.chat import list_chats, get_chat_with_records, create_chat, rename_chat, \
    delete_chat, list_records
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat, Chat, ChatQuestion, ChatMcp
from apps.chat.task.llm import LLMService
from apps.datasource.crud.datasource import get_table_schema
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.user import get_user_info
from apps.system.models.system_model import AiModelDetail
from common.core.deps import SessionDep, CurrentUser, get_current_user

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


@router.post("/mcp_start", operation_id="mcp_start")
async def mcp_start(session: SessionDep, chat: ChatMcp):
    user = await get_current_user(session, chat.token)
    return create_chat(session, user, CreateChat(), False)


@router.post("/mcp_question", operation_id="mcp_question")
async def mcp_question(session: SessionDep, chat: ChatMcp):
    user = await get_current_user(session, chat.token)
    return await stream_sql(session, user, chat)


@router.post("/start")
async def start_chat(session: SessionDep, current_user: CurrentUser, create_chat_obj: CreateChat):
    try:
        return create_chat(session, current_user, create_chat_obj)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/question", operation_id="question")
async def stream_sql(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion):
    """Stream SQL analysis results
    
    Args:
        session: Database session
        current_user: CurrentUser
        request_question: User question model
        
    Returns:
        Streaming response with analysis results
    """

    chat = session.query(Chat).filter(Chat.id == request_question.chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=400,
            detail=f"Chat with id {request_question.chat_id} not found"
        )
    ds: CoreDatasource | None = None
    if chat.datasource:
        # Get available datasource
        ds = session.query(CoreDatasource).filter(CoreDatasource.id == chat.datasource).first()
        if not ds:
            raise HTTPException(
                status_code=500,
                detail="No available datasource configuration found"
            )

        request_question.engine = ds.type_name if ds.type != 'excel' else 'PostgreSQL'

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

    history_records: List[ChatRecord] = list(filter(lambda r: True if r.first_chat != True else False,
                                                    list_records(session=session, current_user=current_user,
                                                                 chart_id=request_question.chat_id)))
    # get schema
    if ds:
        request_question.db_schema = get_table_schema(session=session, ds=ds)

    db_user = get_user_info(session=session, user_id=current_user.id)
    request_question.lang = db_user.language

    llm_service = LLMService(request_question, aimodel, history_records,
                             CoreDatasource(**ds.model_dump()) if ds else None)

    llm_service.init_record(session=session, current_user=current_user)

    def run_task():
        try:
            # return id
            yield orjson.dumps({'type': 'id', 'id': llm_service.get_record().id}).decode() + '\n\n'

            # select datasource if datasource is none
            if not ds:
                ds_res = llm_service.select_datasource(session=session)
                for chunk in ds_res:
                    yield orjson.dumps({'content': chunk, 'type': 'datasource-result'}).decode() + '\n\n'
                yield orjson.dumps({'id': llm_service.ds.id, 'datasource_name': llm_service.ds.name,
                                    'engine_type': llm_service.ds.type_name, 'type': 'datasource'}).decode() + '\n\n'

                llm_service.chat_question.db_schema = get_table_schema(session=session, ds=llm_service.ds)

            # generate sql
            sql_res = llm_service.generate_sql(session=session)
            full_sql_text = ''
            for chunk in sql_res:
                full_sql_text += chunk
                yield orjson.dumps({'content': chunk, 'type': 'sql-result'}).decode() + '\n\n'
            yield orjson.dumps({'type': 'info', 'msg': 'sql generated'}).decode() + '\n\n'

            # filter sql
            print(full_sql_text)
            sql = llm_service.check_save_sql(session=session, res=full_sql_text)
            print(sql)
            yield orjson.dumps({'content': sql, 'type': 'sql'}).decode() + '\n\n'

            # execute sql
            result = llm_service.execute_sql(sql=sql)
            llm_service.save_sql_data(session=session, data_obj=result)
            yield orjson.dumps({'content': orjson.dumps(result).decode(), 'type': 'sql-data'}).decode() + '\n\n'

            # generate chart
            chart_res = llm_service.generate_chart(session=session)
            full_chart_text = ''
            for chunk in chart_res:
                full_chart_text += chunk
                yield orjson.dumps({'content': chunk, 'type': 'chart-result'}).decode() + '\n\n'
            yield orjson.dumps({'type': 'info', 'msg': 'chart generated'}).decode() + '\n\n'

            # filter chart
            print(full_chart_text)
            chart = llm_service.check_save_chart(session=session, res=full_chart_text)
            print(chart)
            yield orjson.dumps({'content': orjson.dumps(chart).decode(), 'type': 'chart'}).decode() + '\n\n'

            llm_service.finish(session=session)
            yield orjson.dumps({'type': 'finish'}).decode() + '\n\n'

        except Exception as e:
            traceback.print_exc()
            llm_service.save_error(session=session, message=str(e))
            yield orjson.dumps({'content': str(e), 'type': 'error'}).decode() + '\n\n'

    return StreamingResponse(run_task(), media_type="text/event-stream")


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

    chat = session.query(Chat).filter(Chat.id == record.chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=400,
            detail=f"Chat with id {record.chart_id} not found"
        )

    if chat.create_by != current_user.id:
        raise HTTPException(
            status_code=401,
            detail=f"You cannot use the chat with id {record.chart_id}"
        )

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

    request_question = ChatQuestion(chat_id=chat.id, question='')
    db_user = get_user_info(session=session, user_id=current_user.id)
    request_question.lang = db_user.language

    llm_service = LLMService(request_question, aimodel)
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
                analysis_res = llm_service.generate_predict(session=session)
                full_text = ''
                for chunk in analysis_res:
                    yield orjson.dumps({'content': chunk, 'type': 'predict-result'}).decode() + '\n\n'
                    full_text += chunk
                yield orjson.dumps({'type': 'info', 'msg': 'predict generated'}).decode() + '\n\n'

                _data = llm_service.check_save_predict_data(session=session, res=full_text)
                yield orjson.dumps({'type': 'predict', 'content': _data}).decode() + '\n\n'

                yield orjson.dumps({'type': 'predict_finish'}).decode() + '\n\n'


        except Exception as e:
            traceback.print_exc()
            # llm_service.save_error(session=session, message=str(e))
            yield orjson.dumps({'content': str(e), 'type': 'error'}).decode() + '\n\n'

    return StreamingResponse(run_task(), media_type="text/event-stream")
