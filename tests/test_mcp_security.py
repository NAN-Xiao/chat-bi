import socket

import pytest
from fastapi import HTTPException

from apps.mcp.mcp import validate_mcp_assistant_url


def test_mcp_assistant_url_rejects_loopback_literal():
    with pytest.raises(HTTPException) as exc:
        validate_mcp_assistant_url("http://127.0.0.1:8000/private")

    assert exc.value.status_code == 400


def test_mcp_assistant_url_rejects_private_dns_resolution(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(HTTPException) as exc:
        validate_mcp_assistant_url("https://api.example.com/data")

    assert exc.value.status_code == 400


def test_mcp_assistant_url_accepts_public_https(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert validate_mcp_assistant_url("https://api.example.com/data") == "https://api.example.com/data"


def test_mcp_assistant_url_rejects_non_http_scheme():
    with pytest.raises(HTTPException) as exc:
        validate_mcp_assistant_url("file:///etc/passwd")

    assert exc.value.status_code == 400
