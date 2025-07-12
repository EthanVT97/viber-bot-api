import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
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
from .config import settings
from .monitoring import setup_monitoring
import asyncpg
import aioredis
import logging
from datetime import datetime
from typing import AsyncGenerator

# Configure logging before app initialization
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Async context manager for app lifespan management"""
    try:
        # Initialize connection pools
        app.state.pg_pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=settings.DATABASE_POOL_MIN,
            max_size=settings.DATABASE_POOL_MAX,
            timeout=settings.DATABASE_TIMEOUT,
            command_timeout=5
        )
        
        app.state.redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS
        )
        
        logger.info("Application startup complete")
        yield
        
    except Exception as e:
        logger.critical(f"Startup failed: {str(e)}")
        raise
        
    finally:
        # Cleanup resources
        if hasattr(app.state, 'pg_pool'):
            await app.state.pg_pool.close()
        if hasattr(app.state, 'redis'):
            await app.state.redis.close()
        logger.info("Application shutdown complete")

app = FastAPI(
    lifespan=lifespan,
    middleware=[
        Middleware(IPWhitelistMiddleware),
        Middleware(APIKeyAuthMiddleware),
        Middleware(GZipMiddleware),
    ],
    title="Viber Bot API",
    description="Production-ready Viber Bot API Service",
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None
)

# Setup monitoring and instrumentation
setup_monitoring(app)
app.include_router(admin_router)
app.state.limiter = limiter

# Enhanced exception handlers
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "message": "Rate limit exceeded",
            "retry_after": str(exc.detail),
            "documentation_url": settings.DOCS_URL
        },
        headers={"Retry-After": str(exc.detail)}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "request_id": request.state.request_id
        }
    )

# API endpoints with transaction support and enhanced error handling
@app.post("/customers")
@limiter.limit(f"{settings.RATE_LIMIT}/minute")
async def create_customer(
    data: CustomerCreate, 
    request: Request,
    db=Depends(get_db)
):
    try:
        async with db.acquire() as connection:
            async with connection.transaction():
                customer_id = await connection.fetchval(
                    """INSERT INTO customers (name, phone, region) 
                    VALUES ($1, $2, $3) 
                    RETURNING id""",
                    data.name, data.phone, data.region
                )
                
                await app.state.redis.hset(
                    f"customer:{customer_id}",
                    mapping={
                        "name": data.name,
                        "phone": data.phone,
                        "region": data.region,
                        "created_at": datetime.utcnow().isoformat()
                    }
                )
                
                logger.info(
                    "New customer created",
                    extra={
                        "customer_id": customer_id,
                        "phone": data.phone,
                        "endpoint": "/customers"
                    }
                )
                
                return {
                    "status": "success",
                    "customer_id": customer_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
    except asyncpg.PostgresError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Failed to create customer"
        )

@app.post("/payments")
@limiter.limit(f"{settings.RATE_LIMIT}/minute")
async def record_payment(
    data: Payment, 
    request: Request,
    db=Depends(get_db)
):
    try:
        async with db.acquire() as connection:
            async with connection.transaction():
                payment_id = await connection.fetchval(
                    """INSERT INTO payments 
                    (user_id, amount, method, reference_id) 
                    VALUES ($1, $2, $3, $4) 
                    RETURNING id""",
                    data.user_id, data.amount, data.method, data.reference_id
                )
                
                logger.info(
                    "Payment recorded",
                    extra={
                        "payment_id": payment_id,
                        "amount": data.amount,
                        "reference": data.reference_id
                    }
                )
                
                return {
                    "status": "success",
                    "payment_id": payment_id,
                    "processed_at": datetime.utcnow().isoformat()
                }
                
    except asyncpg.PostgresError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Failed to record payment"
        )

@app.post("/chat-logs")
@limiter.limit(f"{settings.RATE_LIMIT}/minute")
async def log_chat(
    data: ChatLog, 
    request: Request,
    db=Depends(get_db)
):
    try:
        async with db.acquire() as connection:
            async with connection.transaction():
                chat_id = await connection.fetchval(
                    """INSERT INTO chat_logs 
                    (viber_id, message, type, status) 
                    VALUES ($1, $2, $3, $4) 
                    RETURNING id""",
                    data.viber_id, data.message, data.type, data.status
                )
                
                await app.state.redis.publish(
                    "chat_messages",
                    json.dumps({
                        "id": chat_id,
                        "viber_id": data.viber_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                )
                
                logger.info(
                    "Chat message logged",
                    extra={
                        "chat_id": chat_id,
                        "viber_id": data.viber_id,
                        "message_type": data.type
                    }
                )
                
                return {
                    "status": "success",
                    "chat_id": chat_id,
                    "received_at": datetime.utcnow().isoformat()
                }
                
    except (asyncpg.PostgresError, aioredis.RedisError) as e:
        logger.error(f"Storage error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Failed to log chat message"
        )

# Health check endpoint
@app.get("/health", include_in_schema=False)
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }
