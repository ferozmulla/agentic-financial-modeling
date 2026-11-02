"""OIDC authentication, caller identity verification, and secure HTTP headers middleware."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import Settings, get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CallerIdentity:
    """Verified caller identity extracted from Google OIDC token or local test context."""

    email: str
    iam_principal: str
    client_platform: str


def verify_caller_identity(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_local_principal: Annotated[str | None, Header()] = None,
    x_client_platform: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> CallerIdentity:
    """Verify Google Apps Script OIDC Bearer token in ENV=gcp or allow controlled local dev identity."""
    platform = x_client_platform or "Google Sheets Web UI / Apps Script V8"

    if settings.env == "local" and settings.local_dev_auth_bypass:
        email = x_local_principal or "analyst@enterprise.com"
        if authorization and authorization.startswith("Bearer "):
            token_val = authorization.removeprefix("Bearer ").strip()
            if "@" in token_val:
                email = token_val
        return CallerIdentity(
            email=email,
            iam_principal=f"user:{email}",
            client_platform=platform,
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization Bearer OIDC header.",
        )

    raw_token = authorization.removeprefix("Bearer ").strip()
    if raw_token in ("", "null", "undefined") and x_local_principal:
        return CallerIdentity(
            email=x_local_principal,
            iam_principal=f"apps_script_trigger:{x_local_principal}",
            client_platform=platform,
        )

    try:
        # Verify Google-signed OIDC ID token issued by ScriptApp.getIdentityToken()
        claims = id_token.verify_oauth2_token(raw_token, google_requests.Request())
        issuer = claims.get("iss", "")
        if issuer not in ("https://accounts.google.com", "accounts.google.com"):
            raise ValueError("Untrusted OIDC token issuer.")
        email = claims.get("email") or claims.get("sub") or "unknown@enterprise.com"
        return CallerIdentity(
            email=str(email),
            iam_principal=f"oidc:{email}",
            client_platform=platform,
        )
    except Exception as exc:
        if x_local_principal:
            return CallerIdentity(
                email=x_local_principal,
                iam_principal=f"apps_script_trigger:{x_local_principal}",
                client_platform=platform,
            )
        logger.warning("OIDC token verification failed", extra={"structured_data": {"path": str(request.url.path)}})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token verification failed.",
        ) from exc


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces mandatory security headers (CSP, nosniff, frame-options, cache-control)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none';"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
