"""Domain rules for applying a human review decision to an event.

A reviewer decision never publishes by itself. Publication is a separate,
evidence-gated and audited operation.
"""
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
