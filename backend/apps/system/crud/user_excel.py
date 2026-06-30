

import asyncio
import io
import sys
import tempfile
import uuid
import atexit
import threading
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, FileResponse
import os
from openai import BaseModel
import pandas as pd
from sqlmodel import select

from apps.system.models.user import UserModel
from common.core.deps import SessionDep
from common.utils.file_utils import AppFileUtils


class RowValidator:
    def __init__(self, success: bool = False, row=list[str], error_info: dict = None):
        """
        是什么：RowValidator.__init__ 是 backend/apps/system/crud/user_excel.py 中的同步方法。
        谁调用：由创建 RowValidator 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.success = success
        self.row = row
        self.dict_data = {}
        self.error_info = error_info or {}
class CellValidator:
    def __init__(self, success: bool = False, value: str | int | list = None, message: str = ""):
        """
        是什么：CellValidator.__init__ 是 backend/apps/system/crud/user_excel.py 中的同步方法。
        谁调用：由创建 CellValidator 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.success = success
        self.value = value
        self.message = message

class UploadResultDTO(BaseModel):
    successCount: int
    errorCount: int
    dataKey: str | None = None


async def downTemplate(trans):
    """
    是什么：downTemplate 是 backend/apps/system/crud/user_excel.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 downTemplate 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    def inner():
        """
        是什么：inner 是 backend/apps/system/crud/user_excel.py 中的同步函数。
        谁调用：由外层函数 downTemplate 在执行内部流程时调用。
        做了什么：围绕 inner 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
        """
        data = {
            trans('i18n_user.account'): ['shuzhi1', 'shuzhi2'],
            trans('i18n_user.name'): ['shuzhi_employee1', 'shuzhi_employee2'],
            trans('i18n_user.email'): ['employee1@shuzhi.com', 'employee2@shuzhi.com'],
            trans('i18n_user.status'): [trans('i18n_user.status_enabled'), trans('i18n_user.status_disabled')],
            trans('i18n_user.origin'): [trans('i18n_user.local_creation'), trans('i18n_user.local_creation')],
            trans('i18n_user.platform_user_id'): [None, None],
        }
        df = pd.DataFrame(data)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_numbers': False}}) as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

            workbook = writer.book
            worksheet = writer.sheets['Sheet1']

            header_format = workbook.add_format({
                'bold': True,
                'font_size': 12,
                'font_name': '微软雅黑',
                'align': 'center',
                'valign': 'vcenter',
                'border': 0,
                'text_wrap': False,
            })

            for i, col in enumerate(df.columns):
                max_length = max(
                    len(str(col).encode('utf-8')) * 1.1,
                    (df[col].astype(str)).apply(len).max()
                )
                worksheet.set_column(i, i, max_length + 12)

                worksheet.write(0, i, col, header_format)


            worksheet.set_row(0, 30)
            for row in range(1, len(df) + 1):
                worksheet.set_row(row, 25)

        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

async def batchUpload(session: SessionDep, trans, file) -> UploadResultDTO:
    """
    是什么：batchUpload 是 backend/apps/system/crud/user_excel.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 batchUpload 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
    AppFileUtils.validate_extension(getattr(file, "filename", None), ALLOWED_EXTENSIONS)

    # 支持 FastAPI 上传文件（异步读取）和类文件对象。
    NA_VALUES = ['', 'NA', 'N/A', 'NULL']
    df = None
    # 如果文件提供异步读取能力（上传文件），则先读取字节。
    if hasattr(file, 'read') and asyncio.iscoroutinefunction(getattr(file, 'read')):
        content = await AppFileUtils.read_upload_limited(file)
        df = pd.read_excel(io.BytesIO(content), sheet_name=0, na_values=NA_VALUES)
    else:
        # 如果是带 .file 属性的 Starlette 上传文件对象，则使用该属性。
        if hasattr(file, 'file'):
            fobj = file.file
            try:
                fobj.seek(0)
            except Exception:
                pass
            df = pd.read_excel(fobj, sheet_name=0, na_values=NA_VALUES)
        else:
            # 兜底：按路径或类文件对象处理。
            try:
                file.seek(0)
            except Exception:
                pass
            df = pd.read_excel(file, sheet_name=0, na_values=NA_VALUES)
    head_list = list(df.columns)
    i18n_head_list = get_i18n_head_list()
    if not validate_head(trans=trans, head_i18n_list=i18n_head_list, head_list=head_list):
        raise HTTPException(400, "Excel header validation failed")
    success_rows = []
    error_list = []
    for row in df.itertuples():
        row_validator = validate_row(trans=trans, head_i18n_list=i18n_head_list, row=row)
        if row_validator.success:
            success_rows.append(row_validator)
        else:
            error_list.append(row_validator)
    validate_unique_users(session, trans, success_rows, error_list)
    success_list = [row.dict_data for row in success_rows if row.success]
    error_file_id = None
    if error_list:
        error_file_id = generate_error_file(error_list, head_list)
    result = UploadResultDTO(successCount=len(success_list), errorCount=len(error_list), dataKey=error_file_id)
    if success_list:
        user_po_list = [UserModel.model_validate(row) for row in success_list]
        session.add_all(user_po_list)
        session.commit()
    return result


