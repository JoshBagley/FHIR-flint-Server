"""Unit tests for administrative and medications/reports resource types:
Organization, Practitioner, PractitionerRole, Location,
MedicationRequest, Procedure, DiagnosticReport."""

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_ORGANIZATION

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PRACTITIONER = {
    "resourceType": "Practitioner",
    "name": [{"family": "Jones", "given": ["Alice"], "prefix": ["Dr."]}],
    "gender": "female",
}

SAMPLE_PRACTITIONER_ROLE = {
    "resourceType": "PractitionerRole",
    "practitioner": {"reference": "Practitioner/test-practitioner"},
    "organization": {"reference": "Organization/test-org"},
    "code": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/practitioner-role", "code": "doctor"}]}],
    "active": True,
}

SAMPLE_LOCATION = {
    "resourceType": "Location",
    "name": "Main Campus",
    "status": "active",
    "description": "Primary care building",
    "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode", "code": "HOSP"}]}],
}

SAMPLE_MEDICATION_REQUEST = {
    "resourceType": "MedicationRequest",
    "status": "active",
    "intent": "order",
    "medicationCodeableConcept": {
        "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "1049502", "display": "12 HR Oxycodone"}]
    },
    "subject": {"reference": "Patient/test-patient"},
    "authoredOn": "2024-01-15",
}

SAMPLE_PROCEDURE = {
    "resourceType": "Procedure",
    "status": "completed",
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "80146002", "display": "Appendectomy"}]},
    "subject": {"reference": "Patient/test-patient"},
    "performedDateTime": "2024-01-10",
}

SAMPLE_DIAGNOSTIC_REPORT = {
    "resourceType": "DiagnosticReport",
    "status": "final",
    "code": {"coding": [{"system": "http://loinc.org", "code": "58410-2", "display": "CBC panel"}]},
    "subject": {"reference": "Patient/test-patient"},
    "issued": "2024-01-15T08:00:00Z",
}


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

async def test_create_organization(client: AsyncClient):
    resp = await client.post("/Organization", json=SAMPLE_ORGANIZATION)
    assert resp.status_code == 201
    body = resp.json()
    assert body["resourceType"] == "Organization"
    assert body["name"] == "General Hospital"
    assert "id" in body


