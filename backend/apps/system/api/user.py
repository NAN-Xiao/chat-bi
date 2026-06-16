from collections import defaultdict
from typing import Optional
from fastapi import APIRouter, File, Path, Query, UploadFile
from sqlmodel import SQLModel, or_, select
from apps.datasource.crud.permission import (
    list_user_datasource_ids,
    list_user_datasource_roles,
    update_user_datasources,
)
from apps.datasource.models.datasource import CoreDatasourceUser
from apps.system.crud.user import (
    SYSTEM_ADMIN_ROLES,
    SYSTEM_ROLE_SYSTEM_ADMIN,
    check_account_exists,
    check_email_format,
    check_pwd_format,
    get_db_user,
    is_high_privilege_system_role,
    is_high_privilege_user,
    is_super_admin,
    normalize_system_role,
    single_delete,
)
from apps.system.crud.user_excel import batchUpload, downTemplate, download_error_file
from apps.system.models.user import UserModel
from apps.system.schemas.auth import CacheName, CacheNamespace
from apps.system.schemas.permission import SqlbotPermission, require_permissions
from apps.system.schemas.system_schema import PwdEditor, UserCreator, UserEditor, UserGrid, UserInfoDTO, UserLanguage, UserStatus
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.deps import CurrentUser, SessionDep, Trans
from common.core.pagination import Paginator
from common.core.schemas import PaginatedResponse, PaginationParams
from common.core.security import default_md5_pwd, md5pwd, verify_md5pwd
from common.core.sqlbot_cache import clear_cache
from common.core.config import settings
from apps.swagger.i18n import PLACEHOLDER_PREFIX

router = APIRouter(tags=["system_user"], prefix="/user")


@router.get("/template", include_in_schema=False)
@require_permissions(permission=SqlbotPermission(role=['admin']))
async def templateExcel(trans: Trans):
    return await downTemplate(trans)

@router.post("/batchImport", include_in_schema=False)
@require_permissions(permission=SqlbotPermission(role=['admin']))
async def upload_excel(session: SessionDep, trans: Trans, current_user: CurrentUser, file: UploadFile = File(...)):
    return await batchUpload(session, trans, file)


@router.get("/errorRecord/{file_id}", include_in_schema=False)
@require_permissions(permission=SqlbotPermission(role=['admin']))
async def download_error(file_id: str):
    return download_error_file(file_id)

@router.get("/info", summary=f"{PLACEHOLDER_PREFIX}system_user_current_user", description=f"{PLACEHOLDER_PREFIX}system_user_current_user_desc")
async def user_info(current_user: CurrentUser) -> UserInfoDTO:
    return current_user

 
@router.get("/defaultPwd", include_in_schema=False)
@require_permissions(permission=SqlbotPermission(role=['admin']))
async def default_pwd() -> str:
    return settings.DEFAULT_PWD

