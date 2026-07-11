"""
Authentication module — supports three modes selected by environment variables:

  ENABLE_AUTH=false (default)
      No auth enforced. API key check still applies to /admin and /ai
      when ADMIN_API_KEY is set. Safe for demos.

  ENABLE_AUTH=true  (no OIDC_ISSUER_URL set)
      Built-in JWT via POST /auth/token (Option C).
      Set AUTH_USERNAME + AUTH_PASSWORD in the environment.
      Tokens are HS256-signed with SECRET_KEY, expire after AUTH_TOKEN_EXPIRE_MINUTES.

  ENABLE_AUTH=true  (OIDC_ISSUER_URL set)  ← recommended for SMART on FHIR
      External OIDC provider — Keycloak, Auth0, Azure AD, etc.
      OIDC_ISSUER_URL must point to an OIDC issuer.
      JWKS is fetched from the well-known endpoint and cached for JWKS_CACHE_TTL_SECONDS.
      Tokens must be RS256 or ES256 JWTs issued by that provider.

Dependency summary:

  require_api_key   — legacy X-API-Key header check
  require_auth      — Bearer token check (OIDC or built-in JWT)
  require_access    — combined: require_api_key when ENABLE_AUTH=false,
                      require_auth when ENABLE_AUTH=true. Used on /admin, /ai.

SMART scope enforcement (when ENABLE_AUTH=true):
  The FHIR auth middleware in main.py calls decode_token() + has_fhir_scope()
  on every FHIR request. Scope semantics:

    system/*.read  — read any resource (server-to-server)
    system/*.write — write any resource (server-to-server)
    user/*.read    — clinician read access (user-level context)
    user/*.write   — clinician write access
    patient/*.read — patient-scoped read (context patient only; filtering V2)
    patient/*.write— patient-scoped write

  Wildcard patterns (*.* and /ResourceType.read etc.) are also matched.
"""

import os
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

ENABLE_AUTH: bool = os.environ.get("ENABLE_AUTH", "false").lower() == "true"
SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
OIDC_ISSUER_URL: str = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
AUTH_USERNAME: str = os.environ.get("AUTH_USERNAME", "admin")
AUTH_PASSWORD: str = os.environ.get("AUTH_PASSWORD", "")
AUTH_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("AUTH_TOKEN_EXPIRE_MINUTES", "60"))
JWKS_CACHE_TTL_SECONDS: int = int(os.environ.get("JWKS_CACHE_TTL_SECONDS", "3600"))

_API_KEY: str = os.environ.get("ADMIN_API_KEY", "")

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer_scheme = HTTPBearer(auto_error=False)

# ── Built-in user store (demo/testing only) ───────────────────────────────────
# In a full production deployment these would come from the database.

_BUILTIN_USERS: Dict[str, Dict[str, Any]] = {
    AUTH_USERNAME: {
        "password": AUTH_PASSWORD,
        "roles": ["admin"],
    }
}

# ── JWKS cache (external OIDC only) ──────────────────────────────────────────

_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_time: float = 0.0


async def _get_jwks() -> Dict[str, Any]:
    global _jwks_cache, _jwks_cache_time
    now = time.monotonic()
    if _jwks_cache and (now - _jwks_cache_time) < JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=10) as client:
        oidc_resp = await client.get(f"{OIDC_ISSUER_URL}/.well-known/openid-configuration")
        oidc_resp.raise_for_status()
        jwks_uri = oidc_resp.json()["jwks_uri"]
        jwks_resp = await client.get(jwks_uri)
        jwks_resp.raise_for_status()
        _jwks_cache = jwks_resp.json()
        _jwks_cache_time = now
    return _jwks_cache  # type: ignore[return-value]


# ── Token creation (built-in JWT) ─────────────────────────────────────────────

