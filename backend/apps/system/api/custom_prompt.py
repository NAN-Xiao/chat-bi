import asyncio
import hashlib
import io
import os
import uuid
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlmodel import Session, select

from apps.chat.curd.custom_prompt import CustomPromptTypeEnum
from apps.chat.curd.custom_prompt_manage import (
    batch_create_custom_prompts,
    create_custom_prompt,
    delete_custom_prompts,
    get_all_custom_prompts,
    get_custom_prompt,
    page_custom_prompts,
    update_custom_prompt,
)
from apps.chat.models.chat_model import AxisObj
from apps.chat.models.custom_prompt_model import CustomPrompt, CustomPromptInfo
from apps.datasource.crud.permission import (
    PROJECT_ROLE_ADMIN,
    get_datasource_ids_with_min_role,
    has_datasource_role,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.user import is_system_admin
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.config import settings
from common.core.db import engine
from common.core.deps import CurrentUser, SessionDep, Trans
from common.utils.data_format import DataFormat
from common.utils.excel import get_excel_column_count

router = APIRouter(tags=["CustomPrompt"], prefix="/system/custom_prompt", include_in_schema=False)

path = settings.EXCEL_PATH
session_maker = scoped_session(sessionmaker(bind=engine, class_=Session))


def _visible_datasource_ids(session: SessionDep, current_user: CurrentUser) -> Optional[set[int]]:
    return get_datasource_ids_with_min_role(session, current_user, "project_viewer")


def _require_prompt_scope_admin(session: SessionDep, current_user: CurrentUser, prompt: CustomPromptInfo | CustomPrompt):
    datasource_ids = getattr(prompt, "datasource_ids", None) or []
    specific_ds = bool(getattr(prompt, "specific_ds", False))
    if not specific_ds or not datasource_ids:
        if not is_system_admin(current_user):
            raise HTTPException(status_code=403, detail="Global prompt can only be maintained by system admins")
        return

    for datasource_id in datasource_ids:
        if not has_datasource_role(session, current_user, datasource_id, PROJECT_ROLE_ADMIN):
            raise HTTPException(status_code=403, detail="Project admin access is required")


def _require_prompt_admin(session: SessionDep, current_user: CurrentUser, info: CustomPromptInfo):
    if info.id:
        existing = session.get(CustomPrompt, int(info.id))
        if not existing:
            raise HTTPException(status_code=404, detail="Custom prompt not found")
        _require_prompt_scope_admin(session, current_user, existing)
    _require_prompt_scope_admin(session, current_user, info)


def _require_prompt_ids_admin(session: SessionDep, current_user: CurrentUser, ids: list[int]):
    if not ids:
        return
    rows = session.exec(select(CustomPrompt).where(CustomPrompt.id.in_(ids))).all()
    if len(rows) != len(set(ids)):
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    for row in rows:
        _require_prompt_scope_admin(session, current_user, row)


def _parse_type(value: str) -> CustomPromptTypeEnum:
    try:
        return CustomPromptTypeEnum(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt type")


def _split_query_ids(value) -> Optional[list[int]]:
    if value is None or value == "":
        return None
    values = value if isinstance(value, list) else [value]
    result: list[int] = []
    for item in values:
        if item is None or item == "":
            continue
        for part in str(item).replace(",", "_").split("_"):
            if part.strip():
                result.append(int(part.strip()))
    return result or None


def _query_ids(request: Request, key: str) -> Optional[list[int]]:
    return _split_query_ids(request.query_params.getlist(key))


@router.get("/{custom_prompt_type}/page/{current_page}/{page_size}")
async def pager(
        session: SessionDep,
        current_user: CurrentUser,
        request: Request,
        custom_prompt_type: str,
        current_page: int,
        page_size: int,
        name: Optional[str] = Query(None),
):
    visible_ids = _visible_datasource_ids(session, current_user)
    ds_ids = _query_ids(request, "dslist")
    if ds_ids and visible_ids is not None and not set(ds_ids).issubset(visible_ids):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    current_page, page_size, total_count, total_pages, data = page_custom_prompts(
        session,
        _parse_type(custom_prompt_type),
        current_page,
        page_size,
        name,
        ds_ids,
        visible_ids,
        is_system_admin(current_user),
    )
    return {
        "current_page": current_page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "data": data,
    }


@router.get("/template")
async def excel_template(trans: Trans):
    def inner():
        data_list = [
            {
                "name": trans("i18n_custom_prompt.prompt_word_name_template_example1"),
                "prompt": trans("i18n_custom_prompt.prompt_word_content_template_example1"),
                "datasource": trans("i18n_custom_prompt.effective_data_sources_template_example1"),
                "all_data_sources": "N",
            },
            {
                "name": trans("i18n_custom_prompt.prompt_word_name_template_example2"),
                "prompt": trans("i18n_custom_prompt.prompt_word_content_template_example2"),
                "datasource": "",
                "all_data_sources": "Y",
            },
        ]
        fields = [
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_name_template"), value="name"),
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_content_template"), value="prompt"),
            AxisObj(name=trans("i18n_custom_prompt.effective_data_sources_template"), value="datasource"),
            AxisObj(name=trans("i18n_custom_prompt.all_data_sources_template"), value="all_data_sources"),
        ]
        md_data, field_list = DataFormat.convert_object_array_for_pandas(fields, data_list)
        df = pd.DataFrame(md_data, columns=field_list)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_numbers": False}}) as writer:
            df.to_excel(writer, sheet_name="Sheet1", index=False)
        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/{prompt_id}")
async def get_one(session: SessionDep, current_user: CurrentUser, prompt_id: int):
    info = get_custom_prompt(session, prompt_id)
    if info.specific_ds and not has_datasource_role(session, current_user, info.datasource_ids, "project_viewer"):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    if not info.specific_ds and not is_system_admin(current_user):
        raise HTTPException(status_code=403, detail="Datasource access is required")
    return info


@router.put("")
@system_log(LogConfig(operation_type=OperationType.CREATE_OR_UPDATE, module=OperationModules.PROMPT_WORDS, resource_id_expr="info.id", result_id_expr="result_self"))
async def create_or_update(session: SessionDep, current_user: CurrentUser, info: CustomPromptInfo):
    _require_prompt_admin(session, current_user, info)
    if info.id:
        return update_custom_prompt(session, info)
    return create_custom_prompt(session, info)


@router.delete("")
@system_log(LogConfig(operation_type=OperationType.DELETE, module=OperationModules.PROMPT_WORDS, resource_id_expr="id_list"))
async def delete(session: SessionDep, current_user: CurrentUser, id_list: list[int]):
    _require_prompt_ids_admin(session, current_user, id_list)
    delete_custom_prompts(session, id_list)


@router.get("/{custom_prompt_type}/export")
@system_log(LogConfig(operation_type=OperationType.EXPORT, module=OperationModules.PROMPT_WORDS))
async def export_excel(
        session: SessionDep,
        current_user: CurrentUser,
        request: Request,
        trans: Trans,
        custom_prompt_type: str,
        name: Optional[str] = Query(None),
):
    visible_ids = _visible_datasource_ids(session, current_user)
    ds_ids = _query_ids(request, "dslist")
    if ds_ids and visible_ids is not None and not set(ds_ids).issubset(visible_ids):
        raise HTTPException(status_code=403, detail="Datasource access is required")

    def inner():
        rows = get_all_custom_prompts(
            session,
            _parse_type(custom_prompt_type),
            name,
            ds_ids,
            visible_ids,
            is_system_admin(current_user),
        )
        data_list = [
            {
                "name": row.name,
                "prompt": row.prompt,
                "datasource": ", ".join(row.datasource_names or []) if row.specific_ds else "",
                "all_data_sources": "N" if row.specific_ds else "Y",
            }
            for row in rows
        ]
        fields = [
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_name"), value="name"),
            AxisObj(name=trans("i18n_custom_prompt.prompt_word_content"), value="prompt"),
            AxisObj(name=trans("i18n_custom_prompt.effective_data_sources"), value="datasource"),
            AxisObj(name=trans("i18n_custom_prompt.all_data_sources"), value="all_data_sources"),
        ]
        md_data, field_list = DataFormat.convert_object_array_for_pandas(fields, data_list)
        df = pd.DataFrame(md_data, columns=field_list)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_numbers": False}}) as writer:
            df.to_excel(writer, sheet_name="Sheet1", index=False)
        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/{custom_prompt_type}/uploadExcel")
@system_log(LogConfig(operation_type=OperationType.IMPORT, module=OperationModules.PROMPT_WORDS))
async def upload_excel(
        session: SessionDep,
        trans: Trans,
        current_user: CurrentUser,
        custom_prompt_type: str,
        file: UploadFile = File(...),
):
    if not is_system_admin(current_user):
        raise HTTPException(status_code=403, detail="Global prompt import can only be maintained by system admins")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only support .xlsx/.xls")

    prompt_type = _parse_type(custom_prompt_type)
    os.makedirs(path, exist_ok=True)
    suffix = file.filename.rsplit(".", 1)[-1]
    base_filename = f"{file.filename.rsplit('.', 1)[0]}_{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:10]}"
    filename = f"{base_filename}.{suffix}"
    save_path = os.path.join(path, filename)
    with open(save_path, "wb") as f:
        f.write(await file.read())

    use_cols = [0, 1, 2, 3]

    def inner():
        db_session = session_maker()
        try:
            datasource_name_to_id = {
                row.name.strip(): int(row.id)
                for row in db_session.execute(select(CoreDatasource.id, CoreDatasource.name)).all()
                if row.name
            }
            import_data = []
            for sheet_name in pd.ExcelFile(save_path).sheet_names:
                if get_excel_column_count(save_path, sheet_name) < len(use_cols):
                    raise Exception(trans("i18n_excel_import.col_num_not_match"))
                df = pd.read_excel(
                    save_path,
                    sheet_name=sheet_name,
                    engine="calamine",
                    header=0,
                    usecols=use_cols,
                    dtype=str,
                ).fillna("")
                for _, row in df.iterrows():
                    if row.isnull().all():
                        continue
                    name = row[0].strip() if pd.notna(row[0]) and row[0].strip() else ""
                    prompt = row[1].strip() if pd.notna(row[1]) and row[1].strip() else ""
                    datasource_names = [item.strip() for item in row[2].split(",") if item.strip()] if pd.notna(row[2]) else []
                    all_datasource = bool(pd.notna(row[3]) and row[3].lower().strip() in ["y", "yes", "true"])
                    datasource_ids = [datasource_name_to_id[item] for item in datasource_names if item in datasource_name_to_id]
                    import_data.append(CustomPromptInfo(
                        type=prompt_type,
                        name=name,
                        prompt=prompt,
                        datasource_names=datasource_names,
                        datasource_ids=datasource_ids,
                        specific_ds=not all_datasource,
                    ))
            result = batch_create_custom_prompts(db_session, import_data)

            error_excel_filename = None
            if result["failed_records"]:
                error_rows = []
                for obj in result["failed_records"]:
                    data = obj["data"]
                    error_rows.append({
                        "name": data.name,
                        "prompt": data.prompt,
                        "datasource": ", ".join(data.datasource_names or []),
                        "all_data_sources": "N" if data.specific_ds else "Y",
                        "errors": ", ".join(str(item) for item in obj["errors"]),
                    })
                fields = [
                    AxisObj(name=trans("i18n_custom_prompt.prompt_word_name"), value="name"),
                    AxisObj(name=trans("i18n_custom_prompt.prompt_word_content"), value="prompt"),
                    AxisObj(name=trans("i18n_custom_prompt.effective_data_sources"), value="datasource"),
                    AxisObj(name=trans("i18n_custom_prompt.all_data_sources"), value="all_data_sources"),
                    AxisObj(name=trans("i18n_data_training.error_info"), value="errors"),
                ]
                md_data, field_list = DataFormat.convert_object_array_for_pandas(fields, error_rows)
                df = pd.DataFrame(md_data, columns=field_list)
                error_excel_filename = f"{base_filename}_error.xlsx"
                df.to_excel(os.path.join(path, error_excel_filename), index=False)

            return {
                "success_count": result["success_count"],
                "failed_count": len(result["failed_records"]),
                "duplicate_count": result["duplicate_count"],
                "original_count": result["original_count"],
                "error_excel_filename": error_excel_filename,
            }
        finally:
            db_session.close()

    return await asyncio.to_thread(inner)