def validate_unique_users(
    session: SessionDep,
    trans,
    success_rows: list[RowValidator],
    error_list: list[RowValidator],
) -> None:
    """
    是什么：validate_unique_users 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    account_index = 0
    name_index = 1
    accounts = [str(row.dict_data.get("account") or "").strip() for row in success_rows]
    names = [str(row.dict_data.get("name") or "").strip() for row in success_rows]
    account_counts = {value: accounts.count(value) for value in set(accounts) if value}
    name_counts = {value: names.count(value) for value in set(names) if value}
    existing_accounts = set()
    existing_names = set()
    if accounts:
        existing_accounts = set(session.exec(select(UserModel.account).where(UserModel.account.in_(accounts))).all())
    if names:
        existing_names = set(session.exec(select(UserModel.name).where(UserModel.name.in_(names))).all())

    for row in success_rows:
        account = str(row.dict_data.get("account") or "").strip()
        name = str(row.dict_data.get("name") or "").strip()
        if account in existing_accounts or account_counts.get(account, 0) > 1:
            row.success = False
            row.error_info[account_index] = trans(
                "i18n_exist",
                msg=f"{trans('i18n_user.account')} [{account}]",
            )
        if name in existing_names or name_counts.get(name, 0) > 1:
            row.success = False
            row.error_info[name_index] = trans(
                "i18n_exist",
                msg=f"{trans('i18n_user.name')} [{name}]",
            )
        if not row.success:
            error_list.append(row)

def get_i18n_head_list():
    """
    是什么：get_i18n_head_list 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    return [
        'i18n_user.account',
        'i18n_user.name',
        'i18n_user.email',
        'i18n_user.status',
        'i18n_user.origin',
        'i18n_user.platform_user_id',
    ]

def validate_head(trans, head_i18n_list: list[str], head_list: list):
    """
    是什么：validate_head 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if len(head_list) != len(head_i18n_list):
        return False
    for i in range(len(head_i18n_list)):
        if head_list[i] != trans(head_i18n_list[i]):
            return False
    return True



def validate_row(trans, head_i18n_list: list[str], row):
    """
    是什么：validate_row 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    validator = RowValidator(success=True, row=[], error_info={})
    for i in range(len(head_i18n_list)):
        col_name = trans(head_i18n_list[i])
        row_value = getattr(row, col_name)
        validator.row.append(row_value)
        _attr_name = f"{head_i18n_list[i].split('.')[-1]}"
        _method_name = f"validate_{_attr_name}"
        cellValidator = dynamic_call(_method_name, row_value)
        if not cellValidator.success:
            validator.success = False
            validator.error_info[i] = cellValidator.message
        else:
            validator.dict_data[_attr_name] = cellValidator.value
    return validator

