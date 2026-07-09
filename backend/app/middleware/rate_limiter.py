import time
import logging
from typing import Dict, Tuple
from fastapi import Request, HTTPException, status
import redis.asyncio as aioredis
from app.config.settings import settings

logger = logging.getLogger(__name__)

class RateLimiter:
    """Rate limiter utilizing Redis for production or an in-memory dictionary fallback."""
    def __init__(self):
        self.redis_client = None
        self.in_memory_store: Dict[str, list] = {}  # key -> list of timestamps
        self.initialized = False

    async def init_redis(self):
        if self.initialized:
            return
        try:
            if settings.REDIS_URL:
                self.redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                # Test connection
                await self.redis_client.ping()
                logger.info("RateLimiter: Successfully connected to Redis.")
        except Exception as e:
            logger.warning(f"RateLimiter: Redis connection failed ({e}). Falling back to in-memory rate limiting.")
            self.redis_client = None
        self.initialized = True

    async def is_rate_limited(self, key: str, limit: int, window_seconds: int) -> bool:
        """Checks if a key (e.g., client IP or User ID) has exceeded the rate limit."""
        await self.init_redis()
        
        if self.redis_client:
            try:
                # Use a sliding window rate limiter with Redis sorted sets
                now = time.time()
                clear_before = now - window_seconds
                
                async with self.redis_client.pipeline(transaction=True) as pipe:
                    # Remove timestamps older than the window
                    pipe.zremrangebyscore(key, 0, clear_before)
                    # Add current timestamp
                    pipe.zadd(key, {str(now): now})
                    # Count elements in the window
                    pipe.zcard(key)
                    # Set expiry on the key to prevent leaks
                    pipe.expire(key, window_seconds)
                    
                    _, _, count, _ = await pipe.execute()
                    
                return count > limit
            except Exception as e:
                logger.error(f"RateLimiter: Redis exception ({e}). Falling back to in-memory.")
                # Fallback to in-memory logic on Redis failure
        
        # In-memory rate limiting (fallback)
        now = time.time()
        clear_before = now - window_seconds
        
        # Initialize key list
        if key not in self.in_memory_store:
            self.in_memory_store[key] = []
            
        # Clean expired timestamps
        self.in_memory_store[key] = [t for t in self.in_memory_store[key] if t > clear_before]
        
        # Check limit
        if len(self.in_memory_store[key]) >= limit:
            return True
            
        self.in_memory_store[key].append(now)
        return False

# Global rate limiter instance
limiter = RateLimiter()

def rate_limit(limit: int = 60, window_seconds: int = 60):
    """FastAPI dependency for rate limiting."""
    async def dependency(request: Request):
        # Build rate limit key: combination of user ID (if auth) or client host IP and the route path
        client_ip = request.client.host if request.client else "unknown"
        user_id = "anonymous"
        
        # If user is authenticated, we might have it stored in state (optional)
        if hasattr(request.state, "user") and request.state.user:
            user_id = str(request.state.user.id)
            
        key = f"rate_limit:{user_id}:{client_ip}:{request.url.path}"
        
        if await limiter.is_rate_limited(key, limit, window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )
    return dependency
