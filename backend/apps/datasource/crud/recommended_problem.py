"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import datetime

from sqlmodel import select

from common.core.deps import SessionDep, CurrentUser, Trans
from ..models.datasource import DsRecommendedProblem, RecommendedProblemBase, CoreDatasource, RecommendedProblemResponse
import orjson


def get_datasource_recommended(session: SessionDep, ds_id: int):
    """
    是什么：get_datasource_recommended 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    statement = select(DsRecommendedProblem).where(DsRecommendedProblem.datasource_id == ds_id)
    dsRecommendedProblem = session.exec(statement).all()
    return dsRecommendedProblem

def get_datasource_recommended_chart(session: SessionDep, ds_id: int):
    """
    是什么：get_datasource_recommended_chart 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    statement = select(DsRecommendedProblem.question).where(DsRecommendedProblem.datasource_id == ds_id)
    dsRecommendedProblems = session.exec(statement).all()
    return dsRecommendedProblems


def get_datasource_recommended_base(session: SessionDep, ds_id: int):
    """
    是什么：get_datasource_recommended_base 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    statement = select(CoreDatasource.id,CoreDatasource.recommended_config).where(CoreDatasource.id == ds_id)
    datasourceBase = session.exec(statement).first()
    if datasourceBase is None:
        return RecommendedProblemResponse(ds_id,0,None)
    elif datasourceBase.recommended_config == 1:
        return RecommendedProblemResponse(ds_id,1,None)
    else:
        dsRecommendedProblems = session.exec(select(DsRecommendedProblem.question).where(DsRecommendedProblem.datasource_id == ds_id)).all()
        return RecommendedProblemResponse(ds_id,datasourceBase.recommended_config, orjson.dumps(dsRecommendedProblems).decode())

def save_recommended_problem(session: SessionDep,user: CurrentUser, data_info: RecommendedProblemBase):
    """
    是什么：save_recommended_problem 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存数据源需要的东西，让后续流程能继续往下走。
    """
    session.query(DsRecommendedProblem).filter(DsRecommendedProblem.datasource_id == data_info.datasource_id).delete(synchronize_session=False)
    problemInfo = data_info.problemInfo
    if problemInfo is not None:
        for problemItem in problemInfo:
            problemItem.id = None
            problemItem.create_time = datetime.datetime.now()
            problemItem.create_by = user.id
            record = DsRecommendedProblem(**problemItem.model_dump())
            session.add(record)
            session.flush()
            session.refresh(record)
    session.commit()
