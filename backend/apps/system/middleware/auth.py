
import base64

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security.utils import get_authorization_scheme_param
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from apps.system.crud.apikey_manage import get_api_key
from apps.system.crud.assistant import get_assistant_info, get_assistant_user
from apps.system.crud.tenant import (
    DEFAULT_TENANT_CODE,
    DEFAULT_TENANT_ID,
    DEFAULT_TENANT_NAME,
    TENANT_ROLE_MEMBER,
    TenantContext,
    auto_assign_tenants_by_email_domain,
    attach_tenant_context,
    get_active_tenant,
    resolve_current_tenant,
    validate_tenant_security_policy,
)
from apps.system.crud.user import get_user_by_account, get_user_info
from apps.system.models.system_model import ApiKeyModel, AssistantModel
from apps.system.schemas.system_schema import AssistantHeader, UserInfoDTO
from common.core import security
from common.core.config import settings
from common.core.db import engine
from common.core.deps import get_i18n
from common.core.response_middleware import cors_headers_for_request
from common.core.schemas import TokenPayload
from common.utils.locale import I18n
from common.utils.utils import AppLogUtil, get_origin_from_referer
from common.utils.whitelist import whiteUtils


class TokenMiddleware(BaseHTTPMiddleware):



    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request, call_next):

        if self.is_options(request) or whiteUtils.is_whitelisted(request.url.path):
            return await call_next(request)
        assistantTokenKey = settings.ASSISTANT_TOKEN_KEY
        assistantToken = request.headers.get(assistantTokenKey)
        askToken = request.headers.get("X-ZHISHU-ASK-TOKEN")
        trans = await get_i18n(request)
        if askToken:
            validate_pass, data = await self.validateAskToken(request, askToken, trans)
            if validate_pass:
                request.state.current_user = data
                return await call_next(request)
            message = trans('i18n_permission.authenticate_invalid', msg = data)
            return JSONResponse(message, status_code=401, headers=cors_headers_for_request(request))
        #if assistantToken and assistantToken.lower().startswith("assistant "):
        if assistantToken:
            validator: tuple[any] = await self.validateAssistant(request, assistantToken, trans)
            if validator[0]:
                request.state.current_user = validator[1]
                if request.state.current_user and trans.lang:
                    request.state.current_user.language = trans.lang
                request.state.assistant = validator[2]
                origin = request.headers.get("X-ZHISHU-HOST-ORIGIN") or get_origin_from_referer(request)
                if origin and validator[2]:
                    request.state.assistant.request_origin = origin
                return await call_next(request)
            message = trans('i18n_permission.authenticate_invalid', msg = validator[1])
            return JSONResponse(message, status_code=401, headers=cors_headers_for_request(request))
        #validate pass
        tokenkey = settings.TOKEN_KEY
        token = request.headers.get(tokenkey)
        validate_pass, data = await self.validateToken(request, token, trans)
        if validate_pass:
            request.state.current_user = data
            return await call_next(request)

        message = trans('i18n_permission.authenticate_invalid', msg = data)
        return JSONResponse(message, status_code=401, headers=cors_headers_for_request(request))

    def is_options(self, request: Request):
        return request.method == "OPTIONS"

    def _tenant_id_from_request(
        self,
        request: Request,
        token_tenant_id: int | None = None,
        *,
        allow_header_override: bool = True,
    ) -> int | None:
        if not allow_header_override:
            return token_tenant_id
        raw = request.headers.get("X-ZHISHU-TENANT-ID")
        if not raw:
            return token_tenant_id
        try:
            return int(raw)
        except (TypeError, ValueError):
            return token_tenant_id

    def _apply_session_auth_origin(self, user: UserInfoDTO, auth_origin: int | None) -> UserInfoDTO:
        if auth_origin is None:
            return user
        user.origin = int(auth_origin)
        return user

    def _attach_tenant(
        self,
        request: Request,
        session: Session,
        user: UserInfoDTO,
        token_tenant_id: int | None = None,
        *,
        allow_header_tenant_override: bool = True,
    ) -> UserInfoDTO:
        requested_tenant_id = self._tenant_id_from_request(
            request,
            token_tenant_id,
            allow_header_override=allow_header_tenant_override,
        )
        tenant = resolve_current_tenant(session, user, requested_tenant_id=requested_tenant_id)
        if tenant is not None:
            validate_tenant_security_policy(
                session,
                tenant_id=int(tenant.id),
                user=user,
            )
        request.state.current_tenant = tenant
        return attach_tenant_context(user, tenant)

    def _assistant_tenant_id_from_payload(self, payload: dict, assistant_info: AssistantModel) -> int:
        assistant_tenant_id = int(getattr(assistant_info, "tenant_id", None) or DEFAULT_TENANT_ID)
        payload_tenant_id = payload.get("tenant_id")
        if payload_tenant_id and int(payload_tenant_id) != assistant_tenant_id:
            raise PermissionError("Token tenant payload mismatch!")
        return assistant_tenant_id

    def _attach_assistant_tenant(
        self,
        request: Request,
        session: Session,
        user: UserInfoDTO,
        assistant_info: AssistantModel,
    ) -> UserInfoDTO:
        tenant_id = int(getattr(assistant_info, "tenant_id", None) or DEFAULT_TENANT_ID)
        try:
            tenant = get_active_tenant(session, tenant_id=tenant_id)
        except Exception:
            tenant = None
        if tenant:
            context = TenantContext(
                id=int(tenant.id),
                code=tenant.code,
                name=tenant.name,
                role=TENANT_ROLE_MEMBER,
            )
        elif tenant_id == DEFAULT_TENANT_ID:
            context = TenantContext(
                id=DEFAULT_TENANT_ID,
                code=DEFAULT_TENANT_CODE,
                name=DEFAULT_TENANT_NAME,
                role=TENANT_ROLE_MEMBER,
            )
        else:
            raise PermissionError("Assistant tenant is disabled or does not exist")
        request.state.current_tenant = context
        return attach_tenant_context(user, context)

    async def validateAskToken(self, request: Request, askToken: str | None, trans: I18n):
        if not askToken:
            return False, "Miss Token[X-ZHISHU-ASK-TOKEN]!"
        schema, param = get_authorization_scheme_param(askToken)
        if schema.lower() != "sk":
            return False, "Token schema error!"
        try:
            unverified_payload = jwt.decode(
                param, options={"verify_signature": False, "verify_exp": False}, algorithms=[security.ALGORITHM]
            )
            access_key = unverified_payload.get('access_key', None)

            if not access_key:
                return False, "Miss access_key payload error!"
            with Session(engine) as session:
                api_key_model = await get_api_key(session, access_key)
                api_key_model = ApiKeyModel.model_validate(api_key_model) if api_key_model else None
                if not api_key_model:
                    return False, "Invalid access_key!"
                if not api_key_model.status:
                    return False, "Disabled access_key!"
                payload = jwt.decode(
                    param, api_key_model.secret_key, algorithms=[security.ALGORITHM]
                )
                if payload.get('access_key') != access_key:
                    return False, "Token access_key payload mismatch!"
                api_key_tenant_id = getattr(api_key_model, "tenant_id", None)
                payload_tenant_id = payload.get("tenant_id")
                header_tenant_id = self._tenant_id_from_request(request, None)
                bound_tenant_id = api_key_tenant_id or payload_tenant_id or header_tenant_id
                if api_key_tenant_id and payload_tenant_id and int(payload_tenant_id) != int(api_key_tenant_id):
                    return False, "Token tenant payload mismatch!"
                if api_key_tenant_id and header_tenant_id and int(header_tenant_id) != int(api_key_tenant_id):
                    return False, "Token tenant header mismatch!"
                uid = api_key_model.uid
                session_user = await get_user_info(session = session, user_id = uid)
                if not session_user:
                    message = trans('i18n_not_exist', msg = trans('i18n_user.account'))
                    raise Exception(message)
                session_user = UserInfoDTO.model_validate(session_user)
                if session_user.status != 1:
                    message = trans('i18n_login.user_disable', msg = trans('i18n_concat_admin'))
                    raise Exception(message)
                if auto_assign_tenants_by_email_domain(session, session_user):
                    session.commit()
                session_user = self._attach_tenant(
                    request,
                    session,
                    session_user,
                    bound_tenant_id,
                    allow_header_tenant_override=not bool(api_key_tenant_id),
                )
                return True, session_user
        except Exception as e:
            msg = str(e)
            AppLogUtil.exception(f"Token validation error: {msg}")
            if 'expired' in msg:
                return False, jwt.ExpiredSignatureError(trans('i18n_permission.token_expired'))
            return False, e

    async def validateToken(self, request: Request, token: str | None, trans: I18n):
        if not token:
            return False, f"Miss Token[{settings.TOKEN_KEY}]!"
        schema, param = get_authorization_scheme_param(token)
        if schema.lower() != "bearer":
            return False, "Token schema error!"
        try:
            payload = jwt.decode(
                param, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
            )
            token_data = TokenPayload(**payload)
            with Session(engine) as session:
                session_user = await get_user_info(session = session, user_id = token_data.id)
                if not session_user:
                    message = trans('i18n_not_exist', msg = trans('i18n_user.account'))
                    raise Exception(message)
                session_user = UserInfoDTO.model_validate(session_user)
                if session_user.status != 1:
                    message = trans('i18n_login.user_disable', msg = trans('i18n_concat_admin'))
                    raise Exception(message)
                session_user = self._apply_session_auth_origin(session_user, token_data.auth_origin)
                if auto_assign_tenants_by_email_domain(session, session_user):
                    session.commit()
                session_user = self._attach_tenant(request, session, session_user, token_data.tenant_id)
                return True, session_user
        except Exception as e:
            msg = str(e)
            AppLogUtil.exception(f"Token validation error: {msg}")
            if 'expired' in msg:
                return False, jwt.ExpiredSignatureError(trans('i18n_permission.token_expired'))
            return False, e


    async def validateAssistant(self, request: Request, assistantToken: str | None, trans: I18n) -> tuple[any]:
        if not assistantToken:
            return False, f"Miss Token[{settings.TOKEN_KEY}]!"
        schema, param = get_authorization_scheme_param(assistantToken)

        try:
            if schema.lower() == 'embedded':
                return await self.validateEmbedded(request, param, trans)
            if schema.lower() != "assistant":
                return False, "Token schema error!"
            payload = jwt.decode(
                param, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
            )
            if not payload['assistant_id']:
                return False, "Miss assistant payload error!"
            with Session(engine) as session:
                """ session_user = await get_user_info(session = session, user_id = token_data.id)
                session_user = UserInfoDTO.model_validate(session_user) """
                token_data = TokenPayload(**payload)
                assistant_info = await get_assistant_info(session=session, assistant_id=payload['assistant_id'])
                assistant_info = AssistantModel.model_validate(assistant_info)
                self._assistant_tenant_id_from_payload(payload, assistant_info)
                session_user = get_assistant_user(id = token_data.id)
                session_user = self._attach_assistant_tenant(request, session, session_user, assistant_info)
                assistant_info = AssistantHeader.model_validate(assistant_info.model_dump(exclude_unset=True))
                assistant_info.online = bool(payload.get("assistant_online", False))

                return True, session_user, assistant_info
        except Exception as e:
            AppLogUtil.exception(f"Assistant validation error: {str(e)}")
            # Return False and the exception message
            return False, e

    async def validateEmbedded(self, request: Request, param: str, trans: I18n) -> tuple[any]:
        try:
            unverified_payload: dict = jwt.decode(
                param,
                options={"verify_signature": False, "verify_exp": False},
                algorithms=[security.ALGORITHM]
            )
            app_key = unverified_payload.get('appId', '')
            embeddedId = unverified_payload.get('embeddedId', None)
            if not embeddedId:
                embeddedId = xor_decrypt(app_key)
            with Session(engine) as session:
                assistant_info = await get_assistant_info(session=session, assistant_id=embeddedId)
                assistant_info = AssistantModel.model_validate(assistant_info)
                payload = jwt.decode(
                    param, assistant_info.app_secret, algorithms=[security.ALGORITHM]
                )
                self._assistant_tenant_id_from_payload(payload, assistant_info)
                verified_embedded_id = payload.get('embeddedId', None)
                if not verified_embedded_id and payload.get('appId'):
                    verified_embedded_id = xor_decrypt(payload.get('appId'))
                if str(verified_embedded_id) != str(embeddedId):
                    return False, "Token embeddedId payload mismatch!"
                account = payload.get('account')
                if not account:
                    return False, "Miss account payload error!"
                assistant_info = AssistantHeader.model_validate(assistant_info.model_dump(exclude_unset=True))
                """ session_user = await get_user_info(session = session, user_id = token_data.id)
                session_user = UserInfoDTO.model_validate(session_user) """
                session_user = get_user_by_account(session = session, account=account)
                if not session_user:
                    message = trans('i18n_not_exist', msg = trans('i18n_user.account'))
                    raise Exception(message)
                session_user = await get_user_info(session = session, user_id = session_user.id)

                session_user = UserInfoDTO.model_validate(session_user)
                if session_user.status != 1:
                    message = trans('i18n_login.user_disable', msg = trans('i18n_concat_admin'))
                    raise Exception(message)
                session_user = self._attach_assistant_tenant(request, session, session_user, assistant_info)
                return True, session_user, assistant_info
        except Exception as e:
            AppLogUtil.exception(f"Embedded validation error: {str(e)}")
            # Return False and the exception message
            return False, e

def xor_decrypt(encrypted_str: str, key: int = 0xABCD1234) -> int:
    encrypted_bytes = base64.urlsafe_b64decode(encrypted_str)
    hex_str = encrypted_bytes.hex()
    encrypted_num = int(hex_str, 16)
    return encrypted_num ^ key
