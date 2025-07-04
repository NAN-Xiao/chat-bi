import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request
from common.core.config import settings
class ResponseMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        
        if isinstance(response, JSONResponse) or request.url.path == f"{settings.API_V1_STR}/openapi.json":
            return response
    
        if response.headers.get("content-type") == "application/json":
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                
                raw_data = json.loads(body.decode())
                
                if isinstance(raw_data, dict) and all(k in raw_data for k in ["code", "data", "msg"]):
                    return JSONResponse(
                        content=raw_data,
                        status_code=response.status_code,
                        headers={
                            k: v for k, v in response.headers.items()
                            if k.lower() not in ("content-length", "content-type")
                        }
                    )
                
                wrapped_data = {
                    "code": 0,
                    "data": raw_data,
                    "msg": None
                }
                
                return JSONResponse(
                    content=wrapped_data,
                    status_code=response.status_code,
                    headers={
                        k: v for k, v in response.headers.items()
                        if k.lower() not in ("content-length", "content-type")
                    }
                )
            except Exception as e:
                logging.error(f"Response processing error: {str(e)}", exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={
                        "code": 500,
                        "data": None,
                        "msg": str(e)
                    }
                )
                
        return response


class exception_handler():
    @staticmethod
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "msg": exc.detail,
                "data": None
            }
        )


    @staticmethod
    async def global_exception_handler(request: Request, exc: Exception):
        logging.error(f"Error info: {str(exc)}", exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "msg": str(exc),
                "data": None
            }
        )

