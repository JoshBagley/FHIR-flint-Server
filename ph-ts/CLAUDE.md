# CLAUDE.md — PH-TS FHIR Terminology Server

This file provides context and working conventions for Claude Code when operating in this repository.

---

## Project Overview

**PH-TS** (Public Health Terminology Service) is a FHIR R4 terminology server built for public health vocabulary management. It allows vocabulary SMEs to search, browse, create, and manage value sets backed by standard development organization (SDO) code systems.

**Stack:** FastAPI · PostgreSQL · Elasticsearch · Redis · React/Vite · Nginx · Prometheus · Grafana · Loki · Promtail · Docker Compose

---

## FHIR Server Architecture

**PH-TS is a fully custom-built FHIR R4 server — not HAPI FHIR, not Ontoserver, not any Java-based framework.** It is modeled conceptually after Ontoserver but implemented from scratch in Python.

### What it is NOT
- Not HAPI FHIR (Java)
- Not Ontoserver (commercial)
- Does not use any FHIR library (e.g. `fhir.resources`) — all FHIR models are hand-rolled Pydantic classes

### Layers

**Framework:** FastAPI (uvicorn ASGI). GZip + CORS middleware. Prometheus metrics middleware on every request. All error responses return `OperationOutcome` JSON (never raw HTTP errors).

**FHIR models** — hand-rolled Pydantic, defined in `main.py`:
- `ValueSet`, `CodeSystem`, `ConceptMap` — full R4 shapes
- `Coding`, `CodeableConcept`, `Identifier`, `Meta`, `Narrative`, `ContactDetail`
- `Literal[]` types enforce enums (`content`, `equivalence`, `status`, etc.)

**Storage — three tiers:**

| Layer | Technology | Purpose |
|---|---|---|
| Primary store | PostgreSQL (asyncpg) | FHIR resources as JSONB; version snapshots; audit log; concept mappings; usage analytics |
| Search index | Elasticsearch | Fast full-text + concept search (1.6M docs; nested object limit raised to 50k) |
| Cache | Redis | 120s TTL on list results; LRU eviction; AOF persistence |

**Database Manager** (`main.py:DatabaseManager`):
- `asyncpg` pool (min 10 / max 50 connections)
- Schema self-initializes on startup (`_initialize_schema()`) — idempotent DDL
- Every write atomically goes to `fhir_resources` + `resource_versions` (snapshot) + `audit_log`
- `_extract_source()` reads `http://phts.local/StructureDefinition/source` extension for provenance

**Route modules — three routers:**

| Module | Handles |
|---|---|
| `main.py` (inline) | CRUD + search + history + archive + audit for ValueSet / CodeSystem / ConceptMap |
| `routes/fhir_operations.py` | All FHIR operations: `$expand`, `$validate-code`, `$lookup`, `$translate`, `$subsumes`, `$validate-batch`, `$diff`, `$views`, `$tag-view`, `$stats` |
| `routes/sdo_search.py` | Live SDO connector search (`/sdo/*`), SNOMED hierarchy tree |
| `routes/ai_assist.py` | AI endpoints (`/ai/*`): suggest, describe, map, map-save, provider |

**FHIR Operations implemented:**

| Operation | Endpoint |
|---|---|
| Expand | `GET/POST /ValueSet/$expand` |
| Validate code | `GET/POST /ValueSet/$validate-code` |
| Batch validate | `POST /ValueSet/$validate-batch` (up to 200 codes, concurrent) |
| Lookup | `GET/POST /CodeSystem/$lookup` |
| Translate | `GET/POST /ConceptMap/$translate` |
| Subsumes | `GET /CodeSystem/$subsumes` |
| Version diff | `GET /ValueSet/{id}/$diff` |
| Capability statement | `GET /metadata` |

**Storage tier decision logic** (in `fhir_operations.py`):
`$expand` and `$lookup` check `CodeSystem.content` before sourcing concepts:
1. `content = "complete"` + local concepts exist → serve from Postgres (fast, offline)
2. `content = "not-present"` or `"fragment"` with sparse local data → delegate to SDO connector
3. No local CodeSystem record at all → also delegate externally

`_SYSTEM_URL_TO_SDO` maps canonical FHIR URLs **and** OID aliases to connector IDs so PHIN VADS resources using `urn:oid:` notation route correctly.

---

## Running Services & Ports

| Service | URL | Notes |
|---|---|---|
| Web UI (Nginx) | http://localhost | Reverse proxy entry point |
| Frontend (Vite dev) | http://localhost:5173 | Direct Vite HMR server |
| Backend API | http://localhost:8000 | FastAPI; also at `/` via Nginx |
| API Docs (Swagger) | http://localhost:8000/docs | Auto-generated OpenAPI |
| PostgreSQL | localhost:5432 | DB: `phts`, User: `phts` |
| Elasticsearch | http://localhost:9200 | |
| Redis | localhost:6379 | |
| Grafana | http://localhost:3001 | Metrics + log dashboards (admin/admin) |
| Prometheus | http://localhost:9090 | Metrics scraper |
| Loki | http://localhost:3100 | Log aggregation API |
| Adminer (DB UI) | http://localhost:8181 | Lightweight PostgreSQL browser |
| Kibana | http://localhost:5601 | Elasticsearch browser |

---

## Key Environment Variables (`.env`)

```
AI_PROVIDER=gemini          # anthropic | openai | gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-6
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o
UMLS_API_KEY=               # For VSAC/NLM access
LOINC_USERNAME=             # Legacy — LOINC now uses NLM ClinicalTables (no auth)
LOINC_PASSWORD=             # Legacy
```

After changing `.env`, restart the backend: `docker compose up -d backend`

---

## Project Structure

