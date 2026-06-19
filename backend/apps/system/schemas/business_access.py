from fastapi import HTTPException

from apps.system.crud.user import is_platform_admin
from apps.system.schemas.system_schema import UserInfoDTO
from common.core.deps import CurrentUser, Trans


CHATBI_FORBIDDEN_MESSAGE = "平台管理员用于 SaaS 平台运营管理，不能访问工作空间侧 ChatBI 业务功能。"
TENANT_REQUIRED_MESSAGE = "当前账号尚未加入工作空间，请先创建或加入工作空间后再访问工作空间侧业务功能。"


def ensure_chatbi_business_user(current_user: UserInfoDTO, trans=None) -> None:
    if is_platform_admin(current_user):
        message = (
            trans("i18n_permission.platform_admin_chatbi_forbidden")
            if trans
            else CHATBI_FORBIDDEN_MESSAGE
        )
        raise HTTPException(status_code=403, detail=message)
    if not getattr(current_user, "tenant_id", None):
        raise HTTPException(status_code=403, detail=TENANT_REQUIRED_MESSAGE)


async def require_chatbi_business_user(current_user: CurrentUser, trans: Trans):
    ensure_chatbi_business_user(current_user, trans)
