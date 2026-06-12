"""
Shared pytest fixtures for Flint-FHIR backend tests.

Uses httpx.AsyncClient with FastAPI's ASGI transport so every test runs
against the real application routes without a live network connection.
External services (PostgreSQL, Elasticsearch, Redis) are replaced with
lightweight fakes so the test suite needs no Docker containers.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app import state


# ---------------------------------------------------------------------------
# Fake service implementations
# ---------------------------------------------------------------------------

class FakeDB:
    """In-memory replacement for DatabaseManager."""

    def __init__(self):
        self._store: Dict[str, Dict] = {}
        self._versions: Dict[str, List[Dict]] = {}
        self._counter = 0

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def create_resource(self, resource_type: str, data: Dict) -> str:
        self._counter += 1
        resource_id = data.get("id") or f"test-{self._counter}"
        data = {**data, "id": resource_id, "resourceType": resource_type}
        self._store[resource_id] = data
        self._versions.setdefault(resource_id, [])
        self._versions[resource_id].append({
            "version": 1, "data": data,
            "timestamp": "2024-01-01T00:00:00", "author": "test", "summary": "Created"
        })
        return resource_id

    async def get_resource(self, resource_id: str, version: Optional[int] = None) -> Optional[Dict]:
        if version is not None:
            versions = self._versions.get(resource_id, [])
            for v in versions:
                if v["version"] == version:
                    return v["data"]
            return None
        return self._store.get(resource_id)

    async def update_resource(self, resource_id: str, data: Dict):
        self._store[resource_id] = data
        versions = self._versions.setdefault(resource_id, [])
        versions.append({
            "version": len(versions) + 1, "data": data,
            "timestamp": "2024-01-01T00:00:00", "author": "test", "summary": "Updated"
        })

    async def search_resources(self, resource_type: str, params: Dict, summary: bool = False) -> List[Dict]:
        results = []
        for item in self._store.values():
            if item.get("resourceType") != resource_type:
                continue
            match = True
            for k, v in params.items():
                field_val = item.get(k, "")
                if isinstance(field_val, str) and v.lower() not in field_val.lower():
                    match = False
                    break
                elif field_val != v and not isinstance(field_val, str):
                    match = False
                    break
            if match:
                results.append(item)
        return results

    async def get_version_history(self, resource_id: str) -> List[Dict]:
        return self._versions.get(resource_id, [])

    # pool stub used by /$stats and /analytics/summary
    @property
    def pool(self):
        pool = MagicMock()
        pool.acquire = _fake_pool_acquire(self._store)
        return pool


def _fake_pool_acquire(store: Dict):
    """Returns an async context manager whose conn can fetchval."""
    class _Conn:
        async def fetchval(self, query: str, *args):
            if "ValueSet" in query:
                return sum(1 for v in store.values() if v.get("resourceType") == "ValueSet")
            if "CodeSystem" in query:
                return sum(1 for v in store.values() if v.get("resourceType") == "CodeSystem")
            return 0

    class _Acquire:
        async def __aenter__(self):
            return _Conn()
        async def __aexit__(self, *_):
            pass

    class _Pool:
        def acquire(self):
            return _Acquire()

    return _Pool().acquire


class FakeSearchEngine:
    """No-op Elasticsearch replacement."""

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def index_resource(self, resource: Dict):
        pass

    async def search(self, query: str, resource_type: Optional[str] = None) -> List[Dict]:
        return []


class FakeCache:
    """In-memory Redis replacement."""

    def __init__(self):
        self._data: Dict[str, Any] = {}

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def get(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    async def set(self, key: str, value: Any, ttl: int = 3600):
        self._data[key] = value

    async def delete(self, key: str):
        self._data.pop(key, None)

    async def invalidate_pattern(self, pattern: str):
        prefix = pattern.rstrip("*")
        keys = [k for k in self._data if k.startswith(prefix)]
        for k in keys:
            del self._data[k]

    @property
    def redis_client(self):
        m = AsyncMock()
        m.ping = AsyncMock(return_value=True)
        return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def _inject_fakes():
    """Replace live service instances with fakes before each test."""
    state.db = FakeDB()
    state.search_engine = FakeSearchEngine()
    state.cache = FakeCache()

    yield

    # Reset
    state.db = None
    state.search_engine = None
    state.cache = None


@pytest_asyncio.fixture
async def client():
    """Async HTTP client wired to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

SAMPLE_VALUESET = {
    "resourceType": "ValueSet",
    "url": "http://example.com/vs/gender",
    "name": "AdministrativeGender",
    "title": "Administrative Gender",
    "status": "active",
    "version": "1.0",
    "description": "Gender codes for administrative use",
    "compose": {
        "include": [
            {
                "system": "http://hl7.org/fhir/administrative-gender",
                "concept": [
                    {"code": "male", "display": "Male"},
                    {"code": "female", "display": "Female"},
                    {"code": "other", "display": "Other"},
                    {"code": "unknown", "display": "Unknown"},
                ]
            }
        ]
    }
}

SAMPLE_CODESYSTEM = {
    "resourceType": "CodeSystem",
    "url": "http://example.com/cs/gender",
    "name": "GenderCodes",
    "title": "Gender Codes",
    "status": "active",
    "version": "1.0",
    "content": "complete",
    "concept": [
        {"code": "M", "display": "Male"},
        {"code": "F", "display": "Female"},
    ]
}
