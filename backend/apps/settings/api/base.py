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
    根据文件路径下载 Excel 文件
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