```
ph-ts/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, router registration, search_resources()
│   │   ├── disease_views.json       # Condition/disease view definitions (13 PH views)
│   │   ├── routes/
│   │   │   ├── fhir_operations.py   # FHIR R4 ops + $views/$tag-view disease view endpoints
│   │   │   ├── sdo_search.py        # GET /sdo/systems, /sdo/search, /sdo/lookup, /sdo/snomed/children/{id}
│   │   │   └── ai_assist.py         # POST /ai/suggest, /ai/describe, /ai/map, /ai/map-save, GET /ai/provider
│   │   └── services/
│   │       └── external_cs.py       # SDO connector (SNOMED, ICD-10-CM, LOINC, RxNorm, VSAC)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  # Main app shell; disease view filter in ValueSet browser
│   │   └── ValueSetBuilder.tsx      # 3-panel value set creation page
│   └── vite.config.ts               # Contains usePolling:true for Windows Docker HMR
├── infrastructure/
│   └── docker/nginx/nginx.conf      # Reverse proxy; /ai/ block must come before FHIR regex
├── migration/                       # DB migration tooling
├── docs/                            # ARCHITECTURE.md, DEVELOPMENT.md, local_setup_guide.md, etc.
├── docker-compose.yml
└── .env
```

---

## Backend Conventions

- **Router pattern:** All routes use `APIRouter` with a prefix, registered in `main.py` via `app.include_router()`.
- **FHIR error responses:** Return `{"resourceType": "OperationOutcome", ...}` not plain HTTP errors.
- **SDO connectors** in `external_cs.py` use per-request `aiohttp.ClientSession` with `ClientTimeout(total=15)`.
- **AI provider abstraction** in `ai_assist.py`: a single `_complete(prompt)` function dispatches to Anthropic, OpenAI, or Gemini based on `AI_PROVIDER` env var. All three SDKs are installed.
- **AI fan-out pattern:** `POST /ai/suggest` searches SDOs in parallel with `asyncio.gather()` + `asyncio.wait_for(timeout=8.0)` per system, then passes candidates to the AI for ranking.
- **Summary mode:** `search_resources(summary=True)` uses `jsonb_build_object()` to return metadata only (no `concept`/`compose` arrays). Always includes a precomputed `_conceptCount` field so the UI can display accurate counts without fetching full resources. Also includes `extension` and `useContext` fields for provenance and view tags.
- **Redis list caching:** List endpoints (`GET /ValueSet`, `GET /CodeSystem`) cache results for 120 s. Cache key includes all filter params. Invalidated on any write via `invalidate_pattern("ValueSet:*")`.
- **Custom extension pattern:** `http://phts.local/StructureDefinition/source` tracks import provenance (e.g. `phinvads`, `hl7`, `internal`). Same mechanism used for reading disease view tags from `useContext`.

---

## Frontend Conventions

- **Full-page views** use the early-return pattern — no React Router. `App.tsx` checks `builderOpen` then `expansionResource` before the main return.
- `vite.config.ts` is **baked into the Docker image** (not volume-mounted). Any changes to it require: `docker compose up -d --build frontend`
- Only `frontend/src/` is volume-mounted for HMR.

---

## SDO Integrations

| System | API | Auth |
|---|---|---|
| SNOMED CT | Snowstorm public FHIR server | None |
| ICD-10-CM | NLM ClinicalTables API | None |
| LOINC | fhir.loinc.org (FHIR `$expand`/`$lookup`) | Basic auth: `LOINC_USERNAME`/`LOINC_PASSWORD`; falls back to NLM ClinicalTables if credentials absent |
| RxNorm | NLM RxNav REST API | None |
| VSAC | VSAC FHIR (cts.nlm.nih.gov/fhir) | Basic auth: `apikey:<UMLS_API_KEY>` |
| HL7 v2 Tables | tx.fhir.org (fallback when not locally imported) | None |

---

## Code System Storage and Access Strategy

FHIR R4 defines a `CodeSystem.content` field that controls how concepts are stored and how operations behave. PH-TS uses this to handle both small locally-stored code systems and large externally-delegated ones within a single unified API.

### Storage Tiers

| Tier | `content` value | Where concepts live | Used for |
|---|---|---|---|
| **Complete** | `complete` | Fully stored in PostgreSQL | HL7 FHIR core, ICD-9-CM, ICD-10-CM — manageable size, freely available |
| **Stub** | `not-present` | Not stored locally | SNOMED CT, CPT — too large or license-restricted |
| **Fragment** | `fragment` | Partial subset stored | LOINC — store relevant subsets, delegate the rest |

### Fallback / Delegation Logic (`fhir_operations.py`)

`$expand` and `$lookup` check `CodeSystem.content` before deciding where to get concepts:

1. If `content = "complete"` and concepts exist locally → use local concepts (fast, offline-capable)
2. If `content = "not-present"` or `"fragment"` with no/few local concepts → delegate to `external_cs.py` connectors
3. If no local CodeSystem record at all → also delegate to external connectors

The mapping from FHIR system URL to SDO connector ID is in `_SYSTEM_URL_TO_SDO` at the top of `fhir_operations.py`. It includes both canonical URLs and OID aliases so ValueSets imported from PHIN VADS (which use `urn:oid:` notation) route correctly:

```python
# Canonical URLs
"http://snomed.info/sct"                       → "snomed"
"http://loinc.org"                             → "loinc"
"http://hl7.org/fhir/sid/icd-10-cm"           → "icd10cm"
"http://hl7.org/fhir/sid/icd-9-cm"            → "icd9cm"
"http://www.nlm.nih.gov/research/umls/rxnorm" → "rxnorm"
"https://cts.nlm.nih.gov/fhir"                → "vsac"
# OID aliases (PHIN VADS imports)
"urn:oid:2.16.840.1.113883.6.1"               → "loinc"
"urn:oid:2.16.840.1.113883.6.96"              → "snomed"
"urn:oid:2.16.840.1.113883.6.90"              → "icd10cm"
"urn:oid:2.16.840.1.113883.6.103"             → "icd9cm"
"urn:oid:2.16.840.1.113883.6.88"              → "rxnorm"
```

### Registering a Stub Code System

To register SNOMED CT, CPT, or LOINC as a known system without storing concepts:

```bash
curl -X POST http://localhost/CodeSystem \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "CodeSystem",
    "url": "http://snomed.info/sct",
    "name": "SNOMEDCT",
    "title": "SNOMED Clinical Terms",
    "status": "active",
    "content": "not-present",
    "description": "Delegated to Snowstorm public server for $lookup/$expand."
  }'
```

