import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.datasource.api import datasource as datasource_api
from apps.datasource.models.datasource import ImportRequest


def test_import_to_db_reads_temp_file_from_current_tenant_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(datasource_api, "path", str(tmp_path))
    current_user = SimpleNamespace(id=7, tenant_id=20)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            datasource_api.import_to_db.__wrapped__(
                session=None,
                trans=lambda key: key,
                current_user=current_user,
                import_req=ImportRequest(filePath="../tenant_10/upload.xlsx", sheets=[]),
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "File not found"
    assert (tmp_path / "tenant_20").is_dir()
    assert not (tmp_path / "tenant_10").exists()
