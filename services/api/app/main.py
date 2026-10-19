import json
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, events, health, ingestion, observations, reviews, sources

app = FastAPI(
    title="MCHO API",
    version="0.1.0",
    description=("Evidence-first MENA humanitarian and geospatial observatory API. "
                 "No live feeds are implied; records must be sourced and reviewed."),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

request_logger = logging.getLogger("mcho.request")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@app.middleware("http")
async def trace_request(request: Request, call_next):
    """Add request correlation and latency logging without logging credentials or bodies."""
    provided_id = request.headers.get("x-request-id", "")
    request_id = provided_id if _REQUEST_ID_RE.fullmatch(provided_id) else uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        request_logger.error(json.dumps({
            "event": "request_failed",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }, separators=(",", ":")))
        # Return the same JSON error shape as handled errors, with the correlation ID,
        # and never the exception text (it can contain SQL or connection details).
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    request_logger.info(json.dumps({
        "event": "request_finished",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }, separators=(",", ":")))
    return response

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(observations.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(ingestion.router, prefix="/api/v1")


@app.get("/")
def root():
    return {"service": "MCHO API", "version": "0.1.0", "docs": "/docs", "live_data_configured": False}
