import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from apps.system.crud.tenant import auto_assign_tenants_by_email_domain, ensure_user_sample_workspace_membership
from apps.system.models.system_model import AuthenticationModel
from apps.system.models.user import UserModel, UserPlatformModel
from apps.system.schemas.sso import FeishuSsoConfigDTO, FeishuSsoConfigEditor
from apps.system.schemas.system_schema import BaseUserDTO
from common.core.config import settings
from common.utils.crypto import decrypt_sensitive_text, encrypt_sensitive_text
from common.utils.time import get_timestamp

FEISHU_ORIGIN = 8
FEISHU_AUTH_NAME = "feishu"
FEISHU_AUTH_TYPE = FEISHU_ORIGIN
FEISHU_STATE_TTL_MILLISECONDS = 10 * 60 * 1000

DEFAULT_FEISHU_AUTHORIZE_URL = "https://open.feishu.cn/open-apis/authen/v1/index"
DEFAULT_FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
DEFAULT_FEISHU_TENANT_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
DEFAULT_FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


class FeishuIdentity(BaseModel):
    platform_uid: str
    open_id: str | None = None
    union_id: str | None = None
    user_id: str | None = None
    email: str | None = None
    name: str
    raw: dict[str, Any] = {}


def _clean_text(value: str | None, default: str = "") -> str:
    return (value or default or "").strip()


def _default_redirect_uri() -> str:
    return f"{settings.FRONTEND_HOST.rstrip('/')}/#/login"


def _default_config() -> dict[str, Any]:
    return {
        "app_id": "",
        "app_secret": None,
        "redirect_uri": _default_redirect_uri(),
        "authorize_url": DEFAULT_FEISHU_AUTHORIZE_URL,
        "token_url": DEFAULT_FEISHU_TOKEN_URL,
        "tenant_access_token_url": DEFAULT_FEISHU_TENANT_ACCESS_TOKEN_URL,
        "user_info_url": DEFAULT_FEISHU_USER_INFO_URL,
        "scope": None,
        "token_mode": "oauth_v2",
    }


def _load_config(row: AuthenticationModel | None, *, decrypt_secret: bool = False) -> dict[str, Any]:
    config = _default_config()
    if row and row.config:
        try:
            loaded = json.loads(row.config)
            if isinstance(loaded, dict):
                config.update(loaded)
        except json.JSONDecodeError:
            pass
    if decrypt_secret:
        config["app_secret"] = decrypt_sensitive_text(config.get("app_secret"))
    return config


def _find_row(session: Session) -> AuthenticationModel | None:
    return session.exec(
        select(AuthenticationModel).where(
            AuthenticationModel.type == FEISHU_AUTH_TYPE,
            AuthenticationModel.name == FEISHU_AUTH_NAME,
        )
    ).first()


