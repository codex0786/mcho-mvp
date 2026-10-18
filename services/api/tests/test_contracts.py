from datetime import datetime, timezone
from uuid import uuid4
from app.schemas.events import EventOut, ReviewDecisionIn


def test_review_decision_rejects_unknown_decision():
    try:
        ReviewDecisionIn(decision="publish_anything", rationale="This should not be accepted")
    except Exception:
        return
    raise AssertionError("Invalid decision should fail validation")


def test_event_out_schema_contract():
    now = datetime.now(timezone.utc)
    item = EventOut(
        id=uuid4(), event_type="infrastructure_damage", summary="Fixture only", event_start=now,
        event_end=None, country_code="LB", status="published", verification_status="verified",
        attribution_status="unknown", confidence_label="moderate", spatial_uncertainty_m=100,
        is_synthetic=False, created_at=now, updated_at=now,
    )
    assert item.country_code == "LB"
    assert item.attribution_status == "unknown"
