from __future__ import annotations

from typing import AsyncGenerator

from redis.asyncio import Redis

from app.settings import settings


_redis: Redis | None = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=False)
    yield _redis

