"""Insert clearly synthetic, unpublished demo records. Never represents actual incidents."""
import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import Source, SourceDocument, Event, EventStatus, VerificationStatus

with SessionLocal() as db:
    source = db.scalar(select(Source).where(Source.name == "MCHO Synthetic Demo Source"))
    if source is None:
        source = Source(name="MCHO Synthetic Demo Source", source_type="fixture", access_mode="local_only", license_status="synthetic")
        db.add(source)
        db.flush()
    content = "Synthetic fixture only. No real event is asserted."
    digest = hashlib.sha256(content.encode()).hexdigest()
    doc = db.scalar(select(SourceDocument).where(SourceDocument.source_id == source.id, SourceDocument.content_hash == digest))
    if doc is None:
        doc = SourceDocument(source_id=source.id, title="Synthetic fixture record", canonical_url="https://example.invalid/synthetic-fixture", content_hash=digest, metadata_json={"synthetic": True})
        db.add(doc)
        db.flush()
    exists = db.scalar(select(Event).where(Event.summary == "Synthetic placeholder event — not a real-world report"))
    if exists is None:
        db.add(Event(event_type="synthetic_placeholder", summary="Synthetic placeholder event — not a real-world report", event_start=datetime.now(timezone.utc), status=EventStatus.draft, verification_status=VerificationStatus.unverified, is_synthetic=True, confidence_label="unassessed"))
    db.commit()
print("Synthetic demo fixture ensured. It is unpublished and excluded from public endpoints.")
