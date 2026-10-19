import logging
from redis import Redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger("mcho.health")


def redis_dependency_ready() -> bool:
    """Probe the queue service with a short timeout; never log the URL/credentials."""
    client = None
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False,
        )
        return bool(client.ping())
    except Exception as exc:
        logger.warning("redis_readiness_failed error_type=%s", type(exc).__name__)
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


@router.get("/live")
def live():
    # Liveness deliberately does not require dependencies; the orchestrator should
    # restart the process only when the process itself is unavailable.
    return {"status": "alive"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    dependencies = {"database": "unavailable", "postgis": "unavailable", "redis": "unavailable"}
    try:
        db.execute(text("SELECT 1"))
        dependencies["database"] = "ok"
    except Exception:
        pass

    if dependencies["database"] == "ok":
        try:
            db.execute(text("SELECT PostGIS_Full_Version()"))
            dependencies["postgis"] = "ok"
        except Exception:
            pass

    if redis_dependency_ready():
        dependencies["redis"] = "ok"

    if any(value != "ok" for value in dependencies.values()):
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "dependencies": dependencies},
        )
    return {"status": "ready", "dependencies": dependencies}
