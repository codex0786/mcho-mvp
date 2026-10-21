"""Public lookup of recent Sentinel-2 imagery near a point in the MENA area."""
import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.imagery.sentinel2 import ImagerySearchError, search_scenes
from app.thermal.firms import parse_area

router = APIRouter(prefix="/sentinel2", tags=["satellite imagery"])


@router.get("/scenes")
def sentinel2_scenes(
    lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
    days: int = Query(default=30, ge=5, le=60),
):
    west, south, east, north = parse_area(settings.firms_area)
    if not (west <= lon <= east and south <= lat <= north):
        raise HTTPException(status_code=400, detail="Imagery lookups are limited to the MENA area MCHO covers.")
    try:
        with httpx.Client(follow_redirects=False) as client:
            return search_scenes(client, lat, lon, days)
    except ImagerySearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
