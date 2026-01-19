from __future__ import annotations

from prometheus_client import Counter, Histogram


INGEST_EVENTS_TOTAL = Counter(
    "openstream_ingest_events_total",
    "Total events ingested into Redis Streams",
    ["topic", "partition"],
)

INGEST_BYTES_TOTAL = Counter(
    "openstream_ingest_bytes_total",
    "Total bytes ingested into Redis Streams (approx payload bytes)",
    ["topic", "partition"],
)

INGEST_REQUESTS_TOTAL = Counter(
    "openstream_ingest_requests_total",
    "Total ingestion requests",
    ["status"],
)

CONSUMER_READ_EVENTS_TOTAL = Counter(
    "openstream_consumer_read_events_total",
    "Total events read by consumer groups",
    ["topic", "group"],
)

CONSUMER_ACK_TOTAL = Counter(
    "openstream_consumer_ack_total",
    "Total event IDs acknowledged",
    ["topic", "group"],
)

HTTP_REQUEST_DURATION = Histogram(
    "openstream_http_request_duration_seconds",
    "HTTP request latency seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

