"""Provider-neutral OIDC access-token verification and role authorization.

The API validates JWT access tokens against an explicitly configured issuer,
audience, JWKS endpoint and role claim. Tokens are never decoded without
signature and standard-claim validation. Missing OIDC configuration fails
closed for reviewer/publisher operations.
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError

from app.core.config import settings

ALLOWED_OIDC_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA"}


@dataclass(frozen=True)
class Principal:
    subject: str
    issuer: str
    roles: frozenset[str]

    @property
    def identity(self) -> str:
        """Stable audit identity across multiple trusted issuers."""
        return f"{self.issuer}|{self.subject}"


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)


def _role_values(claims: dict[str, Any], claim_path: str) -> frozenset[str]:
    """Read a role array/string from a claim or dotted nested object path."""
    if claim_path in claims:
        value: Any = claims[claim_path]
    else:
        value = claims
        for part in claim_path.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
    if isinstance(value, str):
        candidates = value.split()
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []
    return frozenset(item.strip() for item in candidates if isinstance(item, str) and item.strip())


def decode_access_token(token: str) -> Principal:
    """Verify an OAuth/OIDC JWT access token and return authn/authz fields."""
    issuer = settings.oidc_issuer.strip()
    audience = settings.oidc_audience.strip()
    jwks_url = settings.oidc_jwks_url.strip()
    if not (issuer and audience and jwks_url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC reviewer authentication is not configured.",
        )

    algorithms = [item.strip() for item in settings.oidc_algorithms.split(",") if item.strip()]
    if not algorithms or any(item not in ALLOWED_OIDC_ALGORITHMS for item in algorithms):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC algorithm configuration is invalid; only approved asymmetric algorithms are allowed.",
        )
    if settings.app_env.lower() in {"production", "prod"} and not (
        issuer.startswith("https://") and jwks_url.startswith("https://")
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production OIDC issuer and JWKS URL must use HTTPS.",
        )

    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
    except PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC signing-key service is temporarily unavailable.",
        ) from exc
    except PyJWKClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token signing key is not trusted.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=algorithms,
            issuer=issuer,
            audience=audience,
            leeway=30,
            options={"require": ["iss", "aud", "exp", "iat", "sub"]},
        )
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has no valid subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Principal(
        subject=subject,
        issuer=issuer,
        roles=_role_values(claims, settings.oidc_role_claim.strip() or "roles"),
    )


def get_current_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not (settings.oidc_issuer.strip() and settings.oidc_audience.strip() and settings.oidc_jwks_url.strip()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC reviewer authentication is not configured.",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed bearer access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(token)


def require_roles(*allowed_roles: str):
    permitted = frozenset(allowed_roles)

    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.roles.intersection(permitted):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for this operation.")
        return principal

    return dependency


require_reviewer = require_roles("reviewer", "admin")
require_review_queue_access = require_roles("reviewer", "publisher", "admin")
require_publisher = require_roles("publisher", "admin")
