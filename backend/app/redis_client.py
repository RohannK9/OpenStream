from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from app.settings import settings


def _key(*parts: str) -> str:
    return ":".join((settings.redis_key_prefix, *parts))


def topic_set_key() -> str:
    return _key("topics")


def topic_meta_key(topic: str) -> str:
    return _key("topic_meta", topic)


def stream_key(topic: str, partition: int) -> str:
    return _key("stream", topic, str(partition))


def stable_partition(topic: str, partition_key: str, partitions: int) -> int:
    # Deterministic across processes; unlike Python's built-in hash().
    digest = hashlib.sha256(f"{topic}:{partition_key}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big", signed=False)
    return value % partitions


@dataclass(frozen=True)
class StreamMessage:
    stream: str
    message_id: str
    fields: dict[str, str]


async def ensure_topic(redis: Redis, *, topic: str, partitions: int) -> None:
    # Track topics and partition count so the UI/summary can discover them.
    await redis.sadd(topic_set_key(), topic)
    await redis.hsetnx(topic_meta_key(topic), "partitions", str(partitions))


async def get_topic_partitions(redis: Redis, *, topic: str) -> int:
    raw = await redis.hget(topic_meta_key(topic), "partitions")
    if raw is None:
        return settings.partitions_default
    try:
        return int(raw)
    except ValueError:
        return settings.partitions_default


def _decode_fields(fields: dict[bytes, bytes]) -> dict[str, str]:
    return {k.decode("utf-8"): v.decode("utf-8") for k, v in fields.items()}


def _coerce_xreadgroup(
    res: list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]
) -> list[StreamMessage]:
    out: list[StreamMessage] = []
    for stream_b, msgs in res:
        stream = stream_b.decode("utf-8")
        for msg_id_b, fields_b in msgs:
            out.append(
                StreamMessage(
                    stream=stream,
                    message_id=msg_id_b.decode("utf-8"),
                    fields=_decode_fields(fields_b),
                )
            )
    return out


async def xreadgroup_multi(
    redis: Redis,
    *,
    group: str,
    consumer: str,
    streams: dict[str, str],
    count: int,
    block_ms: int,
) -> list[StreamMessage]:
    # redis-py expects stream names as bytes/str; we pass str.
    res = await redis.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams=streams,
        count=count,
        block=block_ms if block_ms > 0 else None,
    )
    return _coerce_xreadgroup(res)


async def xinfo_groups_safe(redis: Redis, *, stream: str) -> list[dict[str, Any]]:
    try:
        return await redis.xinfo_groups(stream)
    except Exception:
        # Stream may not exist yet.
        return []

