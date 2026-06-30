from common.core.deps import SessionDep
from ..models.datasource import CoreField, FieldObj
from sqlalchemy import or_, and_


def delete_field_by_ds_id(session: SessionDep, id: int):
    """
    是什么：delete_field_by_ds_id 是 backend/apps/datasource/crud/field.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理数据源相关数据、缓存或临时状态。
    """
    session.query(CoreField).filter(CoreField.ds_id == id).delete(synchronize_session=False)
    session.commit()


def get_fields_by_table_id(session: SessionDep, id: int, field: FieldObj):
    """
    是什么：get_fields_by_table_id 是 backend/apps/datasource/crud/field.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据源相关数据，整理后返回给调用方。
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
    是什么：update_field 是 backend/apps/datasource/crud/field.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：更新数据源相关状态、配置或持久化数据，并保持后续流程可继续使用。
    """
    record = session.query(CoreField).filter(CoreField.id == item.id).first()
    record.checked = item.checked
    record.custom_comment = item.custom_comment
    session.add(record)
    session.commit()
