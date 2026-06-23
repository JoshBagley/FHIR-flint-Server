"""Unit tests for the FHIR Bundle endpoint (POST /).
Tests batch and transaction modes including error isolation, rollback,
urn:uuid reference resolution, ifNoneExist, and ifMatch.
"""

import pytest
from httpx import AsyncClient

from app import state

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patient_entry(full_url: str = ""):
    entry = {
        "resource": {
            "resourceType": "Patient",
            "name": [{"family": "Bundle", "given": ["Test"]}],
            "gender": "male",
        },
        "request": {"method": "POST", "url": "Patient"},
    }
    if full_url:
        entry["fullUrl"] = full_url
    return entry


def _batch(*entries):
    return {"resourceType": "Bundle", "type": "batch", "entry": list(entries)}


def _transaction(*entries):
    return {"resourceType": "Bundle", "type": "transaction", "entry": list(entries)}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

async def test_bundle_wrong_resource_type(client: AsyncClient):
    resp = await client.post("/", json={"resourceType": "Patient"})
    assert resp.status_code == 400
    assert resp.json()["resourceType"] == "OperationOutcome"


async def test_bundle_wrong_type_field(client: AsyncClient):
    resp = await client.post("/", json={"resourceType": "Bundle", "type": "document"})
    assert resp.status_code == 400


async def test_bundle_entry_missing_request(client: AsyncClient):
    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [{"resource": {"resourceType": "Patient"}}]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "batch-response"
    # entry with no request → 400 in per-entry response
    assert "400" in body["entry"][0]["response"]["status"]


# ---------------------------------------------------------------------------
# Batch — basic operations
# ---------------------------------------------------------------------------

async def test_batch_post_creates_resource(client: AsyncClient):
    resp = await client.post("/", json=_batch(_patient_entry()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "batch-response"
    assert body["total"] == 1
    entry = body["entry"][0]
    assert entry["response"]["status"] == "201 Created"
    assert "Patient" in entry["response"]["location"]


async def test_batch_post_multiple_resources(client: AsyncClient):
    resp = await client.post("/", json=_batch(_patient_entry(), _patient_entry()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(e["response"]["status"] == "201 Created" for e in body["entry"])


async def test_batch_get_existing_resource(client: AsyncClient):
    # Pre-create resource via DB
    rid = await state.db.create_resource("Patient", {
        "resourceType": "Patient", "name": [{"family": "Direct"}]
    })

    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {"request": {"method": "GET", "url": f"Patient/{rid}"}}
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    entry = resp.json()["entry"][0]
    assert entry["response"]["status"] == "200 OK"
    assert entry["resource"]["id"] == rid


async def test_batch_get_missing_id_returns_400(client: AsyncClient):
    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {"request": {"method": "GET", "url": "Patient"}}
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    assert "400" in resp.json()["entry"][0]["response"]["status"]


async def test_batch_delete_resource(client: AsyncClient):
    rid = await state.db.create_resource("Patient", {"resourceType": "Patient"})

    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {"request": {"method": "DELETE", "url": f"Patient/{rid}"}}
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    assert resp.json()["entry"][0]["response"]["status"] == "204 No Content"


async def test_batch_put_updates_resource(client: AsyncClient):
    rid = await state.db.create_resource("Patient", {"resourceType": "Patient", "gender": "male"})

    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {
            "resource": {"resourceType": "Patient", "gender": "female"},
            "request": {"method": "PUT", "url": f"Patient/{rid}"},
        }
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    assert resp.json()["entry"][0]["response"]["status"] == "200 OK"


async def test_batch_put_missing_id_returns_400(client: AsyncClient):
    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {
            "resource": {"resourceType": "Patient", "gender": "female"},
            "request": {"method": "PUT", "url": "Patient"},
        }
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    assert "400" in resp.json()["entry"][0]["response"]["status"]


async def test_batch_put_not_found_returns_404(client: AsyncClient):
    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {
            "resource": {"resourceType": "Patient"},
            "request": {"method": "PUT", "url": "Patient/no-such-id"},
        }
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    assert "404" in resp.json()["entry"][0]["response"]["status"]


# ---------------------------------------------------------------------------
# Batch — error isolation
# ---------------------------------------------------------------------------

async def test_batch_error_isolation(client: AsyncClient):
    """A bad entry doesn't prevent other entries from succeeding."""
    bad_entry = {
        "resource": {"resourceType": "Patient"},
        "request": {"method": "PUT", "url": "Patient/nonexistent"},
    }
    good_entry = _patient_entry()

    resp = await client.post("/", json=_batch(bad_entry, good_entry))
    assert resp.status_code == 200
    entries = resp.json()["entry"]
    assert len(entries) == 2
    # First entry fails with 404
    assert "404" in entries[0]["response"]["status"]
    # Second entry succeeds
    assert entries[1]["response"]["status"] == "201 Created"


# ---------------------------------------------------------------------------
# Batch — ifNoneExist
# ---------------------------------------------------------------------------

async def test_batch_if_none_exist_match(client: AsyncClient):
    """ifNoneExist: when one match exists, return 200 without creating duplicate."""
    # Pre-create a Patient with a known identifier
    existing_id = await state.db.create_resource("Patient", {
        "resourceType": "Patient",
        "identifier": [{"system": "http://example.org/mrn", "value": "MRN001"}],
    })

    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {
            "resource": {
                "resourceType": "Patient",
                "identifier": [{"system": "http://example.org/mrn", "value": "MRN001"}],
            },
            "request": {
                "method": "POST",
                "url": "Patient",
                "ifNoneExist": "identifier=MRN001",
            },
        }
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    entry = resp.json()["entry"][0]
    # Should return 200 (found existing) not 201 (created new)
    assert entry["response"]["status"] == "200 OK"


async def test_batch_if_none_exist_no_match_creates(client: AsyncClient):
    """ifNoneExist: when no match exists, create normally."""
    bundle = {"resourceType": "Bundle", "type": "batch", "entry": [
        {
            "resource": {"resourceType": "Patient", "name": [{"family": "New"}]},
            "request": {
                "method": "POST",
                "url": "Patient",
                "ifNoneExist": "identifier=NEWMRN999",
            },
        }
    ]}
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    assert resp.json()["entry"][0]["response"]["status"] == "201 Created"


# ---------------------------------------------------------------------------
# Transaction — basic
# ---------------------------------------------------------------------------

async def test_transaction_post_creates_resources(client: AsyncClient):
    resp = await client.post("/", json=_transaction(_patient_entry(), _patient_entry()))
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "transaction-response"
    assert body["total"] == 2
    assert all(e["response"]["status"] == "201 Created" for e in body["entry"])


async def test_transaction_returns_etag(client: AsyncClient):
    resp = await client.post("/", json=_transaction(_patient_entry()))
    assert resp.status_code == 200
    etag = resp.json()["entry"][0]["response"]["etag"]
    assert etag.startswith('W/"')


# ---------------------------------------------------------------------------
# Transaction — urn:uuid reference resolution
# ---------------------------------------------------------------------------

async def test_transaction_urn_uuid_reference(client: AsyncClient):
    """Observation references Patient created in the same transaction via urn:uuid."""
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "fullUrl": "urn:uuid:patient-1",
                "resource": {
                    "resourceType": "Patient",
                    "name": [{"family": "Ref"}],
                },
                "request": {"method": "POST", "url": "Patient"},
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "final",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9"}]},
                    "subject": {"reference": "urn:uuid:patient-1"},
                },
                "request": {"method": "POST", "url": "Observation"},
            },
        ],
    }
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2

    obs_resource = body["entry"][1]["resource"]
    patient_location = body["entry"][0]["response"]["location"]
    patient_ref = patient_location.split("/_history")[0]  # e.g. "Patient/{id}"

    # The resolved reference in the Observation should point to the created Patient
    assert obs_resource["subject"]["reference"] == patient_ref