Once registered, `$lookup` and `$expand` calls referencing that system URL will automatically route through the appropriate external connector.

### Code System Import Scripts

| Script | Source | Content | Size |
|---|---|---|---|
| `migration/import_hl7_core.py` | packages.fhir.org (`hl7.fhir.r4.core 4.0.1`) | `complete` | ~981 small systems |
| `migration/import_hl7_v2_tables.py` | packages.fhir.org (`hl7.terminology.r4 5.5.0`) | `complete` | ~200 v2 table CodeSystems |
| `migration/import_icd9cm.py` | NLM ClinicalTables API | `complete` | ~14 k codes |
| `migration/phinvads_migrate.py` | PHIN VADS STU3 API | `complete` / `fragment` | 300 CodeSystems (limited by API pagination) |
| `migration/import_phinvads_txt.py` | PHIN VADS .txt downloads (`docs/PHINVADSValueSets/`) | `complete` | 1,995 of 1,998 ValueSets (3 have malformed metadata) |
| `migration/repair_empty_phinvads_valuesets.py` | PHIN VADS STU3 API (targeted repair) | `complete` | Re-fetches concepts for ValueSets imported with empty `compose.include`; PUTs to existing records by ID; safe to re-run |
| `migration/import_cvx.py` | CDC Excel (`docs/cvx_codes/web_cvx.xlsx`) primary; NLM ClinicalTables fallback (`--source nlm`) | `complete` | 289 CVX vaccine codes; includes status (Active/Inactive/Non-US/Never Active) and nonVaccine boolean properties; upserts (PUT if exists, POST if new) |

```bash
# Import HL7 FHIR R4 core administrative code systems (no license required)
python migration/import_hl7_core.py --target-url http://localhost

# Dry run — lists all resources without importing
python migration/import_hl7_core.py --dry-run

# Import HL7 v2 table CodeSystems (~80-120 MB download; enables offline v2 validation)
python migration/import_hl7_v2_tables.py --target-url http://localhost

# Dry run — lists all v2 tables without importing
python migration/import_hl7_v2_tables.py --dry-run

# Import ICD-9-CM (~14 k codes; takes ~10 min due to NLM rate limiting)
python migration/import_icd9cm.py --target-url http://localhost

# Dry run — writes icd9cm_codesystem.json without importing
python migration/import_icd9cm.py --dry-run

# Import PHIN VADS ValueSets from local .txt downloads (PREFERRED — faster and more complete)
# Place .txt files from PHIN VADS "Download Value Set" in docs/PHINVADSValueSets/
python migration/import_phinvads_txt.py --target-url http://localhost

# Dry run to validate parsing without importing
python migration/import_phinvads_txt.py --dry-run

# Import all PHIN VADS CodeSystems via API (limited by PHIN VADS pagination — most are HL7 v2 tables already imported)
python migration/phinvads_migrate.py --resource codesystem --target-url http://localhost

# Import single PHIN VADS ValueSet by OID via API
python migration/phinvads_migrate.py --oid 2.16.840.1.114222.4.11.1066 --target-url http://localhost

# Import CDC CVX vaccine codes (289 codes from Excel file — recommended)
# Requires: pip install openpyxl httpx
python migration/import_cvx.py --target-url http://localhost

# Dry run — writes cvx_codesystem.json without importing
python migration/import_cvx.py --dry-run

# Fallback to NLM ClinicalTables (fewer codes, no status/notes)
python migration/import_cvx.py --source nlm --target-url http://localhost
```

### Licensing Notes

| System | License | Notes |
|---|---|---|
| HL7 FHIR core | None | Part of the FHIR spec, freely redistributable |
| ICD-9-CM | None | CDC/CMS public domain; retired 2015 |
| ICD-10-CM | None | CDC/CMS public domain; active |
| SNOMED CT | Free affiliate license | Register at snomed.org; use `content: "not-present"` and delegate |
| LOINC | Free account | Register at loinc.org; store as `fragment` or `not-present` |
| RxNorm | None | NLM public domain; delegate via RxNav |
| CPT | AMA paid **or** UMLS (free application) | Never store locally without a license; use `content: "not-present"` + VSAC delegation |
| CVX | None | CDC/HL7 public domain; freely redistributable; `content: "complete"` |

---

## PHIN VADS Migration Tool

**Script:** `migration/phinvads_migrate.py`
**Source API:** `https://phinvads.cdc.gov/baseStu3` — FHIR **STU3** (conversion to R4 is handled by the script)

### WAF / Connectivity Quirks
- The PHIN VADS WAF **blocks** `Accept: application/fhir+json` — use `Accept: application/json, */*`
- The WAF **blocks custom User-Agent** strings — use the default httpx User-Agent
- Direct OID path reads (`GET /ValueSet/{oid}`) may be blocked — use identifier search instead
- Response bodies are large and slow (45–90 s per page); `REQUEST_TIMEOUT = 120` and `RETRY_ATTEMPTS = 5`
- PHIN VADS returns a stale `next` link even after the reported `total` is exhausted — the script stops pagination when `len(fetched) >= total` to avoid hanging requests

### OID Lookup Order (most → least reliable)
1. `GET /ValueSet?identifier={bare-oid}&_format=json`
2. `GET /ValueSet?identifier=urn:oid:{oid}&_format=json`
3. `GET /ValueSet/{oid}?_format=json` (fallback, may fail via WAF)

### STU3 → R4 Conversion Notes

**ValueSet fields mapped:**

| PHIN VADS field | FHIR R4 field | Notes |
|---|---|---|
| Value Set OID | `identifier[0].value` | Provenance link back to PHIN VADS UI |
| Value Set Name | `name` | Machine-readable name |
| Value Set Code / title | `title` | Human-readable title |
| Value Set Definition | `description` | Free-text description |
| Release Comments | `description` (appended) | Appended with `\n\nRelease Notes:` prefix; no native R4 field |
| Value Set Status | `status` | Normalised to `active/draft/retired/unknown` |
| VS Last Updated | `date` | ISO date string |
| Value Set Version | `version` | String version label |
| Publisher | `publisher` | |
| Contact | `contact` | Passed through; STU3/R4 shapes are compatible |
| Extensions | `extension` | All STU3 extensions preserved |
| `purpose` / `copyright` | `purpose` / `copyright` | |
| `useContext` / `jurisdiction` | `useContext` / `jurisdiction` | |

