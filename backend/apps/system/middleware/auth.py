
from fastapi import Depends
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from common.core.config import settings
# from common.core.deps import get_current_user
from common.utils.whitelist import whiteUtils

class TokenMiddleware(BaseHTTPMiddleware):
    
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request, call_next):
        tokenkey = settings.TOKEN_KEY
        if self.is_options(request) or whiteUtils.is_whitelisted(request.url.path):
            return await call_next(request)
        token = request.headers.get(tokenkey)
        if not token or not token.startswith("Bearer "):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        """ user = await get_current_user()
        request.state.user = user """
        return await call_next(request)
    
    def is_options(self, request):
        return request.method == "OPTIONS"
    
    