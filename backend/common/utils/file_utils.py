import os
import re
import uuid
from collections.abc import Iterable
from pathlib import Path

from fastapi import HTTPException, UploadFile

from common.core.config import settings

_UPLOAD_CHUNK_SIZE = 1024 * 1024


class AppFileUtils:
    @staticmethod
    def _base_dir() -> Path:
        """
        是什么：AppFileUtils._base_dir 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：围绕 _base_dir 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
        """
        base_dir = Path(settings.UPLOAD_DIR)
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @staticmethod
    def split_filename_and_flag(filename: str) -> tuple[str, str]:
        """
        是什么：AppFileUtils.split_filename_and_flag 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：围绕 split_filename_and_flag 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
        """
        if not filename:
            raise ValueError("filename is required")
        if "," not in filename:
            return os.path.basename(filename), ""
        file_name, flag_name = filename.rsplit(",", 1)
        return os.path.basename(file_name), flag_name.strip()

    @staticmethod
    def check_file(
        file: UploadFile,
        file_types: Iterable[str] | None = None,
        limit_file_size: int | None = None,
    ) -> None:
        """
        是什么：AppFileUtils.check_file 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：校验通用工具相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
        """
        suffix = Path(file.filename or "").suffix.lower()
        if file_types and suffix not in {item.lower() for item in file_types}:
            raise ValueError(f"Unsupported file type: {suffix}")

        if limit_file_size is None:
            return

        current_pos = file.file.tell()
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(current_pos)
        if size > limit_file_size:
            raise ValueError("文件大小超过限制")

    @staticmethod
    def _normalize_extensions(file_types: Iterable[str]) -> set[str]:
        """
        是什么：AppFileUtils._normalize_extensions 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：解析、转换或格式化通用工具相关数据，生成后续流程可使用的结构。
        """
        return {
            item.lower() if item.startswith(".") else f".{item.lower()}"
            for item in file_types
        }

    @staticmethod
    def validate_extension(filename: str | None, file_types: Iterable[str]) -> str:
        """
        是什么：AppFileUtils.validate_extension 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：校验通用工具相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
        """
        suffix = Path(filename or "").suffix.lower()
        if suffix not in AppFileUtils._normalize_extensions(file_types):
            allowed = "/".join(sorted(AppFileUtils._normalize_extensions(file_types)))
            raise HTTPException(status_code=400, detail=f"Only support {allowed}")
        return suffix

    @staticmethod
    def safe_upload_name(filename: str | None, file_types: Iterable[str]) -> tuple[str, str]:
        """
        是什么：AppFileUtils.safe_upload_name 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：围绕 safe_upload_name 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
        """
        suffix = AppFileUtils.validate_extension(filename, file_types)
        raw_name = os.path.basename(filename or "")
        stem = Path(raw_name).stem
        safe_stem = re.sub(r"[^\w\u4e00-\u9fa5-]+", "_", stem).strip("._-")
        if not safe_stem:
            safe_stem = "upload"
        base_filename = f"{safe_stem}_{uuid.uuid4().hex[:10]}"
        return base_filename, f"{base_filename}{suffix}"

    @staticmethod
    def safe_path(base_dir: str | Path, filename: str, *, required_suffix: str | None = None) -> Path:
        """
        是什么：AppFileUtils.safe_path 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：围绕 safe_path 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
        """
        safe_name = os.path.basename(filename or "")
        if not safe_name:
            raise HTTPException(status_code=400, detail="filename is required")
        if required_suffix and not safe_name.lower().endswith(required_suffix.lower()):
            raise HTTPException(status_code=400, detail=f"Only support {required_suffix}")

        base_path = Path(base_dir).resolve()
        target = (base_path / safe_name).resolve()
        try:
            common_path = os.path.commonpath([str(base_path), str(target)])
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Unauthorized file access") from exc
        if common_path != str(base_path):
            raise HTTPException(status_code=403, detail="Unauthorized file access")
        return target

    @staticmethod
    async def read_upload_limited(
        file: UploadFile,
        *,
        limit_file_size: int | None = None,
    ) -> bytes:
        """
        是什么：AppFileUtils.read_upload_limited 是 backend/common/utils/file_utils.py 中的异步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
        """
        limit = limit_file_size if limit_file_size is not None else settings.MAX_UPLOAD_BYTES
        chunks: list[bytes] = []
        total_size = 0

        while True:
            chunk = await file.read(_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total_size += len(chunk)
            if limit and total_size > limit:
                await file.seek(0)
                raise HTTPException(status_code=413, detail="文件大小超过限制")
            chunks.append(chunk)

        await file.seek(0)
        return b"".join(chunks)

    @staticmethod
    async def upload(file: UploadFile) -> str:
        """
        是什么：AppFileUtils.upload 是 backend/common/utils/file_utils.py 中的异步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：围绕 upload 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
        """
        suffix = Path(file.filename or "").suffix.lower()
        file_id = f"{uuid.uuid4().hex}{suffix}"
        file_path = AppFileUtils.get_file_path(file_id)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        content = await AppFileUtils.read_upload_limited(file)
        with open(file_path, "wb") as target:
            target.write(content)
        return file_id

    @staticmethod
    def get_file_path(file_id: str) -> str:
        """
        是什么：AppFileUtils.get_file_path 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
        """
        if not file_id:
            raise ValueError("file_id is required")
        safe_name = os.path.basename(file_id)
        return str(AppFileUtils._base_dir() / safe_name)

    @staticmethod
    def delete_file(file_id: str | None) -> None:
        """
        是什么：AppFileUtils.delete_file 是 backend/common/utils/file_utils.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：删除或清理通用工具相关数据、缓存或临时状态。
        """
        if not file_id:
            return
        try:
            Path(AppFileUtils.get_file_path(file_id)).unlink(missing_ok=True)
        except OSError:
            return
