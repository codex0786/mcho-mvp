from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import Source

router = APIRouter(prefix="/sources", tags=["sources"])

@router.get("")
def list_sources(active_only: bool = Query(default=True), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    query = select(Source)
    if active_only:
        query = query.where(Source.active.is_(True))
    rows = db.scalars(query.order_by(Source.name.asc()).limit(limit)).all()
    return {"items": [{"id": str(s.id), "name": s.name, "source_type": s.source_type,
        "access_mode": s.access_mode, "license_status": s.license_status, "homepage_url": s.homepage_url,
        "active": s.active, "created_at": s.created_at.isoformat()} for s in rows],
        "note": "A registry entry does not mean the source is connected or currently refreshing."}
