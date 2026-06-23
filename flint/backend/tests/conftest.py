"""
Shared pytest fixtures for Flint backend tests.

Uses httpx.AsyncClient with FastAPI's ASGI transport so every test runs
against the real application routes without a live network connection.
External services (PostgreSQL, Elasticsearch, Redis) are replaced with
lightweight fakes so the test suite needs no Docker containers.
"""

import asyncio
import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app import state


# ---------------------------------------------------------------------------
# FakeConn / FakeTxn — used by bundle transaction tests
# ---------------------------------------------------------------------------

class _FakeRow:
    """Dict-like row returned by FakeConn.fetchrow."""
    def __init__(self, data: Dict):
        self._d = data

    def __getitem__(self, key: str):
        return self._d[key]

    def get(self, key: str, default=None):
        return self._d.get(key, default)


class _FakeTxn:
    """Snapshot-and-restore transaction for rollback testing."""

    def __init__(self, store: Dict, versions: Dict):
        self._store = store
        self._versions = versions
        self._snap_store: Dict = {}
        self._snap_versions: Dict = {}

    async def __aenter__(self):
        self._snap_store = copy.deepcopy(self._store)
        self._snap_versions = copy.deepcopy(self._versions)
        return self

    async def __aexit__(self, exc_type, *_):
        if exc_type is not None:
            self._store.clear()
            self._store.update(self._snap_store)
            self._versions.clear()
            self._versions.update(self._snap_versions)


class _FakeConn:
    """Asyncpg connection fake. Shares store/versions with FakeDB by reference."""

    def __init__(self, store: Dict, versions: Dict):
        self._store = store
        self._versions = versions

    async def fetchval(self, query: str, *args):
        """Used by /analytics/summary and /$stats endpoints."""
        for rt in ("ValueSet", "CodeSystem", "ConceptMap", "Patient", "Observation",
                   "Condition", "Encounter", "AllergyIntolerance", "Immunization",
                   "Organization", "Practitioner", "PractitionerRole", "Location",
                   "MedicationRequest", "Procedure", "DiagnosticReport"):
            if rt in query:
                return sum(1 for v in self._store.values() if v.get("resourceType") == rt)
        return 0

    async def fetch(self, query: str, *args):
        return []

    async def fetchrow(self, sql: str, *args):
        if "FROM fhir_resources" in sql:
            # _get_raw: SELECT fr.data, fr.updated_at, MAX(version_number) AS version ... WHERE fr.id = $1
            resource_id = args[0]
            data = self._store.get(resource_id)
            if data is None:
                return None
            vlist = self._versions.get(resource_id, [])
            return _FakeRow({
                "data": json.dumps(data),
                "updated_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "version": len(vlist) if vlist else 1,
            })
        elif "MAX(version_number)" in sql:
            # _update_raw: SELECT MAX(version_number) AS v FROM resource_versions WHERE resource_id = $1
            resource_id = args[0]
            vlist = self._versions.get(resource_id, [])
            return _FakeRow({"v": len(vlist)})
        return None

    async def execute(self, sql: str, *args):
        stripped = sql.strip()
        if "INSERT INTO fhir_resources" in stripped:
            # args: rid, rt, url, version, status, name_val, title, json.dumps(data)
            rid = args[0]
            data = json.loads(args[7])
            self._store[rid] = data
        elif "INSERT INTO resource_versions" in stripped:
            rid = args[0]
            if len(args) == 3:
                # _update_raw: VALUES ($1,$2,$3,...) — rid, version_num, data_json
                version_num, data_json = args[1], args[2]
            else:
                # _create_raw: VALUES ($1,1,$2,...) — rid, data_json (version hardcoded as 1)
                version_num, data_json = 1, args[1]
            self._versions.setdefault(rid, [])
            self._versions[rid].append({"version": version_num, "data": json.loads(data_json)})
        elif stripped.startswith("UPDATE fhir_resources"):
            # args: json.dumps(data), url, version, status, name_val, title, rid
            rid = args[6]
            data = json.loads(args[0])
            self._store[rid] = data
        elif "DELETE FROM fhir_resources" in stripped:
            rid = args[0]
            self._store.pop(rid, None)
        elif "DELETE FROM resource_versions" in stripped:
            rid = args[0]
            self._versions.pop(rid, None)
        # audit_log inserts are silently ignored

    def transaction(self) -> _FakeTxn:
        return _FakeTxn(self._store, self._versions)


class _FakePoolAcquire:
    def __init__(self, store: Dict, versions: Dict):
        self._store = store
        self._versions = versions

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._store, self._versions)

    async def __aexit__(self, *_):
        pass


