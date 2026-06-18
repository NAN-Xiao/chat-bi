import asyncio
import io
import os
from fastapi import HTTPException
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, UploadFile, Query
from fastapi.responses import StreamingResponse
from sqlmodel import select

from apps.chat.models.chat_model import AxisObj
from apps.data_training.curd.data_training import page_data_training, create_training, update_training, delete_training, \
    enable_training, get_all_data_training, batch_create_training
from apps.datasource.crud.permission import (
    current_tenant_id,
    get_datasource_ids_with_min_role,
    has_datasource_access,
)
from apps.data_training.models.data_training_model import DataTraining
from apps.data_training.models.data_training_model import DataTrainingInfo
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.user import is_system_admin
from common.core.config import settings
from common.core.deps import SessionDep, CurrentUser, Trans
from common.utils.data_format import DataFormat
from common.utils.excel import get_excel_column_count
from common.utils.file_utils import AppFileUtils
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log

router = APIRouter(tags=["SQL Examples"], prefix="/system/data-training")


def _visible_datasource_ids(session: SessionDep, current_user: CurrentUser) -> Optional[set[int]]:
    return get_datasource_ids_with_min_role(session, current_user, "project_viewer")


def _can_manage_tenant_semantic_layer(current_user: CurrentUser) -> bool:
    tenant_role = normalize_tenant_role(getattr(current_user, "tenant_role", None))
    return is_system_admin(current_user) or tenant_role in TENANT_ADMIN_ROLES


def _require_training_admin(session: SessionDep, current_user: CurrentUser, info: DataTrainingInfo):
    if not _can_manage_tenant_semantic_layer(current_user):
        raise HTTPException(status_code=403, detail="Tenant admin access is required")
    tenant_id = current_tenant_id(current_user)
    if info.id:
        existing = session.get(DataTraining, int(info.id))
        if not existing:
            raise HTTPException(status_code=404, detail="SQL example not found")
        if int(existing.tenant_id) != tenant_id:
            raise HTTPException(status_code=404, detail="SQL example not found")
    if info.datasource is not None and not has_datasource_access(session, current_user, info.datasource):
        raise HTTPException(status_code=403, detail="Datasource access is required")


def _require_training_ids_admin(session: SessionDep, current_user: CurrentUser, ids: list[int]):
    if not ids:
        return
    if not _can_manage_tenant_semantic_layer(current_user):
        raise HTTPException(status_code=403, detail="Tenant admin access is required")
    rows = session.exec(
        select(DataTraining.datasource).where(
            DataTraining.id.in_(ids),
            DataTraining.tenant_id == current_tenant_id(current_user),
        )
    ).all()
    if len(rows) != len(set(ids)):
        raise HTTPException(status_code=404, detail="SQL example not found")


@router.get("/page/{current_page}/{page_size}", summary=f"{PLACEHOLDER_PREFIX}get_dt_page")
async def pager(session: SessionDep, current_user: CurrentUser, current_page: int, page_size: int,
                question: Optional[str] = Query(None, description="搜索问题(可选)"),
                datasource: Optional[int] = Query(None, description="数据源ID(可选)")):
    datasource_ids = _visible_datasource_ids(session, current_user)
    if datasource is not None:
        if datasource_ids is not None and datasource not in datasource_ids:
            raise HTTPException(status_code=403, detail="Datasource access is required")
        datasource_ids = {datasource}
    current_page, page_size, total_count, total_pages, _list = page_data_training(session, current_page, page_size,
                                                                                  question, datasource_ids,
                                                                                  current_tenant_id(current_user))

    return {
        "current_page": current_page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "data": _list
    }


@router.put("", response_model=int, summary=f"{PLACEHOLDER_PREFIX}create_or_update_dt")
@system_log(LogConfig(operation_type=OperationType.CREATE_OR_UPDATE, module=OperationModules.DATA_TRAINING,resource_id_expr='info.id', result_id_expr="result_self"))
async def create_or_update(session: SessionDep, current_user: CurrentUser, trans: Trans, info: DataTrainingInfo):
    info.tenant_id = current_tenant_id(current_user)
    _require_training_admin(session, current_user, info)
    if info.id:
        return update_training(session, info, trans)
    else:
        return create_training(session, info, trans)


