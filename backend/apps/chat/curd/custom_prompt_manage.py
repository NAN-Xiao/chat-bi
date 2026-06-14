import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select

from apps.chat.curd.custom_prompt import CustomPromptTypeEnum
from apps.chat.models.custom_prompt_model import CustomPrompt, CustomPromptInfo
from apps.datasource.models.datasource import CoreDatasource
from common.core.deps import SessionDep


def _normalize_type(custom_prompt_type: CustomPromptTypeEnum | str | None) -> CustomPromptTypeEnum:
    if isinstance(custom_prompt_type, CustomPromptTypeEnum):
        return custom_prompt_type
    try:
        return CustomPromptTypeEnum(str(custom_prompt_type))
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported custom prompt type")


def _normalize_ids(datasource_ids: Optional[list[int]]) -> list[int]:
    result: list[int] = []
    for item in datasource_ids or []:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(result))


def _datasource_name_map(session: SessionDep, datasource_ids: list[int]) -> dict[int, str]:
    if not datasource_ids:
        return {}
    rows = session.execute(
        select(CoreDatasource.id, CoreDatasource.name).where(CoreDatasource.id.in_(datasource_ids))
    ).all()
    return {int(row.id): row.name for row in rows}


def _to_info(row: CustomPrompt, ds_names: Optional[dict[int, str]] = None) -> CustomPromptInfo:
    datasource_ids = _normalize_ids(row.datasource_ids)
    ds_names = ds_names or {}
    return CustomPromptInfo(
        id=row.id,
        type=_normalize_type(row.type) if row.type else None,
        create_time=row.create_time,
        name=row.name,
        prompt=row.prompt,
        specific_ds=bool(row.specific_ds),
        datasource_ids=datasource_ids,
        datasource_names=[ds_names[item] for item in datasource_ids if item in ds_names],
    )


def _access_conditions(accessible_datasource_ids: Optional[set[int]], include_global: bool = True):
    if accessible_datasource_ids is None:
        return []
    conditions = []
    for ds_id in accessible_datasource_ids:
        conditions.append(CustomPrompt.datasource_ids.contains([int(ds_id)]))
    if include_global:
        conditions.extend([
            CustomPrompt.datasource_ids == [],
            CustomPrompt.specific_ds == False,
            CustomPrompt.specific_ds.is_(None),
        ])
    return conditions


def _build_query(
        custom_prompt_type: CustomPromptTypeEnum | str,
        name: Optional[str] = None,
        dslist: Optional[list[int]] = None,
        accessible_datasource_ids: Optional[set[int]] = None,
        include_global: bool = True,
):
    prompt_type = _normalize_type(custom_prompt_type)
    stmt = select(CustomPrompt).where(CustomPrompt.type == prompt_type)

    if name and name.strip():
        keyword = f"%{name.strip()}%"
        stmt = stmt.where(or_(CustomPrompt.name.ilike(keyword), CustomPrompt.prompt.ilike(keyword)))

    access_conditions = _access_conditions(accessible_datasource_ids, include_global)
    if accessible_datasource_ids is not None:
        stmt = stmt.where(or_(*access_conditions) if access_conditions else False)

    if dslist:
        ds_conditions = [CustomPrompt.datasource_ids.contains([int(ds_id)]) for ds_id in dslist]
        if include_global:
            ds_conditions.extend([
                CustomPrompt.datasource_ids == [],
                CustomPrompt.specific_ds == False,
                CustomPrompt.specific_ds.is_(None),
            ])
        stmt = stmt.where(or_(*ds_conditions))

    return stmt


