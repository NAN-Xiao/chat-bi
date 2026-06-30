"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import os
import re
import uuid
from collections.abc import Iterable
from pathlib import Path

from fastapi import HTTPException, UploadFile

from common.core.config import settings

_UPLOAD_CHUNK_SIZE = 1024 * 1024


class AppFileUtils:
    """
    类说明：AppFileUtils 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    @staticmethod
    def _base_dir() -> Path:
        """
        是什么：AppFileUtils._base_dir 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        base_dir = Path(settings.UPLOAD_DIR)
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @staticmethod
    def split_filename_and_flag(filename: str) -> tuple[str, str]:
        """
        是什么：AppFileUtils.split_filename_and_flag 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
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
        是什么：AppFileUtils.check_file 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：检查通用工具里的数据、权限或配置是否合法，不对就及时拦住。
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
        是什么：AppFileUtils._normalize_extensions 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        return {
            item.lower() if item.startswith(".") else f".{item.lower()}"
            for item in file_types
        }

    @staticmethod
    def validate_extension(filename: str | None, file_types: Iterable[str]) -> str:
        """
        是什么：AppFileUtils.validate_extension 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：检查通用工具里的数据、权限或配置是否合法，不对就及时拦住。
        """
        suffix = Path(filename or "").suffix.lower()
        if suffix not in AppFileUtils._normalize_extensions(file_types):
            allowed = "/".join(sorted(AppFileUtils._normalize_extensions(file_types)))
            raise HTTPException(status_code=400, detail=f"Only support {allowed}")
        return suffix

    @staticmethod
    def safe_upload_name(filename: str | None, file_types: Iterable[str]) -> tuple[str, str]:
        """
        是什么：AppFileUtils.safe_upload_name 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
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
        是什么：AppFileUtils.safe_path 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
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
        是什么：AppFileUtils.read_upload_limited 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
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
        是什么：AppFileUtils.upload 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
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
        是什么：AppFileUtils.get_file_path 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
        """
        if not file_id:
            raise ValueError("file_id is required")
        safe_name = os.path.basename(file_id)
        return str(AppFileUtils._base_dir() / safe_name)

    @staticmethod
    def delete_file(file_id: str | None) -> None:
        """
        是什么：AppFileUtils.delete_file 是 AppFileUtils 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具不再需要的数据、缓存或临时内容清理掉。
        """
        if not file_id:
            return
        try:
            Path(AppFileUtils.get_file_path(file_id)).unlink(missing_ok=True)
        except OSError:
            return
