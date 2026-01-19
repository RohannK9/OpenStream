from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.logging import configure_logging
from app.metrics import HTTP_REQUEST_DURATION
from app.routers import admin_routes, auth_routes, consumer_routes, metrics_routes, producer_routes
from app.settings import settings


configure_logging()

app = FastAPI(
    title="OpenStream API",
    version="0.1.0",
    description="Open-source event streaming platform API (Redis Streams backbone).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prometheus_timing(request: Request, call_next):
    # Avoid labeling high-cardinality paths; routers also use template labels.
    start = time.perf_counter()
    resp = await call_next(request)
    dur = time.perf_counter() - start
    try:
        HTTP_REQUEST_DURATION.labels(method=request.method, path="raw").observe(dur)
    except Exception:
        pass
    return resp


@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/metrics", include_in_schema=False)
@app.get("/metrics/", include_in_schema=False)
async def metrics() -> Response:
    # Serve both /metrics and /metrics/ without redirects (avoids noisy 307 logs).
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


app.include_router(auth_routes.router)
app.include_router(producer_routes.router)
app.include_router(consumer_routes.router)
app.include_router(admin_routes.router)
app.include_router(metrics_routes.router)

