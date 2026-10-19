from fastapi import APIRouter, Depends

from app.core.security import Principal, get_current_principal

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/me")
def current_identity(principal: Principal = Depends(get_current_principal)):
    """Return identity and roles from a verified OIDC access token; never echo the token."""
    return {
        "subject": principal.subject,
        "issuer": principal.issuer,
        "identity": principal.identity,
        "roles": sorted(principal.roles),
    }