@router.get("/pager/{pageNum}/{pageSize}", response_model=PaginatedResponse[UserGrid], summary=f"{PLACEHOLDER_PREFIX}system_user_grid", description=f"{PLACEHOLDER_PREFIX}system_user_grid")
@require_permissions(permission=SqlbotPermission(role=['admin']))
async def pager(
    session: SessionDep,
    current_user: CurrentUser,
    pageNum: int = Path(..., title=f"{PLACEHOLDER_PREFIX}page_num", description=f"{PLACEHOLDER_PREFIX}page_num"),
    pageSize: int = Path(..., title=f"{PLACEHOLDER_PREFIX}page_size", description=f"{PLACEHOLDER_PREFIX}page_size"),
    keyword: Optional[str] = Query(None, description=f"{PLACEHOLDER_PREFIX}keyword"),
    status: Optional[int] = Query(None, description=f"{PLACEHOLDER_PREFIX}status"),
    origins: Optional[list[int]] = Query(None, description=f"{PLACEHOLDER_PREFIX}origin"),
):
    pagination = PaginationParams(page=pageNum, size=pageSize)
    paginator = Paginator(session)
    filters = {}
    
    origin_stmt = (
        select(UserModel.id, UserModel.account)
        .distinct()
        .order_by(UserModel.account)
    )
    if is_super_admin(current_user):
        origin_stmt = origin_stmt.where(UserModel.system_role != SYSTEM_ROLE_SYSTEM_ADMIN)
    else:
        origin_stmt = origin_stmt.where(~UserModel.system_role.in_(SYSTEM_ADMIN_ROLES))
    
    if origins:
        origin_stmt = origin_stmt.where(UserModel.origin.in_(origins))
    if status is not None:
        origin_stmt = origin_stmt.where(UserModel.status == status)        
    if keyword:
        keyword_pattern = f"%{keyword}%"
        origin_stmt = origin_stmt.where(
            or_(
                UserModel.account.ilike(keyword_pattern),
                UserModel.name.ilike(keyword_pattern),
                UserModel.email.ilike(keyword_pattern)
            )
        )
        
    user_page = await paginator.get_paginated_response(
        stmt=origin_stmt,
        pagination=pagination,
        **filters)
    uid_list = [item.get('id') for item in user_page.items]
    if not uid_list:
        return user_page
    users = session.exec(
        select(UserModel).where(UserModel.id.in_(uid_list)).order_by(UserModel.account, UserModel.create_time)
    ).all()
    result = []
    for user in users:
        item = user.model_dump()
        result.append(item)
    project_rows = session.exec(
        select(CoreDatasourceUser.user_id, CoreDatasourceUser.ds_id, CoreDatasourceUser.role).where(
            CoreDatasourceUser.user_id.in_(uid_list)
        )
    ).all()
    project_map = defaultdict(list)
    project_role_map = defaultdict(dict)
    for user_id, ds_id, role in project_rows:
        project_map[int(user_id)].append(int(ds_id))
        project_role_map[int(user_id)][int(ds_id)] = role or "viewer"
    for item in result:
        item["project_ids"] = project_map.get(int(item["id"]), [])
        item["project_role_map"] = project_role_map.get(int(item["id"]), {})
    user_page.items = result
    return user_page

def format_user_dict(row) -> dict:
    result_dict = {}
    for item, key in zip(row, row._fields):
        if isinstance(item, SQLModel):
            result_dict.update(item.model_dump())
        else:
            result_dict[key] = item
    
    return result_dict

@router.get("/{id}", response_model=UserEditor, summary=f"{PLACEHOLDER_PREFIX}user_detail_api", description=f"{PLACEHOLDER_PREFIX}user_detail_api")
@require_permissions(permission=SqlbotPermission(role=['admin']))
async def query(session: SessionDep, current_user: CurrentUser, trans: Trans, id: int = Path(description=f"{PLACEHOLDER_PREFIX}uid")) -> UserEditor:
    db_user: UserModel = get_db_user(session = session, user_id = id)
    if is_high_privilege_user(db_user) and not is_super_admin(current_user):
        raise Exception("Only system admin can manage administrator roles")
    result = UserEditor.model_validate(db_user.model_dump())
    result.project_ids = list_user_datasource_ids(session, id)
    result.project_role_map = list_user_datasource_roles(session, id)
    return result


@router.post("", summary=f"{PLACEHOLDER_PREFIX}user_create_api", description=f"{PLACEHOLDER_PREFIX}user_create_api")
@require_permissions(permission=SqlbotPermission(role=['admin']))
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.USER,
    result_id_expr="id"
))
async def user_create(session: SessionDep, current_user: CurrentUser, creator: UserCreator, trans: Trans):
    return await create(session=session, current_user=current_user, creator=creator, trans=trans)
    