**Concept / compose fields:**

| PHIN VADS field | FHIR R4 field | Notes |
|---|---|---|
| Concept Code | `compose.include.concept[].code` | |
| Concept Name | `compose.include.concept[].display` | |
| Preferred Concept Name | `compose.include.concept[].designation[]` | Preserved if PHIN VADS STU3 API returns `designation` arrays; `designation.use` normalised to a structured `Coding` if STU3 returned a plain string |
| Code System OID | `compose.include.system` | **Normalised** from `urn:oid:X` to canonical FHIR URL (e.g. `urn:oid:2.16.840.1.113883.6.1` → `http://loinc.org`) for 30+ well-known systems; unknown OIDs kept as `urn:oid:X` |
| Code System Version | `compose.include.version` | Passed through |

**Other STU3 → R4 conversion rules:**
- CodeSystem `content` field: valid R4 values are `not-present`, `example`, `fragment`, `complete`, `supplement`
- CodeSystem `hierarchyMeaning` defaults to `is-a` when absent
- `expansion` blocks are structurally identical STU3/R4 — passed through unchanged

### OID → Canonical URL Normalization

`_OID_TO_CANONICAL` in `phinvads_migrate.py` maps 30+ OIDs to canonical FHIR URLs. Key mappings:

| OID | Canonical URL |
|---|---|
| `2.16.840.1.113883.6.1` | `http://loinc.org` |
| `2.16.840.1.113883.6.96` | `http://snomed.info/sct` |
| `2.16.840.1.113883.6.90` | `http://hl7.org/fhir/sid/icd-10-cm` |
| `2.16.840.1.113883.6.103` | `http://hl7.org/fhir/sid/icd-9-cm` |
| `2.16.840.1.113883.6.88` | `http://www.nlm.nih.gov/research/umls/rxnorm` |
| `2.16.840.1.113883.5.1` | `http://terminology.hl7.org/CodeSystem/v3-AdministrativeGender` |
| *(+ 25 more HL7 v3/v2 OIDs)* | `http://terminology.hl7.org/CodeSystem/v3-*` / `v2-*` |

Unknown OIDs are kept as `urn:oid:X` rather than being dropped. The same mapping is mirrored as OID aliases in `_SYSTEM_URL_TO_SDO` in `fhir_operations.py` so `$expand`/`$lookup` routing works even if an OID slips through.

### Duplicate Import Prevention

Before each POST the script calls `GET /{type}?url=X&version=Y` on the target server. If a resource with that URL and version already exists it is **skipped** (counted in `Skipped` in the migration summary). This makes re-runs safe. The database also enforces a partial UNIQUE index:

```sql
CREATE UNIQUE INDEX idx_unique_resource_url_version
ON fhir_resources(resource_type, url, version)
WHERE url IS NOT NULL AND version IS NOT NULL;
```

### Versioning

The database supports storing multiple versions of the same ValueSet (same `url`, different `version`). The `resource_versions` table records every edit as a numbered snapshot. Use the API to retrieve history:

```bash
# Get all versions of a resource
GET /ValueSet/{id}/_history

# Diff two version numbers
GET /ValueSet/{id}/$diff?from_version=1&to_version=2
```

### Usage Examples
```bash
# Full bulk migration (all ValueSets + CodeSystems)
python migration/phinvads_migrate.py --target-url http://localhost

# CodeSystems only
python migration/phinvads_migrate.py --resource codesystem --target-url http://localhost

# ValueSets only
python migration/phinvads_migrate.py --resource valueset --target-url http://localhost

# Single ValueSet by OID
python migration/phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1

# Dry run with JSON output (no POST to server)
python migration/phinvads_migrate.py --dry-run --output-dir ./exported

# Resume from checkpoint after interruption
python migration/phinvads_migrate.py --resume checkpoint.json

# ValueSets only, smaller batches
python migration/phinvads_migrate.py --resource valueset --batch-size 25
```

---

## Multi-Environment Deployment

PH-TS uses Docker Compose file layering + profiles + `.env` files to support dev, demo, and production from a single codebase.

### File structure

| File | Purpose | Auto-loaded? |
|------|---------|-------------|
| `docker-compose.yml` | Base: all service definitions, profiles | Always |
| `docker-compose.override.yml` | Dev: hot-reload, src mounts, direct port exposure | Yes (dev) |
| `docker-compose.prod.yml` | Prod/demo: SSL nginx, 4-worker backend, no dev mounts | Explicit (`-f`) |
| `.env` | Local secrets (gitignored) | Default |
| `.env.demo` / `.env.prod` | Cloud secrets (gitignored) | Explicit (`--env-file`) |
| `.env.*.example` | Committed templates with placeholder values | — |

### Service profiles

| Profile | Services | Activate with |
|---------|---------|--------------|
| *(none)* | postgres, elasticsearch, redis, backend, frontend, nginx | `docker compose up -d` |
| `observability` | + prometheus, grafana, loki, promtail | `--profile observability` |
| `tools` | + adminer | `--profile tools` |
| `admin` | + pgadmin, kibana | `--profile admin` |

### Commands by environment

```bash
# Local dev — core only (auto-loads docker-compose.override.yml)
docker compose up -d

# Local dev — full stack with observability
docker compose --profile observability --profile tools up -d

# Demo — core only
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.demo up -d

# Demo — with observability
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.demo --profile observability up -d

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.prod --profile observability up -d
```

### Cloud deployment checklist

1. Provision VM (AWS t3.large or Azure D2s_v3, 8 GB RAM, 50+ GB disk)
2. Install Docker: `curl https://get.docker.com | sh && sudo usermod -aG docker $USER`
3. Copy repo to VM: `rsync -av --exclude='.env' ph-ts/ user@host:~/ph-ts/`
4. Create secrets file on VM: `cp .env.demo.example .env.demo` and fill in values
5. Provision SSL: `sudo certbot certonly --standalone -d your-domain.com`
6. Edit `infrastructure/docker/nginx/nginx.prod.conf`: replace `YOUR_DOMAIN_HERE`
7. Backup local Postgres and restore on VM:
   ```bash
   # Local
   docker compose exec postgres pg_dump phts -U phts > phts-backup.sql
   # VM
   docker compose up -d postgres
   docker compose exec -T postgres psql phts -U phts < phts-backup.sql
   ```
