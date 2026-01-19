from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=200)
    partition_key: str | None = Field(default=None, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp_ms: int | None = None


class IngestRequest(BaseModel):
    # Batch ingestion for throughput. Single events can be sent as a list of length 1.
    events: list[EventIn] = Field(min_length=1, max_length=5000)
    partitions: int | None = Field(default=None, ge=1, le=4096)


class IngestedEvent(BaseModel):
    partition: int
    redis_id: str


class IngestResponse(BaseModel):
    topic: str
    partitions: int
    results: list[IngestedEvent]


class ReadRequest(BaseModel):
    consumer: str = Field(min_length=1, max_length=200)
    count: int = Field(default=100, ge=1, le=5000)
    block_ms: int = Field(default=1000, ge=0, le=30000)
    partitions: list[int] | None = None


class ReadEvent(BaseModel):
    partition: int
    redis_id: str
    event_type: str | None = None
    payload_json: str | None = None
    timestamp_ms: int | None = None
    partition_key: str | None = None


class ReadResponse(BaseModel):
    topic: str
    group: str
    consumer: str
    events: list[ReadEvent]


class AckItem(BaseModel):
    partition: int = Field(ge=0)
    redis_ids: list[str] = Field(min_length=1, max_length=5000)


class AckRequest(BaseModel):
    items: list[AckItem] = Field(min_length=1, max_length=4096)


class AckResponse(BaseModel):
    topic: str
    group: str
    acked: int


class ClaimRequest(BaseModel):
    consumer: str = Field(min_length=1, max_length=200)
    min_idle_ms: int = Field(default=60000, ge=0, le=86_400_000)
    count: int = Field(default=100, ge=1, le=5000)
    start_id: str = Field(default="0-0")
    partitions: list[int] | None = None


class ClaimResponse(BaseModel):
    topic: str
    group: str
    consumer: str
    claimed: int
    events: list[ReadEvent]


class GroupCreateRequest(BaseModel):
    group: str = Field(min_length=1, max_length=200)
    start_id: str = Field(default="$")  # "$" means start from new entries
    partitions: int | None = Field(default=None, ge=1, le=4096)


class GroupResetRequest(BaseModel):
    start_id: str = Field(default="0-0")


class TokenRequest(BaseModel):
    sub: str = Field(min_length=1, max_length=200)
    role: Literal["producer", "consumer", "admin"]
    admin_secret: str = Field(min_length=1)


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"

