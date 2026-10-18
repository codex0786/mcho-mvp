from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "alive"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db.execute(text("SELECT PostGIS_Full_Version()"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database/PostGIS not ready") from exc
    return {"status": "ready", "dependencies": {"database": "ok", "postgis": "ok"}}
