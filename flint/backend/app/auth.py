"""
Authentication module — supports three modes selected by environment variables:

  ENABLE_AUTH=false (default)
      No auth enforced. API key check still applies to /admin and /ai
      when ADMIN_API_KEY is set. Safe for demos.

  ENABLE_AUTH=true  (no OIDC_ISSUER_URL set)
      Built-in JWT via POST /auth/token (Option C).
      Set AUTH_USERNAME + AUTH_PASSWORD in the environment.
      Tokens are HS256-signed with SECRET_KEY, expire after AUTH_TOKEN_EXPIRE_MINUTES.

  ENABLE_AUTH=true  (OIDC_ISSUER_URL set)
      External OIDC provider (Option A).
      OIDC_ISSUER_URL must point to an OIDC issuer (Keycloak, Auth0, Azure AD, etc.).
      JWKS is fetched from the well-known endpoint and cached for JWKS_CACHE_TTL_SECONDS.
      Tokens must be RS256 or ES256 JWTs issued by that provider.

Dependency summary:

  require_api_key   — legacy X-API-Key header check (unchanged)
  require_auth      — Bearer token check (OIDC or built-in JWT)
  require_access    — combined: require_api_key when ENABLE_AUTH=false,
                      require_auth when ENABLE_AUTH=true. Use this on
                      protected routers (/admin, /ai).
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
