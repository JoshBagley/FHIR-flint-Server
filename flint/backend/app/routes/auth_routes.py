"""
Authentication endpoints.

POST /auth/token
    OAuth2 password grant — built-in JWT mode only (ENABLE_AUTH=true, no OIDC_ISSUER_URL).
    Returns a Bearer token valid for AUTH_TOKEN_EXPIRE_MINUTES (default 60).
    Requires AUTH_USERNAME and AUTH_PASSWORD env vars.

GET  /auth/.well-known/smart-configuration
    SMART on FHIR discovery document (RFC 8414 / SMART App Launch 2.0).
    Always available — clients use this to discover auth endpoints and capabilities.
    When ENABLE_AUTH=false the authorization_endpoint is omitted to signal
    that auth is not required.
"""

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import (
    AUTH_TOKEN_EXPIRE_MINUTES,
    ENABLE_AUTH,
    OIDC_ISSUER_URL,
    create_access_token,
    verify_builtin_credentials,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Also expose at the SMART-standard top-level path (no /auth prefix)
well_known_router = APIRouter(tags=["Authentication"])

_BASE_URL = os.environ.get("BASE_URL", "")
# Browser-facing OIDC URL (may differ from OIDC_ISSUER_URL which is Docker-internal)
_OIDC_PUBLIC_URL = os.environ.get("OIDC_PUBLIC_ISSUER_URL", "").rstrip("/") or OIDC_ISSUER_URL


@router.post("/token", summary="Obtain a Bearer token (built-in JWT)")
async def get_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 Resource Owner Password Credentials grant.
    Only available when ENABLE_AUTH=true and OIDC_ISSUER_URL is not set.
    Set AUTH_USERNAME and AUTH_PASSWORD in the environment to enable.
    """
    if not ENABLE_AUTH:
        raise HTTPException(
            status_code=404,
            detail="Auth is disabled (ENABLE_AUTH=false). No token needed.",
        )
    if OIDC_ISSUER_URL:
        raise HTTPException(
            status_code=400,
            detail=(
                "Server is configured for external OIDC. "
                f"Obtain a token from {OIDC_ISSUER_URL} instead."
            ),
        )
    user = verify_builtin_credentials(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password (or AUTH_PASSWORD not configured)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(form_data.username, user["roles"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": AUTH_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get(
    "/.well-known/smart-configuration",
    summary="SMART on FHIR discovery document",
    response_model=None,
)
async def smart_configuration():
    """
    SMART App Launch 2.0 well-known discovery document.
    Clients fetch this to learn about supported auth capabilities.
    """
    base = _BASE_URL.rstrip("/")
    token_endpoint = (
        f"{OIDC_ISSUER_URL}/protocol/openid-connect/token"
        if OIDC_ISSUER_URL
        else f"{base}/auth/token"
    )
    doc: dict = {
        "token_endpoint": token_endpoint,
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "grant_types_supported": (
            ["authorization_code", "client_credentials"] if OIDC_ISSUER_URL else ["password", "client_credentials"]
        ),
        "scopes_supported": ["openid", "profile", "fhirUser", "launch/patient", "system/*.read", "system/*.write"],
        "capabilities": [
            "launch-standalone",
            "client-public",
            "client-confidential-symmetric",
            "permission-v2",
        ],
        "code_challenge_methods_supported": ["S256"],
        "auth_required": ENABLE_AUTH,
    }
    if OIDC_ISSUER_URL:
        doc["issuer"] = _OIDC_PUBLIC_URL
        doc["authorization_endpoint"] = f"{_OIDC_PUBLIC_URL}/protocol/openid-connect/auth"
        doc["token_endpoint"] = f"{_OIDC_PUBLIC_URL}/protocol/openid-connect/token"
        doc["jwks_uri"] = f"{_OIDC_PUBLIC_URL}/protocol/openid-connect/certs"
        doc["userinfo_endpoint"] = f"{_OIDC_PUBLIC_URL}/protocol/openid-connect/userinfo"
        doc["end_session_endpoint"] = f"{_OIDC_PUBLIC_URL}/protocol/openid-connect/logout"
    elif ENABLE_AUTH:
        doc["issuer"] = base
        doc["jwks_uri"] = f"{base}/auth/.well-known/jwks.json"

    return doc


@router.get("/userinfo", summary="Proxy userinfo to OIDC provider", response_model=None)
async def userinfo_proxy(request: Request):
    """Proxies GET /auth/userinfo to the OIDC provider using the caller's Bearer token.
    Avoids cross-origin issues when the OIDC provider is on a different port."""
    if not OIDC_ISSUER_URL:
        raise HTTPException(status_code=404, detail="OIDC not configured")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    userinfo_url = f"{OIDC_ISSUER_URL}/protocol/openid-connect/userinfo"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(userinfo_url, headers={"Authorization": auth})
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail="Userinfo request failed")
    return resp.json()


@well_known_router.get(
    "/.well-known/smart-configuration",
    summary="SMART on FHIR discovery document (SMART standard location)",
    response_model=None,
)
async def smart_configuration_top_level():
    """Alias at the FHIR-base well-known location required by SMART App Launch spec."""
    return await smart_configuration()
