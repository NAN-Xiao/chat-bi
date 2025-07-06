from fastapi import APIRouter
from sqlmodel import select    
from apps.system.models.system_model import WorkspaceBase, WorkspaceEditor, WorkspaceModel
from common.core.deps import SessionDep
from common.utils.time import get_timestamp

router = APIRouter(tags=["system/workspace"], prefix="/system/workspace")

@router.get("", response_model=list[WorkspaceModel])
async def query(session: SessionDep):
    return session.exec(select(WorkspaceModel).order_by(WorkspaceModel.create_time)).all()

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
async def get_one(session: SessionDep, id: int):
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    return db_model

@router.delete("/{id}")  
async def delete(session: SessionDep, id: int):
    db_model = session.get(WorkspaceModel, id)
    if not db_model:
        raise ValueError(f"WorkspaceModel with id {id} not found")
    session.delete(db_model)
    session.commit()