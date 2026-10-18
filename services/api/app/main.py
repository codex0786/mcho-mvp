from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import events, health, observations, reviews, sources

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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Reviewer-Key"],
)
app.include_router(health.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(observations.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")


@app.get("/")
def root():
    return {"service": "MCHO API", "version": "0.1.0", "docs": "/docs", "live_data_configured": False}