async def test_get_organization(client: AsyncClient):
    create = await client.post("/Organization", json=SAMPLE_ORGANIZATION)
    rid = create.json()["id"]

    resp = await client.get(f"/Organization/{rid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


async def test_update_organization(client: AsyncClient):
    create = await client.post("/Organization", json=SAMPLE_ORGANIZATION)
    rid = create.json()["id"]

    updated = {**SAMPLE_ORGANIZATION, "name": "Regional Medical Center"}
    resp = await client.put(f"/Organization/{rid}", json=updated)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Regional Medical Center"


async def test_delete_organization(client: AsyncClient):
    create = await client.post("/Organization", json=SAMPLE_ORGANIZATION)
    rid = create.json()["id"]

    assert (await client.delete(f"/Organization/{rid}")).status_code == 204
    assert (await client.get(f"/Organization/{rid}")).status_code == 404


async def test_search_organization(client: AsyncClient):
    await client.post("/Organization", json=SAMPLE_ORGANIZATION)
    resp = await client.get("/Organization")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resourceType"] == "Bundle"
    assert body["total"] >= 1


async def test_organization_history(client: AsyncClient):
    create = await client.post("/Organization", json=SAMPLE_ORGANIZATION)
    rid = create.json()["id"]

    resp = await client.get(f"/Organization/{rid}/_history")
    assert resp.status_code == 200
    assert resp.json()["type"] == "history"


async def test_organization_not_found(client: AsyncClient):
    resp = await client.get("/Organization/no-such-org")
    assert resp.status_code == 404
    assert resp.json()["resourceType"] == "OperationOutcome"


# ---------------------------------------------------------------------------
# Practitioner
# ---------------------------------------------------------------------------

async def test_create_practitioner(client: AsyncClient):
    resp = await client.post("/Practitioner", json=SAMPLE_PRACTITIONER)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "Practitioner"


async def test_crud_practitioner(client: AsyncClient):
    create = await client.post("/Practitioner", json=SAMPLE_PRACTITIONER)
    rid = create.json()["id"]

    assert (await client.get(f"/Practitioner/{rid}")).status_code == 200

    updated = {**SAMPLE_PRACTITIONER, "gender": "unknown"}
    assert (await client.put(f"/Practitioner/{rid}", json=updated)).status_code == 200

    assert (await client.delete(f"/Practitioner/{rid}")).status_code == 204


async def test_search_practitioner(client: AsyncClient):
    await client.post("/Practitioner", json=SAMPLE_PRACTITIONER)
    resp = await client.get("/Practitioner")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# ---------------------------------------------------------------------------
# PractitionerRole
# ---------------------------------------------------------------------------

async def test_create_practitioner_role(client: AsyncClient):
    resp = await client.post("/PractitionerRole", json=SAMPLE_PRACTITIONER_ROLE)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "PractitionerRole"


async def test_crud_practitioner_role(client: AsyncClient):
    create = await client.post("/PractitionerRole", json=SAMPLE_PRACTITIONER_ROLE)
    rid = create.json()["id"]

    assert (await client.get(f"/PractitionerRole/{rid}")).status_code == 200

    updated = {**SAMPLE_PRACTITIONER_ROLE, "active": False}
    assert (await client.put(f"/PractitionerRole/{rid}", json=updated)).status_code == 200

    assert (await client.delete(f"/PractitionerRole/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

async def test_create_location(client: AsyncClient):
    resp = await client.post("/Location", json=SAMPLE_LOCATION)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "Location"
    assert resp.json()["name"] == "Main Campus"


async def test_crud_location(client: AsyncClient):
    create = await client.post("/Location", json=SAMPLE_LOCATION)
    rid = create.json()["id"]

    assert (await client.get(f"/Location/{rid}")).status_code == 200

    updated = {**SAMPLE_LOCATION, "status": "inactive"}
    assert (await client.put(f"/Location/{rid}", json=updated)).status_code == 200

    assert (await client.delete(f"/Location/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# MedicationRequest
# ---------------------------------------------------------------------------

async def test_create_medication_request(client: AsyncClient):
    resp = await client.post("/MedicationRequest", json=SAMPLE_MEDICATION_REQUEST)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "MedicationRequest"
    assert resp.json()["status"] == "active"


async def test_crud_medication_request(client: AsyncClient):
    create = await client.post("/MedicationRequest", json=SAMPLE_MEDICATION_REQUEST)
    rid = create.json()["id"]

    assert (await client.get(f"/MedicationRequest/{rid}")).status_code == 200

    updated = {**SAMPLE_MEDICATION_REQUEST, "status": "completed"}
    assert (await client.put(f"/MedicationRequest/{rid}", json=updated)).status_code == 200

    assert (await client.delete(f"/MedicationRequest/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# Procedure
# ---------------------------------------------------------------------------

async def test_create_procedure(client: AsyncClient):
    resp = await client.post("/Procedure", json=SAMPLE_PROCEDURE)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "Procedure"


async def test_crud_procedure(client: AsyncClient):
    create = await client.post("/Procedure", json=SAMPLE_PROCEDURE)
    rid = create.json()["id"]

    assert (await client.get(f"/Procedure/{rid}")).status_code == 200

    updated = {**SAMPLE_PROCEDURE, "status": "not-done"}
    assert (await client.put(f"/Procedure/{rid}", json=updated)).status_code == 200

    assert (await client.delete(f"/Procedure/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# DiagnosticReport
# ---------------------------------------------------------------------------

async def test_create_diagnostic_report(client: AsyncClient):
    resp = await client.post("/DiagnosticReport", json=SAMPLE_DIAGNOSTIC_REPORT)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "DiagnosticReport"


async def test_crud_diagnostic_report(client: AsyncClient):
    create = await client.post("/DiagnosticReport", json=SAMPLE_DIAGNOSTIC_REPORT)
    rid = create.json()["id"]

    assert (await client.get(f"/DiagnosticReport/{rid}")).status_code == 200

    updated = {**SAMPLE_DIAGNOSTIC_REPORT, "status": "amended"}
    assert (await client.put(f"/DiagnosticReport/{rid}", json=updated)).status_code == 200

    assert (await client.delete(f"/DiagnosticReport/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# Parameterized: POST all 7 administrative/medication types
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resource_type, payload", [
    ("Organization", SAMPLE_ORGANIZATION),
    ("Practitioner", SAMPLE_PRACTITIONER),
    ("PractitionerRole", SAMPLE_PRACTITIONER_ROLE),
    ("Location", SAMPLE_LOCATION),
    ("MedicationRequest", SAMPLE_MEDICATION_REQUEST),
    ("Procedure", SAMPLE_PROCEDURE),
    ("DiagnosticReport", SAMPLE_DIAGNOSTIC_REPORT),
])
async def test_create_admin_resource_type(client: AsyncClient, resource_type: str, payload: dict):
    resp = await client.post(f"/{resource_type}", json=payload)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == resource_type
    assert "id" in resp.json()
