from fastapi import FastAPI, Request, Depends
from fastapi.middleware import Middleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from .middleware import IPWhitelistMiddleware, APIKeyAuthMiddleware
from .rate_limiter import limiter
from .models import CustomerCreate, Payment, ChatLog
from .admin import router as admin_router
import logging
from datetime import datetime

app = FastAPI(middleware=[
    Middleware(IPWhitelistMiddleware),
    Middleware(APIKeyAuthMiddleware)
])

app.include_router(admin_router)
app.state.limiter = limiter

# Configure logging
logging.basicConfig(
    filename="logs/api.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

@app.exception_handler(RateLimitExceeded)
async def handle_rate_limit(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Too many requests"},
        headers={"Retry-After": str(exc.detail)}
    )

@app.post("/customers")
@limiter.limit("5/minute")
async def create_customer(data: CustomerCreate, request: Request):
    logging.info(f"New customer: {data.phone}")
    return {"status": "success"}

@app.post("/payments")
@limiter.limit("5/minute")
async def record_payment(data: Payment, request: Request):
    logging.info(f"Payment recorded: {data.reference_id}")
    return {"status": "success"}

@app.post("/chat-logs")
@limiter.limit("5/minute")
async def log_chat(data: ChatLog, request: Request):
    logging.info(f"Chat from {data.viber_id}")
    return {"status": "success"}
