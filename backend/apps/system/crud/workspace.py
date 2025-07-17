
from typing import Optional
from sqlmodel import Session, func, select, update

from apps.system.models.system_model import UserWsModel
from apps.system.models.user import UserModel

async def reset_single_user_oid(session: Session, uid: int, oid: int, add: Optional[bool] = True):
    user_model = session.get(UserModel, uid)
    if not user_model:
        return
    origin_oid = user_model.oid
    if add and (not origin_oid or origin_oid == 0):
        user_model.oid = oid
        session.add(user_model)
    if not add and origin_oid and origin_oid == oid:
        user_model.oid = 0
        user_ws = session.exec(select(UserWsModel).where(UserWsModel.uid == uid, UserWsModel.oid != oid)).first()
        if user_ws:
            user_model.oid = user_ws.oid
        session.add(user_model)
    
async def reset_user_oid(session: Session, oid: int):
    stmt = (
        select(
            UserModel.id,
            UserModel.oid,
            func.coalesce(
                func.array_remove(
                    func.array_agg(UserWsModel.oid),
                    None
                ),
                []
            ).label("oid_list")
        )
        .join(UserWsModel, UserModel.id == UserWsModel.uid, isouter=True)
        .where(UserModel.id != 1)
        .group_by(UserModel.id)
    )
    
    user_filter = (
        select(UserModel.id)
            .join(UserWsModel, UserModel.id == UserWsModel.uid)
            .where(UserWsModel.oid == oid)
            .distinct()
    )
    stmt = stmt.where(UserModel.id.in_(user_filter))
    
    result_user_list = session.exec(stmt)
    for row in result_user_list:
        result_dict = {}
        for item, key in zip(row, row._fields):
            result_dict[key] = item
                
        origin_oid = result_dict['oid']
        oid_list: list = list(filter(lambda x: x != oid, result_dict['oid_list']))
        if origin_oid not in oid_list:
            result_dict['oid'] = oid_list[0] if oid_list else 0
            if result_dict['oid'] != origin_oid:
                result_dict.pop("oid_list", None)
                update_stmt = update(UserModel).where(UserModel.id == result_dict['id']).values(oid=result_dict['oid'])
                session.exec(update_stmt)
