"""
Admin user management — proxy Keycloak admin operations and sync FHIR resources.

GET  /admin/users                  List realm users with roles + FHIR link
POST /admin/users/admin            Create Keycloak account with fhir-admin role (no FHIR resource)
POST /admin/users/clinician        Create Practitioner + Keycloak account + PractitionerRole
POST /admin/users/patient          Create Patient + Keycloak portal account
PATCH /admin/users/{kc_id}/status  Activate or deactivate a Keycloak user

All create/status-change operations are written to audit_log (resource_type='KeycloakUser').
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app import state
from app.auth import require_access

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keycloak admin config — derived from OIDC_ISSUER_URL
# ---------------------------------------------------------------------------

_OIDC_URL = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
KC_ADMIN_USER = os.environ.get("KC_ADMIN_USER", "admin")
KC_ADMIN_PASSWORD = os.environ.get("KC_ADMIN_PASSWORD", "admin")


def _parse_kc() -> tuple[str, str]:
    if "/realms/" in _OIDC_URL:
        base, realm = _OIDC_URL.split("/realms/", 1)
        return base, realm
    return _OIDC_URL, "fhir"


_KC_BASE, _KC_REALM = _parse_kc()
_KC_ADMIN = f"{_KC_BASE}/admin/realms/{_KC_REALM}"

_token_cache: Dict[str, Any] = {}

router = APIRouter(prefix="/admin", tags=["Admin Users"], dependencies=[Depends(require_access)])


# ---------------------------------------------------------------------------
# Keycloak admin helpers
# ---------------------------------------------------------------------------

async def _kc_admin_token() -> str:
    now = time.monotonic()
    if _token_cache.get("token") and now < _token_cache.get("expires_at", 0.0):
        return _token_cache["token"]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{_KC_BASE}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": KC_ADMIN_USER,
                "password": KC_ADMIN_PASSWORD,
            },
        )
        if not resp.is_success:
            raise HTTPException(502, f"Keycloak admin auth failed: {resp.text[:200]}")
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + data.get("expires_in", 60) - 15
        return data["access_token"]


async def _kc(method: str, path: str, **kwargs) -> httpx.Response:
    token = await _kc_admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    if "json" in kwargs:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=10) as client:
        return await client.request(method, f"{_KC_ADMIN}{path}", headers=headers, **kwargs)


async def _kc_get(path: str) -> Any:
    resp = await _kc("GET", path)
    resp.raise_for_status()
    return resp.json()


def _kc_id_from_location(location: str) -> str:
    return location.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------------------
# Audit logging helpers
# ---------------------------------------------------------------------------

def _actor(payload: Optional[Dict[str, Any]]) -> str:
    """Extract a human-readable actor string from the JWT payload."""
    if not payload:
        return "api-key"
    return payload.get("preferred_username") or payload.get("sub") or "unknown"


async def _log_identity_event(kc_id: str, action: str, actor: str, summary: str) -> None:
    """Append a user-management event to audit_log (resource_type='KeycloakUser')."""
    try:
        async with state.db.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO audit_log (resource_id, resource_type, action, actor, summary)
                   VALUES ($1, 'KeycloakUser', $2, $3, $4)""",
                kc_id, action, actor, summary,
            )
    except Exception:
        logger.exception("Failed to write identity audit log for kc_id=%s", kc_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(search: Optional[str] = Query(None)):
    """List all realm users enriched with FHIR roles and fhirUser attribute."""
    qs = f"/users?max=200{'&search=' + search if search else ''}"
    users: List[Dict] = await _kc_get(qs)

    async def _enrich(user: Dict) -> Dict:
        try:
            mappings = await _kc_get(f"/users/{user['id']}/role-mappings/realm")
            roles = [r["name"] for r in mappings if r["name"].startswith("fhir-")]
        except Exception:
            roles = []
        attrs = user.get("attributes") or {}
        fhir_user_list: List[str] = attrs.get("fhirUser") or []
        return {
            "id": user["id"],
            "username": user.get("username"),
            "email": user.get("email"),
            "firstName": user.get("firstName"),
            "lastName": user.get("lastName"),
            "enabled": user.get("enabled", True),
            "createdTimestamp": user.get("createdTimestamp"),
            "fhirUser": fhir_user_list[0] if fhir_user_list else None,
            "roles": roles,
        }

    enriched = await asyncio.gather(*[_enrich(u) for u in users])
    return {"users": list(enriched), "total": len(enriched)}


# ---------------------------------------------------------------------------

class CreateAdminRequest(BaseModel):
    firstName: str
    lastName: str
    email: str
    username: str
    password: str


@router.post("/users/admin", status_code=201)
async def create_admin(
    req: CreateAdminRequest,
    payload: Optional[Dict[str, Any]] = Depends(require_access),
):
    """Create a Keycloak account with fhir-admin role. No FHIR resource is created."""
    kc_resp = await _kc("POST", "/users", json={
        "username": req.username,
        "email": req.email,
        "firstName": req.firstName,
        "lastName": req.lastName,
        "enabled": True,
        "emailVerified": True,
        "credentials": [{"type": "password", "value": req.password, "temporary": True}],
    })
    if kc_resp.status_code != 201:
        raise HTTPException(400, f"Keycloak user creation failed: {kc_resp.text[:300]}")

    kc_id = _kc_id_from_location(kc_resp.headers.get("Location", ""))
    role = await _kc_get("/roles/fhir-admin")
    await _kc("POST", f"/users/{kc_id}/role-mappings/realm", json=[role])

    actor = _actor(payload)
    await _log_identity_event(
        kc_id, "create", actor,
        f"Created admin account: {req.username} ({req.email})",
    )
    logger.info("Admin account created: kc_id=%s username=%s by=%s", kc_id, req.username, actor)

    return {"kcId": kc_id, "username": req.username}


# ---------------------------------------------------------------------------

class CreateClinicianRequest(BaseModel):
    firstName: str
    lastName: str
    email: str
    username: str
    password: str
    prefix: Optional[str] = None
    gender: Optional[str] = None
    organization_id: Optional[str] = None
    specialty: Optional[str] = None


@router.post("/users/clinician", status_code=201)
async def create_clinician(
    req: CreateClinicianRequest,
    payload: Optional[Dict[str, Any]] = Depends(require_access),
):
    """Create a Practitioner resource + Keycloak account + optional PractitionerRole."""
    name_entry: Dict[str, Any] = {
        "use": "official",
        "family": req.lastName,
        "given": [req.firstName],
    }
    if req.prefix:
        name_entry["prefix"] = [req.prefix]

    prac_data: Dict[str, Any] = {
        "resourceType": "Practitioner",
        "active": True,
        "name": [name_entry],
        "gender": req.gender or "unknown",
        "telecom": [{"system": "email", "value": req.email, "use": "work"}],
    }
    prac_id = await state.db.create_resource("Practitioner", prac_data)
    fhir_ref = f"Practitioner/{prac_id}"

    kc_resp = await _kc("POST", "/users", json={
        "username": req.username,
        "email": req.email,
        "firstName": req.firstName,
        "lastName": req.lastName,
        "enabled": True,
        "emailVerified": True,
        "credentials": [{"type": "password", "value": req.password, "temporary": True}],
        "attributes": {"fhirUser": [fhir_ref]},
    })
    if kc_resp.status_code != 201:
        await state.db.delete_resource(prac_id)
        raise HTTPException(400, f"Keycloak user creation failed: {kc_resp.text[:300]}")

    kc_id = _kc_id_from_location(kc_resp.headers.get("Location", ""))
    role = await _kc_get("/roles/fhir-clinician")
    await _kc("POST", f"/users/{kc_id}/role-mappings/realm", json=[role])

    if req.organization_id:
        display = " ".join(filter(None, [req.prefix, req.firstName, req.lastName]))
        pr: Dict[str, Any] = {
            "resourceType": "PractitionerRole",
            "active": True,
            "practitioner": {"reference": fhir_ref, "display": display},
            "organization": {"reference": f"Organization/{req.organization_id}"},
        }
        if req.specialty:
            pr["specialty"] = [{"text": req.specialty}]
        await state.db.create_resource("PractitionerRole", pr)

    actor = _actor(payload)
    await _log_identity_event(
        kc_id, "create", actor,
        f"Created clinician account: {req.username} ({req.email}) → {fhir_ref}",
    )
    logger.info("Clinician account created: kc_id=%s fhir=%s by=%s", kc_id, fhir_ref, actor)

    return {"kcId": kc_id, "fhirId": prac_id, "fhirUser": fhir_ref}


# ---------------------------------------------------------------------------

class CreatePatientRequest(BaseModel):
    firstName: str
    lastName: str
    email: str
    username: str
    temporaryPassword: str = "ChangeMe123!"
    birthDate: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    generalPractitioner: Optional[str] = None


@router.post("/users/patient", status_code=201)
async def create_patient_account(
    req: CreatePatientRequest,
    payload: Optional[Dict[str, Any]] = Depends(require_access),
):
    """Create a Patient resource + Keycloak portal account."""
    telecom = [{"system": "email", "value": req.email}]
    if req.phone:
        telecom.append({"system": "phone", "value": req.phone})

    patient_data: Dict[str, Any] = {
        "resourceType": "Patient",
        "active": True,
        "name": [{"use": "official", "family": req.lastName, "given": [req.firstName]}],
        "gender": req.gender or "unknown",
        "telecom": telecom,
    }
    if req.birthDate:
        patient_data["birthDate"] = req.birthDate
    if req.generalPractitioner:
        patient_data["generalPractitioner"] = [{"reference": req.generalPractitioner}]

    patient_id = await state.db.create_resource("Patient", patient_data)
    fhir_ref = f"Patient/{patient_id}"

    kc_resp = await _kc("POST", "/users", json={
        "username": req.username,
        "email": req.email,
        "firstName": req.firstName,
        "lastName": req.lastName,
        "enabled": True,
        "emailVerified": False,
        "credentials": [{"type": "password", "value": req.temporaryPassword, "temporary": True}],
        "attributes": {"fhirUser": [fhir_ref]},
    })
    if kc_resp.status_code != 201:
        await state.db.delete_resource(patient_id)
        raise HTTPException(400, f"Keycloak user creation failed: {kc_resp.text[:300]}")

    kc_id = _kc_id_from_location(kc_resp.headers.get("Location", ""))
    role = await _kc_get("/roles/fhir-patient")
    await _kc("POST", f"/users/{kc_id}/role-mappings/realm", json=[role])

    actor = _actor(payload)
    await _log_identity_event(
        kc_id, "create", actor,
        f"Created patient portal account: {req.username} ({req.email}) → {fhir_ref}",
    )
    logger.info("Patient account created: kc_id=%s fhir=%s by=%s", kc_id, fhir_ref, actor)

    return {"kcId": kc_id, "fhirId": patient_id, "fhirUser": fhir_ref}


# ---------------------------------------------------------------------------

class UpdateStatusRequest(BaseModel):
    enabled: bool


@router.patch("/users/{kc_id}/status")
async def update_user_status(
    kc_id: str,
    req: UpdateStatusRequest,
    payload: Optional[Dict[str, Any]] = Depends(require_access),
):
    """Activate or deactivate a Keycloak user."""
    user = await _kc_get(f"/users/{kc_id}")
    user["enabled"] = req.enabled
    resp = await _kc("PUT", f"/users/{kc_id}", json=user)
    if not resp.is_success:
        raise HTTPException(502, f"Keycloak update failed: {resp.text[:200]}")

    action = "enable" if req.enabled else "disable"
    actor = _actor(payload)
    username = user.get("username", kc_id)
    await _log_identity_event(
        kc_id, action, actor,
        f"{'Activated' if req.enabled else 'Deactivated'} account: {username}",
    )
    logger.info("Account %s: kc_id=%s username=%s by=%s", action, kc_id, username, actor)

    return {"id": kc_id, "enabled": req.enabled}
