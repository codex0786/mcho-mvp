import os
from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
app = Celery("mcho_workers", broker=redis_url, backend=redis_url)
app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC", enable_utc=True)

@app.task(name="mcho.health_check")
def health_check() -> dict[str, str]:
    return {"status": "ok", "component": "worker", "note": "No provider polling enabled by default."}

@app.task(name="mcho.ingest_source")
def ingest_source(source_key: str) -> dict[str, str]:
    # Placeholder intentionally refuses to imply ingestion has run.
    return {"status": "not_configured", "source_key": source_key, "detail": "Configure a reviewed provider adapter before scheduling ingestion."}
