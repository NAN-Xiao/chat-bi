"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from common.core.deps import SessionDep
from ..models.datasource import CoreField, FieldObj
from sqlalchemy import or_, and_


def delete_field_by_ds_id(session: SessionDep, id: int):
    """
    是什么：delete_field_by_ds_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源不再需要的数据、缓存或临时内容清理掉。
    """
    session.query(CoreField).filter(CoreField.ds_id == id).delete(synchronize_session=False)
    session.commit()


def get_fields_by_table_id(session: SessionDep, id: int, field: FieldObj):
    """
    是什么：get_fields_by_table_id 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    if field and field.fieldName:
        return session.query(CoreField).filter(
            and_(CoreField.table_id == id, or_(CoreField.field_name.like(f'%{field.fieldName}%'),
                                               CoreField.field_name.like(f'%{field.fieldName.lower()}%'),
                                               CoreField.field_name.like(f'%{field.fieldName.upper()}%')))).order_by(
            CoreField.field_index.asc()).all()
    else:
        return session.query(CoreField).filter(CoreField.table_id == id).order_by(CoreField.field_index.asc()).all()


def update_field(session: SessionDep, item: CoreField):
    """
    是什么：update_field 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
    record = session.query(CoreField).filter(CoreField.id == item.id).first()
    record.checked = item.checked
    record.custom_comment = item.custom_comment
    session.add(record)
    session.commit()
