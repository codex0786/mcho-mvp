import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationStatus(str, enum.Enum):
    unverified = "unverified"
    provisional = "provisional"
    verified = "verified"
    disputed = "disputed"
    rejected = "rejected"


class EventStatus(str, enum.Enum):
    draft = "draft"
    pending_review = "pending_review"
    published = "published"
    corrected = "corrected"
    withdrawn = "withdrawn"


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    access_mode: Mapped[str] = mapped_column(String(60), nullable=False, default="public")
    license_status: Mapped[str] = mapped_column(String(60), nullable=False, default="unreviewed")
    homepage_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("source_id", "content_hash", name="uq_source_document_hash"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    license_note: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_event_start", "event_start"),
        Index("ix_events_verification_status", "verification_status"),
        Index("ix_events_status", "status"),
        Index("ix_events_geometry", "geometry", postgresql_using="gist"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    event_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    country_code: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus, name="event_status"), default=EventStatus.draft, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"), default=VerificationStatus.unverified, nullable=False
    )
    attribution_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    confidence_label: Mapped[str] = mapped_column(String(40), nullable=False, default="unassessed")
    spatial_uncertainty_m: Mapped[int | None] = mapped_column(Integer)
    geometry = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False)
    attribution_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EventEvidence(Base):
    __tablename__ = "event_evidence"
    __table_args__ = (UniqueConstraint("event_id", "source_document_id", "relationship", name="uq_event_evidence_link"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EventRevision(Base):
    __tablename__ = "event_revisions"
    __table_args__ = (UniqueConstraint("event_id", "revision_number", name="uq_event_revision_number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[str] = mapped_column(String(160), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_tasks.id", ondelete="RESTRICT"), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[str] = mapped_column(String(60), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SatelliteScene(Base):
    __tablename__ = "satellite_scenes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    mission: Mapped[str | None] = mapped_column(String(120))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    footprint = mapped_column(Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False))
    asset_uri: Mapped[str | None] = mapped_column(Text)
    access_status: Mapped[str] = mapped_column(String(40), nullable=False, default="discovered")
    quality_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    license_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MaritimeAggregate(Base):
    __tablename__ = "maritime_aggregates"
    __table_args__ = (Index("ix_maritime_area_period", "area_id", "period_start", "period_end"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[float] = mapped_column(nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    coverage_fraction: Mapped[float | None] = mapped_column()
    source_version: Mapped[str] = mapped_column(String(120), nullable=False)
    quality_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class HumanitarianIndicator(Base):
    __tablename__ = "humanitarian_indicators"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    indicator_type: Mapped[str] = mapped_column(String(100), nullable=False)
    geography_id: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float | None] = mapped_column()
    unit: Mapped[str] = mapped_column(String(60), nullable=False)
    estimate_status: Mapped[str] = mapped_column(String(40), nullable=False, default="reported")
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id", ondelete="RESTRICT"))
    quality_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
