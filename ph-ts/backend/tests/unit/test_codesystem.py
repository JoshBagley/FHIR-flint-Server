"""Unit tests for CodeSystem CRUD and $lookup operation."""

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_CODESYSTEM


pytestmark = pytest.mark.asyncio


async def test_create_codesystem(client: AsyncClient):
    resp = await client.post("/CodeSystem", json=SAMPLE_CODESYSTEM)
    assert resp.status_code == 201
    body = resp.json()
    assert body["resourceType"] == "CodeSystem"
    assert body["name"] == "GenderCodes"
    assert "id" in body


async def test_get_codesystem(client: AsyncClient):
    create = await client.post("/CodeSystem", json=SAMPLE_CODESYSTEM)
    resource_id = create.json()["id"]

    resp = await client.get(f"/CodeSystem/{resource_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == resource_id


async def test_get_codesystem_not_found(client: AsyncClient):
    resp = await client.get("/CodeSystem/no-such-id")
    assert resp.status_code == 404
    assert resp.json()["resourceType"] == "OperationOutcome"


async def test_search_codesystem_by_name(client: AsyncClient):
    await client.post("/CodeSystem", json=SAMPLE_CODESYSTEM)
    resp = await client.get("/CodeSystem?name=GenderCodes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1


async def test_lookup_code_found(client: AsyncClient):
    await client.post("/CodeSystem", json=SAMPLE_CODESYSTEM)
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": "http://example.com/cs/gender", "code": "M"}
    )
    assert resp.status_code == 200
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params["display"]["valueString"] == "Male"


async def test_lookup_code_not_found(client: AsyncClient):
    await client.post("/CodeSystem", json=SAMPLE_CODESYSTEM)
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": "http://example.com/cs/gender", "code": "X"}
    )
    assert resp.status_code == 200
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params["result"]["valueBoolean"] is False


async def test_lookup_missing_system(client: AsyncClient):
    resp = await client.get("/CodeSystem/$lookup", params={"code": "M"})
    assert resp.status_code == 400


async def test_lookup_unknown_system(client: AsyncClient):
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": "http://example.com/cs/unknown", "code": "M"}
    )
    assert resp.status_code == 404