8. `docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.demo up -d --build`

### What changes between dev and prod

| Concern | Dev | Prod/demo |
|---------|-----|-----------|
| Backend CMD | `--reload` (1 worker) | `--workers 4` (no reload) |
| Frontend | Vite dev server (port 5173, HMR) | Nginx static serve (port 80) |
| nginx config | `nginx.conf` (HTTP only, frontend:5173) | `nginx.prod.conf` (HTTPS, frontend:80) |
| Ports exposed | All services exposed to host | Only 80/443 via nginx |
| Base image | `python:3.12-slim` + `apt-get upgrade` | Same |

---

## Nginx Routing Notes

- Location blocks must be ordered **specific before general**.
- The `/ai/` block has `proxy_read_timeout 120s` (Claude/Gemini can be slow).
- The FHIR API regex covers: `^/(ValueSet|CodeSystem|ConceptMap|metadata|analytics|sdo|\$stats)`
- After editing `nginx.conf`: `docker compose exec nginx nginx -s reload`
- A second `server` block handles `phinvads.test` (legacy URL redirect demo — see "Legacy URL Redirect" section).
- **Do not use `*.cdc.gov` for mock domains** — HSTS preloading forces HTTPS; use `.test` TLD instead.

---

## Common Commands

```bash
# Start everything
docker compose up -d

# Rebuild a single service (e.g., after requirements.txt change)
docker compose up -d --build backend

# Rebuild frontend (required after vite.config.ts changes)
docker compose up -d --build frontend

# Reload nginx config without restart
docker compose exec nginx nginx -s reload

# Tail backend logs
docker compose logs backend -f

# Check which AI provider is active
curl http://localhost:8000/ai/provider

# Test SDO systems
curl http://localhost:8000/sdo/systems

# Run backend tests
docker compose exec backend pytest
```

---

## Observability

### Metrics — Prometheus + Grafana
- Prometheus scrapes `/metrics` every 15 s; Grafana dashboard **PH-TS Overview** shows request rates, latency, error rates, resource counts.
- Dashboard JSON: `grafana/dashboards/fhir_overview.json`
- Datasource UIDs are provisioned and auto-assigned by Grafana; the dashboard JSON must reference the actual UID. If panels show "No data" after a fresh volume, the UID may have changed — check `GET http://localhost:3001/api/datasources` and update the JSON.

### Logs — Loki + Promtail
- **Promtail** (`phts-promtail`) mounts `/var/run/docker.sock` and `/var/lib/docker/containers`, discovers all containers via Docker SD, ships logs to Loki.
- **Loki** (`phts-loki`) stores log streams; queryable via Grafana Explore (Loki datasource) or **PH-TS Logs** dashboard.
- Config files: `loki/loki-config.yml`, `promtail/promtail-config.yml`

**Useful LogQL queries:**
```logql
{service="backend"} |= "HTTP/1"                          # all API requests
{service="backend"} |~ " [45][0-9]{2} "                  # 4xx/5xx errors
{service="backend"} |= "/ValueSet/$expand"               # expand calls only
{compose_project="ph-ts"} |~ "(?i)error|exception"      # errors, all containers
```

---

## Terminology Validation

PH-TS supports code validation for FHIR resources, HL7 v2 messages, and any
system that needs to confirm a code is valid in a given code system or ValueSet.

**Key endpoints:**

| Endpoint | Purpose |
|---|---|
| `GET /ValueSet/$validate-code?url=&code=` | Validate one code against a ValueSet |
| `GET /CodeSystem/$lookup?system=&code=[&property=...]` | Look up one code; optional hierarchy properties for LOINC |
| `POST /ValueSet/$validate-batch` | Validate up to 200 codes concurrently |
| `GET /ConceptMap/$translate?system=&code=[&url=][&target=]` | Translate a code to another system via ConceptMap |
| `GET /CodeSystem/$subsumes?system=&codeA=&codeB=` | Check hierarchy relationship between two codes |
| `GET /ValueSet/$expand?url=...fhir_vs=isa/{id}` | Expand all descendants of a SNOMED CT concept |
| `GET /sdo/snomed/children/{concept_id}?edition=` | Lazy hierarchy tree node — returns direct children + parent |
| `POST /ai/map-save` | Save AI cross-system mapping results as a FHIR R4 ConceptMap |
| `GET /ValueSet/$views` | List disease/condition views with live tagged-ValueSet counts |
| `POST /ValueSet/$tag-view?resource_id=&view_id=` | Tag a ValueSet with a disease/condition view (idempotent) |
| `DELETE /ValueSet/$tag-view?resource_id=&view_id=` | Remove a disease/condition view tag from a ValueSet |
| `GET /ValueSet?context-value-code={code}` | Filter ValueSets by condition code in `useContext` |

**Quick examples:**

```bash
# Validate a code against a ValueSet
curl "http://localhost/ValueSet/\$validate-code?url=http://hl7.org/fhir/ValueSet/administrative-gender&code=M"

# Look up a LOINC code
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6"

# Look up with LOINC hierarchy properties (requires LOINC credentials)
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6&property=parent&property=COMPONENT"

# Batch validate coded fields from an HL7 v2 message
curl -X POST http://localhost/ValueSet/\$validate-batch \
  -H "Content-Type: application/json" \
  -d '{"items":[
    {"code":"M",       "system":"http://terminology.hl7.org/CodeSystem/v2-0001"},
    {"code":"94500-6", "system":"http://loinc.org"},
    {"code":"J12.82",  "system":"http://hl7.org/fhir/sid/icd-10-cm"}
  ]}'

# Translate HL7 v2 sex code to FHIR gender (using local ConceptMap)
curl "http://localhost/ConceptMap/\$translate?url=http://example.org/map/v2-sex-to-fhir&system=http://terminology.hl7.org/CodeSystem/v2-0001&code=M"

# Check SNOMED CT subsumption (is Diabetes mellitus an ancestor of Type 2 DM?)
curl "http://localhost/CodeSystem/\$subsumes?system=http://snomed.info/sct&codeA=73211009&codeB=44054006"

# Expand all descendants of Diabetes mellitus via SNOMED ECL (inline, no stored ValueSet needed)
curl "http://localhost/ValueSet/\$expand?url=http://snomed.info/sct?fhir_vs=isa/73211009&count=50"
```

