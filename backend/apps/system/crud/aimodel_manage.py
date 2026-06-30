"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from sqlmodel import Session, select

from apps.system.models.system_model import AiModelDetail, AiModelBrief
from common.core.db import engine
from common.utils.utils import AppLogUtil


async def async_model_info():
    """
    是什么：async_model_info 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：get_ai_model_list 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
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