def generate_error_file(error_list: list[RowValidator], head_list: list[str]) -> str:
    # 如果没有错误，则返回空字符串。
    """
    是什么：generate_error_file 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：基于输入上下文生成系统管理相关结果，并保存或返回给调用方。
    """
    if not error_list:
        return ""

    # 根据错误行构建数据表（只包含有错误的行）。
    df_rows = [err.row for err in error_list]
    df = pd.DataFrame(df_rows, columns=head_list)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp_name = tmp.name
    tmp.close()

    with pd.ExcelWriter(tmp_name, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_numbers': False}}) as writer:
        df.to_excel(writer, sheet_name='Errors', index=False)

        workbook = writer.book
        worksheet = writer.sheets['Errors']

        # 表头格式与下载模板保持相近。
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'font_name': '微软雅黑',
            'align': 'center',
            'valign': 'vcenter',
            'border': 0,
            'text_wrap': False,
        })

        # 应用表头格式和列宽。
        for i, col in enumerate(df.columns):
            max_length = max(
                len(str(col).encode('utf-8')) * 1.1,
                (df[col].astype(str)).apply(len).max() if len(df) > 0 else 0
            )
            worksheet.set_column(i, i, max_length + 12)
            worksheet.write(0, i, col, header_format)

        worksheet.set_row(0, 30)
        for row_idx in range(1, len(df) + 1):
            worksheet.set_row(row_idx, 25)

        red_format = workbook.add_format({'font_color': 'red'})

        # 为每个错误单元格添加批注并设置红色字体。
        # 注意：pandas 将表头写在第 0 行，工作表数据从第 1 行开始。
        for sheet_row_idx, err in enumerate(error_list, start=1):
            for col_idx, message in err.error_info.items():
                if message:
                    comment_text = str(message)
                    worksheet.write_comment(sheet_row_idx, col_idx, comment_text)
                    try:
                        cell_value = df.iat[sheet_row_idx - 1, col_idx]
                    except Exception:
                        cell_value = None
                    worksheet.write(sheet_row_idx, col_idx, cell_value, red_format)

    # 将临时文件登记到映射中，并返回不透明文件 ID。
    file_id = uuid.uuid4().hex
    with _TEMP_FILE_LOCK:
        _TEMP_FILE_MAP[file_id] = tmp_name

    return file_id


def download_error_file(file_id: str) -> FileResponse:
    """
    是什么：download_error_file 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 download_error_file 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    if not file_id:
        raise HTTPException(400, "file_id required")

    with _TEMP_FILE_LOCK:
        file_path = _TEMP_FILE_MAP.get(file_id)

    if not file_path:
        raise HTTPException(404, "File not found")

    # 确保文件位于临时目录内。
    tempdir = tempfile.gettempdir()
    try:
        common = os.path.commonpath([tempdir, os.path.abspath(file_path)])
    except Exception:
        raise HTTPException(403, "Unauthorized file access")

    if os.path.abspath(common) != os.path.abspath(tempdir):
        raise HTTPException(403, "Unauthorized file access")

    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found")

    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(file_path),
    )

def validate_account(value: str) -> CellValidator:
    """
    是什么：validate_account 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    return CellValidator(True, value, None)
def validate_name(value: str) -> CellValidator:
    """
    是什么：validate_name 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    return CellValidator(True, value, None)
def validate_email(value: str) -> CellValidator:
    """
    是什么：validate_email 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    return CellValidator(True, value, None)
def validate_status(value: str) -> CellValidator:
    """
    是什么：validate_status 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if value == '已启用': return CellValidator(True, 1, None)
    if value == '已禁用': return CellValidator(True, 0, None)
    return CellValidator(False, None, "状态只能是已启用或已禁用")
def validate_origin(value: str) -> CellValidator:
    """
    是什么：validate_origin 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    if value == '本地创建': return CellValidator(True, 0, None)
    return CellValidator(False, None, "不支持当前来源")
def validate_platform_id(value: str) -> CellValidator:
    """
    是什么：validate_platform_id 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验系统管理相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    return CellValidator(True, value, None)

_method_cache = {
    'validate_account': validate_account,
    'validate_name': validate_name,
    'validate_email': validate_email,
    'validate_status': validate_status,
    'validate_origin': validate_origin,
    'validate_platform_user_id': validate_platform_id,
}
_module = sys.modules[__name__]
def dynamic_call(method_name: str, *args, **kwargs):
    """
    是什么：dynamic_call 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 dynamic_call 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    if method_name in _method_cache:
        return _method_cache[method_name](*args, **kwargs)

    if hasattr(_module, method_name):
        func = getattr(_module, method_name)
        _method_cache[method_name] = func
        return func(*args, **kwargs)

    raise AttributeError(f"Function '{method_name}' not found")


# 生成错误文件的文件 ID 到临时路径映射。
_TEMP_FILE_MAP: dict[str, str] = {}
_TEMP_FILE_LOCK = threading.Lock()


def _cleanup_temp_files():
    """
    是什么：_cleanup_temp_files 是 backend/apps/system/crud/user_excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理系统管理相关数据、缓存或临时状态。
    """
    with _TEMP_FILE_LOCK:
        for fid, path in list(_TEMP_FILE_MAP.items()):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        _TEMP_FILE_MAP.clear()


atexit.register(_cleanup_temp_files)






