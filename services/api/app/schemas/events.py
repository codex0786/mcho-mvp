from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    summary: str | None = Field(default=None, min_length=15, max_length=5000)
    verification_status: Literal["unverified"] | None = None


EventType = Literal[
    "armed_clash_reported",
    "airstrike_reported",
    "civilian_casualties",
    "mass_casualty",
    "displacement",
    "infrastructure_damage",
    "humanitarian_access",
    "blockade_violation",
    "explosive_hazard",
    "detention",
    "protection_incident",
    "perpetrator_attribution",
    "other",
]


class EventDraftFromDocumentIn(BaseModel):
    """Analyst-authored event candidate linked to one reviewed source document."""

    event_type: EventType
    summary: str = Field(min_length=15, max_length=5000)
    event_start: datetime | None = None
    event_end: datetime | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    spatial_uncertainty_m: int | None = Field(default=None, ge=1, le=100000)
    rationale: str = Field(min_length=15, max_length=5000)

    @field_validator("event_start", "event_end")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Event timestamps must include a timezone offset.")
        return value

    @model_validator(mode="after")
    def validate_time_and_location(self):
        if self.event_start and self.event_end and self.event_end < self.event_start:
            raise ValueError("event_end must not precede event_start.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together.")
        if self.latitude is not None and self.spatial_uncertainty_m is None:
            raise ValueError("A location point requires an explicit spatial uncertainty estimate.")
        return self
