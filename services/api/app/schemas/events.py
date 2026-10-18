from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_type: str
    summary: str
    event_start: datetime | None
    event_end: datetime | None
    country_code: str | None
    status: str
    verification_status: str
    attribution_status: str
    confidence_label: str
    spatial_uncertainty_m: int | None
    is_synthetic: bool
    created_at: datetime
    updated_at: datetime


class EventPage(BaseModel):
    items: list[EventOut]
    next_cursor: str | None = None
    response_generated_at: datetime


class ReviewDecisionIn(BaseModel):
    decision: str = Field(pattern="^(accept_provisional|verify|dispute|reject|request_more_evidence)$")
    rationale: str = Field(min_length=10, max_length=5000)


class CorrectionIn(BaseModel):
    rationale: str = Field(min_length=10, max_length=5000)
    summary: str | None = Field(default=None, max_length=5000)
    verification_status: str | None = Field(default=None, pattern="^(unverified|provisional|verified|disputed|rejected)$")
