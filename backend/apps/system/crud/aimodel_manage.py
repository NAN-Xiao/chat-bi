from sqlmodel import Session, select

from apps.system.models.system_model import AiModelDetail, AiModelBrief
from common.core.db import engine
from common.utils.utils import AppLogUtil


async def async_model_info():
    """
    是什么：async_model_info 是 backend/apps/system/crud/aimodel_manage.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 async_model_info 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    with Session(engine) as session:
        model_list = session.exec(select(AiModelDetail)).all()
        any_model_change = False
        if model_list:
            for model in model_list:
                current_model_change = False
                if model.supplier and model.supplier == 12:
                    model.supplier = 15
                    any_model_change = True
                    current_model_change = True
                if current_model_change:
                    session.add(model)
        if any_model_change:
            session.commit()
            AppLogUtil.info("✅ AI 模型历史数据兼容处理完成")


def get_ai_model_list(session: Session, with_default: bool = True):
    """
    是什么：get_ai_model_list 是 backend/apps/system/crud/aimodel_manage.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    where_condition = True
    if with_default:
        where_condition = AiModelDetail.default_model == True
    stmt = (
        select(
            AiModelDetail.id,
            AiModelDetail.name,
            AiModelDetail.default_model,
            AiModelDetail.supplier,
        )
        .order_by(AiModelDetail.default_model.desc())
    )
    if with_default:
        stmt = stmt.where(where_condition)
    rows = session.exec(stmt).all()

    return [
        AiModelBrief(
            id=row[0],
            name=row[1],
            default_model=row[2],
            supplier=row[3],
        )
        for row in rows
    ]
