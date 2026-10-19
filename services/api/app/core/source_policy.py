"""Single definition of when a source's records may support published output.

Every gate that depends on source eligibility (draft creation, publication,
evidence invalidation, public source listing, ingestion queueing and the worker)
must use these helpers, so a rule change cannot leave one path behind.
"""
from typing import Any

from app.models.entities import Source, SourceDocument
from app.schemas.sources import APPROVED_LICENSE_STATUSES


def source_is_publishable(source: Any) -> bool:
    """Active, with an approved licence status, reviewed terms and a retention policy."""
    return bool(
        source is not None
        and source.active
        and source.license_status in APPROVED_LICENSE_STATUSES
        and source.terms_reviewed_at is not None
        and source.terms_reviewed_by
        and source.license_terms_url
        and source.retention_policy
    )


def publishable_source_clauses() -> tuple:
    """SQL equivalent of :func:`source_is_publishable` for use in ``.where(...)``."""
    return (
        Source.active.is_(True),
        Source.license_status.in_(APPROVED_LICENSE_STATUSES),
        Source.terms_reviewed_at.is_not(None),
        Source.terms_reviewed_by.is_not(None),
        Source.license_terms_url.is_not(None),
        Source.retention_policy.is_not(None),
    )


def eligible_evidence_clauses() -> tuple:
    """A publishable source plus an individually approved source document."""
    return (*publishable_source_clauses(), SourceDocument.review_status == "approved")
