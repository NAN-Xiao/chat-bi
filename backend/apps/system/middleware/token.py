
from fastapi import HTTPException, Request
from common.core.config import settings
from common.core.deps import get_current_user




async def verify_token(request: Request, call_next):
    print(request.url.path)
    if request.url.path == "/login/localLogin":
        return await call_next(request)
    try:
        key = settings.TOKEN_KEY
        token = request.headers.get(key)
        get_current_user(token)
    except (Exception):
        return HTTPException(status_code=401, detail="Invalid token")
    response = await call_next(request)
    return response


    