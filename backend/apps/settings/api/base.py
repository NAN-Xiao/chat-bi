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
    是什么：download_excel 是 backend/apps/settings/api/base.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 download_excel 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
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
