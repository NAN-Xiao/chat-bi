from fastapi import APIRouter
from sqlmodel import select    
from apps.system.models.system_model import WorkspaceBase, WorkspaceEditor, WorkspaceModel
from common.core.deps import SessionDep, Trans
from common.utils.time import get_timestamp

router = APIRouter(tags=["system/workspace"], prefix="/system/workspace")

@router.get("", response_model=list[WorkspaceModel])
async def query(session: SessionDep, trans: Trans):
    list_result = session.exec(select(WorkspaceModel).order_by(WorkspaceModel.create_time)).all()
    for ws in list_result:
        if ws.name.startswith('i18n'):
            ws.name =  trans(ws.name)
    return list_result

@router.post("")
async def add(session: SessionDep, creator: WorkspaceBase):
    db_model = WorkspaceModel.model_validate(creator)
    db_model.create_time = get_timestamp()
    session.add(db_model)
    session.commit()
    
@router.put("")
async def update(session: SessionDep, editor: WorkspaceEditor):
    id = editor.id
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    update_data = WorkspaceModel.model_validate(editor)
    db_model.sqlmodel_update(update_data)
    session.add(db_model)
    session.commit()

@router.get("/{id}", response_model=WorkspaceModel)    
async def get_one(session: SessionDep, trans: Trans, id: int):
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    if db_model.name.startswith('i18n'):
        db_model.name = trans(db_model.name)
    return db_model

@router.delete("/{id}")  
async def delete(session: SessionDep, id: int):
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    session.delete(db_model)
    session.commit()

@router.post("/user/{id}")     
async def bindUser(session: SessionDep, user_id: int):
    pass