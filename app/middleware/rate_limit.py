from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as aioredis
from app.config import settings
import time
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis
    - Per-IP rate limiting
    - Configurable limits per minute/hour
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.redis_client = None
    
    async def setup_redis(self):
        """Initialize Redis connection lazily"""
        if not self.redis_client:
            try:
                self.redis_client = await aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self.redis_client.ping()
                logger.info("✅ Rate limiter connected to Redis")
            except Exception as e:
                logger.warning(f"⚠️ Redis unavailable for rate limiting: {e}")
                self.redis_client = None
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Setup Redis if not initialized
        if self.redis_client is None:
            await self.setup_redis()
        
        # If Redis is unavailable, skip rate limiting
        if self.redis_client is None:
            return await call_next(request)
        
        # Get client IP
        client_ip = request.client.host
        if request.headers.get("X-Forwarded-For"):
            client_ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
        
        # Check rate limits
        try:
            is_limited, retry_after = await self._check_rate_limit(client_ip)
            
            if is_limited:
                logger.warning(f"🚫 Rate limit exceeded for IP: {client_ip}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many requests. Try again in {retry_after} seconds.",
                        "retry_after": retry_after
                    },
                    headers={"Retry-After": str(retry_after)}
                )
        
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Don't block request if rate limiting fails
        
        return await call_next(request)
    
    async def _check_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        """
        Check if IP has exceeded rate limits
        Returns: (is_limited, retry_after_seconds)
        """
        current_time = int(time.time())
        
        # Per-minute limit
        minute_key = f"rate_limit:{client_ip}:minute:{current_time // 60}"
        minute_count = await self.redis_client.incr(minute_key)
        
        if minute_count == 1:
            await self.redis_client.expire(minute_key, 60)
        
        if minute_count > settings.RATE_LIMIT_PER_MINUTE:
            retry_after = 60 - (current_time % 60)
            return True, retry_after
        
        # Per-hour limit
        hour_key = f"rate_limit:{client_ip}:hour:{current_time // 3600}"
        hour_count = await self.redis_client.incr(hour_key)
        
        if hour_count == 1:
            await self.redis_client.expire(hour_key, 3600)
        
        if hour_count > settings.RATE_LIMIT_PER_HOUR:
            retry_after = 3600 - (current_time % 3600)
            return True, retry_after
        
        return False, 0


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Validate incoming requests:
    - File size limits
    - Content type validation
    - Request body size limits
    """
    
    MAX_REQUEST_SIZE = 50 * 1024 * 1024  # 50MB max request size
    
    async def dispatch(self, request: Request, call_next):
        # Check Content-Length header
        if request.headers.get("content-length"):
            content_length = int(request.headers["content-length"])
            
            if content_length > self.MAX_REQUEST_SIZE:
                logger.warning(f"🚫 Request too large: {content_length} bytes")
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "error": "request_too_large",
                        "message": f"Request body exceeds maximum size of {self.MAX_REQUEST_SIZE / (1024*1024)}MB"
                    }
                )
        
        return await call_next(request)