@router.delete("", summary=f"{PLACEHOLDER_PREFIX}delete_dt")
@system_log(LogConfig(operation_type=OperationType.DELETE, module=OperationModules.DATA_TRAINING,resource_id_expr='id_list'))
async def delete(session: SessionDep, current_user: CurrentUser, id_list: list[int]):
    _require_training_ids_admin(session, current_user, id_list)
    delete_training(session, id_list, current_tenant_id(current_user))


@router.get("/{id}/enable/{enabled}", summary=f"{PLACEHOLDER_PREFIX}enable_dt")
@system_log(LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.DATA_TRAINING,resource_id_expr='id'))
async def enable(session: SessionDep, current_user: CurrentUser, id: int, enabled: bool, trans: Trans):
    _require_training_ids_admin(session, current_user, [id])
    enable_training(session, id, enabled, trans, current_tenant_id(current_user))


@router.get("/export", summary=f"{PLACEHOLDER_PREFIX}export_dt")
@system_log(LogConfig(operation_type=OperationType.EXPORT, module=OperationModules.DATA_TRAINING))
async def export_excel(session: SessionDep, trans: Trans, current_user: CurrentUser,
                       question: Optional[str] = Query(None, description="搜索术语(可选)"),
                       datasource: Optional[int] = Query(None, description="数据源ID(可选)")):
    datasource_ids = _visible_datasource_ids(session, current_user)
    if datasource is not None:
        if datasource_ids is not None and datasource not in datasource_ids:
            raise HTTPException(status_code=403, detail="Datasource access is required")
        datasource_ids = {datasource}

    def inner():
        _list = get_all_data_training(session, question, datasource_ids, current_tenant_id(current_user))

        data_list = []
        for obj in _list:
            _data = {
                "question": obj.question,
                "description": obj.description,
                "datasource_name": obj.datasource_name,
                "advanced_application_name": obj.advanced_application_name,
            }
            data_list.append(_data)

        fields = []
        fields.append(AxisObj(name=trans('i18n_data_training.problem_description'), value='question'))
        fields.append(AxisObj(name=trans('i18n_data_training.sample_sql'), value='description'))
        fields.append(AxisObj(name=trans('i18n_data_training.effective_data_sources'), value='datasource_name'))
        fields.append(
            AxisObj(name=trans('i18n_data_training.advanced_application'), value='advanced_application_name'))

        md_data, _fields_list = DataFormat.convert_object_array_for_pandas(fields, data_list)

        df = pd.DataFrame(md_data, columns=_fields_list)

        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine='xlsxwriter',
                            engine_kwargs={'options': {'strings_to_numbers': False}}) as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/template", summary=f"{PLACEHOLDER_PREFIX}excel_template_dt")
async def excel_template(trans: Trans, current_user: CurrentUser):
    def inner():
        data_list = []
        _data1 = {
            "question": '查询TEST表内所有ID',
            "description": 'SELECT id FROM TEST',
            "datasource_name": '生效数据源1',
            "advanced_application_name": '生效高级应用名称',
        }
        data_list.append(_data1)

        fields = []
        fields.append(AxisObj(name=trans('i18n_data_training.problem_description_template'), value='question'))
        fields.append(AxisObj(name=trans('i18n_data_training.sample_sql_template'), value='description'))
        fields.append(
            AxisObj(name=trans('i18n_data_training.effective_data_sources_template'), value='datasource_name'))
        fields.append(
            AxisObj(name=trans('i18n_data_training.advanced_application_template'),
                    value='advanced_application_name'))

        md_data, _fields_list = DataFormat.convert_object_array_for_pandas(fields, data_list)

        df = pd.DataFrame(md_data, columns=_fields_list)

        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine='xlsxwriter',
                            engine_kwargs={'options': {'strings_to_numbers': False}}) as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


path = settings.EXCEL_PATH

from sqlalchemy.orm import sessionmaker, scoped_session
from common.core.db import engine
from sqlmodel import Session

