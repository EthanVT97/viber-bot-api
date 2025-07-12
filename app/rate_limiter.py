import time
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from config import settings
import aioredis
import ujson
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

class EnhancedLimiter(Limiter):
    def __init__(self):
        super().__init__(
            key_func=self._enhanced_key_func,
            default_limits=[f"{settings.RATE_LIMIT} per minute"]
        )
    
    async def _enhanced_key_func(self, request: Request) -> str:
        """Enhanced key function that considers both IP and API key"""
        client_ip = get_remote_address(request)
        api_key = request.headers.get("X-API-Key", "")
        return f"{client_ip}:{api_key}"

limiter = EnhancedLimiter()

@asynccontextmanager
async def redis_connection(request: Request):
    """Context manager for Redis connection handling"""
    try:
        if not hasattr(request.app.state, 'redis'):
            request.app.state.redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        yield request.app.state.redis
    except aioredis.RedisError as e:
        logger.error(f"Redis connection error: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable"
        )

async def sliding_window_rate_limiter(request: Request, call_next):
    """Sliding window rate limiter using Redis sorted sets"""
    async with redis_connection(request) as redis:
        identifier = limiter._enhanced_key_func(request)
        current_time = int(time.time())
        window_size = 60  # seconds
        
        try:
            # Use Redis pipeline for atomic operations
            pipeline = redis.pipeline()
            key = f"rate_limit:{identifier}"
            
            # Add current timestamp to the set
            pipeline.zadd(key, {str(current_time): current_time})
            
            # Remove old timestamps (outside window)
            pipeline.zremrangebyscore(key, 0, current_time - window_size)
            
            # Get count of remaining timestamps
            pipeline.zcard(key)
            
            # Set expiration
            pipeline.expire(key, window_size + 10)  # Extra buffer
            
            # Execute all commands
            _, _, request_count, _ = await pipeline.execute()
            
            # Check rate limit
            if request_count > settings.RATE_LIMIT:
                reset_time = current_time + window_size
                raise RateLimitExceeded(
                    detail={
                        "error": "rate_limit_exceeded",
                        "limit": settings.RATE_LIMIT,
                        "remaining": 0,
                        "reset": reset_time
                    },
                    retry_after=reset_time - current_time
                )
            
            # Add rate limit headers to response
            response = await call_next(request)
            response.headers.update({
                "X-RateLimit-Limit": str(settings.RATE_LIMIT),
                "X-RateLimit-Remaining": str(max(0, settings.RATE_LIMIT - request_count)),
                "X-RateLimit-Reset": str(current_time + window_size)
            })
            
            return response
            
        except aioredis.RedisError as e:
            logger.error(f"Redis operation failed: {str(e)}")
            # Fail open - don't block requests if Redis is down
            return await call_next(request)

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Enhanced rate limit exceeded handler"""
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "message": "Rate limit exceeded",
            "limit": exc.detail.get("limit"),
            "remaining": exc.detail.get("remaining"),
            "reset": exc.detail.get("reset")
        },
        headers={
            "Retry-After": str(exc.retry_after),
            "X-RateLimit-Limit": str(exc.detail.get("limit")),
            "X-RateLimit-Remaining": str(exc.detail.get("remaining")),
            "X-RateLimit-Reset": str(exc.detail.get("reset"))
        }
    )

def get_rate_limiter():
    """Get the configured rate limiter instance"""
    return {
        "limiter": limiter,
        "middleware": sliding_window_rate_limiter,
        "exception_handler": rate_limit_exceeded_handler
        }
