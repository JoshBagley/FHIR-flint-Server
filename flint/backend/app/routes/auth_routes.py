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

import base64
import json
import os
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
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

# Realm path extracted from the internal OIDC issuer URL (e.g. "/realms/fhir").
# Used to build public Keycloak URLs dynamically from the request origin, so
# Inferno's Docker backend and the browser see consistently reachable URLs.
_REALM_PATH = urlparse(OIDC_ISSUER_URL).path.rstrip("/") if OIDC_ISSUER_URL else ""


@router.post("/token", summary="Obtain a Bearer token (built-in JWT)")
async def get_token(form_data: OAuth2PasswordRequestForm = Depends()):  # noqa: B008
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


_US_CORE_GRANULAR_SCOPES = [
    "patient/Patient.rs", "patient/AllergyIntolerance.rs", "patient/CarePlan.rs",
    "patient/CareTeam.rs", "patient/Condition.rs", "patient/Coverage.rs",
    "patient/Device.rs", "patient/DiagnosticReport.rs", "patient/DocumentReference.rs",
    "patient/Encounter.rs", "patient/Endpoint.rs", "patient/Goal.rs",
    "patient/Immunization.rs", "patient/Location.rs", "patient/Media.rs",
    "patient/Medication.rs", "patient/MedicationDispense.rs", "patient/MedicationRequest.rs",
    "patient/Observation.rs", "patient/Organization.rs", "patient/Practitioner.rs",
    "patient/PractitionerRole.rs", "patient/Procedure.rs", "patient/Provenance.rs",
    "patient/QuestionnaireResponse.rs", "patient/RelatedPerson.rs",
    "patient/ServiceRequest.rs", "patient/Specimen.rs",
]


@router.get(
    "/.well-known/smart-configuration",
    summary="SMART on FHIR discovery document",
    response_model=None,
)
async def smart_configuration(request: Request):
    """
    SMART App Launch 2.0 well-known discovery document.
    Clients fetch this to learn about supported auth capabilities.
    """
    base = _BASE_URL.rstrip("/")
    # Build origin from the incoming request so the token proxy URL is reachable
    # by whoever fetched this document (browser or Docker container alike).
    request_origin = f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"

    if OIDC_ISSUER_URL:
        token_endpoint = f"{request_origin}/auth/token-proxy"
    else:
        token_endpoint = f"{base}/auth/token"

    doc: dict = {
        "token_endpoint": token_endpoint,
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "grant_types_supported": (
            ["authorization_code", "refresh_token", "client_credentials"]
            if OIDC_ISSUER_URL
            else ["password", "client_credentials"]
        ),
        "scopes_supported": [
            "openid", "profile", "fhirUser", "offline_access",
            "launch/patient", "launch/encounter",
            "patient/*.read", "patient/*.rs",
            *_US_CORE_GRANULAR_SCOPES,
            "user/*.read", "user/*.write",
            "system/*.read", "system/*.write", "system/*.*",
        ],
        "capabilities": [
            "launch-standalone",
            "client-public",
            "client-confidential-symmetric",
            "context-standalone-patient",
            "sso-openid-connect",
            "permission-offline",
            "permission-v2",
            "permission-patient",
            "permission-user",
        ],
        "code_challenge_methods_supported": ["S256"],
        "auth_required": ENABLE_AUTH,
    }
    if OIDC_ISSUER_URL:
        # Build Keycloak public URLs dynamically from the request origin so that
        # both browser (localhost) and Inferno Docker (host.docker.internal) get
        # URLs they can actually reach.  The realm path comes from the internal
        # OIDC_ISSUER_URL (e.g. "/realms/fhir").
        kc_base = f"{request_origin}{_REALM_PATH}"
        doc["issuer"] = kc_base
        doc["authorization_endpoint"] = f"{kc_base}/protocol/openid-connect/auth"
        doc["jwks_uri"] = f"{kc_base}/protocol/openid-connect/certs"
        doc["userinfo_endpoint"] = f"{kc_base}/protocol/openid-connect/userinfo"
        doc["end_session_endpoint"] = f"{kc_base}/protocol/openid-connect/logout"
    elif ENABLE_AUTH:
        doc["issuer"] = base
        doc["jwks_uri"] = f"{base}/auth/.well-known/jwks.json"

    return doc


@router.post("/token-proxy", summary="Token endpoint proxy — injects SMART launch context", response_model=None)
async def token_proxy(request: Request):
    """
    Proxies the OAuth2 token exchange to Keycloak and promotes `patient` and
    `fhirUser` JWT claims into the token response body as required by SMART
    App Launch 2.0 (§ 7.1.2 — launch context in token response).
    """
    if not OIDC_ISSUER_URL:
        raise HTTPException(status_code=404, detail="OIDC not configured")

    form_data = await request.form()
    kc_token_url = f"{OIDC_ISSUER_URL}/protocol/openid-connect/token"

    # Forward the public hostname so Keycloak uses the correct issuer context
    # when KC_HOSTNAME is not fixed (tokens must have iss matching the proxy hostname).
    public_host = request.headers.get("host", "localhost")
    proxy_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Forwarded-Host": public_host,
        "X-Forwarded-Proto": request.url.scheme,
        "X-Forwarded-Port": "80",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(kc_token_url, data=dict(form_data), headers=proxy_headers)

    _TOKEN_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}

    if not resp.is_success:
        return Response(
            content=resp.content, status_code=resp.status_code,
            media_type="application/json", headers=_TOKEN_HEADERS,
        )

    token_body = resp.json()

    # Decode access token (without verification — we trust our own Keycloak)
    # and promote SMART launch context claims into the response body.
    access_token = token_body.get("access_token", "")
    if access_token:
        try:
            payload_b64 = access_token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            jwt_claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            for claim in ("patient", "fhirUser"):
                if claim in jwt_claims and claim not in token_body:
                    token_body[claim] = jwt_claims[claim]
        except Exception:  # noqa: BLE001, S110
            pass

    return JSONResponse(content=token_body, headers=_TOKEN_HEADERS)


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
async def smart_configuration_top_level(request: Request):
    """Alias at the FHIR-base well-known location required by SMART App Launch spec."""
    return await smart_configuration(request)
