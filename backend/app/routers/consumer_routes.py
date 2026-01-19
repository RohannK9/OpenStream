from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis

from app.auth import Principal, require_roles
from app.deps import get_redis
from app.metrics import CONSUMER_ACK_TOTAL, CONSUMER_READ_EVENTS_TOTAL, HTTP_REQUEST_DURATION
from app.models import (
    AckRequest,
    AckResponse,
    ClaimRequest,
    ClaimResponse,
    ReadEvent,
    ReadRequest,
    ReadResponse,
)
from app.redis_client import get_topic_partitions, stream_key, xreadgroup_multi


router = APIRouter(prefix="/v1/topics", tags=["consumers"])


def _partition_from_stream(topic: str, stream: str) -> int:
    # stream format: os:stream:{topic}:{partition}
    # take last segment
    try:
        return int(stream.split(":")[-1])
    except Exception:
        return 0


@router.post("/{topic}/groups/{group}/read", response_model=ReadResponse)
async def read_group(
    topic: str,
    group: str,
    req: ReadRequest,
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("consumer", "admin"))],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ReadResponse:
    with HTTP_REQUEST_DURATION.labels(
        method="POST", path="/v1/topics/{topic}/groups/{group}/read"
    ).time():
        partitions = await get_topic_partitions(redis, topic=topic)
        parts = req.partitions or list(range(partitions))
        streams = {stream_key(topic, p): ">" for p in parts}

        try:
            msgs = await xreadgroup_multi(
                redis,
                group=group,
                consumer=req.consumer,
                streams=streams,
                count=req.count,
                block_ms=req.block_ms,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail="Read failed") from e

        events: list[ReadEvent] = []
        for m in msgs:
            p = _partition_from_stream(topic, m.stream)
            events.append(
                ReadEvent(
                    partition=p,
                    redis_id=m.message_id,
                    event_type=m.fields.get("event_type"),
                    payload_json=m.fields.get("payload_json"),
                    timestamp_ms=int(m.fields["timestamp_ms"]) if "timestamp_ms" in m.fields else None,
                    partition_key=m.fields.get("partition_key"),
                )
            )

        if events:
            CONSUMER_READ_EVENTS_TOTAL.labels(topic=topic, group=group).inc(len(events))

        return ReadResponse(topic=topic, group=group, consumer=req.consumer, events=events)


@router.post("/{topic}/groups/{group}/ack", response_model=AckResponse)
async def ack_group(
    topic: str,
    group: str,
    req: AckRequest,
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("consumer", "admin"))],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AckResponse:
    with HTTP_REQUEST_DURATION.labels(method="POST", path="/v1/topics/{topic}/groups/{group}/ack").time():
        acked = 0
        for item in req.items:
            skey = stream_key(topic, item.partition)
            try:
                n = await redis.xack(skey, group, *item.redis_ids)
                acked += int(n)
            except Exception as e:
                raise HTTPException(status_code=500, detail="Ack failed") from e

        if acked:
            CONSUMER_ACK_TOTAL.labels(topic=topic, group=group).inc(acked)

        return AckResponse(topic=topic, group=group, acked=acked)


@router.post("/{topic}/groups/{group}/claim", response_model=ClaimResponse)
async def claim_pending(
    topic: str,
    group: str,
    req: ClaimRequest,
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("consumer", "admin"))],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ClaimResponse:
    with HTTP_REQUEST_DURATION.labels(
        method="POST", path="/v1/topics/{topic}/groups/{group}/claim"
    ).time():
        partitions = await get_topic_partitions(redis, topic=topic)
        parts = req.partitions or list(range(partitions))

        claimed_events: list[ReadEvent] = []
        claimed = 0

        # Use XAUTOCLAIM to move stale pending entries to this consumer.
        for p in parts:
            skey = stream_key(topic, p)
            try:
                next_start, msgs = await redis.xautoclaim(
                    skey,
                    group,
                    req.consumer,
                    min_idle_time=req.min_idle_ms,
                    start_id=req.start_id,
                    count=req.count,
                )
            except Exception:
                continue

            for msg_id_b, fields_b in msgs:
                msg_id = msg_id_b.decode("utf-8") if isinstance(msg_id_b, bytes) else str(msg_id_b)
                fields = {
                    (k.decode("utf-8") if isinstance(k, bytes) else str(k)): (
                        v.decode("utf-8") if isinstance(v, bytes) else str(v)
                    )
                    for k, v in fields_b.items()
                }
                claimed += 1
                claimed_events.append(
                    ReadEvent(
                        partition=p,
                        redis_id=msg_id,
                        event_type=fields.get("event_type"),
                        payload_json=fields.get("payload_json"),
                        timestamp_ms=int(fields["timestamp_ms"]) if "timestamp_ms" in fields else None,
                        partition_key=fields.get("partition_key"),
                    )
                )

        return ClaimResponse(
            topic=topic, group=group, consumer=req.consumer, claimed=claimed, events=claimed_events
        )

