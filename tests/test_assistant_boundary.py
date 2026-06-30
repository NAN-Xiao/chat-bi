import json
import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from apps.system.api import assistant as assistant_api
from apps.system.models.system_model import AssistantModel
from common.core import deps


def _assistant_model() -> AssistantModel:
    return AssistantModel(
        id=1,
        name="Embedded Assistant",
        type=1,
        domain="https://example.com",
        description="demo",
        configuration=json.dumps({
            "endpoint": "https://internal.example.com/ds",
            "timeout": 10,
            "aes_key": "secret-key",
            "aes_iv": "secret-iv",
            "certificate": [
                {
                    "type": "localStorage",
                    "source": "token",
                    "target": "header",
                    "target_key": "Authorization",
                }
            ],
            "welcome": "hello",
            "theme": "#3370ff",
            "logo": "logo.png",
            "auto_ds": True,
        }),
        app_id="app-id",
        app_secret="app-secret",
        enable_custom_model=False,
        custom_model="",
    )


def test_public_assistant_info_hides_backend_connection_config():
    public_info = assistant_api._public_assistant_info(_assistant_model())
    config = json.loads(public_info.configuration)

    assert public_info.app_id == "app-id"
    assert not hasattr(public_info, "app_secret")
    assert config == {
        "welcome": "hello",
        "theme": "#3370ff",
        "logo": "logo.png",
        "auto_ds": True,
    }


def test_cross_origin_assistant_info_can_include_certificate_rules():
    public_info = assistant_api._public_assistant_info(
        _assistant_model(),
        include_certificate=True,
    )
    config = json.loads(public_info.configuration)

    assert "certificate" in config
    assert "endpoint" not in config
    assert "aes_key" not in config
    assert "aes_iv" not in config


def test_assistant_online_header_cannot_override_validated_assistant_state():
    request = Request({
        "type": "http",
        "headers": [
            (b"x-shuzhi-assistant-online", b"true"),
        ],
    })
    request.state.assistant = SimpleNamespace(online=False, certificate=None)

    assistant = asyncio.run(deps.get_current_assistant(request))

    assert assistant.online is False