def page_custom_prompts(
        session: SessionDep,
        custom_prompt_type: CustomPromptTypeEnum | str,
        current_page: int = 1,
        page_size: int = 10,
        name: Optional[str] = None,
        dslist: Optional[list[int]] = None,
        accessible_datasource_ids: Optional[set[int]] = None,
        include_global: bool = True,
):
    stmt = _build_query(custom_prompt_type, name, dslist, accessible_datasource_ids, include_global)
    total_count = session.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    page_size = max(10, page_size)
    total_pages = (total_count + page_size - 1) // page_size if total_count else 0
    current_page = max(1, min(current_page, total_pages)) if total_pages > 0 else 1

    rows = session.execute(
        stmt.order_by(CustomPrompt.create_time.desc(), CustomPrompt.id.desc())
        .offset((current_page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    datasource_ids: list[int] = []
    for row in rows:
        datasource_ids.extend(_normalize_ids(row.datasource_ids))
    ds_names = _datasource_name_map(session, list(dict.fromkeys(datasource_ids)))

    return current_page, page_size, total_count, total_pages, [_to_info(row, ds_names) for row in rows]


def get_all_custom_prompts(
        session: SessionDep,
        custom_prompt_type: CustomPromptTypeEnum | str,
        name: Optional[str] = None,
        dslist: Optional[list[int]] = None,
        accessible_datasource_ids: Optional[set[int]] = None,
        include_global: bool = True,
) -> list[CustomPromptInfo]:
    stmt = _build_query(custom_prompt_type, name, dslist, accessible_datasource_ids, include_global)
    rows = session.execute(stmt.order_by(CustomPrompt.create_time.desc(), CustomPrompt.id.desc())).scalars().all()

    datasource_ids: list[int] = []
    for row in rows:
        datasource_ids.extend(_normalize_ids(row.datasource_ids))
    ds_names = _datasource_name_map(session, list(dict.fromkeys(datasource_ids)))

    return [_to_info(row, ds_names) for row in rows]


def get_custom_prompt(session: SessionDep, prompt_id: int) -> CustomPromptInfo:
    row = session.get(CustomPrompt, prompt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    ds_names = _datasource_name_map(session, _normalize_ids(row.datasource_ids))
    return _to_info(row, ds_names)


def create_custom_prompt(session: SessionDep, info: CustomPromptInfo) -> int:
    if not info.name or not info.name.strip():
        raise HTTPException(status_code=400, detail="Prompt name is required")
    if not info.prompt or not info.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt content is required")

    prompt_type = _normalize_type(info.type)
    specific_ds = bool(info.specific_ds)
    datasource_ids = _normalize_ids(info.datasource_ids) if specific_ds else []
    if specific_ds and not datasource_ids:
        raise HTTPException(status_code=400, detail="Datasource is required")

    exists = session.execute(
        select(func.count()).select_from(CustomPrompt).where(
            CustomPrompt.type == prompt_type,
            CustomPrompt.name == info.name.strip(),
            CustomPrompt.id != (info.id or 0),
        )
    ).scalar()
    if exists:
        raise HTTPException(status_code=400, detail="Prompt name already exists")

    row = CustomPrompt(
        type=prompt_type,
        create_time=datetime.datetime.now(),
        name=info.name.strip(),
        prompt=info.prompt.strip(),
        specific_ds=specific_ds,
        datasource_ids=datasource_ids,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    return int(row.id)


def update_custom_prompt(session: SessionDep, info: CustomPromptInfo) -> int:
    if not info.id:
        return create_custom_prompt(session, info)
    row = session.get(CustomPrompt, int(info.id))
    if not row:
        raise HTTPException(status_code=404, detail="Custom prompt not found")
    if not info.name or not info.name.strip():
        raise HTTPException(status_code=400, detail="Prompt name is required")
    if not info.prompt or not info.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt content is required")

    prompt_type = _normalize_type(info.type or row.type)
    specific_ds = bool(info.specific_ds)
    datasource_ids = _normalize_ids(info.datasource_ids) if specific_ds else []
    if specific_ds and not datasource_ids:
        raise HTTPException(status_code=400, detail="Datasource is required")

    exists = session.execute(
        select(func.count()).select_from(CustomPrompt).where(
            CustomPrompt.type == prompt_type,
            CustomPrompt.name == info.name.strip(),
            CustomPrompt.id != int(info.id),
        )
    ).scalar()
    if exists:
        raise HTTPException(status_code=400, detail="Prompt name already exists")

    row.type = prompt_type
    row.name = info.name.strip()
    row.prompt = info.prompt.strip()
    row.specific_ds = specific_ds
    row.datasource_ids = datasource_ids
    session.add(row)
    session.flush()
    return int(row.id)


def delete_custom_prompts(session: SessionDep, ids: list[int]):
    normalized_ids = _normalize_ids(ids)
    if not normalized_ids:
        return
    session.execute(delete(CustomPrompt).where(CustomPrompt.id.in_(normalized_ids)))
    session.flush()


def batch_create_custom_prompts(session: SessionDep, info_list: list[CustomPromptInfo]):
    failed_records = []
    success_count = 0
    seen: set[tuple[str, str, str]] = set()

    datasource_name_to_id = {
        row.name.strip(): int(row.id)
        for row in session.execute(select(CoreDatasource.id, CoreDatasource.name)).all()
        if row.name
    }

    for info in info_list:
        try:
            specific_ds = bool(info.specific_ds)
            datasource_ids = _normalize_ids(info.datasource_ids)
            if specific_ds and not datasource_ids and info.datasource_names:
                datasource_ids = [
                    datasource_name_to_id[name.strip()]
                    for name in info.datasource_names
                    if name and name.strip() in datasource_name_to_id
                ]
            if specific_ds and not datasource_ids:
                raise HTTPException(status_code=400, detail="Datasource is required")
            info.datasource_ids = datasource_ids

            key = (
                str(_normalize_type(info.type).value),
                (info.name or "").strip().lower(),
                ",".join(str(item) for item in sorted(datasource_ids)) if specific_ds else "all",
            )
            if key in seen:
                raise HTTPException(status_code=400, detail="Duplicate prompt in import file")
            seen.add(key)
            create_custom_prompt(session, info)
            session.commit()
            success_count += 1
        except Exception as exc:
            failed_records.append({"data": info, "errors": [getattr(exc, "detail", str(exc))]})
            session.rollback()

    return {
        "success_count": success_count,
        "failed_records": failed_records,
        "duplicate_count": 0,
        "original_count": len(info_list),
    }
