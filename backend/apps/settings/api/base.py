"""
脚本说明：这个脚本放后端业务的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from apps.swagger.i18n import PLACEHOLDER_PREFIX
from common.core.config import settings
from common.core.file import FileRequest
from common.utils.file_utils import AppFileUtils

router = APIRouter(tags=["System"], prefix="/system")

path = settings.EXCEL_PATH


@router.post("/download-fail-info", summary=f"{PLACEHOLDER_PREFIX}download-fail-info")
async def download_excel(req: FileRequest):
    """
    是什么：download_excel 是一个接口入口，负责接住后端业务相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    filename = os.path.basename(req.file or "")
    file_path = AppFileUtils.safe_path(path, filename, required_suffix="_error.xlsx")

    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise HTTPException(404, "File Not Exists")

    # 获取文件名
    filename = os.path.basename(str(file_path))

    # 返回文件
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
