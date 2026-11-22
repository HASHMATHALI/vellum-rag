"""Sliding-window rate limiting (Redis sorted sets, in-memory fallback).

Note: the in-memory fallback is per-process. With several workers/instances configure REDIS_URL so limits are shared.
"""
import logging
import secrets
import time
from typing import Dict, List

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from app.config.settings import settings

logger = logging.getLogger(__name__)


def client_ip(request: Request) -> str:
    """Client address, honouring X-Forwarded-For only for the configured number of trusted proxy hops."""
    hops = settings.TRUSTED_PROXY_HOPS
    if hops > 0:
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self):
        self.redis_client = None
        self.memory: Dict[str, List[float]] = {}
        self.initialized = False
        self._last_sweep = time.time()

    async def init_redis(self):
        if self.initialized:
            return
        self.initialized = True
        if not settings.REDIS_URL:
            return
        try:
            self.redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)
            await self.redis_client.ping()
            logger.info("RateLimiter: using Redis.")
        except Exception as e:
            logger.warning("RateLimiter: Redis unavailable (%s); using in-memory limits.", type(e).__name__)
            self.redis_client = None

    def reset(self):
        self.memory.clear()

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Records a hit; returns True when the request exceeds the limit."""
        await self.init_redis()
        now = time.time()
        if self.redis_client:
            try:
                async with self.redis_client.pipeline(transaction=True) as pipe:
                    pipe.zremrangebyscore(key, 0, now - window_seconds)
                    pipe.zadd(key, {f"{now}:{secrets.token_hex(4)}": now})
                    pipe.zcard(key)
                    pipe.expire(key, window_seconds)
                    _, _, count, _ = await pipe.execute()
                return count > limit
            except Exception as e:
                logger.error("RateLimiter: Redis error (%s); falling back to memory.", type(e).__name__)
        if now - self._last_sweep > 300:
            self.memory = {k: [t for t in v if t > now - 3600] for k, v in self.memory.items()}
            self.memory = {k: v for k, v in self.memory.items() if v}
            self._last_sweep = now
        hits = [t for t in self.memory.get(key, []) if t > now - window_seconds]
        limited = len(hits) >= limit
        if not limited:
            hits.append(now)
        self.memory[key] = hits
        return limited


limiter = RateLimiter()


def _raise(window_seconds: int):
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please try again later.",
        headers={"Retry-After": str(window_seconds)},
    )


def rate_limit_ip(name: str, limit: int, window_seconds: int):
    async def dependency(request: Request):
        if await limiter.hit(f"rl:{name}:ip:{client_ip(request)}", limit, window_seconds):
            _raise(window_seconds)
    return dependency


def rate_limit_user(name: str, limit: int, window_seconds: int):
    from app.auth.dependencies import get_current_user

    async def dependency(request: Request, user=Depends(get_current_user)):
        if await limiter.hit(f"rl:{name}:user:{user.id}", limit, window_seconds):
            _raise(window_seconds)
    return dependency


async def rate_limit_key(key: str, limit: int, window_seconds: int) -> None:
    """Imperative check for keys only known inside the handler (e.g. login e-mail)."""
    if await limiter.hit(f"rl:{key}", limit, window_seconds):
        _raise(window_seconds)
