"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import json

from fastapi import Request
from sqlmodel import select

from common.core.deps import SessionDep
from common.utils.file_utils import AppFileUtils
from apps.system.models.system_model import SysArgModel


async def get_group_args(session: SessionDep, flag: str | None = None) -> list[SysArgModel]:
    """
    是什么：get_group_args 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    stmt = select(SysArgModel).order_by(SysArgModel.sort_no, SysArgModel.pkey)
    if flag:
        stmt = stmt.where(SysArgModel.pkey.startswith(f"{flag}."))
    return session.exec(stmt).all()


async def save_group_args(
    session: SessionDep,
    sys_args: list[SysArgModel],
    file_mapping: dict[str, str] | None = None,
) -> None:
    """
    是什么：save_group_args 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    file_mapping = file_mapping or {}
    keys = [item.pkey for item in sys_args if item.pkey]
    if not keys:
        return

    existing_rows = session.exec(select(SysArgModel).where(SysArgModel.pkey.in_(keys))).all()
    existing = {item.pkey: item for item in existing_rows}
    for item in sys_args:
        pkey = item.pkey
        short_key = pkey.split(".", 1)[1] if "." in pkey else pkey
        pval = file_mapping.get(short_key, item.pval)
        if item.ptype == "file":
            old = existing.get(pkey)
            if old and old.pval and old.pval != pval:
                AppFileUtils.delete_file(old.pval)

        if pkey in existing:
            row = existing[pkey]
            row.pval = None if pval is None else str(pval)
            row.ptype = item.ptype or "str"
            row.sort_no = item.sort_no or 1
        else:
            row = SysArgModel(
                pkey=pkey,
                pval=None if pval is None else str(pval),
                ptype=item.ptype or "str",
                sort_no=item.sort_no or 1,
            )
        session.add(row)

async def get_parameter_args(session: SessionDep) -> list[SysArgModel]:
    """
    是什么：get_parameter_args 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    group_args = await get_group_args(session=session)
    return [x for x in group_args if not x.pkey.startswith('appearance.')]

async def get_groups(session: SessionDep, flag: str) -> list[SysArgModel]:
    """
    是什么：get_groups 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    group_args = await get_group_args(session=session, flag=flag)
    return group_args

async def save_parameter_args(session: SessionDep, request: Request):
    """
    是什么：save_parameter_args 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
    allow_file_mapping = {
        """ "test_logo": { "types": [".jpg", ".jpeg", ".png"], "size": 5 * 1024 * 1024 } """
    }
    form_data = await request.form()
    files = form_data.getlist("files")
    json_text = form_data.get("data")
    sys_args = [
        SysArgModel(**{**item, "pkey": f"{item['pkey']}"})
        for item in json.loads(json_text)
        if "pkey" in item
    ]
    if not sys_args:
        return
    file_mapping = None
    if files:
        file_mapping = {}
        for file in files:
            origin_file_name = file.filename
            file_name, flag_name = AppFileUtils.split_filename_and_flag(origin_file_name)
            file.filename = file_name
            allow_limit_obj = allow_file_mapping.get(flag_name)
            if allow_limit_obj:
                AppFileUtils.check_file(file=file, file_types=allow_limit_obj.get("types"), limit_file_size=allow_limit_obj.get("size"))
            else:
                raise Exception(f'The file [{file_name}] is not allowed to be uploaded!')
            file_id = await AppFileUtils.upload(file)
            file_mapping[f"{flag_name}"] = file_id
    
    await save_group_args(session=session, sys_args=sys_args, file_mapping=file_mapping)
