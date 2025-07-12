from fastapi import FastAPI, Request, Depends
from fastapi.middleware import Middleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from .middleware import IPWhitelistMiddleware, APIKeyAuthMiddleware
from .rate_limiter import limiter
from .models import CustomerCreate, Payment, ChatLog
from .admin import router as admin_router
from .database import get_db
from .security import validate_api_key
from .config import config
import asyncpg
import aioredis
import logging
from datetime import datetime
import time

app = FastAPI(
    middleware=[
        Middleware(IPWhitelistMiddleware),
        Middleware(APIKeyAuthMiddleware),
        Middleware(GZipMiddleware)
    ]
)

app.include_router(admin_router)
app.state.limiter = limiter

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "ip": "%(client_ip)s"}'
)

class StructuredMessage:
    def __init__(self, message, **kwargs):
        self.message = message
        self.kwargs = kwargs

    def __str__(self):
        return f"{self.message} {json.dumps(self.kwargs)}"

# Async database and Redis connection pools
@app.on_event("startup")
async def startup_event():
    # PostgreSQL connection pool
    app.state.pg_pool = await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=5,
        max_size=20,
        timeout=30,
        command_timeout=5
    )
    
    # Redis connection
    app.state.redis = await aioredis.from_url(
        config.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20
    )
    
    # Initialize monitoring if configured
    if hasattr(config, 'SENTRY_DSN') and config.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            environment=config.ENVIRONMENT
        )
        app.add_middleware(SentryAsgiMiddleware)

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.pg_pool.close()
    await app.state.redis.close()

# Exception handlers
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "message": "Rate limit exceeded",
            "retry_after": str(exc.detail)
        },
        headers={"Retry-After": str(exc.detail)}
    )

# API endpoints with improved logging and database integration
@app.post("/customers")
@limiter.limit("5/minute")
async def create_customer(
    data: CustomerCreate, 
    request: Request,
    db=Depends(get_db)
):
    async with db.acquire() as connection:
        # Example database operation
        customer_id = await connection.fetchval(
            "INSERT INTO customers (name, phone, region) VALUES ($1, $2, $3) RETURNING id",
            data.name, data.phone, data.region
        )
        
        # Structured logging
        logging.info(
            StructuredMessage(
                "New customer created",
                customer_id=customer_id,
                phone=data.phone,
                endpoint="/customers"
            ),
            extra={"client_ip": request.client.host}
        )
        
        # Cache in Redis
        await app.state.redis.hset(
            f"customer:{customer_id}",
            mapping={
                "name": data.name,
                "phone": data.phone,
                "region": data.region
            }
        )
        
        return {
            "status": "success",
            "customer_id": customer_id,
            "timestamp": datetime.utcnow().isoformat()
        }

@app.post("/payments")
@limiter.limit("5/minute")
async def record_payment(
    data: Payment, 
    request: Request,
    db=Depends(get_db)
):
    async with db.acquire() as connection:
        payment_id = await connection.fetchval(
            """INSERT INTO payments 
            (user_id, amount, method, reference_id) 
            VALUES ($1, $2, $3, $4) RETURNING id""",
            data.user_id, data.amount, data.method, data.reference_id
        )
        
        logging.info(
            StructuredMessage(
                "Payment recorded",
                payment_id=payment_id,
                amount=data.amount,
                reference=data.reference_id
            ),
            extra={"client_ip": request.client.host}
        )
        
        return {
            "status": "success",
            "payment_id": payment_id,
            "processed_at": datetime.utcnow().isoformat()
        }

@app.post("/chat-logs")
@limiter.limit("5/minute")
async def log_chat(
    data: ChatLog, 
    request: Request,
    db=Depends(get_db)
):
    async with db.acquire() as connection:
        chat_id = await connection.fetchval(
            """INSERT INTO chat_logs 
            (viber_id, message, type, status) 
            VALUES ($1, $2, $3, $4) RETURNING id""",
            data.viber_id, data.message, data.type, data.status
        )
        
        logging.info(
            StructuredMessage(
                "Chat message logged",
                chat_id=chat_id,
                viber_id=data.viber_id,
                message_type=data.type
            ),
            extra={"client_ip": request.client.host}
        )
        
        # Publish to Redis pub/sub for real-time processing
        await app.state.redis.publish(
            "chat_messages",
            json.dumps({
                "id": chat_id,
                "viber_id": data.viber_id,
                "timestamp": datetime.utcnow().isoformat()
            })
        )
        
        return {
            "status": "success",
            "chat_id": chat_id,
            "received_at": datetime.utcnow().isoformat()
        }