async def create(session: SessionDep, current_user: CurrentUser, creator: UserCreator, trans: Trans):
    if check_account_exists(session=session, account=creator.account):
        raise Exception(trans('i18n_exist', msg = f"{trans('i18n_user.account')} [{creator.account}]"))
    """ if check_email_exists(session=session, email=creator.email):
        raise Exception(trans('i18n_exist', msg = f"{trans('i18n_user.email')} [{creator.email}]")) """
    if not check_email_format(creator.email):
        raise Exception(trans('i18n_format_invalid', key = f"{trans('i18n_user.email')} [{creator.email}]"))
    #data = creator.model_dump(exclude_unset=True)
    data = creator.model_dump(exclude={"project_ids", "project_role_map"})
    data["system_role"] = normalize_system_role(data.get("system_role"))
    if is_high_privilege_system_role(data["system_role"]) and not is_super_admin(current_user):
        raise Exception("Only system admin can grant administrator roles")
    user_model = UserModel.model_validate(data)
    #user_model.create_time = get_timestamp()
    user_model.language = "zh-CN"
    session.add(user_model)
    session.flush()
    if creator.project_ids is not None:
        update_user_datasources(
            session,
            current_user,
            user_model.id,
            creator.project_ids,
            creator.project_role_map,
        )
    return user_model

    
@router.put("", summary=f"{PLACEHOLDER_PREFIX}user_update_api", description=f"{PLACEHOLDER_PREFIX}user_update_api")
@require_permissions(permission=SqlbotPermission(role=['admin']))
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="editor.id")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.USER,
    resource_id_expr="editor.id"
))
async def update(session: SessionDep, current_user: CurrentUser, editor: UserEditor, trans: Trans):
    user_model: UserModel = get_db_user(session = session, user_id = editor.id)
    if not user_model:
        raise Exception(f"User with id [{editor.id}] not found!")
    if editor.account != user_model.account:
        raise Exception(f"account cannot be changed!")
    """ if editor.email != user_model.email and check_email_exists(session=session, email=editor.email):
        raise Exception(trans('i18n_exist', msg = f"{trans('i18n_user.email')} [{editor.email}]")) """
    if not check_email_format(editor.email):
        raise Exception(trans('i18n_format_invalid', key = f"{trans('i18n_user.email')} [{editor.email}]"))
    data = editor.model_dump(exclude_unset=True, exclude={"project_ids", "project_role_map"})
    data["system_role"] = normalize_system_role(data.get("system_role"))
    if is_high_privilege_user(user_model) and not is_super_admin(current_user):
        raise Exception("Only system admin can manage administrator roles")
    if is_high_privilege_system_role(data["system_role"]) and not is_super_admin(current_user):
        raise Exception("Only system admin can grant administrator roles")
    if is_super_admin(user_model) and data["system_role"] != SYSTEM_ROLE_SYSTEM_ADMIN:
        raise Exception("System admin role cannot be removed from this endpoint")
    user_model.sqlmodel_update(data)
    session.add(user_model)
    if editor.project_ids is not None:
        update_user_datasources(
            session,
            current_user,
            user_model.id,
            editor.project_ids,
            editor.project_role_map,
        )

@router.delete("/{id}", summary=f"{PLACEHOLDER_PREFIX}user_del_api", description=f"{PLACEHOLDER_PREFIX}user_del_api")
@require_permissions(permission=SqlbotPermission(role=['admin']))
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.USER,
    resource_id_expr="id"
))
async def delete(session: SessionDep, current_user: CurrentUser, id: int = Path(description=f"{PLACEHOLDER_PREFIX}uid")):
    user_model = get_db_user(session=session, user_id=id)
    if is_super_admin(user_model):
        raise Exception("System admin cannot be deleted")
    if is_high_privilege_user(user_model) and not is_super_admin(current_user):
        raise Exception("Administrator roles cannot be deleted")
    await single_delete(session, id)

