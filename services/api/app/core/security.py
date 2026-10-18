import secrets
from fastapi import Header, HTTPException, status
from app.core.config import settings


def require_reviewer(x_reviewer_key: str | None = Header(default=None)) -> str:
    configured = settings.reviewer_api_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reviewer actions are disabled until REVIEWER_API_KEY is configured.",
        )
    if not x_reviewer_key or not secrets.compare_digest(x_reviewer_key, configured):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer authorization required.")
    return "api-key-reviewer"
