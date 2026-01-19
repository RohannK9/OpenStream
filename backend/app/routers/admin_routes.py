from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis

from app.auth import Principal, require_roles
from app.deps import get_redis
from app.metrics import HTTP_REQUEST_DURATION
from app.models import GroupCreateRequest, GroupResetRequest
from app.redis_client import ensure_topic, get_topic_partitions, stream_key
from app.settings import settings


router = APIRouter(prefix="/v1/topics", tags=["admin"])


@router.post("/{topic}/groups")
async def create_group(
    topic: str,
    req: GroupCreateRequest,
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("admin"))],
    redis: Annotated[Redis, Depends(get_redis)],
):
    with HTTP_REQUEST_DURATION.labels(method="POST", path="/v1/topics/{topic}/groups").time():
        partitions = req.partitions or await get_topic_partitions(redis, topic=topic)
        await ensure_topic(redis, topic=topic, partitions=partitions)
        created = 0
        for p in range(partitions):
            skey = stream_key(topic, p)
            try:
                # mkstream=True creates stream if doesn't exist yet.
                await redis.xgroup_create(name=skey, groupname=req.group, id=req.start_id, mkstream=True)
                created += 1
            except Exception:
                # BUSYGROUP or other errors; treat as already created.
                continue
        return {"topic": topic, "group": req.group, "partitions": partitions, "created": created}


@router.post("/{topic}/groups/{group}/reset")
async def reset_group(
    topic: str,
    group: str,
    req: GroupResetRequest,
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("admin"))],
    redis: Annotated[Redis, Depends(get_redis)],
):
    """
    Reset a consumer group's offset for replay.
    Equivalent to: XGROUP SETID <stream> <group> <start_id>
    """
    with HTTP_REQUEST_DURATION.labels(
        method="POST", path="/v1/topics/{topic}/groups/{group}/reset"
    ).time():
        partitions = await get_topic_partitions(redis, topic=topic)
        updated = 0
        for p in range(partitions):
            skey = stream_key(topic, p)
            try:
                await redis.xgroup_setid(name=skey, groupname=group, id=req.start_id)
                updated += 1
            except Exception:
                continue
        if updated == 0:
            raise HTTPException(status_code=404, detail="Group not found on any partition")
        return {"topic": topic, "group": group, "start_id": req.start_id, "updated_partitions": updated}


@router.get("/{topic}/describe")
async def describe_topic(
    topic: str,
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("admin", "consumer", "producer"))],
    redis: Annotated[Redis, Depends(get_redis)],
):
    partitions = await get_topic_partitions(redis, topic=topic)
    return {"topic": topic, "partitions": partitions, "max_stream_len": settings.backpressure_max_stream_len}

