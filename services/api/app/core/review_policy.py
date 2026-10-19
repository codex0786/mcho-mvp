"""Domain rules for human review and public event publication.

Review decisions never publish by themselves. Publication is a separate,
evidence-gated, audited action. The latest editor, reviewer and publisher must
be distinct people for each version that is published.
"""
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.entities import Event


def _enum_or_string(current: Any, value: str) -> Any:
    enum_type = type(current)
    if getattr(enum_type, "__members__", None):
        return enum_type(value)
    return value


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def ensure_independent_reviewer(latest_editor_id: str | None, reviewer_id: str) -> None:
    """A person must not review the version they most recently edited."""
    if latest_editor_id and latest_editor_id == reviewer_id:
        raise ValueError("The latest event editor cannot review their own version.")


def ensure_independent_publisher(
    latest_editor_id: str | None,
    reviewer_id: str,
    publisher_id: str,
) -> None:
    """Require a three-person chain for the exact event version being published."""
    ensure_independent_reviewer(latest_editor_id, reviewer_id)
    if publisher_id == latest_editor_id:
        raise ValueError("The latest event editor cannot publish their own version.")
    if publisher_id == reviewer_id:
        raise ValueError("The reviewer cannot publish the same event version they reviewed.")


def is_approval_decision(decision: str) -> bool:
    """Only explicit verify/provisional acceptance decisions can precede publication."""
    return decision in {"verify", "accept_provisional"}


def ensure_review_after_latest_revision(
    revision_changed_at: datetime,
    decision_created_at: datetime,
) -> None:
    """A review is valid only if it was recorded after the latest immutable revision."""
    if decision_created_at <= revision_changed_at:
        raise ValueError("A new independent review is required after the latest event revision.")


def apply_review_decision(event: "Event", decision: str) -> "Event":
    if event.is_synthetic:
        raise ValueError("Synthetic fixture records cannot be reviewed as real events.")

    if decision == "verify":
        event.verification_status = _enum_or_string(event.verification_status, "verified")
    elif decision == "accept_provisional":
        event.verification_status = _enum_or_string(event.verification_status, "provisional")
    elif decision == "dispute":
        event.verification_status = _enum_or_string(event.verification_status, "disputed")
        if _value(event.status) == "published":
            event.status = _enum_or_string(event.status, "corrected")
    elif decision == "reject":
        event.verification_status = _enum_or_string(event.verification_status, "rejected")
        event.status = _enum_or_string(event.status, "withdrawn")
    elif decision == "request_more_evidence":
        next_status = "corrected" if _value(event.status) == "published" else "pending_review"
        event.status = _enum_or_string(event.status, next_status)
    else:
        raise ValueError(f"Unsupported review decision: {decision}")
    return event
