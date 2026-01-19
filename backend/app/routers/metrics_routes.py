from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis

from app.auth import Principal, require_roles
from app.deps import get_redis
from app.metrics import HTTP_REQUEST_DURATION
from app.redis_client import get_topic_partitions, stream_key, topic_set_key, xinfo_groups_safe


router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


@router.get("/summary")
async def metrics_summary(
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("admin", "consumer", "producer"))],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    """
    UI-friendly JSON summary (fast-ish, not exhaustive).
    Prometheus remains the source of truth for time-series history.
    """
    with HTTP_REQUEST_DURATION.labels(method="GET", path="/v1/metrics/summary").time():
        topics_b = await redis.smembers(topic_set_key())
        topics = sorted([t.decode("utf-8") if isinstance(t, bytes) else str(t) for t in topics_b])

        topic_stats: list[dict[str, Any]] = []
        for topic in topics:
            partitions = await get_topic_partitions(redis, topic=topic)
            partitions_stats: list[dict[str, Any]] = []
            for p in range(partitions):
                skey = stream_key(topic, p)
                length = await redis.xlen(skey)
                groups = await xinfo_groups_safe(redis, stream=skey)
                partitions_stats.append(
                    {
                        "partition": p,
                        "stream": skey,
                        "length": int(length),
                        "groups": groups,
                    }
                )
            topic_stats.append({"topic": topic, "partitions": partitions, "partition_stats": partitions_stats})

        # Basic Redis memory usage for quick diagnostics.
        info = await redis.info(section="memory")
        used_memory = info.get("used_memory", None)
        used_memory_human = info.get("used_memory_human", None)

        return {
            "topics": topic_stats,
            "redis": {"used_memory": used_memory, "used_memory_human": used_memory_human},
        }

