import os
import httpx
from celery import Celery
from mcho_workers.ingestion import execute_ingestion

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
app = Celery("mcho_workers", broker=redis_url, backend=redis_url)
app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
)


@app.task(name="mcho.health_check")
def health_check() -> dict[str, str]:
    return {"status": "ok", "component": "worker", "note": "Provider polling is manual and disabled until configured."}


@app.task(
    bind=True,
    name="mcho.ingest_source",
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def ingest_source(self, source_id: str, run_id: str):
    return execute_ingestion(
        source_id_raw=source_id,
        run_id_raw=run_id,
        attempt=self.request.retries,
        max_retries=self.max_retries or 5,
    )