@router.delete("", summary=f"{PLACEHOLDER_PREFIX}user_batchdel_api", description=f"{PLACEHOLDER_PREFIX}user_batchdel_api")
@require_permissions(permission=SqlbotPermission(role=['admin']))
@system_log(LogConfig(operation_type=OperationType.DELETE,module=OperationModules.USER,resource_id_expr="id_list"))
async def batch_del(session: SessionDep, current_user: CurrentUser, id_list: list[int]):
    for id in id_list:
        user_model = get_db_user(session=session, user_id=id)
        if is_super_admin(user_model):
            raise Exception("System admin cannot be deleted")
        if is_high_privilege_user(user_model) and not is_super_admin(current_user):
            raise Exception("Administrator roles cannot be deleted")
        await single_delete(session, id)
    
@router.put("/language", summary=f"{PLACEHOLDER_PREFIX}language_change", description=f"{PLACEHOLDER_PREFIX}language_change")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
async def langChange(session: SessionDep, current_user: CurrentUser, trans: Trans, language: UserLanguage):
    lang = language.language
    if lang not in ["zh-CN", "zh-TW", "en", "ko-KR"]:
        raise Exception(trans('i18n_user.language_not_support', key = lang))
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    db_user.language = lang
    session.add(db_user)

   
@router.patch("/pwd/{id}", summary=f"{PLACEHOLDER_PREFIX}reset_pwd", description=f"{PLACEHOLDER_PREFIX}reset_pwd")
@require_permissions(permission=SqlbotPermission(role=['admin'])) 
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="id")
@system_log(LogConfig(operation_type=OperationType.RESET_PWD,module=OperationModules.USER,resource_id_expr="id"))
async def pwdReset(session: SessionDep, current_user: CurrentUser, trans: Trans, id: int = Path(description=f"{PLACEHOLDER_PREFIX}uid")):
    db_user: UserModel = get_db_user(session=session, user_id=id)
    if is_high_privilege_user(db_user) and not is_super_admin(current_user):
        raise Exception(trans('i18n_permission.no_permission', url = " patch[/user/pwd/id],", msg = trans('i18n_permission.only_admin')))
    db_user.password = default_md5_pwd()
    session.add(db_user)

@router.put("/pwd", summary=f"{PLACEHOLDER_PREFIX}update_pwd", description=f"{PLACEHOLDER_PREFIX}update_pwd")
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="current_user.id")
@system_log(LogConfig(operation_type=OperationType.UPDATE_PWD,module=OperationModules.USER,result_id_expr="id"))
async def pwdUpdate(session: SessionDep, current_user: CurrentUser, trans: Trans, editor: PwdEditor):
    new_pwd = editor.new_pwd
    if not check_pwd_format(new_pwd):
        raise Exception(trans('i18n_format_invalid', key = trans('i18n_user.password')))
    db_user: UserModel = get_db_user(session=session, user_id=current_user.id)
    if not verify_md5pwd(editor.pwd, db_user.password):
        raise Exception(trans('i18n_error', key = trans('i18n_user.password')))
    db_user.password = md5pwd(new_pwd)
    session.add(db_user)
    return db_user

    
@router.patch("/status", summary=f"{PLACEHOLDER_PREFIX}update_status", description=f"{PLACEHOLDER_PREFIX}update_status")
@require_permissions(permission=SqlbotPermission(role=['admin']))
@clear_cache(namespace=CacheNamespace.AUTH_INFO, cacheName=CacheName.USER_INFO, keyExpression="statusDto.id")
@system_log(LogConfig(operation_type=OperationType.UPDATE_STATUS,module=OperationModules.USER, resource_id_expr="statusDto.id"))
async def statusChange(session: SessionDep, current_user: CurrentUser, trans: Trans, statusDto: UserStatus):
    status = statusDto.status
    if status not in [0, 1]:
        return {"message": "status not supported"}
    db_user: UserModel = get_db_user(session=session, user_id=statusDto.id)
    if is_high_privilege_user(db_user) and status == 0 and not is_super_admin(current_user):
        raise Exception(trans('i18n_permission.no_permission', url = ", ", msg = trans('i18n_permission.only_admin')))
    if is_super_admin(db_user) and status == 0:
        raise Exception("System admin cannot be disabled")
    db_user.status = status
    session.add(db_user)
