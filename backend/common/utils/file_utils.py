import os
import uuid
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile

from common.core.config import settings


class SQLBotFileUtils:
    @staticmethod
    def _base_dir() -> Path:
        base_dir = Path(settings.UPLOAD_DIR)
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @staticmethod
    def split_filename_and_flag(filename: str) -> tuple[str, str]:
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
    async def upload(file: UploadFile) -> str:
        suffix = Path(file.filename or "").suffix.lower()
        file_id = f"{uuid.uuid4().hex}{suffix}"
        file_path = SQLBotFileUtils.get_file_path(file_id)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        with open(file_path, "wb") as target:
            target.write(content)
        await file.seek(0)
        return file_id

    @staticmethod
    def get_file_path(file_id: str) -> str:
        if not file_id:
            raise ValueError("file_id is required")
        safe_name = os.path.basename(file_id)
        return str(SQLBotFileUtils._base_dir() / safe_name)

    @staticmethod
    def delete_file(file_id: str | None) -> None:
        if not file_id:
            return
        try:
            Path(SQLBotFileUtils.get_file_path(file_id)).unlink(missing_ok=True)
        except OSError:
            return
