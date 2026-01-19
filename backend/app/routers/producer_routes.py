from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis

from app.auth import Principal, require_roles
from app.deps import get_redis
from app.metrics import (
    HTTP_REQUEST_DURATION,
    INGEST_BYTES_TOTAL,
    INGEST_EVENTS_TOTAL,
    INGEST_REQUESTS_TOTAL,
)
from app.models import IngestRequest, IngestResponse, IngestedEvent
from app.redis_client import ensure_topic, get_topic_partitions, stable_partition, stream_key
from app.settings import settings


router = APIRouter(prefix="/v1/topics", tags=["producers"])


@router.post("/{topic}/events", response_model=IngestResponse)
async def ingest_events(
    topic: str,
    req: IngestRequest,
    request: Request,
    _p: Annotated[Principal, Depends(require_roles("producer", "admin"))],
    redis: Annotated[Redis, Depends(get_redis)],
) -> IngestResponse:
    with HTTP_REQUEST_DURATION.labels(method="POST", path="/v1/topics/{topic}/events").time():
        partitions = req.partitions or await get_topic_partitions(redis, topic=topic)
        await ensure_topic(redis, topic=topic, partitions=partitions)

        results: list[IngestedEvent] = []

        # Hot path: append-only XADD; ensure ordering per partition.
        try:
            for ev in req.events:
                pkey = ev.partition_key or ""
                partition = stable_partition(topic, pkey, partitions)
                skey = stream_key(topic, partition)

                # Backpressure (simple): cap stream length to avoid unbounded growth
                # if retention/consumption is misconfigured.
                if settings.backpressure_max_stream_len > 0:
                    length = await redis.xlen(skey)
                    if length >= settings.backpressure_max_stream_len:
                        INGEST_REQUESTS_TOTAL.labels(status="backpressure").inc()
                        raise HTTPException(
                            status_code=429,
                            detail={
                                "error": "backpressure",
                                "message": "Stream is at/over max length; consumers are too slow or retention too high.",
                                "topic": topic,
                                "partition": partition,
                                "stream_len": length,
                            },
                            headers={"Retry-After": "1"},
                        )

                payload_json = json.dumps(ev.payload, separators=(",", ":"), ensure_ascii=False)
                fields = {
                    "event_type": ev.event_type,
                    "payload_json": payload_json,
                }
                if ev.timestamp_ms is not None:
                    fields["timestamp_ms"] = str(ev.timestamp_ms)
                if ev.partition_key is not None:
                    fields["partition_key"] = ev.partition_key

                redis_id = await redis.xadd(skey, fields)
                # redis-py returns bytes when decode_responses=False
                if isinstance(redis_id, bytes):
                    redis_id = redis_id.decode("utf-8")

                results.append(IngestedEvent(partition=partition, redis_id=redis_id))
                INGEST_EVENTS_TOTAL.labels(topic=topic, partition=str(partition)).inc()
                INGEST_BYTES_TOTAL.labels(topic=topic, partition=str(partition)).inc(len(payload_json))

            INGEST_REQUESTS_TOTAL.labels(status="ok").inc()
            return IngestResponse(topic=topic, partitions=partitions, results=results)
        except HTTPException:
            raise
        except Exception as e:
            INGEST_REQUESTS_TOTAL.labels(status="error").inc()
            raise HTTPException(status_code=500, detail="Ingestion failed") from e

