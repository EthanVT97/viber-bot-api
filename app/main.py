import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware import Middleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from slowapi.errors import RateLimitExceeded
from .middleware import IPWhitelistMiddleware, APIKeyAuthMiddleware, RequestContextMiddleware
from .rate_limiter import limiter
from .models import CustomerCreate, Payment, ChatLog
from .admin import router as admin_router
from .database import get_db
from .security import validate_api_key
from .config import settings
from .monitoring import setup_monitoring
from .cache import cache_response
import asyncpg
import aioredis
import logging
from datetime import datetime
from typing import AsyncGenerator, Dict, Any
import uuid

# Configure structured logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(request_id)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Async context manager for app lifespan management with health checks"""
    try:
        # Initialize connection pools with health checks
        app.state.pg_pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=settings.DATABASE_POOL_MIN,
            max_size=settings.DATABASE_POOL_MAX,
            timeout=settings.DATABASE_TIMEOUT,
            command_timeout=5
        )
        # Verify database connection
        async with app.state.pg_pool.acquire() as conn:
            await conn.execute("SELECT 1")
        
        app.state.redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS
        )
        # Verify Redis connection
        await app.state.redis.ping()
        
        logger.info("Application startup complete", extra={
            "db_connections": settings.DATABASE_POOL_MIN,
            "redis_connections": settings.REDIS_MAX_CONNECTIONS
        })
        
        yield
        
    except Exception as e:
        logger.critical(f"Startup failed: {str(e)}", exc_info=True)
        raise
        
    finally:
        # Cleanup resources with timeout
        try:
            if hasattr(app.state, 'pg_pool'):
                await asyncio.wait_for(app.state.pg_pool.close(), timeout=5)
            if hasattr(app.state, 'redis'):
                await asyncio.wait_for(app.state.redis.close(), timeout=5)
            logger.info("Application shutdown complete")
        except asyncio.TimeoutError:
            logger.error("Resource cleanup timed out")

app = FastAPI(
    lifespan=lifespan,
    middleware=[
        Middleware(RequestContextMiddleware),  # Adds request_id and timing
        Middleware(IPWhitelistMiddleware),
        Middleware(APIKeyAuthMiddleware),
        Middleware(GZipMiddleware),
    ],
    title="Viber Bot API",
    description="Production-ready Viber Bot API Service",
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None
)

# Setup monitoring and instrumentation
setup_monitoring(app)
app.include_router(admin_router, prefix="/admin")
app.state.limiter = limiter

# Enhanced exception handlers
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=jsonable_encoder({
            "status": "error",
            "code": "rate_limit_exceeded",
            "message": "Too many requests",
            "limit": settings.RATE_LIMIT,
            "retry_after": exc.retry_after,
            "request_id": request.state.request_id,
            "documentation_url": settings.DOCS_URL
        }),
        headers={"Retry-After": str(exc.retry_after)}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder({
            "status": "error",
            "code": exc.detail.get("code") if isinstance(exc.detail, dict) else "http_error",
            "message": exc.detail.get("message") if isinstance(exc.detail, dict) else exc.detail,
            "request_id": request.state.request_id
        }),
        headers=exc.headers
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())
    logger.critical(f"Unhandled exception - {error_id}: {str(exc)}", exc_info=True,
                  extra={"request_id": request.state.request_id})
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "code": "internal_server_error",
            "message": "An unexpected error occurred",
            "error_id": error_id,
            "request_id": request.state.request_id
        }
    )

# API endpoints with enhanced features
@app.post("/customers", status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT}/minute")
@cache_response(key_prefix="customer", ttl=3600)
async def create_customer(
    data: CustomerCreate, 
    request: Request,
    db=Depends(get_db)
) -> Dict[str, Any]:
    """Create a new customer with data validation and caching"""
    try:
        async with db.acquire() as connection:
            async with connection.transaction():
                # Insert with conflict handling
                customer_id = await connection.fetchval(
                    """INSERT INTO customers (name, phone, region) 
                    VALUES ($1, $2, $3)
                    ON CONFLICT (phone) DO UPDATE SET 
                    name = EXCLUDED.name, region = EXCLUDED.region
                    RETURNING id""",
                    data.name, data.phone, data.region
                )
                
                customer_data = {
                    "id": customer_id,
                    "name": data.name,
                    "phone": data.phone,
                    "region": data.region,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                # Cache customer data
                await request.app.state.redis.hset(
                    f"customer:{customer_id}",
                    mapping=customer_data
                )
                
                logger.info("Customer created/updated", extra={
                    "customer_id": customer_id,
                    "operation": "create_customer"
                })
                
                return {
                    "status": "success",
                    "data": customer_data,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
    except asyncpg.PostgresError as e:
        logger.error(f"Database error: {str(e)}", extra={
            "request_id": request.state.request_id
        })
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "database_error",
                "message": "Failed to process customer data"
            }
        )

# Health check endpoint with system status
@app.get("/health", include_in_schema=False)
async def health_check(request: Request) -> Dict[str, Any]:
    """Comprehensive health check endpoint"""
    checks = {
        "database": False,
        "redis": False,
        "status": "healthy"
    }
    
    try:
        # Check database connection
        async with request.app.state.pg_pool.acquire() as conn:
            await conn.execute("SELECT 1")
            checks["database"] = True
    except Exception as e:
        checks["database"] = False
        checks["status"] = "degraded"
        logger.warning(f"Database health check failed: {str(e)}")
    
    try:
        # Check Redis connection
        await request.app.state.redis.ping()
        checks["redis"] = True
    except Exception as e:
        checks["redis"] = False
        checks["status"] = "degraded"
        logger.warning(f"Redis health check failed: {str(e)}")
    
    return {
        **checks,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat()
        }
