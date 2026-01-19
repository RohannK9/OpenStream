# OpenStream (Redis Streams Event Platform) — fully open-source

An open-source, distributed event streaming platform designed to handle **millions of events/day** with **fault tolerance**, **ordering per partition**, **replayable events**, and **high observability** — built on **Redis Streams** + **FastAPI** + **PostgreSQL** + **Prometheus/Grafana** + **Vue.js**.

## High-level architecture

```mermaid
flowchart LR
  P[Producers] -->|HTTPS + JWT| API[FastAPI Ingestion API]
  API -->|XADD (partitioned)| RS[(Redis Streams)]
  RS -->|XREADGROUP| C[Consumers / Workers]
  RS -->|XREAD (persist cursor)| PER[Persister Service]
  PER --> PG[(PostgreSQL Event Store)]
  API --> M[Prometheus /metrics]
  RS --> MX[Metrics Collector]
  C -->|OTel spans| OT[OpenTelemetry Collector]
  API -->|OTel spans| OT
  OT --> TR[(Jaeger/Tempo/ELK optional)]
  M --> PR[(Prometheus)]
  PR --> G[(Grafana)]
  UI[Vue Dashboard] --> API
  UI --> G
```

## Components and responsibilities

- **FastAPI Gateway (`backend/`)**
  - AuthN/AuthZ (JWT) for producers/consumers/admin.
  - **Ingestion**: validates payload, computes partition, appends to Redis Stream.
  - **Backpressure**: rejects/429 when stream length or lag exceeds thresholds.
  - **Replay controls**: create/reset consumer group offsets, new replay groups.
  - **Metrics**: exposes Prometheus `/metrics`, plus JSON summaries for the UI.

- **Redis Streams (messaging backbone)**
  - Partitioned append-only log: one stream per `(topic, partition)`.
  - Consumer groups for parallel processing and server-side offset tracking.
  - Supports claiming pending messages (fault recovery) and id-based reads (replay).

- **PostgreSQL (durable event store)**
  - Stores an immutable copy of each event (stream id, payload, timestamps).
  - Enables long-term retention, audits, historical analytics, replays from storage.

- **Persister / Replicator (`backend/worker_persist.py`)**
  - Reads each Redis stream sequentially from a per-stream cursor.
  - Inserts into Postgres (idempotent on `(stream, redis_id)`).
  - Uses a **Redis lease/lock** for leader election per partition to avoid duplicate persistence.

- **Consumers (`backend/worker_consumer.py` + your services)**
  - Use `XREADGROUP` to process events in parallel across partitions.
  - Acknowledge with `XACK`; claim stuck messages with `XAUTOCLAIM`.

- **Observability (`observability/`)**
  - Prometheus scrapes backend `/metrics`.
  - Grafana dashboards show throughput, lag, pending, storage usage, error rates.
  - Optional OpenTelemetry collector for traces/logs export.

## Ordering, durability, replay — how guarantees work

### Ordering per partition

- **Producer side**: events are deterministically mapped to a partition by `partition_key` using rendezvous hashing (stable mapping as nodes scale).
- **Log side**: each Redis Stream is append-only; IDs are monotonically increasing **within a stream**.
- **Consumer side**: `XREADGROUP` preserves per-stream ordering; with one consumer per partition (or careful concurrency), processing is ordered.
- **Guarantee**: **total order per (topic, partition)**; no total order across partitions (by design).

### Event durability

- **Primary durability**: Redis persistence (AOF) + replication (Redis primary/replica) via container setup; in Kubernetes, run Redis HA (Sentinel) or Cluster.
- **Secondary durability**: persister writes every event into Postgres (immutable event store).
- **Write acknowledgement**: ingestion returns success only after `XADD` succeeds (and optionally after enqueue-to-persist watermark if you enable it).

### Replay capability

Replay is implemented in two ways:

- **From Redis (short/medium retention)**:
  - Create a new consumer group at id `0-0` or a timestamp-based id.
  - Or reset an existing group offset via `XGROUP SETID`.
- **From Postgres (long retention)**:
  - Rehydrate events by time range / id range and republish to a replay topic, or let consumers read directly from storage for bulk backfills.

### Fault tolerance (ingestion, persistence, consumption)

- **Leader election**: per-partition persistence uses a Redis lock with TTL; on failure, another instance takes over.
- **Consumer failover**: stuck messages are reclaimed using `XAUTOCLAIM` after an idle threshold.
- **Backpressure**: ingestion checks (a) stream length, (b) consumer lag/pending; returns `429` with `Retry-After` and/or can shed load per topic.

## API sketch (FastAPI)

- **Producers**
  - `POST /v1/topics/{topic}/events` — ingest event (partitioned)
- **Consumers**
  - `POST /v1/topics/{topic}/groups/{group}/read` — read via `XREADGROUP`
  - `POST /v1/topics/{topic}/groups/{group}/ack` — ack IDs
  - `POST /v1/topics/{topic}/groups/{group}/claim` — claim stuck/pending
- **Admin / Replay**
  - `POST /v1/topics/{topic}/groups` — create group at start id
  - `POST /v1/topics/{topic}/groups/{group}/reset` — reset group offset (replay)
- **Observability**
  - `GET /v1/metrics/summary` — JSON summary for UI
  - `GET /metrics` — Prometheus

## Running locally (Docker Compose)

