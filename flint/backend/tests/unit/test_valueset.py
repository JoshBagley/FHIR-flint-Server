"""Unit tests for ValueSet CRUD and FHIR operations."""

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_VALUESET


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def test_create_valueset(client: AsyncClient):
    resp = await client.post("/ValueSet", json=SAMPLE_VALUESET)
    assert resp.status_code == 201
    body = resp.json()
    assert body["resourceType"] == "ValueSet"
    assert body["name"] == "AdministrativeGender"
    assert "id" in body


async def test_get_valueset(client: AsyncClient):
    create = await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resource_id = create.json()["id"]

    resp = await client.get(f"/ValueSet/{resource_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == resource_id


async def test_get_valueset_not_found(client: AsyncClient):
    resp = await client.get("/ValueSet/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["resourceType"] == "OperationOutcome"


async def test_update_valueset(client: AsyncClient):
    create = await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resource_id = create.json()["id"]

    updated = {**SAMPLE_VALUESET, "version": "2.0", "description": "Updated description"}
    resp = await client.put(f"/ValueSet/{resource_id}", json=updated)
    assert resp.status_code == 200
    assert resp.json()["version"] == "2.0"


async def test_search_valueset_by_name(client: AsyncClient):
    await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resp = await client.get("/ValueSet?name=AdministrativeGender")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resourceType"] == "Bundle"
    assert body["total"] >= 1
    names = [e["resource"]["name"] for e in body["entry"]]
    assert "AdministrativeGender" in names


async def test_search_valueset_no_results(client: AsyncClient):
    resp = await client.get("/ValueSet?name=NonExistentValueSet999")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["entry"] == []


async def test_valueset_history(client: AsyncClient):
    create = await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resource_id = create.json()["id"]

    resp = await client.get(f"/ValueSet/{resource_id}/_history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "history"
    assert body["total"] >= 1


# ---------------------------------------------------------------------------
# $expand
# ---------------------------------------------------------------------------

async def test_expand_valueset(client: AsyncClient):
    await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/gender"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["resourceType"] == "ValueSet"
    expansion = body["expansion"]
    assert expansion["total"] == 4
    codes = [c["code"] for c in expansion["contains"]]
    assert "male" in codes
    assert "female" in codes


async def test_expand_valueset_with_filter(client: AsyncClient):
    await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/gender", "filter": "mal"}
    )
    assert resp.status_code == 200
    body = resp.json()
    codes = [c["code"] for c in body["expansion"]["contains"]]
    assert "male" in codes
    assert "female" in codes   # "female" contains "mal" in "female"
    assert "other" not in codes


async def test_expand_valueset_pagination(client: AsyncClient):
    await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/gender", "count": 2, "offset": 0}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["expansion"]["contains"]) == 2
    assert body["expansion"]["total"] == 4


async def test_expand_missing_url(client: AsyncClient):
    resp = await client.get("/ValueSet/$expand")
    assert resp.status_code == 400


async def test_expand_unknown_url(client: AsyncClient):
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/unknown"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# $validate-code
# ---------------------------------------------------------------------------

async def test_validate_code_valid(client: AsyncClient):
    await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resp = await client.get(
        "/ValueSet/$validate-code",
        params={"url": "http://example.com/vs/gender", "code": "male"}
    )
    assert resp.status_code == 200
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params["result"]["valueBoolean"] is True


async def test_validate_code_invalid(client: AsyncClient):
    await client.post("/ValueSet", json=SAMPLE_VALUESET)
    resp = await client.get(
        "/ValueSet/$validate-code",
        params={"url": "http://example.com/vs/gender", "code": "notacode"}
    )
    assert resp.status_code == 200
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params["result"]["valueBoolean"] is False


async def test_validate_code_missing_params(client: AsyncClient):
    resp = await client.get("/ValueSet/$validate-code", params={"url": "http://example.com/vs/gender"})
    assert resp.status_code == 400