**Load HL7 v2 tables for offline validation (run once):**

```bash
python migration/import_hl7_v2_tables.py --target-url http://localhost
```

Full documentation: `docs/validation_guide.md`

---

## Disease / Condition Views

PH-TS supports PHIN VADS-style condition/disease views using the FHIR R4 `useContext` mechanism (Option A — no schema change required).

### How It Works

Each "view" is a named grouping of ValueSets associated with a public health disease or condition. The association is stored directly on the ValueSet as a `useContext` entry:

```json
{
  "code": {
    "system": "http://terminology.hl7.org/CodeSystem/usage-context-type",
    "code": "focus",
    "display": "Clinical Focus"
  },
  "valueCodeableConcept": {
    "coding": [{ "system": "http://snomed.info/sct", "code": "840539006", "display": "COVID-19" }],
    "text": "COVID-19"
  }
}
```

### View Definitions

Defined in `backend/app/disease_views.json` — **107 views** aligned 1:1 with the PHIN VADS exported view files in `docs/PHINVADSViews/`. Each view ID is a URL slug derived from the filename.

Examples:

| View ID | Display |
|---|---|
| `covid-19-case-notification` | COVID-19 Case Notification |
| `tuberculosis-case-notification` | Tuberculosis Case Notification |
| `hiv` | (none — mapped from old hand-crafted set, now replaced) |
| `immunization-messaging-hl7-version-2-5-1` | Immunization Messaging - HL7 Version 2.5.1 |
| `syndromic-surveillance` | Syndromic Surveillance |
| `generic-case-notification-mmg-version-2` | Generic Case Notification MMG - Version 2 |

`system` = `https://phinvads.cdc.gov/vads/view`, `code` = the slug (not SNOMED codes).

To regenerate views from the file listing (e.g. after adding new view files):
```bash
python migration/tag_disease_views.py --generate-views
```

To add new views: re-export from PHIN VADS into `docs/PHINVADSViews/` and run `--generate-views`.

### Tagging ValueSets

```bash
# Tag a ValueSet with a view
curl -X POST "http://localhost/ValueSet/\$tag-view?resource_id=YOUR_ID&view_id=covid-19-case-notification"

# Remove a tag
curl -X DELETE "http://localhost/ValueSet/\$tag-view?resource_id=YOUR_ID&view_id=covid-19-case-notification"

# Browse the view catalogue (with live counts)
curl "http://localhost/ValueSet/\$views"

# Filter ValueSets by view slug
curl "http://localhost/ValueSet?context-value-code=covid-19-case-notification&_summary=true"
```

The `$tag-view` POST is idempotent — calling it twice does not create duplicate `useContext` entries.

### Auto-Tagging Script

`migration/tag_disease_views.py` reads all 107 `View_*.txt` files from `docs/PHINVADSViews/`, resolves OIDs to PH-TS resource IDs, and calls `$tag-view` for each match.

```bash
# Preview (dry-run, default)
python migration/tag_disease_views.py --target-url http://localhost

# Apply all tags
python migration/tag_disease_views.py --apply --target-url http://localhost

# Filter to specific views
python migration/tag_disease_views.py --filter covid influenza --target-url http://localhost

# Show OIDs not found in PH-TS
python migration/tag_disease_views.py --show-unmatched --target-url http://localhost

# Regenerate disease_views.json from view files
python migration/tag_disease_views.py --generate-views
```

OID resolution order: `url=https://phinvads.cdc.gov/baseStu3/ValueSet/{oid}` first (matches how both importers store the `url` field), then `identifier={oid}` (bare OID, fallback).

### Curation Status (as of 2026-03-30)

2,750 tags applied across 988 ValueSets / 107 views. 323 OIDs in view files were not found in PH-TS (those ValueSets were not imported). Re-run `--apply` after importing additional ValueSets to pick up new matches.

### UI

The ValueSet browser in `App.tsx` shows a **"Condition / View"** dropdown filter when `GET /ValueSet/$views` returns results. The dropdown lists all views with their current counts; selecting one issues a `?context-value-code=` query to the backend. The ValueSet detail drawer has a collapsible checkbox panel for adding/removing view tags on individual resources.

---

## Legacy URL Redirect (Mock PHIN VADS)

PH-TS can resolve legacy PHIN VADS links and open the cached resource automatically in the UI.

### How It Works

```
http://phinvads.test/vads/ViewValueSet.action?oid=2.16.840.1.114222.4.11.1038
  → nginx 302 → http://localhost/?phts_oid=2.16.840.1.114222.4.11.1038&phts_type=ValueSet
    → App.tsx deep-link handler reads ?phts_oid=, fetches by identifier, opens drawer
```

### Setup (one-time, per machine)

Add to `C:\Windows\System32\drivers\etc\hosts` (run Notepad as Administrator):
```
127.0.0.1   phinvads.test
```

### nginx Server Block

`infrastructure/docker/nginx/nginx.conf` contains a second `server` block for `phinvads.test`:
- `/vads/ViewValueSet.action?oid=X` → `302 http://localhost/?phts_oid=X&phts_type=ValueSet`
- `/vads/ViewCodeSystem.action?oid=X` → `302 http://localhost/?phts_oid=X&phts_type=CodeSystem`
- All other paths → `302 http://localhost/`

After editing nginx.conf: `docker compose exec nginx nginx -s reload` (no rebuild needed).

### Frontend Deep-Link Handler (`App.tsx`)

