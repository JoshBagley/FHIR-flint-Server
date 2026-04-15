"""
Custom FHIR R4 Terminology Server
==================================
A high-performance terminology server built from scratch to mimic Ontoserver
capabilities with enhanced features for public health vocabulary management.

Key Features:
- FHIR R4 ValueSet and CodeSystem operations
- Fast search with Elasticsearch
- Version control with full history
- Multi-user authoring with RBAC
- Advanced analytics and reporting
- Automated concept mapping
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
from contextlib import asynccontextmanager
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import uuid
import hashlib
from collections import defaultdict
import asyncio
import asyncpg
from elasticsearch import AsyncElasticsearch
import redis.asyncio as redis
import json
import os
import time
import logging
import sys
from app import state
from app.routes.fhir_operations import router as fhir_operations_router
from app.routes.sdo_search import router as sdo_router
from app.routes.ai_assist import router as ai_router

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    'fhir_requests_total', 'Total FHIR requests',
    ['method', 'endpoint', 'status']
)
REQUEST_DURATION = Histogram(
    'fhir_request_duration_seconds', 'FHIR request duration',
    ['method', 'endpoint']
)
RESOURCE_COUNT = Counter(
    'fhir_resources_total', 'Total FHIR resources created/updated',
    ['resource_type', 'operation']
)


# ============================================================================
# FHIR Resource Models
# ============================================================================

class FHIRResourceType(str, Enum):
    VALUESET = "ValueSet"
    CODESYSTEM = "CodeSystem"
    CONCEPTMAP = "ConceptMap"


class ResourceStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"
    UNKNOWN = "unknown"


class ContactPoint(BaseModel):
    system: Optional[str] = None
    value: Optional[str] = None
    use: Optional[str] = None


class ContactDetail(BaseModel):
    name: Optional[str] = None
    telecom: Optional[List[ContactPoint]] = []


class Coding(BaseModel):
    system: Optional[str] = None
    version: Optional[str] = None
    code: Optional[str] = None
    display: Optional[str] = None
    userSelected: Optional[bool] = None


class CodeableConcept(BaseModel):
    coding: Optional[List[Coding]] = []
    text: Optional[str] = None


class Identifier(BaseModel):
    system: Optional[str] = None
    value: Optional[str] = None
    use: Optional[str] = None


class Meta(BaseModel):
    versionId: Optional[str] = None
    lastUpdated: Optional[datetime] = None
    source: Optional[str] = None
    profile: Optional[List[str]] = []
    security: Optional[List[Coding]] = []
    tag: Optional[List[Coding]] = []


class Narrative(BaseModel):
    status: Literal["generated", "extensions", "additional", "empty"]
    div: str


class ValueSetConcept(BaseModel):
    code: str
    display: Optional[str] = None
    designation: Optional[List[Dict[str, Any]]] = []


class ValueSetInclude(BaseModel):
    system: Optional[str] = None
    version: Optional[str] = None
    concept: Optional[List[ValueSetConcept]] = []
    filter: Optional[List[Dict[str, Any]]] = []
    valueSet: Optional[List[str]] = []


class ValueSetCompose(BaseModel):
    lockedDate: Optional[str] = None
    inactive: Optional[bool] = None
    include: List[ValueSetInclude] = []
    exclude: Optional[List[ValueSetInclude]] = []


class ValueSetExpansionContains(BaseModel):
    system: Optional[str] = None
    abstract: Optional[bool] = None
    inactive: Optional[bool] = None
    version: Optional[str] = None
    code: Optional[str] = None
    display: Optional[str] = None
    designation: Optional[List[Dict[str, Any]]] = []
    contains: Optional[List['ValueSetExpansionContains']] = []


class ValueSetExpansion(BaseModel):
    identifier: Optional[str] = None
    timestamp: datetime
    total: Optional[int] = None
    offset: Optional[int] = None
    parameter: Optional[List[Dict[str, Any]]] = []
    contains: Optional[List[ValueSetExpansionContains]] = []


class ValueSet(BaseModel):
    resourceType: Literal["ValueSet"] = "ValueSet"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    implicitRules: Optional[str] = None
    language: Optional[str] = None
    text: Optional[Narrative] = None
    url: Optional[str] = None
    identifier: Optional[List[Identifier]] = []
    version: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    status: ResourceStatus
    experimental: Optional[bool] = None
    date: Optional[str] = None
    publisher: Optional[str] = None
    contact: Optional[List[ContactDetail]] = []
    description: Optional[str] = None
    useContext: Optional[List[Dict[str, Any]]] = []
    jurisdiction: Optional[List[CodeableConcept]] = []
    immutable: Optional[bool] = None
    purpose: Optional[str] = None
    copyright: Optional[str] = None
    compose: Optional[ValueSetCompose] = None
    expansion: Optional[ValueSetExpansion] = None
    extension: Optional[List[Dict[str, Any]]] = []


class CodeSystemProperty(BaseModel):
    code: str
    uri: Optional[str] = None
    description: Optional[str] = None
    type: Literal["code", "Coding", "string", "integer", "boolean", "dateTime", "decimal"]


class CodeSystemConceptProperty(BaseModel):
    code: str
    valueCode: Optional[str] = None
    valueCoding: Optional[Coding] = None
    valueString: Optional[str] = None
    valueInteger: Optional[int] = None
    valueBoolean: Optional[bool] = None
    valueDateTime: Optional[datetime] = None
    valueDecimal: Optional[float] = None


class CodeSystemConceptDesignation(BaseModel):
    language: Optional[str] = None
    use: Optional[Coding] = None
    value: str


class CodeSystemConcept(BaseModel):
    code: str
    display: Optional[str] = None
    definition: Optional[str] = None
    designation: Optional[List[CodeSystemConceptDesignation]] = []
    property: Optional[List[CodeSystemConceptProperty]] = []
    concept: Optional[List['CodeSystemConcept']] = []


class CodeSystem(BaseModel):
    resourceType: Literal["CodeSystem"] = "CodeSystem"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    url: Optional[str] = None
    identifier: Optional[List[Identifier]] = []
    version: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    status: ResourceStatus
    experimental: Optional[bool] = None
    date: Optional[str] = None
    publisher: Optional[str] = None
    contact: Optional[List[ContactDetail]] = []
    description: Optional[str] = None
    useContext: Optional[List[Dict[str, Any]]] = []
    jurisdiction: Optional[List[CodeableConcept]] = []
    purpose: Optional[str] = None
    copyright: Optional[str] = None
    caseSensitive: Optional[bool] = None
    valueSet: Optional[str] = None
    hierarchyMeaning: Optional[Literal["grouped-by", "is-a", "part-of", "classified-with"]] = None
    compositional: Optional[bool] = None
    versionNeeded: Optional[bool] = None
    content: Literal["not-present", "example", "fragment", "complete", "supplement"]
    supplements: Optional[str] = None
    count: Optional[int] = None
    filter: Optional[List[Dict[str, Any]]] = []
    property: Optional[List[CodeSystemProperty]] = []
    concept: Optional[List[CodeSystemConcept]] = []
    extension: Optional[List[Dict[str, Any]]] = []


class ConceptMapGroupElementTarget(BaseModel):
    code: Optional[str] = None
    display: Optional[str] = None
    equivalence: Literal[
        "relatedto", "equivalent", "equal", "wider", "subsumes",
        "narrower", "specializes", "inexact", "unmatched", "disjoint"
    ] = "equivalent"
    comment: Optional[str] = None
    dependsOn: Optional[List[Dict[str, Any]]] = []
    product: Optional[List[Dict[str, Any]]] = []


class ConceptMapGroupElement(BaseModel):
    code: Optional[str] = None
    display: Optional[str] = None
    target: Optional[List[ConceptMapGroupElementTarget]] = []


class ConceptMapGroup(BaseModel):
    source: Optional[str] = None
    sourceVersion: Optional[str] = None
    target: Optional[str] = None
    targetVersion: Optional[str] = None
    element: List[ConceptMapGroupElement] = []
    unmapped: Optional[Dict[str, Any]] = None


class ConceptMap(BaseModel):
    resourceType: Literal["ConceptMap"] = "ConceptMap"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    url: Optional[str] = None
    identifier: Optional[List[Identifier]] = []
    version: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    status: ResourceStatus
    experimental: Optional[bool] = None
    date: Optional[str] = None
    publisher: Optional[str] = None
    contact: Optional[List[ContactDetail]] = []
    description: Optional[str] = None
    purpose: Optional[str] = None
    copyright: Optional[str] = None
    sourceUri: Optional[str] = None
    sourceCanonical: Optional[str] = None
    targetUri: Optional[str] = None
    targetCanonical: Optional[str] = None
    group: Optional[List[ConceptMapGroup]] = []
    extension: Optional[List[Dict[str, Any]]] = []


# ============================================================================
# Database Layer
# ============================================================================

class DatabaseManager:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=10, max_size=50, command_timeout=60)
        await self._initialize_schema()

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def _initialize_schema(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS fhir_resources (
                    id VARCHAR(64) PRIMARY KEY,
                    resource_type VARCHAR(50) NOT NULL,
                    url VARCHAR(500),
                    version VARCHAR(50),
                    status VARCHAR(20),
                    name VARCHAR(255),
                    title VARCHAR(500),
                    data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    created_by VARCHAR(100),
                    updated_by VARCHAR(100)
                );

                CREATE INDEX IF NOT EXISTS idx_resource_type ON fhir_resources(resource_type);
                CREATE INDEX IF NOT EXISTS idx_url ON fhir_resources(url);
                CREATE INDEX IF NOT EXISTS idx_status ON fhir_resources(status);
                CREATE INDEX IF NOT EXISTS idx_name ON fhir_resources(name);
                CREATE INDEX IF NOT EXISTS idx_data_gin ON fhir_resources USING GIN (data);

                CREATE TABLE IF NOT EXISTS resource_versions (
                    id SERIAL PRIMARY KEY,
                    resource_id VARCHAR(64) NOT NULL,
                    version_number INTEGER NOT NULL,
                    data JSONB NOT NULL,
                    change_summary TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    created_by VARCHAR(100),
                    UNIQUE(resource_id, version_number)
                );

                CREATE INDEX IF NOT EXISTS idx_version_resource ON resource_versions(resource_id);

                -- Deduplicate fhir_resources: for each (resource_type, url, version) group
                -- where both url and version are non-null, keep only the oldest row.
                -- This is a no-op once the data is already clean.
                WITH ranked AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY resource_type, url, version
                               ORDER BY created_at ASC
                           ) AS rn
                    FROM fhir_resources
                    WHERE url IS NOT NULL AND version IS NOT NULL
                )
                DELETE FROM fhir_resources
                WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

                -- Remove orphaned version-history rows whose parent resource was removed
                DELETE FROM resource_versions
                WHERE resource_id NOT IN (SELECT id FROM fhir_resources);

                -- Enforce uniqueness on (resource_type, url, version) going forward.
                -- Partial index: only applies when both url and version are present,
                -- so unversioned resources are not affected.
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_resource_url_version
                ON fhir_resources(resource_type, url, version)
                WHERE url IS NOT NULL AND version IS NOT NULL;

                CREATE TABLE IF NOT EXISTS concept_mappings (
                    id SERIAL PRIMARY KEY,
                    source_system VARCHAR(255),
                    source_code VARCHAR(100),
                    target_system VARCHAR(255),
                    target_code VARCHAR(100),
                    equivalence VARCHAR(50),
                    confidence DECIMAL(3,2),
                    created_at TIMESTAMP DEFAULT NOW(),
                    created_by VARCHAR(100)
                );

                CREATE INDEX IF NOT EXISTS idx_source_mapping ON concept_mappings(source_system, source_code);
                CREATE INDEX IF NOT EXISTS idx_target_mapping ON concept_mappings(target_system, target_code);

                CREATE TABLE IF NOT EXISTS usage_analytics (
                    id SERIAL PRIMARY KEY,
                    resource_type VARCHAR(50),
                    resource_id VARCHAR(64),
                    operation VARCHAR(50),
                    user_id VARCHAR(100),
                    timestamp TIMESTAMP DEFAULT NOW(),
                    response_time_ms INTEGER,
                    metadata JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_analytics_timestamp ON usage_analytics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_analytics_resource ON usage_analytics(resource_id);

                -- Archive support
                ALTER TABLE fhir_resources ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_archived ON fhir_resources(archived);

                -- Source / provenance
                ALTER TABLE fhir_resources ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'internal';
                CREATE INDEX IF NOT EXISTS idx_source ON fhir_resources(source);

                -- Audit log
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    resource_id VARCHAR(64) NOT NULL,
                    resource_type VARCHAR(50) NOT NULL,
                    action VARCHAR(20) NOT NULL,
                    actor VARCHAR(100),
                    timestamp TIMESTAMP DEFAULT NOW(),
                    summary TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_id);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

                -- PHIN VADS sync history
                CREATE TABLE IF NOT EXISTS sync_log (
                    id             SERIAL PRIMARY KEY,
                    source         TEXT NOT NULL DEFAULT 'phinvads',
                    resource_type  TEXT NOT NULL DEFAULT 'all',
                    started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at   TIMESTAMPTZ,
                    status         TEXT NOT NULL DEFAULT 'running',
                    new_count      INT DEFAULT 0,
                    skipped_count  INT DEFAULT 0,
                    error_count    INT DEFAULT 0,
                    output_tail    TEXT,
                    triggered_by   TEXT DEFAULT 'ui',
                    dry_run        BOOLEAN DEFAULT FALSE
                );
                ALTER TABLE sync_log ADD COLUMN IF NOT EXISTS dry_run BOOLEAN DEFAULT FALSE;
            """)

    def _extract_source(self, data: Dict[str, Any]) -> str:
        for ext in data.get('extension', []):
            if ext.get('url') == 'http://phts.local/StructureDefinition/source':
                return ext.get('valueCode', 'internal')
        return 'internal'

    async def create_resource(self, resource_type: str, data: Dict[str, Any], user: str = "system") -> str:
        resource_id = data.get('id', str(uuid.uuid4()))
        data['id'] = resource_id
        source = self._extract_source(data)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO fhir_resources (id, resource_type, url, version, status, name, title, data, source, created_by, updated_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """, resource_id, resource_type, data.get('url'), data.get('version'),
                data.get('status'), data.get('name'), data.get('title'),
                json.dumps(data), source, user, user)

            await conn.execute("""
                INSERT INTO resource_versions (resource_id, version_number, data, created_by)
                VALUES ($1, 1, $2, $3)
            """, resource_id, json.dumps(data), user)

            await conn.execute("""
                INSERT INTO audit_log (resource_id, resource_type, action, actor, summary)
                VALUES ($1, $2, 'create', $3, $4)
            """, resource_id, resource_type, user, f"Created {resource_type}/{resource_id}")

        return resource_id

    async def update_resource(self, resource_id: str, data: Dict[str, Any], user: str = "system") -> bool:
        async with self.pool.acquire() as conn:
            version_row = await conn.fetchrow("""
                SELECT MAX(version_number) as max_version FROM resource_versions WHERE resource_id = $1
            """, resource_id)

            next_version = (version_row['max_version'] or 0) + 1

            source = self._extract_source(data)
            result = await conn.execute("""
                UPDATE fhir_resources
                SET data = $1, url = $2, version = $3, status = $4, name = $5,
                    title = $6, source = $7, updated_at = NOW(), updated_by = $8
                WHERE id = $9
            """, json.dumps(data), data.get('url'), data.get('version'),
                data.get('status'), data.get('name'), data.get('title'),
                source, user, resource_id)

            await conn.execute("""
                INSERT INTO resource_versions (resource_id, version_number, data, created_by)
                VALUES ($1, $2, $3, $4)
            """, resource_id, next_version, json.dumps(data), user)

            await conn.execute("""
                INSERT INTO audit_log (resource_id, resource_type, action, actor, summary)
                VALUES ($1, $2, 'update', $3, $4)
            """, resource_id, data.get('resourceType', 'Unknown'), user, f"Updated to version {next_version}")

            # asyncpg returns a status string like "UPDATE 1"; parse row count to be robust
            affected = int(result.split()[-1]) if result and result.split() else 0
            return affected > 0

    async def delete_resource(self, resource_id: str, user: str = "system") -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT resource_type FROM fhir_resources WHERE id = $1", resource_id)
            resource_type = row['resource_type'] if row else 'Unknown'
            await conn.execute("""
                INSERT INTO audit_log (resource_id, resource_type, action, actor, summary)
                VALUES ($1, $2, 'delete', $3, $4)
            """, resource_id, resource_type, user, f"Permanently deleted {resource_type}/{resource_id}")
            await conn.execute("DELETE FROM resource_versions WHERE resource_id = $1", resource_id)
            result = await conn.execute("DELETE FROM fhir_resources WHERE id = $1", resource_id)
            affected = int(result.split()[-1]) if result and result.split() else 0
            return affected > 0

    async def archive_resource(self, resource_id: str, archived: bool = True, user: str = "system") -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT resource_type FROM fhir_resources WHERE id = $1", resource_id)
            if not row:
                return False
            resource_type = row['resource_type']
            result = await conn.execute(
                "UPDATE fhir_resources SET archived = $1, updated_at = NOW(), updated_by = $2 WHERE id = $3",
                archived, user, resource_id
            )
            action = 'archive' if archived else 'unarchive'
            label = 'Archived' if archived else 'Restored'
            await conn.execute("""
                INSERT INTO audit_log (resource_id, resource_type, action, actor, summary)
                VALUES ($1, $2, $3, $4, $5)
            """, resource_id, resource_type, action, user, f"{label} {resource_type}/{resource_id}")
            affected = int(result.split()[-1]) if result and result.split() else 0
            return affected > 0

    async def get_audit_log(self, resource_id: str) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, resource_id, resource_type, action, actor, timestamp, summary
                FROM audit_log WHERE resource_id = $1 ORDER BY timestamp DESC
            """, resource_id)
            return [{
                'id': row['id'],
                'resourceId': row['resource_id'],
                'resourceType': row['resource_type'],
                'action': row['action'],
                'actor': row['actor'],
                'timestamp': row['timestamp'].isoformat(),
                'summary': row['summary'],
            } for row in rows]

    async def get_resource(self, resource_id: str, version: Optional[int] = None) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            if version:
                row = await conn.fetchrow("""
                    SELECT data FROM resource_versions WHERE resource_id = $1 AND version_number = $2
                """, resource_id, version)
            else:
                row = await conn.fetchrow("SELECT data FROM fhir_resources WHERE id = $1", resource_id)

            return json.loads(row['data']) if row else None

    async def search_resources(self, resource_type: str, params: Dict[str, Any], summary: bool = False, archived_only: bool = False) -> List[Dict]:
        archived_condition = "archived = TRUE" if archived_only else "archived = FALSE"
        conditions = ["resource_type = $1", archived_condition]
        values = [resource_type]
        param_idx = 2

        if 'name' in params:
            conditions.append(f"name ILIKE ${param_idx}")
            values.append(f"%{params['name']}%")
            param_idx += 1

        if 'status' in params:
            conditions.append(f"status = ${param_idx}")
            values.append(params['status'])
            param_idx += 1

        if 'url' in params:
            conditions.append(f"url = ${param_idx}")
            values.append(params['url'])
            param_idx += 1

        if 'identifier' in params:
            # Normalise to bare OID so we can match both storage forms:
            # some importers store "urn:oid:{oid}", others store the bare OID.
            ident_val = params['identifier']
            if ident_val.startswith('urn:oid:'):
                ident_val = ident_val[len('urn:oid:'):]
            conditions.append(f"""
                EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(data->'identifier', '[]'::jsonb)) AS ident
                    WHERE ident->>'value' = ${param_idx}
                       OR ident->>'value' = 'urn:oid:' || ${param_idx}
                )
            """)
            values.append(ident_val)
            param_idx += 1

        if 'content' in params:
            conditions.append(f"data->>'content' = ${param_idx}")
            values.append(params['content'])
            param_idx += 1

        if 'context-value-code' in params:
            # Match any useContext entry whose valueCodeableConcept.coding[].code matches
            conditions.append(f"""
                EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(data->'useContext', '[]'::jsonb)) AS uc,
                         jsonb_array_elements(COALESCE(uc->'valueCodeableConcept'->'coding', '[]'::jsonb)) AS coding
                    WHERE coding->>'code' = ${param_idx}
                )
            """)
            values.append(params['context-value-code'])
            param_idx += 1

        if 'context-type' in params:
            # Match useContext entries whose code.code equals the requested type (e.g. 'focus')
            conditions.append(f"""
                EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(data->'useContext', '[]'::jsonb)) AS uc
                    WHERE uc->'code'->>'code' = ${param_idx}
                )
            """)
            values.append(params['context-type'])
            param_idx += 1

        if 'source' in params:
            # Filter by the phts.local/source extension (phinvads | hl7 | hl7v2 | vsac | icd9cm | phts)
            source_val = params['source']
            if source_val == 'phts':
                # 'phts' means internally created — no source extension, or extension value is 'internal'
                conditions.append(f"""
                    (
                        NOT EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements(COALESCE(data->'extension', '[]'::jsonb)) AS ext
                            WHERE ext->>'url' = 'http://phts.local/StructureDefinition/source'
                        )
                        OR EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements(COALESCE(data->'extension', '[]'::jsonb)) AS ext
                            WHERE ext->>'url' = 'http://phts.local/StructureDefinition/source'
                              AND ext->>'valueCode' = 'internal'
                        )
                    )
                """)
            else:
                conditions.append(f"""
                    EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(COALESCE(data->'extension', '[]'::jsonb)) AS ext
                        WHERE ext->>'url' = 'http://phts.local/StructureDefinition/source'
                          AND ext->>'valueCode' = ${param_idx}
                    )
                """)
                values.append(source_val)
                param_idx += 1

        if summary:
            # Return metadata only — strips concept/compose arrays for fast list queries.
            # ~10-50x less data transferred for CodeSystems/ValueSets with large concept lists.
            select_expr = """jsonb_build_object(
                'id', id,
                'resourceType', resource_type,
                'url', url,
                'name', name,
                'status', status,
                'title', data->>'title',
                'version', data->>'version',
                'description', data->>'description',
                'content', data->>'content',
                'publisher', data->>'publisher',
                'date', data->>'date',
                'identifier', data->'identifier',
                'extension', data->'extension',
                'useContext', data->'useContext',
                '_conceptCount', CASE
                    WHEN resource_type = 'CodeSystem' THEN
                        jsonb_array_length(COALESCE(data->'concept', '[]'::jsonb))
                    WHEN resource_type = 'ValueSet' THEN
                        COALESCE((
                            SELECT SUM(jsonb_array_length(inc->'concept'))
                            FROM jsonb_array_elements(COALESCE(data#>'{compose,include}', '[]'::jsonb)) AS inc
                            WHERE jsonb_typeof(inc->'concept') = 'array'
                        ), 0)::int
                    ELSE 0
                END
            )"""
        else:
            select_expr = "data"

        query = f"SELECT {select_expr} AS data FROM fhir_resources WHERE {' AND '.join(conditions)} ORDER BY updated_at DESC LIMIT 5000"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *values)
            return [json.loads(row['data']) for row in rows]

    async def get_version_history(self, resource_id: str) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT version_number, data, created_at, created_by, change_summary
                FROM resource_versions WHERE resource_id = $1 ORDER BY version_number DESC
            """, resource_id)

            return [{
                'version': row['version_number'],
                'data': json.loads(row['data']),
                'timestamp': row['created_at'].isoformat(),
                'author': row['created_by'],
                'summary': row['change_summary']
            } for row in rows]


# ============================================================================
# Search Engine (Elasticsearch)
# ============================================================================

class SearchEngine:
    def __init__(self, hosts: List[str]):
        self.es: Optional[AsyncElasticsearch] = None
        self.hosts = hosts

    async def connect(self):
        self.es = AsyncElasticsearch(self.hosts)
        await self._initialize_indices()

    async def disconnect(self):
        if self.es:
            await self.es.close()

    async def _initialize_indices(self):
        index_settings = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "medical_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "snowball", "asciifolding"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "resourceType": {"type": "keyword"},
                    "id": {"type": "keyword"},
                    "name": {"type": "text", "analyzer": "medical_analyzer"},
                    "title": {"type": "text", "analyzer": "medical_analyzer"},
                    "description": {"type": "text", "analyzer": "medical_analyzer"},
                    "status": {"type": "keyword"},
                    "concepts": {
                        "type": "nested",
                        "properties": {
                            "code": {"type": "keyword"},
                            "display": {"type": "text", "analyzer": "medical_analyzer"}
                        }
                    }
                }
            }
        }

        if not await self.es.indices.exists(index="fhir_resources"):
            await self.es.indices.create(index="fhir_resources", body=index_settings)

    async def index_resource(self, resource: Dict[str, Any]):
        doc = {
            "resourceType": resource.get("resourceType"),
            "id": resource.get("id"),
            "name": resource.get("name"),
            "title": resource.get("title"),
            "description": resource.get("description"),
            "status": resource.get("status"),
            "concepts": self._extract_concepts(resource)
        }
        await self.es.index(index="fhir_resources", id=resource.get("id"), document=doc)

    async def delete_resource(self, resource_id: str):
        try:
            await self.es.delete(index="fhir_resources", id=resource_id)
        except Exception:
            pass  # Not indexed or already removed — not an error

    def _extract_concepts(self, resource: Dict) -> List[Dict]:
        concepts = []
        if resource.get("resourceType") == "ValueSet":
            for include in resource.get("compose", {}).get("include", []):
                for concept in include.get("concept", []):
                    concepts.append({"code": concept.get("code"), "display": concept.get("display")})
        elif resource.get("resourceType") == "CodeSystem":
            for concept in resource.get("concept", []):
                concepts.append({"code": concept.get("code"), "display": concept.get("display")})
        return concepts

    async def search(self, query: str, resource_type: Optional[str] = None) -> List[Dict]:
        must_clauses = [{
            "multi_match": {
                "query": query,
                "fields": ["name^3", "title^2", "description", "concepts.display"],
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        }]

        if resource_type:
            must_clauses.append({"term": {"resourceType": resource_type}})

        result = await self.es.search(
            index="fhir_resources",
            body={"query": {"bool": {"must": must_clauses}}, "size": 50}
        )
        return [hit["_source"] for hit in result["hits"]["hits"]]


# ============================================================================
# Cache Layer (Redis)
# ============================================================================

class CacheManager:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None

    async def connect(self):
        self.redis_client = await redis.from_url(self.redis_url)

    async def disconnect(self):
        if self.redis_client:
            await self.redis_client.close()

    async def get(self, key: str) -> Optional[Dict]:
        value = await self.redis_client.get(key)
        return json.loads(value) if value else None

    async def set(self, key: str, value: Dict, ttl: int = 3600):
        await self.redis_client.setex(key, ttl, json.dumps(value))

    async def delete(self, key: str):
        await self.redis_client.delete(key)

    async def invalidate_pattern(self, pattern: str):
        keys = await self.redis_client.keys(pattern)
        if keys:
            await self.redis_client.delete(*keys)


# ============================================================================
# Main Application
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL", "postgresql://phts:phts_dev_password@postgres:5432/phts")
    elasticsearch_hosts = os.getenv("ELASTICSEARCH_HOSTS", "http://elasticsearch:9200").split(",")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")

    logger.info("Starting PH-TS FHIR Terminology Server...")

    state.db = DatabaseManager(database_url)
    await state.db.connect()
    logger.info("PostgreSQL connected")

    state.search_engine = SearchEngine(elasticsearch_hosts)
    await state.search_engine.connect()
    logger.info("Elasticsearch connected")

    state.cache = CacheManager(redis_url)
    await state.cache.connect()
    logger.info("Redis connected")

    logger.info("All services initialized")
    yield

    logger.info("Shutting down...")
    if state.db:
        await state.db.disconnect()
    if state.search_engine:
        await state.search_engine.disconnect()
    if state.cache:
        await state.cache.disconnect()


app = FastAPI(
    title="PH-TS - Public Health Terminology Service",
    description="High-performance FHIR R4 terminology server for public health",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost", "http://localhost:3000", "http://localhost:5173"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fhir_operations_router)
app.include_router(sdo_router)
app.include_router(ai_router)

from app.routes.admin import router as admin_router  # noqa: E402
app.include_router(admin_router)

from app.routes.mcp_chat import router as mcp_chat_router  # noqa: E402
app.include_router(mcp_chat_router)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    REQUEST_DURATION.labels(method=request.method, endpoint=request.url.path).observe(duration)
    response.headers["X-Process-Time"] = str(round(duration, 4))
    logger.info(f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s")
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "processing", "diagnostics": exc.detail}]
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "fatal", "code": "exception", "diagnostics": "An internal server error occurred"}]
        }
    )


@app.get("/")
async def root():
    return {
        "name": "PH-TS - Public Health Terminology Service",
        "version": "1.0.0",
        "status": "operational",
        "fhirVersion": "4.0.1",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    status = {"status": "healthy", "services": {}}
    try:
        if not state.db or not state.db.pool:
            raise RuntimeError("Database not initialised")
        async with state.db.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        status["services"]["database"] = "healthy"
    except Exception as e:
        status["services"]["database"] = f"unhealthy: {e}"
        status["status"] = "degraded"
    try:
        if not state.search_engine or not state.search_engine.es:
            raise RuntimeError("Search engine not initialised")
        await state.search_engine.es.cluster.health()
        status["services"]["search"] = "healthy"
    except Exception as e:
        status["services"]["search"] = f"unhealthy: {e}"
        status["status"] = "degraded"
    try:
        if not state.cache or not state.cache.redis_client:
            raise RuntimeError("Cache not initialised")
        await state.cache.redis_client.ping()
        status["services"]["cache"] = "healthy"
    except Exception as e:
        status["services"]["cache"] = f"unhealthy: {e}"
        status["status"] = "degraded"
    return status


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/analytics/summary")
async def analytics_summary():
    async with state.db.pool.acquire() as conn:
        vs_count = await conn.fetchval("SELECT COUNT(*) FROM fhir_resources WHERE resource_type = 'ValueSet' AND archived = FALSE")
        cs_count = await conn.fetchval("SELECT COUNT(*) FROM fhir_resources WHERE resource_type = 'CodeSystem' AND archived = FALSE")
        archived_count = await conn.fetchval("SELECT COUNT(*) FROM fhir_resources WHERE archived = TRUE")
        version_count = await conn.fetchval("SELECT COUNT(*) FROM resource_versions")
    return {
        "total_valuesets": vs_count or 0,
        "total_codesystems": cs_count or 0,
        "archived_resources": archived_count or 0,
        "total_versions": version_count or 0,
    }


@app.get("/metadata")
async def capability_statement():
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "date": datetime.now().isoformat(),
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "format": ["json"],
        "rest": [{
            "mode": "server",
            "resource": [
                {
                    "type": "ValueSet",
                    "interaction": [
                        {"code": "read"}, {"code": "create"},
                        {"code": "update"}, {"code": "search-type"}
                    ],
                    "searchParam": [
                        {"name": "name", "type": "string"},
                        {"name": "url", "type": "uri"},
                        {"name": "status", "type": "token"}
                    ]
                },
                {
                    "type": "CodeSystem",
                    "interaction": [
                        {"code": "read"}, {"code": "create"},
                        {"code": "update"}, {"code": "search-type"}
                    ]
                }
            ]
        }]
    }


# ============================================================================
# ValueSet Endpoints
# ============================================================================

@app.post("/ValueSet", status_code=201)
async def create_value_set(value_set: ValueSet):
    data = value_set.model_dump(exclude_none=True)
    resource_id = await state.db.create_resource("ValueSet", data)
    await state.search_engine.index_resource(data)
    await state.cache.invalidate_pattern("ValueSet:*")
    RESOURCE_COUNT.labels(resource_type="ValueSet", operation="create").inc()
    resource = await state.db.get_resource(resource_id)
    return JSONResponse(content=resource, status_code=201)


@app.get("/ValueSet/{resource_id}")
async def get_value_set(resource_id: str, version: Optional[int] = None):
    cache_key = f"ValueSet:{resource_id}:{version or 'latest'}"
    cached = await state.cache.get(cache_key)
    if cached:
        return cached

    resource = await state.db.get_resource(resource_id, version)
    if not resource:
        raise HTTPException(status_code=404, detail=f"ValueSet/{resource_id} not found")

    await state.cache.set(cache_key, resource)
    return resource


@app.put("/ValueSet/{resource_id}")
async def update_value_set(resource_id: str, value_set: ValueSet):
    existing = await state.db.get_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"ValueSet/{resource_id} not found")

    data = value_set.model_dump(exclude_none=True)
    data['id'] = resource_id
    await state.db.update_resource(resource_id, data)
    await state.search_engine.index_resource(data)
    await state.cache.invalidate_pattern(f"ValueSet:{resource_id}:*")
    RESOURCE_COUNT.labels(resource_type="ValueSet", operation="update").inc()
    return await state.db.get_resource(resource_id)


@app.delete("/ValueSet/{resource_id}", status_code=204)
async def delete_value_set(resource_id: str):
    existing = await state.db.get_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"ValueSet/{resource_id} not found")
    await state.db.delete_resource(resource_id)
    await state.search_engine.delete_resource(resource_id)
    await state.cache.invalidate_pattern(f"ValueSet:{resource_id}:*")
    await state.cache.invalidate_pattern("ValueSet:*")


@app.get("/ValueSet")
async def search_value_sets(
    name: Optional[str] = Query(None),
    url: Optional[str] = Query(None),
    identifier: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    context_value_code: Optional[str] = Query(None, alias="context-value-code"),
    context_type: Optional[str] = Query(None, alias="context-type"),
    source: Optional[str] = Query(None, description="Filter by import source: phinvads | hl7 | hl7v2 | vsac | icd9cm | phts"),
    _archived: bool = Query(False, alias="_archived", description="Return archived resources instead of active ones"),
    _summary: bool = Query(False, alias="_summary"),
):
    if q:
        results = await state.search_engine.search(q, "ValueSet")
        return {"resourceType": "Bundle", "type": "searchset", "total": len(results), "entry": [{"resource": r} for r in results]}

    params = {}
    if name:
        params['name'] = name
    if url:
        params['url'] = url
    if identifier:
        params['identifier'] = identifier
    if status:
        params['status'] = status
    if context_value_code:
        params['context-value-code'] = context_value_code
    if context_type:
        params['context-type'] = context_type
    if source:
        params['source'] = source

    # Archived queries are not cached (small volume, infrequent access)
    if _archived:
        results = await state.db.search_resources("ValueSet", params, summary=_summary, archived_only=True)
        return {"resourceType": "Bundle", "type": "searchset", "total": len(results), "entry": [{"resource": r} for r in results]}

    # Cache list results — key includes all filter params so different searches cache independently.
    # Invalidated automatically by invalidate_pattern("ValueSet:*") on create/update/delete/archive.
    cache_key = f"ValueSet:list:{name or ''}:{url or ''}:{identifier or ''}:{status or ''}:{context_value_code or ''}:{source or ''}:{_summary}"
    cached = await state.cache.get(cache_key)
    if cached:
        return cached

    results = await state.db.search_resources("ValueSet", params, summary=_summary)
    bundle = {"resourceType": "Bundle", "type": "searchset", "total": len(results), "entry": [{"resource": r} for r in results]}
    await state.cache.set(cache_key, bundle, ttl=120)
    return bundle


@app.get("/ValueSet/{resource_id}/_history")
async def get_value_set_history(resource_id: str):
    history = await state.db.get_version_history(resource_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"ValueSet/{resource_id} not found")
    return {"resourceType": "Bundle", "type": "history", "total": len(history), "entry": history}


@app.patch("/ValueSet/{resource_id}/$archive", status_code=200)
async def archive_value_set(resource_id: str, restore: bool = Query(False)):
    existing = await state.db.get_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"ValueSet/{resource_id} not found")
    archived = not restore
    success = await state.db.archive_resource(resource_id, archived=archived)
    if not success:
        raise HTTPException(status_code=500, detail="Archive operation failed")
    await state.cache.invalidate_pattern(f"ValueSet:{resource_id}:*")
    await state.cache.invalidate_pattern("ValueSet:*")
    return {"resourceId": resource_id, "archived": archived}


@app.get("/ValueSet/{resource_id}/$audit")
async def get_value_set_audit(resource_id: str):
    existing = await state.db.get_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"ValueSet/{resource_id} not found")
    entries = await state.db.get_audit_log(resource_id)
    return {"resourceId": resource_id, "total": len(entries), "entries": entries}


# ============================================================================
# CodeSystem Endpoints
# ============================================================================

@app.post("/CodeSystem", status_code=201)
async def create_code_system(code_system: CodeSystem):
    data = code_system.model_dump(exclude_none=True)
    resource_id = await state.db.create_resource("CodeSystem", data)
    await state.search_engine.index_resource(data)
    await state.cache.invalidate_pattern("CodeSystem:*")
    RESOURCE_COUNT.labels(resource_type="CodeSystem", operation="create").inc()
    resource = await state.db.get_resource(resource_id)
    return JSONResponse(content=resource, status_code=201)


@app.get("/CodeSystem/{resource_id}")
async def get_code_system(resource_id: str, version: Optional[int] = None):
    cache_key = f"CodeSystem:{resource_id}:{version or 'latest'}"
    cached = await state.cache.get(cache_key)
    if cached:
        return cached

    resource = await state.db.get_resource(resource_id, version)
    if not resource:
        raise HTTPException(status_code=404, detail=f"CodeSystem/{resource_id} not found")

    await state.cache.set(cache_key, resource)
    return resource


@app.put("/CodeSystem/{resource_id}")
async def update_code_system(resource_id: str, code_system: CodeSystem):
    existing = await state.db.get_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"CodeSystem/{resource_id} not found")

    data = code_system.model_dump(exclude_none=True)
    data['id'] = resource_id
    await state.db.update_resource(resource_id, data)
    await state.search_engine.index_resource(data)
    await state.cache.invalidate_pattern(f"CodeSystem:{resource_id}:*")
    RESOURCE_COUNT.labels(resource_type="CodeSystem", operation="update").inc()
    return await state.db.get_resource(resource_id)


@app.get("/CodeSystem")
async def search_code_systems(
    name: Optional[str] = Query(None),
    url: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    content: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    _summary: bool = Query(False, alias="_summary"),
):
    if q:
        results = await state.search_engine.search(q, "CodeSystem")
        return {"resourceType": "Bundle", "type": "searchset", "total": len(results), "entry": [{"resource": r} for r in results]}

    params = {}
    if name:
        params['name'] = name
    if url:
        params['url'] = url
    if status:
        params['status'] = status
    if content:
        params['content'] = content

    cache_key = f"CodeSystem:list:{name or ''}:{url or ''}:{status or ''}:{content or ''}:{_summary}"
    cached = await state.cache.get(cache_key)
    if cached:
        return cached

    results = await state.db.search_resources("CodeSystem", params, summary=_summary)
    bundle = {"resourceType": "Bundle", "type": "searchset", "total": len(results), "entry": [{"resource": r} for r in results]}
    await state.cache.set(cache_key, bundle, ttl=120)
    return bundle


@app.get("/CodeSystem/{resource_id}/_history")
async def get_code_system_history(resource_id: str):
    history = await state.db.get_version_history(resource_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"CodeSystem/{resource_id} not found")
    return {"resourceType": "Bundle", "type": "history", "total": len(history), "entry": history}


# ============================================================================
# ConceptMap Endpoints
# ============================================================================

@app.post("/ConceptMap", status_code=201)
async def create_concept_map(concept_map: ConceptMap):
    data = concept_map.model_dump(exclude_none=True)
    resource_id = await state.db.create_resource("ConceptMap", data)
    await state.search_engine.index_resource(data)
    await state.cache.invalidate_pattern("ConceptMap:*")
    RESOURCE_COUNT.labels(resource_type="ConceptMap", operation="create").inc()
    resource = await state.db.get_resource(resource_id)
    return JSONResponse(content=resource, status_code=201)


@app.get("/ConceptMap/{resource_id}")
async def get_concept_map(resource_id: str, version: Optional[int] = None):
    cache_key = f"ConceptMap:{resource_id}:{version or 'latest'}"
    cached = await state.cache.get(cache_key)
    if cached:
        return cached

    resource = await state.db.get_resource(resource_id, version)
    if not resource:
        raise HTTPException(status_code=404, detail=f"ConceptMap/{resource_id} not found")

    await state.cache.set(cache_key, resource)
    return resource


@app.put("/ConceptMap/{resource_id}")
async def update_concept_map(resource_id: str, concept_map: ConceptMap):
    existing = await state.db.get_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"ConceptMap/{resource_id} not found")

    data = concept_map.model_dump(exclude_none=True)
    data['id'] = resource_id
    await state.db.update_resource(resource_id, data)
    await state.search_engine.index_resource(data)
    await state.cache.invalidate_pattern(f"ConceptMap:{resource_id}:*")
    RESOURCE_COUNT.labels(resource_type="ConceptMap", operation="update").inc()
    return await state.db.get_resource(resource_id)


@app.delete("/ConceptMap/{resource_id}", status_code=204)
async def delete_concept_map(resource_id: str):
    existing = await state.db.get_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"ConceptMap/{resource_id} not found")
    await state.db.delete_resource(resource_id)
    await state.search_engine.delete_resource(resource_id)
    await state.cache.invalidate_pattern(f"ConceptMap:{resource_id}:*")
    await state.cache.invalidate_pattern("ConceptMap:*")


@app.get("/ConceptMap")
async def search_concept_maps(
    name: Optional[str] = Query(None),
    url: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None)
):
    if q:
        results = await state.search_engine.search(q, "ConceptMap")
        return {"resourceType": "Bundle", "type": "searchset", "total": len(results), "entry": [{"resource": r} for r in results]}

    params = {}
    if name:
        params['name'] = name
    if url:
        params['url'] = url
    if status:
        params['status'] = status

    results = await state.db.search_resources("ConceptMap", params)
    return {"resourceType": "Bundle", "type": "searchset", "total": len(results), "entry": [{"resource": r} for r in results]}


@app.get("/ConceptMap/{resource_id}/_history")
async def get_concept_map_history(resource_id: str):
    history = await state.db.get_version_history(resource_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"ConceptMap/{resource_id} not found")
    return {"resourceType": "Bundle", "type": "history", "total": len(history), "entry": history}
