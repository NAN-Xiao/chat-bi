"""
脚本说明：验证数据源查询超时默认值，避免慢查询默认过早断开。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from apps.datasource.models.datasource import DatasourceConf
from apps.datasource.utils.utils import aes_decrypt
from apps.system.crud.assistant import get_out_ds_conf


def _external_datasource() -> SimpleNamespace:
    return SimpleNamespace(
        host="example.com",
        port=3306,
        user="reader",
        password="secret",
        dataBase="analytics",
        extraParams="",
        db_schema="",
        mode="",
    )


def test_datasource_conf_defaults_to_90_seconds() -> None:
    """
    是什么：未显式填写 timeout 的数据源配置应默认使用 90 秒。
    """
    assert DatasourceConf().timeout == 90


def test_external_datasource_conf_defaults_to_90_seconds() -> None:
    """
    是什么：外部数据源转换为加密配置时，也应默认写入 90 秒。
    """
    encrypted = get_out_ds_conf(_external_datasource())
    conf = json.loads(aes_decrypt(encrypted))

    assert conf["timeout"] == 90


def test_get_session_uses_90_seconds_for_external_datasource(monkeypatch) -> None:
    """
    是什么：运行查询时，外部数据源会通过 90 秒默认值生成连接配置。
    """
    from apps.db import db
    from apps.system.schemas.system_schema import AssistantOutDsSchema

    captured = {}

    class _Session:
        pass

    def fake_get_out_ds_conf(ds, timeout=90):
        captured["timeout"] = timeout
        return "{}"

    def fake_get_engine(ds, timeout=0):
        captured["engine_timeout"] = timeout
        return object()

    monkeypatch.setattr(db, "get_out_ds_conf", fake_get_out_ds_conf)
    monkeypatch.setattr(db, "get_engine", fake_get_engine)
    monkeypatch.setattr(db, "sessionmaker", lambda bind: lambda: _Session())

    datasource = AssistantOutDsSchema(name="external", type="mysql")
    db.get_session(datasource)

    assert captured["timeout"] == 90
    assert captured["engine_timeout"] == 0