# ---------------------------------------------------------------------------
# Transaction — rollback on error
# ---------------------------------------------------------------------------

async def test_transaction_rollback_on_entry_error(client: AsyncClient):
    """If any entry fails, the whole transaction rolls back."""
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "fullUrl": "urn:uuid:patient-rollback",
                "resource": {
                    "resourceType": "Patient",
                    "name": [{"family": "ShouldNotExist"}],
                },
                "request": {"method": "POST", "url": "Patient"},
            },
            {
                "resource": {"resourceType": "Patient"},
                "request": {"method": "PUT", "url": "Patient/no-such-id"},  # will 404
            },
        ],
    }
    resp = await client.post("/", json=bundle)
    # Transaction must fail with 400 OperationOutcome
    assert resp.status_code == 400
    body = resp.json()
    assert body["resourceType"] == "OperationOutcome"

    # Verify the first entry's Patient was NOT persisted (rolled back)
    # The store should have 0 Patient resources
    patients = [v for v in state.db._store.values() if v.get("resourceType") == "Patient"]
    assert len(patients) == 0


async def test_transaction_rollback_preserves_existing_data(client: AsyncClient):
    """Rollback must not delete resources that existed before the transaction."""
    # Create a patient before the transaction
    existing_rid = await state.db.create_resource("Patient", {
        "resourceType": "Patient", "name": [{"family": "PreExisting"}]
    })

    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("urn:uuid:p1"),
            {"resource": {"resourceType": "Patient"}, "request": {"method": "PUT", "url": "Patient/bad"}},
        ],
    }
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 400

    # Pre-existing patient must still be there
    assert state.db._store.get(existing_rid) is not None


# ---------------------------------------------------------------------------
# Transaction — ifMatch
# ---------------------------------------------------------------------------

async def test_transaction_put_if_match_correct(client: AsyncClient):
    """Transaction PUT with correct ifMatch version succeeds."""
    rid = await state.db.create_resource("Patient", {"resourceType": "Patient", "gender": "male"})
    # After one create, versionId = "1"

    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": {"resourceType": "Patient", "gender": "female"},
                "request": {"method": "PUT", "url": f"Patient/{rid}", "ifMatch": 'W/"1"'},
            }
        ],
    }
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 200
    assert resp.json()["entry"][0]["response"]["status"] == "200 OK"


async def test_transaction_put_if_match_conflict(client: AsyncClient):
    """Transaction PUT with wrong ifMatch causes rollback."""
    rid = await state.db.create_resource("Patient", {"resourceType": "Patient", "gender": "male"})

    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": {"resourceType": "Patient", "gender": "female"},
                "request": {"method": "PUT", "url": f"Patient/{rid}", "ifMatch": 'W/"999"'},
            }
        ],
    }
    resp = await client.post("/", json=bundle)
    assert resp.status_code == 400
    assert resp.json()["resourceType"] == "OperationOutcome"


# ---------------------------------------------------------------------------
# Empty bundle
# ---------------------------------------------------------------------------

async def test_batch_empty_bundle(client: AsyncClient):
    resp = await client.post("/", json={"resourceType": "Bundle", "type": "batch", "entry": []})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["entry"] == []


async def test_transaction_empty_bundle(client: AsyncClient):
    resp = await client.post("/", json={"resourceType": "Bundle", "type": "transaction", "entry": []})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
