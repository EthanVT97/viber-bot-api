from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from config import config

class IPWhitelistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.client.host != config.WHITELISTED_IP:
            raise HTTPException(status_code=403, detail="IP not allowed")
        return await call_next(request)

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        api_key = request.headers.get("X-API-Key", "")

        if "/customers" in path and api_key != config.CUSTOMER_API_KEY:
            raise HTTPException(status_code=401)
        if "/payments" in path and api_key != config.BILLING_API_KEY:
            raise HTTPException(status_code=401)
        if "/chat-logs" in path and api_key != config.CHATLOG_API_KEY:
            raise HTTPException(status_code=401)

        return await call_next(request)