def create_access_token(subject: str, roles: List[str]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=AUTH_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": subject, "roles": roles, "exp": expire, "iss": "flint"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_builtin_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Return user dict if credentials are valid, None otherwise."""
    if not AUTH_PASSWORD:
        return None
    user = _BUILTIN_USERS.get(username)
    if not user or not password or password != user["password"]:
        return None
    return user


# ── SMART scope helpers ───────────────────────────────────────────────────────

async def decode_token(token: str) -> Dict[str, Any]:
    """Decode a JWT and return the payload. Raises JWTError on failure (not HTTPException)."""
    if OIDC_ISSUER_URL:
        jwks = await _get_jwks()
        return jwt.decode(token, jwks, algorithms=["RS256", "ES256"], options={"verify_aud": False})
    else:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("iss") != "flint":
            raise JWTError("Invalid issuer")
        return payload


def get_roles(token_payload: Dict[str, Any]) -> List[str]:
    """Extract FHIR realm roles from a Keycloak or built-in JWT token.

    Keycloak places realm roles at realm_access.roles.
    Built-in JWT (create_access_token) puts them at the top-level 'roles' key.
    """
    kc_roles = (token_payload.get("realm_access") or {}).get("roles") or []
    if kc_roles:
        return list(kc_roles)
    return list(token_payload.get("roles") or [])


def check_role_scope_compatibility(roles: List[str], token_payload: Dict[str, Any]) -> Optional[str]:
    """Return an error string if the role+scope combination is not permitted, else None.

    fhir-patient   → only patient/* scopes allowed
    fhir-clinician → user/* and patient/* allowed; system/* denied
    fhir-admin     → unrestricted
    no FHIR role   → no additional restriction (service accounts, built-in JWT)
    """
    scopes = set((token_payload.get("scope") or "").split())
    has_system = any(s.startswith("system/") for s in scopes)
    if "fhir-patient" in roles and has_system:
        return "fhir-patient role may not use system/* scopes"
    if "fhir-clinician" in roles and has_system:
        return "fhir-clinician role may not use system/* scopes"
    return None


def _extract_fhir_id(fhir_user: str, resource_type: str) -> Optional[str]:
    """Extract bare UUID from a relative or absolute FHIR reference.

    Handles both relative ("Patient/uuid") and absolute
    ("http://example.com/Patient/uuid") fhirUser claim formats.
    """
    prefix = f"{resource_type}/"
    if fhir_user.startswith(prefix):
        return fhir_user[len(prefix):] or None
    # Absolute URL — find the last occurrence of "/{resource_type}/"
    sep = f"/{prefix}"
    idx = fhir_user.rfind(sep)
    if idx != -1:
        candidate = fhir_user[idx + len(sep):]
        return candidate or None
    return None


def get_clinician_id(token_payload: Dict[str, Any]) -> Optional[str]:
    """Return the bare Practitioner UUID for fhir-clinician tokens, else None.

    Used by Option B panel filtering in resource_factory._search/_read.
    The Practitioner ID comes from the fhirUser claim (relative or absolute URL).

    Option C (future — CareTeam-based access):
      Replace this simple ID lookup with a check against CareTeam resources.
      Each clinical resource read/search would need a correlated subquery:
        EXISTS (
          SELECT 1 FROM fhir_resources ct
          WHERE ct.resource_type = 'CareTeam'
            AND ct.data->'subject'->>'reference' = {patient_ref}
            AND ct.data->'participant' @> '[{"member":{"reference":"Practitioner/{id}"}}]'
        )
      This covers Observation, Condition, Encounter, etc. — not just Patient lists.
      Requires CareTeam resources to be populated and kept current.
    """
    roles = get_roles(token_payload)
    if "fhir-clinician" not in roles:
        return None
    fhir_user = (token_payload.get("fhirUser") or "").strip()
    return _extract_fhir_id(fhir_user, "Practitioner")


def get_patient_context(token_payload: Dict[str, Any]) -> Optional[str]:
    """Return the bare patient UUID if this token is patient-scoped, else None.

    Returns None (no filtering) for admin/clinician tokens with broad access.
    Returns None for service accounts (client_credentials) with no fhirUser.
    Returns the UUID portion of Patient/{id} from the fhirUser claim for patients.
    """
    roles = get_roles(token_payload)
    if "fhir-admin" in roles:
        return None
    scopes = set((token_payload.get("scope") or "").split())
    has_broad = any(s.startswith("user/") or s.startswith("system/") for s in scopes)
    if "fhir-clinician" in roles and has_broad:
        return None
    fhir_user = (token_payload.get("fhirUser") or "").strip()
    return _extract_fhir_id(fhir_user, "Patient")


def has_fhir_scope(token_payload: Dict[str, Any], method: str) -> bool:
    """Return True if the token's scopes grant access for the given HTTP method.

    Recognises both SMART v1 and v2 scope patterns:
      v1: {context}/{resource}.read|write|*   e.g. patient/*.read
      v2: {context}/{resource}.{chars}        e.g. patient/Patient.rs
          where chars are single-letter codes: r=read, s=search,
          c=create, u=update, d=delete, *=all

    Write methods: POST, PUT, PATCH, DELETE.
    """
    scopes = set((token_payload.get("scope") or "").split())
    is_write = method in ("POST", "PUT", "PATCH", "DELETE")
    for scope in scopes:
        context, _, resource_part = scope.partition("/")
        if context not in ("system", "user", "patient"):
            continue
        _, _, access = resource_part.rpartition(".")
        if not access:
            continue
        # SMART v1 keywords
        if access == "*" or "*" in access:
            return True
        if not is_write and access == "read":
            return True
        if is_write and access == "write":
            return True
        # SMART v2 single-char codes: r=read, s=search, c=create, u=update, d=delete
        if not is_write and ("r" in access or "s" in access):
            return True
        if is_write and any(c in access for c in "cud"):
            return True
    return False


# ── Auth dependencies ─────────────────────────────────────────────────────────

async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Require X-API-Key header when ADMIN_API_KEY env var is set.
    When ADMIN_API_KEY is unset (local dev), the check is skipped."""
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[Dict[str, Any]]:
    """Validate Bearer token. Returns decoded payload or None when ENABLE_AUTH=false."""
    if not ENABLE_AUTH:
        return None

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        if OIDC_ISSUER_URL:
            jwks = await _get_jwks()
            payload = jwt.decode(
                token,
                jwks,
                algorithms=["RS256", "ES256"],
                options={"verify_aud": False},
            )
        else:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("iss") != "flint":
                raise JWTError("Invalid issuer")
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload


async def require_access(
    x_api_key: str = Header(default=""),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[Dict[str, Any]]:
    """
    Single dependency for protected routers (/admin, /ai).

    ENABLE_AUTH=false → enforce X-API-Key (legacy demo mode).
    ENABLE_AUTH=true  → enforce Bearer token (SMART on FHIR / JWT mode).
    """
    if ENABLE_AUTH:
        return await require_auth(credentials)
    else:
        await require_api_key(x_api_key)
        return None