session_maker = scoped_session(sessionmaker(bind=engine, class_=Session))


@router.post("/uploadExcel", summary=f"{PLACEHOLDER_PREFIX}upload_excel_dt")
@system_log(LogConfig(operation_type=OperationType.IMPORT, module=OperationModules.DATA_TRAINING))
async def upload_excel(session: SessionDep, trans: Trans, current_user: CurrentUser,
    datasource: Optional[int] = Query(None, description="数据源ID(可选)"),
                       file: UploadFile = File(...)):
    if datasource is None:
        raise HTTPException(status_code=400, detail="Datasource is required")
    if not _can_manage_tenant_semantic_layer(current_user):
        raise HTTPException(status_code=403, detail="Tenant admin access is required")
    if not has_datasource_access(session, current_user, datasource):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

    os.makedirs(path, exist_ok=True)
    base_filename, filename = AppFileUtils.safe_upload_name(file.filename, ALLOWED_EXTENSIONS)
    save_path = str(AppFileUtils.safe_path(path, filename))
    with open(save_path, "wb") as f:
        f.write(await AppFileUtils.read_upload_limited(file))

    use_cols = [0, 1, 2, 3]  # 问题, 描述, 数据源名称, 高级应用名称

    def inner():

        session = session_maker()

        sheet_names = pd.ExcelFile(save_path).sheet_names

        import_data = []

        for sheet_name in sheet_names:

            if get_excel_column_count(save_path, sheet_name) < len(use_cols):
                raise Exception(trans("i18n_excel_import.col_num_not_match"))

            df = pd.read_excel(
                save_path,
                sheet_name=sheet_name,
                engine='calamine',
                header=0,
                usecols=use_cols,
                dtype=str
            ).fillna("")

            for index, row in df.iterrows():
                # 跳过空行
                if row.isnull().all():
                    continue

                question = row[0].strip() if pd.notna(row[0]) and row[0].strip() else ''
                description = row[1].strip() if pd.notna(row[1]) and row[1].strip() else ''
                datasource_name = row[2].strip() if pd.notna(row[2]) and row[2].strip() else ''

                advanced_application_name = row[3].strip() if len(row) > 3 and pd.notna(row[3]) and row[3].strip() else ''

                import_data.append(
                    DataTrainingInfo(question=question, description=description,
                                     datasource=datasource,
                                     datasource_name=datasource_name,
                                     advanced_application_name=advanced_application_name))

        res = batch_create_training(session, import_data, trans, current_tenant_id(current_user))

        failed_records = res['failed_records']

        error_excel_filename = None

        if len(failed_records) > 0:
            data_list = []
            for obj in failed_records:
                _data = {
                    "question": obj['data'].question,
                    "description": obj['data'].description,
                    "datasource_name": obj['data'].datasource_name,
                    "advanced_application_name": obj['data'].advanced_application_name,
                    "errors": obj['errors']
                }
                data_list.append(_data)

            fields = []
            fields.append(AxisObj(name=trans('i18n_data_training.problem_description'), value='question'))
            fields.append(AxisObj(name=trans('i18n_data_training.sample_sql'), value='description'))
            fields.append(AxisObj(name=trans('i18n_data_training.effective_data_sources'), value='datasource_name'))
            fields.append(
                AxisObj(name=trans('i18n_data_training.advanced_application'), value='advanced_application_name'))
            fields.append(AxisObj(name=trans('i18n_data_training.error_info'), value='errors'))

            md_data, _fields_list = DataFormat.convert_object_array_for_pandas(fields, data_list)

            df = pd.DataFrame(md_data, columns=_fields_list)
            error_excel_filename = f"{base_filename}_error.xlsx"
            save_error_path = os.path.join(path, error_excel_filename)
            # 保存 DataFrame 到 Excel
            df.to_excel(save_error_path, index=False)

        return {
            'success_count': res['success_count'],
            'failed_count': len(failed_records),
            'duplicate_count': res['duplicate_count'],
            'original_count': res['original_count'],
            'error_excel_filename': error_excel_filename,
        }

    return await asyncio.to_thread(inner)
