import datetime
from typing import List

from sqlalchemy import and_

from apps.chat.models.chat_model import Chat, ChatRecord, CreateChat, ChatInfo, RenameChat, ChatQuestion
from apps.datasource.models.datasource import CoreDatasource
from common.core.deps import SessionDep, CurrentUser


def list_chats(session: SessionDep, current_user: CurrentUser) -> List[Chat]:
    chart_list = session.query(Chat).filter(Chat.create_by == current_user.id).order_by(
        Chat.create_time.desc()).all()
    return chart_list


def rename_chat(session: SessionDep, rename_object: RenameChat) -> str:
    chat = session.query(Chat).filter(Chat.id == rename_object.id).first()
    if not chat:
        raise Exception(f"Chat with id {rename_object.id} not found")

    chat.brief = rename_object.brief.strip()[:20]
    session.add(chat)
    session.flush()
    session.refresh(chat)

    brief = chat.brief
    session.commit()
    return brief


def delete_chat(session, chart_id) -> str:
    chat = session.query(Chat).filter(Chat.id == chart_id).first()
    if not chat:
        return f'Chat with id {chart_id} has been deleted'

    session.delete(chat)
    session.commit()

    return f'Chat with id {chart_id} has been deleted'


def get_chat_with_records(session: SessionDep, chart_id: int, current_user: CurrentUser) -> ChatInfo:
    chat = session.query(Chat).filter(Chat.id == chart_id).first()
    if not chat:
        raise Exception(f"Chat with id {chart_id} not found")

    chat_info = ChatInfo(**chat.model_dump())

    ds = session.query(CoreDatasource).filter(CoreDatasource.id == chat.datasource).first()
    if not ds:
        chat_info.datasource_exists = False
        chat_info.datasource_name = 'Datasource not exist'
    else:
        chat_info.datasource_exists = True
        chat_info.datasource_name = ds.name

    record_list = session.query(ChatRecord).filter(
        and_(Chat.create_by == current_user.id, ChatRecord.chat_id == chart_id)).order_by(ChatRecord.create_time).all()

    chat_info.records = record_list

    return chat_info


def list_records(session: SessionDep, chart_id: int, current_user: CurrentUser) -> List[ChatRecord]:
    record_list = session.query(ChatRecord).filter(
        and_(Chat.create_by == current_user.id, ChatRecord.chat_id == chart_id)).order_by(ChatRecord.create_time).all()
    return record_list


def create_chat(session: SessionDep, current_user: CurrentUser, create_chat_obj: CreateChat) -> ChatInfo:
    if not create_chat_obj.datasource:
        raise Exception("Datasource cannot be None")

    if not create_chat_obj.question or create_chat_obj.question.strip() == '':
        raise Exception("Question cannot be Empty")

    chat = Chat(create_time=datetime.datetime.now(),
                create_by=current_user.id,
                brief=create_chat_obj.question.strip()[:20],
                datasource=create_chat_obj.datasource)

    ds = session.query(CoreDatasource).filter(CoreDatasource.id == create_chat_obj.datasource).first()

    if not ds:
        raise Exception(f"Datasource with id {create_chat_obj.datasource} not found")

    chat.engine_type = ds.type_name

    chat_info = ChatInfo(**chat.model_dump())

    session.add(chat)
    session.flush()
    session.refresh(chat)
    chat_info.id = chat.id
    session.commit()

    return chat_info


def save_question(session: SessionDep, current_user: CurrentUser, question: ChatQuestion) -> ChatRecord:
    if not question.chat_id:
        raise Exception("ChatId cannot be None")
    if not question.question or question.question.strip() == '':
        raise Exception("Question cannot be Empty")

    chat = session.query(Chat).filter(Chat.id == question.chat_id).first()
    if not chat:
        raise Exception(f"Chat with id {question.chat_id} not found")

    record = ChatRecord()
    record.question = question.question
    record.chat_id = chat.id
    record.create_time = datetime.datetime.now()
    record.create_by = current_user.id
    record.datasource = chat.datasource
    record.engine_type = chat.engine_type

    result = ChatRecord(**record.model_dump())

    session.add(record)
    session.flush()
    session.refresh(record)
    result.id = record.id
    session.commit()

    return result


def save_full_sql_message(session: SessionDep, record_id: int, full_message: str) -> ChatRecord:
    return save_full_sql_message_and_answer(session=session, record_id=record_id, full_message=full_message, answer='')


def save_full_sql_message_and_answer(session: SessionDep, record_id: int, answer: str, full_message: str) -> ChatRecord:
    if not record_id:
        raise Exception("Record id cannot be None")
    record = session.query(ChatRecord).filter(ChatRecord.id == record_id).first()
    record.full_sql_message = full_message
    record.sql_answer = answer

    result = ChatRecord(**record.model_dump())

    session.add(record)
    session.flush()
    session.refresh(record)

    session.commit()

    return result


def save_full_chart_message(session: SessionDep, id: int, full_message: str) -> ChatRecord:
    if not id:
        raise Exception("Record id cannot be None")
    record = session.query(ChatRecord).filter(ChatRecord.id == id).first()
    record.full_chart_message = full_message

    result = ChatRecord(**record.model_dump())

    session.add(record)
    session.flush()
    session.refresh(record)

    session.commit()

    return result


def save_answer(session: SessionDep, id: int, answer: str) -> ChatRecord:
    if not id:
        raise Exception("Record id cannot be None")

    record = session.query(ChatRecord).filter(ChatRecord.id == id).first()
    record.answer = answer

    result = ChatRecord(**record.model_dump())

    session.add(record)
    session.flush()
    session.refresh(record)

    session.commit()

    return result