class _FakePool:
    def __init__(self, store: Dict, versions: Dict):
        self._store = store
        self._versions = versions

    def acquire(self) -> _FakePoolAcquire:
        return _FakePoolAcquire(self._store, self._versions)


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
            "timestamp": "2024-01-01T00:00:00", "author": "test", "summary": "Created",
        })
        return resource_id

    async def get_resource(self, resource_id: str, version: Optional[int] = None) -> Optional[Dict]:
        if version is not None:
            for v in self._versions.get(resource_id, []):
                if v["version"] == version:
                    return v["data"]
            return None
        data = self._store.get(resource_id)
        if data is None:
            return None
        # Inject meta so ETag / If-Match checks work in tests
        data = dict(data)
        vlist = self._versions.get(resource_id, [])
        data["meta"] = {
            "versionId": str(len(vlist)) if vlist else "1",
            "lastUpdated": "2024-01-01T00:00:00Z",
        }
        return data

    async def update_resource(self, resource_id: str, data: Dict):
        self._store[resource_id] = data
        versions = self._versions.setdefault(resource_id, [])
        versions.append({
            "version": len(versions) + 1, "data": data,
            "timestamp": "2024-01-01T00:00:00", "author": "test", "summary": "Updated",
        })

    async def delete_resource(self, resource_id: str, user: str = "system") -> bool:
        if resource_id not in self._store:
            return False
        del self._store[resource_id]
        self._versions.pop(resource_id, None)
        return True

    async def archive_resource(self, resource_id: str, archived: bool = True) -> bool:
        data = self._store.get(resource_id)
        if data is None:
            return False
        self._store[resource_id] = {**data, "_archived": archived}
        return True

    async def get_audit_log(self, resource_id: str) -> List[Dict]:
        return [
            {"action": "create" if i == 0 else "update", "version": v["version"], "actor": "test"}
            for i, v in enumerate(self._versions.get(resource_id, []))
        ]

    async def search_resources(
        self,
        resource_type: str,
        params: Dict,
        summary: bool = False,
        archived_only: bool = False,
        limit: int = 20,
        offset: int = 0,
        sort: Optional[str] = None,
    ) -> Tuple[int, List[Dict]]:
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
                elif not isinstance(field_val, str) and field_val != v:
                    match = False
                    break
            if match:
                results.append(item)
        paged = results[offset:offset + limit]
        return len(results), paged

    async def search_resources_ex(
        self,
        resource_type: str,
        base_params: Dict,
        extra_condition_pairs: List,
        summary: bool = False,
        archived_only: bool = False,
        limit: int = 20,
        offset: int = 0,
        sort: Optional[str] = None,
    ) -> Tuple[int, List[Dict]]:
        results = []
        for item in self._store.values():
            if item.get("resourceType") != resource_type:
                continue
            match = True
            if "name" in base_params:
                v = base_params["name"].lower()
                name_val = str(item.get("name", "") or "")
                title_val = str(item.get("title", "") or "")
                url_val = str(item.get("url", "") or "")
                if v not in name_val.lower() and v not in title_val.lower() and v not in url_val.lower():
                    match = False
            if "status" in base_params and item.get("status") != base_params["status"]:
                match = False
            if "url" in base_params and item.get("url") != base_params["url"]:
                match = False
            if match:
                results.append(item)
        # extra_condition_pairs (JSONB SQL fragments) are not evaluated in the fake
        paged = results[offset:offset + limit]
        return len(results), paged

    async def get_version_history(self, resource_id: str) -> List[Dict]:
        return self._versions.get(resource_id, [])

    @property
    def pool(self) -> _FakePool:
        return _FakePool(self._store, self._versions)


class FakeSearchEngine:
    """No-op Elasticsearch replacement."""

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def index_resource(self, resource: Dict):
        pass

    async def delete_resource(self, resource_id: str):
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
        for k in [k for k in self._data if k.startswith(prefix)]:
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

SAMPLE_PATIENT = {
    "resourceType": "Patient",
    "name": [{"family": "Smith", "given": ["John"]}],
    "gender": "male",
    "birthDate": "1990-01-15",
}

SAMPLE_OBSERVATION = {
    "resourceType": "Observation",
    "status": "final",
    "code": {
        "coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel"}]
    },
    "subject": {"reference": "Patient/test-patient"},
    "valueQuantity": {"value": 120, "unit": "mmHg"},
}

SAMPLE_CONDITION = {
    "resourceType": "Condition",
    "subject": {"reference": "Patient/test-patient"},
    "code": {
        "coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Type 2 diabetes mellitus"}]
    },
    "clinicalStatus": {"coding": [{"code": "active"}]},
}

SAMPLE_ORGANIZATION = {
    "resourceType": "Organization",
    "name": "General Hospital",
    "type": [{"coding": [{"code": "prov", "system": "http://terminology.hl7.org/CodeSystem/organization-type"}]}],
}
