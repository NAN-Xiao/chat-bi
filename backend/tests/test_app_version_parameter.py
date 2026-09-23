import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.system.crud.parameter_manage import APP_VERSION_KEY, get_app_version, save_parameter_args


class FakeSession:
    def __init__(self, version=None):
        self.row = None if version is None else SimpleNamespace(pkey=APP_VERSION_KEY, pval=version)
        self.saved = []

    def exec(self, statement):
        if " IN " in str(statement):
            return SimpleNamespace(all=lambda: [self.row] if self.row else [])
        return SimpleNamespace(first=lambda: self.row)

    def add(self, row):
        self.saved.append(row)


class FakeRequest:
    def __init__(self, version):
        self.version = version

    async def form(self):
        data = json.dumps([{"pkey": APP_VERSION_KEY, "pval": self.version}])
        return SimpleNamespace(get=lambda key: data if key == "data" else None, getlist=lambda key: [])


def test_app_version_defaults_only_when_not_configured():
    assert get_app_version(FakeSession()) == "v1.3.0"
    assert get_app_version(FakeSession("v2.4.1")) == "v2.4.1"
    assert get_app_version(FakeSession("")) == ""


def test_app_version_can_be_saved_and_reloaded():
    session = FakeSession()
    asyncio.run(save_parameter_args(session, FakeRequest(" v2.4.1 ")))
    assert session.saved[0].pkey == APP_VERSION_KEY
    assert session.saved[0].pval == "v2.4.1"
    session.row = session.saved[0]
    assert get_app_version(session) == "v2.4.1"


@pytest.mark.parametrize("version", ["", "1.3.0", "v1.2", "v1.2.3<script>"])
def test_app_version_rejects_invalid_values(version):
    session = FakeSession()
    with pytest.raises(HTTPException) as error:
        asyncio.run(save_parameter_args(session, FakeRequest(version)))
    assert error.value.status_code == 400
    assert not session.saved
