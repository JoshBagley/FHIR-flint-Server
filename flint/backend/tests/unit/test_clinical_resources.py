"""Unit tests for clinical resource types: Patient, Observation, Condition,
Encounter, AllergyIntolerance, Immunization."""

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_PATIENT, SAMPLE_OBSERVATION, SAMPLE_CONDITION

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Patient CRUD
# ---------------------------------------------------------------------------

async def test_create_patient(client: AsyncClient):
    resp = await client.post("/Patient", json=SAMPLE_PATIENT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["resourceType"] == "Patient"
    assert "id" in body


async def test_get_patient(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    resp = await client.get(f"/Patient/{rid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


async def test_get_patient_not_found(client: AsyncClient):
    resp = await client.get("/Patient/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["resourceType"] == "OperationOutcome"


async def test_update_patient(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    updated = {**SAMPLE_PATIENT, "gender": "female"}
    resp = await client.put(f"/Patient/{rid}", json=updated)
    assert resp.status_code == 200
    assert resp.json()["gender"] == "female"


async def test_delete_patient(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    resp = await client.delete(f"/Patient/{rid}")
    assert resp.status_code == 204

    get_resp = await client.get(f"/Patient/{rid}")
    assert get_resp.status_code == 404


async def test_delete_patient_not_found(client: AsyncClient):
    resp = await client.delete("/Patient/does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Patient ETag / optimistic locking
# ---------------------------------------------------------------------------

async def test_patient_etag_on_create(client: AsyncClient):
    resp = await client.post("/Patient", json=SAMPLE_PATIENT)
    assert "ETag" in resp.headers
    assert resp.headers["ETag"].startswith('W/"')


async def test_patient_etag_on_read(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    resp = await client.get(f"/Patient/{rid}")
    assert "ETag" in resp.headers


async def test_patient_if_match_correct(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]
    etag = create.headers["ETag"]

    updated = {**SAMPLE_PATIENT, "gender": "female"}
    resp = await client.put(f"/Patient/{rid}", json=updated, headers={"If-Match": etag})
    assert resp.status_code == 200


async def test_patient_if_match_conflict(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    updated = {**SAMPLE_PATIENT, "gender": "female"}
    resp = await client.put(
        f"/Patient/{rid}", json=updated, headers={"If-Match": 'W/"999"'}
    )
    assert resp.status_code == 412
    assert resp.json()["resourceType"] == "OperationOutcome"


# ---------------------------------------------------------------------------
# Patient version history
# ---------------------------------------------------------------------------

async def test_patient_history(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    resp = await client.get(f"/Patient/{rid}/_history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "history"
    assert body["total"] >= 1


async def test_patient_versioned_read(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    resp = await client.get(f"/Patient/{rid}/_history/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


async def test_patient_versioned_read_not_found(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    resp = await client.get(f"/Patient/{rid}/_history/999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Patient search
# ---------------------------------------------------------------------------

async def test_search_patient_all(client: AsyncClient):
    await client.post("/Patient", json=SAMPLE_PATIENT)
    resp = await client.get("/Patient")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resourceType"] == "Bundle"
    assert body["type"] == "searchset"
    assert body["total"] >= 1


async def test_search_patient_empty(client: AsyncClient):
    resp = await client.get("/Patient?family=NoSuchPatient999")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["entry"] == []


async def test_search_patient_by_gender(client: AsyncClient):
    await client.post("/Patient", json=SAMPLE_PATIENT)
    # extra_condition_pairs not evaluated in fake — just verify bundle shape
    resp = await client.get("/Patient?gender=male")
    assert resp.status_code == 200
    assert resp.json()["resourceType"] == "Bundle"


# ---------------------------------------------------------------------------
# Patient audit
# ---------------------------------------------------------------------------

async def test_patient_audit(client: AsyncClient):
    create = await client.post("/Patient", json=SAMPLE_PATIENT)
    rid = create.json()["id"]

    resp = await client.get(f"/Patient/{rid}/$audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resourceId"] == rid
    assert body["total"] >= 1


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

async def test_create_observation(client: AsyncClient):
    resp = await client.post("/Observation", json=SAMPLE_OBSERVATION)
    assert resp.status_code == 201
    body = resp.json()
    assert body["resourceType"] == "Observation"
    assert body["status"] == "final"


async def test_get_observation(client: AsyncClient):
    create = await client.post("/Observation", json=SAMPLE_OBSERVATION)
    rid = create.json()["id"]

    resp = await client.get(f"/Observation/{rid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


async def test_update_observation(client: AsyncClient):
    create = await client.post("/Observation", json=SAMPLE_OBSERVATION)
    rid = create.json()["id"]

    updated = {**SAMPLE_OBSERVATION, "status": "amended"}
    resp = await client.put(f"/Observation/{rid}", json=updated)
    assert resp.status_code == 200
    assert resp.json()["status"] == "amended"


async def test_delete_observation(client: AsyncClient):
    create = await client.post("/Observation", json=SAMPLE_OBSERVATION)
    rid = create.json()["id"]

    resp = await client.delete(f"/Observation/{rid}")
    assert resp.status_code == 204


async def test_search_observation(client: AsyncClient):
    await client.post("/Observation", json=SAMPLE_OBSERVATION)
    resp = await client.get("/Observation")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# ---------------------------------------------------------------------------
# Condition
# ---------------------------------------------------------------------------

async def test_create_condition(client: AsyncClient):
    resp = await client.post("/Condition", json=SAMPLE_CONDITION)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "Condition"


async def test_get_condition(client: AsyncClient):
    create = await client.post("/Condition", json=SAMPLE_CONDITION)
    rid = create.json()["id"]

    resp = await client.get(f"/Condition/{rid}")
    assert resp.status_code == 200


async def test_update_condition(client: AsyncClient):
    create = await client.post("/Condition", json=SAMPLE_CONDITION)
    rid = create.json()["id"]

    updated = {**SAMPLE_CONDITION, "clinicalStatus": {"coding": [{"code": "resolved"}]}}
    resp = await client.put(f"/Condition/{rid}", json=updated)
    assert resp.status_code == 200


async def test_search_condition(client: AsyncClient):
    await client.post("/Condition", json=SAMPLE_CONDITION)
    resp = await client.get("/Condition")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# ---------------------------------------------------------------------------
# Encounter
# ---------------------------------------------------------------------------

SAMPLE_ENCOUNTER = {
    "resourceType": "Encounter",
    "status": "finished",
    "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
    "subject": {"reference": "Patient/test-patient"},
}


async def test_create_encounter(client: AsyncClient):
    resp = await client.post("/Encounter", json=SAMPLE_ENCOUNTER)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "Encounter"


async def test_crud_encounter(client: AsyncClient):
    create = await client.post("/Encounter", json=SAMPLE_ENCOUNTER)
    rid = create.json()["id"]

    assert (await client.get(f"/Encounter/{rid}")).status_code == 200

    updated = {**SAMPLE_ENCOUNTER, "status": "in-progress"}
    assert (await client.put(f"/Encounter/{rid}", json=updated)).status_code == 200

    assert (await client.delete(f"/Encounter/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# AllergyIntolerance
# ---------------------------------------------------------------------------

SAMPLE_ALLERGY = {
    "resourceType": "AllergyIntolerance",
    "patient": {"reference": "Patient/test-patient"},
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "372687004", "display": "Amoxicillin"}]},
    "clinicalStatus": {"coding": [{"code": "active"}]},
    "criticality": "high",
}


async def test_create_allergy(client: AsyncClient):
    resp = await client.post("/AllergyIntolerance", json=SAMPLE_ALLERGY)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "AllergyIntolerance"


async def test_crud_allergy(client: AsyncClient):
    create = await client.post("/AllergyIntolerance", json=SAMPLE_ALLERGY)
    rid = create.json()["id"]

    assert (await client.get(f"/AllergyIntolerance/{rid}")).status_code == 200
    assert (await client.delete(f"/AllergyIntolerance/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# Immunization
# ---------------------------------------------------------------------------

SAMPLE_IMMUNIZATION = {
    "resourceType": "Immunization",
    "status": "completed",
    "vaccineCode": {"coding": [{"system": "http://hl7.org/fhir/sid/cvx", "code": "207", "display": "COVID-19"}]},
    "patient": {"reference": "Patient/test-patient"},
    "occurrenceDateTime": "2021-03-15",
}


async def test_create_immunization(client: AsyncClient):
    resp = await client.post("/Immunization", json=SAMPLE_IMMUNIZATION)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == "Immunization"


async def test_crud_immunization(client: AsyncClient):
    create = await client.post("/Immunization", json=SAMPLE_IMMUNIZATION)
    rid = create.json()["id"]

    assert (await client.get(f"/Immunization/{rid}")).status_code == 200

    updated = {**SAMPLE_IMMUNIZATION, "status": "not-done"}
    assert (await client.put(f"/Immunization/{rid}", json=updated)).status_code == 200
    assert (await client.delete(f"/Immunization/{rid}")).status_code == 204


# ---------------------------------------------------------------------------
# Parameterized: POST all 6 clinical types
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resource_type, payload", [
    ("Patient", SAMPLE_PATIENT),
    ("Observation", SAMPLE_OBSERVATION),
    ("Condition", SAMPLE_CONDITION),
    ("Encounter", SAMPLE_ENCOUNTER),
    ("AllergyIntolerance", SAMPLE_ALLERGY),
    ("Immunization", SAMPLE_IMMUNIZATION),
])
async def test_create_clinical_resource_type(client: AsyncClient, resource_type: str, payload: dict):
    resp = await client.post(f"/{resource_type}", json=payload)
    assert resp.status_code == 201
    assert resp.json()["resourceType"] == resource_type
    assert "id" in resp.json()
