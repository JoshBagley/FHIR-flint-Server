"""Unit tests for health, metadata, and analytics endpoints."""

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def test_root(client: AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["fhirVersion"] == "4.0.1"
    assert "docs" in body


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "services" in body


async def test_metadata_capability_statement(client: AsyncClient):
    resp = await client.get("/metadata")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resourceType"] == "CapabilityStatement"
    assert body["fhirVersion"] == "4.0.1"
    resource_types = [r["type"] for r in body["rest"][0]["resource"]]
    assert "ValueSet" in resource_types
    assert "CodeSystem" in resource_types


async def test_analytics_summary_empty(client: AsyncClient):
    resp = await client.get("/analytics/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_valuesets" in body
    assert "total_codesystems" in body
    assert body["total_valuesets"] == 0
    assert body["total_codesystems"] == 0


async def test_analytics_summary_with_data(client: AsyncClient):
    from tests.conftest import SAMPLE_VALUESET, SAMPLE_CODESYSTEM
    await client.post("/ValueSet", json=SAMPLE_VALUESET)
    await client.post("/CodeSystem", json=SAMPLE_CODESYSTEM)

    resp = await client.get("/analytics/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_valuesets"] >= 1
    assert body["total_codesystems"] >= 1


async def test_stats_endpoint(client: AsyncClient):
    resp = await client.get("/$stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resourceType"] == "Parameters"
    names = [p["name"] for p in body["parameter"]]
    assert "total_valuesets" in names
    assert "total_codesystems" in names