A `useEffect` keyed on `loadingResources` with a `deepLinkHandled` ref fires once after the initial resource list loads (to avoid a race with `setSelectedResource(null)` in `loadResources`). It:
1. Reads `?phts_oid=` and `?phts_type=` from `window.location.search`
2. Calls `GET /{type}?identifier={oid}&_summary=true`
3. Sets `selectedResource` to open the detail drawer in `fullPage` mode (fills the screen)
4. Cleans the URL via `window.history.replaceState`

In `fullPage` mode the `DetailPanel` header shows a **"← PH-TS"** back-link (`href="/"`) so users can return to the main browser after following a redirect link. The `×` close button still works for users who navigated there from within the app.

### Domain Choice

Use `.test` TLD (IANA-reserved for testing). Do **not** use `*.cdc.gov` subdomains — browsers enforce HSTS preloading for `*.gov`, forcing HTTPS on port 443 (nothing listens there). Underscores in hostnames (e.g. `mock_phinvads`) are also rejected by Chrome/Firefox per RFC 1123.

---

## SNOMED CT Hierarchy Tree

The ValueSet Builder includes a lazy-loaded hierarchy tree for SNOMED CT concept browsing.

**Backend:** `GET /sdo/snomed/children/{concept_id}?edition=international|us`
- Uses `tx.fhir.org ValueSet/$expand` with ECL operators: `<!{id}` (direct children) and `>!{id}` (direct parents), fetched concurrently with a display name lookup
- Returns: `{ conceptId, display, system, children: [{code, display}], childCount, parent, edition }`
- Falls back to International Edition if US Edition module is not available on tx.fhir.org
- Note: `CodeSystem/$lookup?property=child` was tried first but tx.fhir.org does not reliably return child properties for SNOMED CT — ECL `$expand` is the correct approach

**Frontend (ValueSetBuilder.tsx):**
- Toggle between **flat results** (existing ECL search) and **tree view** via "Browse Tree" button
- Tree nodes lazy-expand on chevron click — only fetches children when a node is opened
- Hover to reveal "+" button to add a concept to the basket
- Shows "(International Edition fallback)" warning when US was requested but unavailable

---

## Known Issues / History