```bash
docker compose up --build
```

- **API**: `http://localhost:8000`
- **Swagger**: `http://localhost:8000/docs`
- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3001` (admin/admin)
- **UI**: `http://localhost:3000`

## Configuration (env vars)

You can configure services either by editing `docker-compose.yml` (already populated with sane defaults) **or** by using your own gitignored `.env` files locally and wiring them in via Compose (e.g., `env_file:`) if you prefer.

### Backend (FastAPI)

Configured in `docker-compose.yml` under the `api` service.

- **REDIS_URL**: Redis connection string (e.g. `redis://redis:6379/0`)
- **DATABASE_URL**: Postgres connection string (used by storage layer once enabled)
- **AUTH_JWT_SECRET**: JWT signing secret (change in prod)
- **AUTH_JWT_ISSUER / AUTH_JWT_AUDIENCE**: JWT validation settings
- **AUTH_ADMIN_SECRET**: dev-only secret that allows minting tokens via `POST /v1/auth/token`
- **PARTITIONS_DEFAULT**: default partition count for new topics
- **BACKPRESSURE_MAX_STREAM_LEN**: simple backpressure cap per partition stream length
- **CORS_ALLOW_ORIGINS**: comma-separated allowed origins (set to `http://localhost:3000` for the Vue UI)

### Frontend (Vue)

In Docker Compose, the UI reads runtime config from environment variables:

- **OPENSTREAM_API_BASE_URL**: API base URL (default `http://localhost:8000`)
- **OPENSTREAM_GRAFANA_URL**: Grafana URL (default `http://localhost:3001`)
- **OPENSTREAM_PROMETHEUS_URL**: Prometheus URL (default `http://localhost:9090`)

For non-docker local dev (`npm run dev`), you can use the `VITE_*` equivalents via a local `.env` file in `frontend/` (gitignored).

## Walkthrough (how to use)

### 1) Start the platform

```bash
cd "/Users/rohannk/Desktop/Testing message/Project"
docker compose up --build
```

Open:

- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Grafana: `http://localhost:3001` (admin/admin)

### 2) Mint a token (dev)

In the UI:

- Keep `admin` role selected
- Enter `AUTH_ADMIN_SECRET` (default in compose is `dev-admin-secret`)
- Click **Mint token**

Or via curl:

```bash
curl -sS -X POST http://localhost:8000/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"sub":"me","role":"admin","admin_secret":"dev-admin-secret"}'
```

Copy the returned `token` and use it as `Authorization: Bearer <token>` for protected endpoints.

### 3) Produce events

```bash
TOKEN="paste-token-here"
curl -sS -X POST "http://localhost:8000/v1/topics/orders/events" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {"event_type":"order.created","partition_key":"user-1","payload":{"order_id":"o-1","amount":12.34}},
      {"event_type":"order.created","partition_key":"user-2","payload":{"order_id":"o-2","amount":98.76}}
    ],
    "partitions": 8
  }'
```

This appends to Redis Streams `os:stream:orders:{partition}` with **ordering per partition**.

### 4) Create a consumer group

Create group from “now” (only new events):

```bash
curl -sS -X POST "http://localhost:8000/v1/topics/orders/groups" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"group":"orders-workers","start_id":"$"}'
```

Create group from the beginning (replay everything currently retained in Redis):

```bash
curl -sS -X POST "http://localhost:8000/v1/topics/orders/groups" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"group":"orders-replay","start_id":"0-0"}'
```

### 5) Consume + ack

Read:

```bash
curl -sS -X POST "http://localhost:8000/v1/topics/orders/groups/orders-workers/read" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"consumer":"c1","count":100,"block_ms":1000}'
```

Ack:

```bash
curl -sS -X POST "http://localhost:8000/v1/topics/orders/groups/orders-workers/ack" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"partition":0,"redis_ids":["1730000000000-0"]}]}'
```

If a consumer crashes and leaves pending entries, reclaim them:

```bash
curl -sS -X POST "http://localhost:8000/v1/topics/orders/groups/orders-workers/claim" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"consumer":"c2","min_idle_ms":60000,"count":100}'
```

### 6) Replay (reset group offset)

Reset a group to reprocess from the beginning:

```bash
curl -sS -X POST "http://localhost:8000/v1/topics/orders/groups/orders-workers/reset" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"start_id":"0-0"}'
```

### 7) Observe

- UI calls `GET /v1/metrics/summary` (requires token) and shows:
  - partition stream lengths
  - consumer group pending + lag (from Redis `XINFO GROUPS`)
- Prometheus scrapes `GET /metrics/` (no auth) and Grafana visualizes trends.

## Tech stack recommendation

- **Backend**: Python FastAPI, Redis Streams, PostgreSQL
- **Frontend**: Vue.js
- **Metrics**: Prometheus + Grafana
- **Tracing/logging**: OpenTelemetry (collector) + Jaeger/Tempo/ELK (optional)
- **Containerization**: Docker Compose; optional Kubernetes with Redis HA + HPA

## Resume bullet (example)

- Designed and implemented a fully open-source **distributed event streaming platform** (FastAPI + Redis Streams + Postgres) delivering **partition-ordered, replayable logs** with **fault-tolerant ingestion**, consumer-group parallelism, backpressure controls, and **real-time observability** via Prometheus/Grafana and OpenTelemetry—processing **millions of events/day** without paid messaging services.