def _secret_is_mask(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or set(stripped) == {"*"}


def _is_config_valid(config: dict[str, Any], *, enable: bool) -> bool:
    return bool(
        enable
        and _clean_text(config.get("app_id"))
        and _clean_text(decrypt_sensitive_text(config.get("app_secret")))
        and _clean_text(config.get("redirect_uri"))
        and _clean_text(config.get("authorize_url"))
        and _clean_text(config.get("token_url"))
        and _clean_text(config.get("user_info_url"))
    )


def _to_dto(row: AuthenticationModel | None) -> FeishuSsoConfigDTO:
    config = _load_config(row, decrypt_secret=False)
    secret_configured = bool(_clean_text(decrypt_sensitive_text(config.get("app_secret"))))
    return FeishuSsoConfigDTO(
        enable=bool(row.enable) if row else False,
        valid=bool(row.valid) if row else False,
        app_id=_clean_text(config.get("app_id")),
        redirect_uri=_clean_text(config.get("redirect_uri"), _default_redirect_uri()),
        authorize_url=_clean_text(config.get("authorize_url"), DEFAULT_FEISHU_AUTHORIZE_URL),
        token_url=_clean_text(config.get("token_url"), DEFAULT_FEISHU_TOKEN_URL),
        tenant_access_token_url=_clean_text(
            config.get("tenant_access_token_url"),
            DEFAULT_FEISHU_TENANT_ACCESS_TOKEN_URL,
        ),
        user_info_url=_clean_text(config.get("user_info_url"), DEFAULT_FEISHU_USER_INFO_URL),
        scope=_clean_text(config.get("scope")) or None,
        token_mode=config.get("token_mode") if config.get("token_mode") in {"oauth_v2", "authen_v1"} else "oauth_v2",
        secret_configured=secret_configured,
    )


def get_feishu_sso_config(session: Session) -> FeishuSsoConfigDTO:
    return _to_dto(_find_row(session))


def upsert_feishu_sso_config(session: Session, editor: FeishuSsoConfigEditor) -> FeishuSsoConfigDTO:
    row = _find_row(session)
    existing_config = _load_config(row, decrypt_secret=False)
    config = _default_config()
    config.update(existing_config)
    config.update(
        {
            "app_id": _clean_text(editor.app_id),
            "redirect_uri": _clean_text(editor.redirect_uri, _default_redirect_uri()),
            "authorize_url": _clean_text(editor.authorize_url, DEFAULT_FEISHU_AUTHORIZE_URL),
            "token_url": _clean_text(editor.token_url, DEFAULT_FEISHU_TOKEN_URL),
            "tenant_access_token_url": _clean_text(
                editor.tenant_access_token_url,
                DEFAULT_FEISHU_TENANT_ACCESS_TOKEN_URL,
            ),
            "user_info_url": _clean_text(editor.user_info_url, DEFAULT_FEISHU_USER_INFO_URL),
            "scope": _clean_text(editor.scope) or None,
            "token_mode": editor.token_mode,
        }
    )
    if not _secret_is_mask(editor.app_secret):
        config["app_secret"] = encrypt_sensitive_text(editor.app_secret)

    valid = _is_config_valid(config, enable=editor.enable)
    now = get_timestamp()
    if row is None:
        row = AuthenticationModel(
            name=FEISHU_AUTH_NAME,
            type=FEISHU_AUTH_TYPE,
            config=json.dumps(config, ensure_ascii=False),
            enable=bool(editor.enable),
            valid=valid,
            create_time=now,
        )
    else:
        row.config = json.dumps(config, ensure_ascii=False)
        row.enable = bool(editor.enable)
        row.valid = valid
    session.add(row)
    session.flush()
    return _to_dto(row)


def _base64_urlsafe(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _sign_state(raw_payload: str) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw_payload.encode("utf-8"), hashlib.sha256).digest()
    return _base64_urlsafe(digest)


def create_feishu_state(*, redirect: str | None = None, tenant_id: int | None = None) -> str:
    payload: dict[str, Any] = {
        "provider": FEISHU_AUTH_NAME,
        "ts": get_timestamp(),
        "nonce": secrets.token_urlsafe(16),
    }
    if redirect:
        payload["redirect"] = redirect[:1000]
    if tenant_id:
        payload["tenant_id"] = int(tenant_id)
    raw_payload = _base64_urlsafe(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return f"{FEISHU_AUTH_NAME}:{raw_payload}.{_sign_state(raw_payload)}"


def parse_feishu_state(state: str) -> dict[str, Any]:
    prefix = f"{FEISHU_AUTH_NAME}:"
    if not state or not state.startswith(prefix) or "." not in state:
        raise ValueError("Invalid Feishu login state")
    raw_payload, signature = state[len(prefix):].split(".", 1)
    if not hmac.compare_digest(signature, _sign_state(raw_payload)):
        raise ValueError("Invalid Feishu login state")
    padding = "=" * (-len(raw_payload) % 4)
    payload = json.loads(base64.urlsafe_b64decode((raw_payload + padding).encode("utf-8")).decode("utf-8"))
    if payload.get("provider") != FEISHU_AUTH_NAME:
        raise ValueError("Invalid Feishu login state")
    if get_timestamp() - int(payload.get("ts") or 0) > FEISHU_STATE_TTL_MILLISECONDS:
        raise ValueError("Feishu login state expired")
    return payload


def build_feishu_authorize_url(
    session: Session,
    *,
    redirect: str | None = None,
    tenant_id: int | None = None,
) -> str | None:
    row = _find_row(session)
    dto = _to_dto(row)
    if not dto.enable or not dto.valid:
        return None
    state = create_feishu_state(redirect=redirect, tenant_id=tenant_id)
    params = {
        "app_id": dto.app_id,
        "redirect_uri": dto.redirect_uri,
        "state": state,
    }
    if dto.scope:
        params["scope"] = dto.scope
    return f"{dto.authorize_url}?{urlencode(params)}"


def get_enabled_feishu_config(session: Session) -> dict[str, Any]:
    row = _find_row(session)
    dto = _to_dto(row)
    if not dto.enable or not dto.valid:
        raise ValueError("Feishu SSO is not enabled")
    return _load_config(row, decrypt_secret=True)


def _extract_response_data(payload: dict[str, Any], *, context: str) -> dict[str, Any]:
    code = payload.get("code", 0)
    if code not in (0, "0", None):
        raise ValueError(payload.get("msg") or payload.get("message") or f"Feishu {context} failed")
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


async def _post_json(url: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise ValueError("Feishu request failed") from exc


async def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise ValueError("Feishu request failed") from exc


async def _exchange_authen_v1_token(config: dict[str, Any], code: str) -> str:
    tenant_payload = await _post_json(
        _clean_text(config.get("tenant_access_token_url"), DEFAULT_FEISHU_TENANT_ACCESS_TOKEN_URL),
        {
            "app_id": config["app_id"],
            "app_secret": config["app_secret"],
        },
    )
    tenant_token = tenant_payload.get("tenant_access_token") or _extract_response_data(
        tenant_payload,
        context="tenant token",
    ).get("tenant_access_token")
    if not tenant_token:
        raise ValueError("Feishu tenant access token is missing")
    token_payload = await _post_json(
        _clean_text(config.get("token_url"), DEFAULT_FEISHU_TOKEN_URL),
        {
            "grant_type": "authorization_code",
            "code": code,
        },
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    token_data = _extract_response_data(token_payload, context="token exchange")
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("Feishu user access token is missing")
    return access_token


async def _exchange_oauth_v2_token(config: dict[str, Any], code: str) -> str:
    token_payload = await _post_json(
        _clean_text(config.get("token_url"), DEFAULT_FEISHU_TOKEN_URL),
        {
            "grant_type": "authorization_code",
            "client_id": config["app_id"],
            "client_secret": config["app_secret"],
            "code": code,
            "redirect_uri": config["redirect_uri"],
        },
    )
    token_data = _extract_response_data(token_payload, context="token exchange")
    access_token = token_data.get("access_token") or token_data.get("user_access_token")
    if not access_token:
        raise ValueError("Feishu user access token is missing")
    return access_token


async def fetch_feishu_identity(config: dict[str, Any], code: str) -> FeishuIdentity:
    mode = config.get("token_mode") if config.get("token_mode") in {"oauth_v2", "authen_v1"} else "oauth_v2"
    access_token = (
        await _exchange_authen_v1_token(config, code)
        if mode == "authen_v1"
        else await _exchange_oauth_v2_token(config, code)
    )
    info_payload = await _get_json(
        _clean_text(config.get("user_info_url"), DEFAULT_FEISHU_USER_INFO_URL),
        headers={"Authorization": f"Bearer {access_token}"},
    )
    data = _extract_response_data(info_payload, context="user info")
    platform_uid = _clean_text(data.get("open_id")) or _clean_text(data.get("union_id")) or _clean_text(data.get("user_id"))
    if not platform_uid:
        raise ValueError("Feishu user id is missing")
    email = _clean_text(data.get("email")) or None
    name = (
        _clean_text(data.get("name"))
        or _clean_text(data.get("en_name"))
        or (email.split("@", 1)[0] if email else "")
        or f"feishu_{platform_uid[:12]}"
    )
    return FeishuIdentity(
        platform_uid=platform_uid,
        open_id=_clean_text(data.get("open_id")) or None,
        union_id=_clean_text(data.get("union_id")) or None,
        user_id=_clean_text(data.get("user_id")) or None,
        email=email,
        name=name,
        raw=data,
    )


def _find_platform_binding(session: Session, identity: FeishuIdentity) -> UserPlatformModel | None:
    candidates = {identity.platform_uid}
    for item in (identity.open_id, identity.union_id, identity.user_id):
        if item:
            candidates.add(item)
    return session.exec(
        select(UserPlatformModel).where(
            UserPlatformModel.origin == FEISHU_ORIGIN,
            UserPlatformModel.platform_uid.in_(candidates),
        )
    ).first()


def _find_user_by_email(session: Session, email: str | None) -> UserModel | None:
    if not email:
        return None
    return session.exec(select(UserModel).where(func.lower(UserModel.email) == email.lower())).first()


def _value_exists(session: Session, field, value: str) -> bool:
    return session.exec(select(UserModel.id).where(field == value)).first() is not None


def _unique_user_value(session: Session, field, base: str, fallback: str) -> str:
    cleaned = _clean_text(base) or fallback
    cleaned = cleaned[:100]
    if not _value_exists(session, field, cleaned):
        return cleaned
    suffix = hashlib.sha1(fallback.encode("utf-8")).hexdigest()[:8]
    max_base_len = 100 - len(suffix) - 1
    candidate = f"{cleaned[:max_base_len]}_{suffix}"
    index = 2
    while _value_exists(session, field, candidate):
        tail = f"{suffix}{index}"
        candidate = f"{cleaned[:100 - len(tail) - 1]}_{tail}"
        index += 1
    return candidate


def _bind_platform(session: Session, *, user_id: int, identity: FeishuIdentity) -> None:
    existing = _find_platform_binding(session, identity)
    if existing:
        existing.uid = int(user_id)
        existing.platform_uid = identity.platform_uid
        session.add(existing)
        return
    session.add(
        UserPlatformModel(
            uid=int(user_id),
            origin=FEISHU_ORIGIN,
            platform_uid=identity.platform_uid,
        )
    )


def bind_or_create_feishu_user(session: Session, identity: FeishuIdentity) -> BaseUserDTO:
    binding = _find_platform_binding(session, identity)
    if binding:
        user = session.get(UserModel, int(binding.uid))
        if not user:
            raise ValueError("Bound Feishu user does not exist")
        ensure_user_sample_workspace_membership(session, user)
        return BaseUserDTO.model_validate(user.model_dump())

    user = _find_user_by_email(session, identity.email)
    if user is None:
        account_base = identity.email or f"feishu_{identity.platform_uid}"
        account = _unique_user_value(session, UserModel.account, account_base, identity.platform_uid)
        name = _unique_user_value(session, UserModel.name, identity.name, identity.platform_uid)
        user = UserModel(
            account=account,
            name=name,
            email=identity.email or "",
            status=1,
            origin=FEISHU_ORIGIN,
            language="zh-CN",
            system_role="viewer",
        )
        session.add(user)
        session.flush()

    _bind_platform(session, user_id=int(user.id), identity=identity)
    auto_assign_tenants_by_email_domain(session, user)
    ensure_user_sample_workspace_membership(session, user)
    return BaseUserDTO.model_validate(user.model_dump())


def token_expires_delta() -> timedelta:
    return timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