- **ValueSet list concept count showed 0 (fixed 2026-03-29)** — `_summary=true` stripped `compose`/`concept` arrays so `countConcepts()` returned 0 for all resources. Fixed by adding `_conceptCount` to the `jsonb_build_object()` summary query (computed inline via `jsonb_array_length` for CodeSystems and a correlated subquery for ValueSets).
- **SNOMED CT US Edition 404/422 on `$expand`** — tx.fhir.org does not have the US Edition module (`731000124108`) loaded. `expand_snomed_ecl_us()` now tries the US module URL first, then silently falls back to International Edition, labelling results with the actual edition used.
- **SNOMED hierarchy tree showed 0 children (fixed 2026-03-29)** — `get_snomed_children()` was using `CodeSystem/$lookup?property=child` which tx.fhir.org does not reliably return for SNOMED CT. Fixed to use `ValueSet/$expand` with ECL operators: `<!{id}` for direct children and `>!{id}` for direct parents. These are fetched concurrently alongside the display name lookup, with the same US→International fallback pattern.
- **`GET /ValueSet?identifier=` silently ignored (fixed 2026-03-30)** — `identifier` was not wired up in `search_value_sets` or `search_resources`. The parameter was ignored and all 1,998 ValueSets were returned, causing the auto-tagging script to map every OID to `entries[0]` (same 1-2 resources for every view). Fixed: `identifier` param added to endpoint; `search_resources` now queries `identifier[].value` JSONB array and strips `urn:oid:` prefix automatically.
- **`identifier` search missed `urn:oid:`-prefixed values (fixed 2026-04-15)** — The `import_phinvads_txt.py` importer stores identifiers as `urn:oid:{oid}` but the JSONB query searched for the bare OID only (after stripping the prefix from the query param). This broke the PHIN VADS legacy URL redirect — the frontend called `GET /ValueSet?identifier={bare-oid}` and got 0 results. Fixed: the SQL WHERE clause now matches `ident->>'value' = $n OR ident->>'value' = 'urn:oid:' || $n`, covering both storage forms.
- **Auto-tag script used wrong OID lookup form (fixed 2026-03-30)** — `tag_disease_views.py` was trying `identifier=urn:oid:{oid}` first, which both matched nothing (before the fix above) and was the wrong format. Changed primary lookup to `url=https://phinvads.cdc.gov/baseStu3/ValueSet/{oid}` which matches the `url` column directly. Bare OID `identifier=` is now the fallback.
- **Auto-tag script crashed on Windows terminal (fixed 2026-03-30)** — Unicode box-drawing characters (`──`, `→`, `…`) in `print()` calls caused `UnicodeEncodeError` on Windows cp1252 terminal. Replaced with ASCII equivalents (`--`, `->`, `...`).
- **HL7 v2 search returned "Unknown system"** — `hl7v2` was in the `SYSTEMS` dict but not in `_SEARCH_FNS`. Fixed by adding `_search_hl7v2_local()` which queries locally-imported HL7 v2 table CodeSystems in PostgreSQL directly.
- **LOINC fhir.loinc.org returns 401** — switched to NLM ClinicalTables as the LOINC source. `LOINC_USERNAME`/`LOINC_PASSWORD` are no longer used.
- **Gemini free tier quota** — `gemini-2.0-flash` requires billing enabled on the Google Cloud project. The free tier limit is 0 RPM for this model.
- **Vite HMR on Windows Docker** — requires `usePolling: true` in `vite.config.ts`. This is already set.
- **`google-generativeai` is deprecated** — the project uses `google-genai>=1.0.0` (new SDK) with `from google import genai` import style.
- **HL7 core import: `meta.lastUpdated` datetime error** — HL7 package resources contain `meta.lastUpdated` which causes JSON serialization failures; `import_hl7_core.py` strips `meta` before POST.
- **HL7 core import: partial datetime 422 errors** — `concept[].property[].valueDateTime` can contain `"2000-11"` (year-month only) which Pydantic rejects; `import_hl7_core.py` strips all `concept[].property` arrays.
- **Elasticsearch nested objects limit** — large CodeSystems can hit the default 10 k nested object limit. Fix: `PUT /fhir_resources/_settings {"index.mapping.nested_objects.limit": 100000}`
- **PHIN VADS `httpcore.ReadError`** — PHIN VADS drops TLS connections mid-response body; not wrapped by httpx as `RequestError`. The migration script catches `Exception` broadly in its retry loop to handle this.
- **PHIN VADS stale `next` link** — PHIN VADS pagination returns a `next` link even after all resources are fetched; the script stops when `len(fetched) >= bundle.total` to prevent hanging requests.
- **PHIN VADS LOINC CodeSystem 500 error** — The LOINC CodeSystem (`2.16.840.1.113883.6.1`) consistently returns HTTP 500 when imported; expected — LOINC is too large for local storage and should remain a delegated stub.
- **PHIN VADS Preferred Concept Name** — Only present in the Excel download, not always in the FHIR STU3 API `designation` arrays. The migration preserves designations when present but cannot reconstruct them from the API if absent.
- **`import_phinvads_txt.py` duplicate-key 500s on re-run** — With `CONCURRENT_POSTS=10`, the dedup `GET /ValueSet?url=...` check can race against concurrent POSTs and miss an in-flight insert. The POST then hits `idx_unique_resource_url_version` and returns HTTP 500. Safe to ignore — data is in the DB. Re-runs are idempotent for already-imported resources.
- **3 PHIN VADS `.txt` files unparseable** — `PHVS_AdministrativeProcedure_CDC_ICD-10PCS_V11.txt`, `PHVS_LabTestName_CDC_V10.txt`, and `PHVS_LabTestResultCoded_CDC_V2.txt` have malformed metadata rows (OID field empty or missing). These 3 cannot be auto-imported and are not in the DB.
- **`import_phinvads_txt.py` split-row metadata bug (fixed 2026-04-15)** — Some `.txt` files (e.g. `PHVS_VaccinesAdministered_PediatricFlu_V1.txt`) put the Value Set Name alone on row 1 and the OID/code/version on the next row with a leading tab. The CSV parser read row 1 as the values row and got an empty OID, creating records with no URL that couldn't be expanded. Fixed: after reading the first metadata row, if OID is empty the parser now scans subsequent rows for one containing an OID and merges the fields. The 4 duplicate ghost records in the DB were repaired (3 deleted, 1 patched with correct URL/OID/metadata).
- **`import_phinvads_txt.py` double-blank-line parse bug (fixed 2026-03-25)** — Some PHIN VADS `.txt` files have two blank lines between the metadata section and the concept section. The parser was using the second blank line as the `csv.DictReader` header row, yielding 0 concepts. Fixed by skipping all leading blank lines before the concept section.
- **ES nested object limit** — Raised to 50,000 via `PUT /fhir_resources/_settings {"index.mapping.nested_objects.limit": 50000}` to support large PHIN VADS ValueSets. Default is 10,000. If the setting resets after an ES container restart, re-apply it before running large imports.
- **PHIN VADS source badge showed "PHTS" (fixed 2026-04-14)** — 137 PHIN VADS resources were imported before the source extension code existed in `_post_resource()`. They had no `extension` key in their JSONB data; `_extract_source()` returned `'internal'`; the frontend displayed "PHTS". Fixed by SQL backfill: injected `{"url":"http://phts.local/StructureDefinition/source","valueCode":"phinvads"}` into `data->'extension'` and set `source='phinvads'` for all records where `url LIKE 'https://phinvads.cdc.gov/%'` and extension was absent. Redis cache flushed after.
- **`update_resource()` did not update `source` column (fixed 2026-04-14)** — The UPDATE query in `DatabaseManager.update_resource()` (`main.py`) omitted the `source` column, so a PUT with a corrected source extension would not update the DB column used for `?source=` filtering. Fixed: `_extract_source(data)` is now called and `source=$7` included in the UPDATE (parameter indices shifted).
- **`nul` file created in `backend/` directory (fixed 2026-04-15)** — Windows reserved device name (`nul` ≡ `/dev/null`) was created as a literal file when a migration script redirected output. Git refuses to commit files named after reserved device names. Deleted with `rm backend/nul`. If it reappears, check migration scripts for Windows-incompatible output redirection.
- **Mock PHIN VADS domain rejects: underscores and `*.cdc.gov`** — `mock_phinvads.cdc.gov` fails in browsers: (1) underscores are invalid in RFC 1123 hostnames and rejected by Chrome/Firefox; (2) `*.cdc.gov` is in the HSTS preload list, forcing HTTPS to port 443. Use `phinvads.test` instead.
- **PHIN VADS legacy URL redirect broken (fixed 2026-04-15)** — The full redirect chain (`phinvads.test` → nginx 302 → frontend identifier lookup → open drawer) was broken because the identifier JSONB query only matched bare OIDs but the txt importer stores them as `urn:oid:{oid}`. Fixed by the identifier search dual-form fix above. The full-page detail view now also includes a "← PH-TS" back-link so users can return to the main UI after following a redirect.
- **Empty ValueSet ghost records from import race conditions (fixed 2026-04-15)** — 13 completely empty ValueSet records (no URL, title, name, identifier, or concepts) existed in the DB from concurrent-POST race conditions during bulk import. Deleted via SQL. The frontend now handles missing-URL resources gracefully: expansion shows an error message instead of calling `$expand?url=`, and the "Raw $expand JSON" link is hidden.
- **AI chat code hallucinations (fixed 2026-04-15)** — The `/ai/chat` endpoint was answering questions about specific code numbers from training memory, producing wrong or invented displays (e.g. SNOMED 119297000 described as "COVID-19 vaccination" instead of "Blood specimen"). Fixed with two layers: (1) Pre-lookup injection — before each AI call, code patterns (SNOMED 6–12 digit, LOINC `##-#`, ICD-10-CM `A##.x`) are detected in the user's latest message and looked up against the live terminology server; authoritative results are injected into the system prompt. (2) Hard rules in the system prompt forbid the AI from stating code meanings from training memory and instruct it to say "I cannot confirm" when no live lookup result was provided. `/ai/suggest` also received a tightened prompt requiring exact candidate display names to be preserved verbatim.
