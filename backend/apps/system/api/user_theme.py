"""Account-owned color preference, independent of workspace and auth cache shards."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlmodel import select

from apps.system.models.user import UserModel
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep

router = APIRouter()


class ColorThemePreference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    theme: Literal['light', 'dark']


def require_account_session(request: Request, current_user: CurrentUser) -> None:
    # Embedded tokens may act as an assistant owner, not as that owner's account.
    if request.headers.get(settings.ASSISTANT_TOKEN_KEY) or request.headers.get('X-SHUZHI-ASK-TOKEN'):
        raise HTTPException(403, 'Account session required')
    # Identity assertion only, never a target user. Prevent a delayed request from
    # being authenticated as a newly logged-in account by the browser interceptor.
    if request.headers.get('X-SHUZHI-ACCOUNT-ID') != str(current_user.id):
        raise HTTPException(409, '登录账户已变化，请刷新页面后重试')


@router.get('/color-theme', response_model=ColorThemePreference)
def get_color_theme(request: Request, session: SessionDep, current_user: CurrentUser):
    require_account_session(request, current_user)
    theme = session.exec(select(UserModel.color_theme).where(UserModel.id == int(current_user.id))).first()
    if theme is None:
        raise HTTPException(404, 'Account not found')
    return ColorThemePreference(theme=theme)


@router.put('/color-theme', response_model=ColorThemePreference)
def save_color_theme(request: Request, preference: ColorThemePreference, session: SessionDep, current_user: CurrentUser):
    require_account_session(request, current_user)
    # Update only this setting; concurrent account edits must not be overwritten.
    result = session.execute(update(UserModel).where(UserModel.id == int(current_user.id)).values(color_theme=preference.theme))
    if result.rowcount != 1:
        raise HTTPException(404, 'Account not found')
    session.commit()
    return preference
