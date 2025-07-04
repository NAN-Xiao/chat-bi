import json
from typing import List, Union
from apps.system.schemas.ai_model_schema import AiModelConfigItem, AiModelCreator, AiModelEditor, AiModelGridItem
from fastapi import APIRouter, Query
from sqlmodel import func, select

from apps.system.models.system_model import AiModelDetail
from common.core.deps import SessionDep
from common.utils.time import get_timestamp

router = APIRouter(tags=["system/aimodel"], prefix="/system/aimodel")

@router.get("", response_model=list[AiModelGridItem])
async def query(
        session: SessionDep,
        keyword: Union[str, None] = Query(default=None, max_length=255)
):
    statement = select(AiModelDetail.id, 
                       AiModelDetail.name, 
                       AiModelDetail.model_type, 
                       AiModelDetail.base_model, 
                       AiModelDetail.supplier, 
                       AiModelDetail.default_model)
    if keyword is not None:
        statement = statement.where(AiModelDetail.name.like(f"%{keyword}%"))
    
    items = session.exec(statement).all()
    return items

@router.get("/{id}", response_model=AiModelEditor)
async def get_model_by_id(
        session: SessionDep,
        id: int
):
    db_model = session.get(AiModelDetail, id)
    if not db_model:
        raise ValueError(f"AiModelDetail with id {id} not found")

    config_list: List[AiModelConfigItem] = []
    if db_model.config:
        try:
            raw = json.loads(db_model.config)
            config_list = [AiModelConfigItem(**item) for item in raw]
        except Exception:
            pass
    data = AiModelDetail.model_validate(db_model).model_dump(exclude_unset=True)
    data.pop("config", None)
    data["config_list"] = config_list
    return AiModelEditor(**data)

@router.post("")
async def add_model(
        session: SessionDep,
        creator: AiModelCreator
):
    data = creator.model_dump(exclude_unset=True)
    data["config"] = json.dumps([item.model_dump(exclude_unset=True) for item in creator.config_list])
    data.pop("config_list", None)
    detail = AiModelDetail.model_validate(data)
    detail.create_time = get_timestamp()
    count = session.exec(select(func.count(AiModelDetail.id))).one()
    if count == 0:
        detail.default_model = True
    session.add(detail)
    session.commit()

@router.put("")
async def update_model(
        session: SessionDep,
        editor: AiModelEditor
):
    id = int(editor.id)
    data = editor.model_dump(exclude_unset=True)
    data["config"] = json.dumps([item.model_dump(exclude_unset=True) for item in editor.config_list])
    data.pop("config_list", None)
    db_model = session.get(AiModelDetail, id)
    update_data = AiModelDetail.model_validate(data)
    db_model.sqlmodel_update(update_data)
    session.add(db_model)
    session.commit()

@router.delete("/{id}")
async def delete_model(
        session: SessionDep,
        id: int
):
    item = session.get(AiModelDetail, id)
    session.delete(item)
    session.commit()
    