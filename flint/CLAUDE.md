# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# CLAUDE.md — Flint FHIR Server

This file provides context and working conventions for Claude Code when operating in this repository.

---

## Project Overview

**Flint** is a general-purpose FHIR R4 server. Current capabilities include terminology and vocabulary management (ValueSet authoring, code validation, SDO search), with a roadmap to support core FHIR resources and a full agentic UI.

**Stack:** FastAPI · PostgreSQL · Elasticsearch · Redis · React/Vite · Nginx · Prometheus · Grafana · Loki · Promtail · Docker Compose

---

## FHIR Server Architecture

**Flint is a fully custom-built FHIR R4 server — not HAPI FHIR, not Ontoserver, not any Java-based framework.** It is modeled conceptually after Ontoserver but implemented from scratch in Python.

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
- `_extract_source()` reads `http://flint.local/StructureDefinition/source` extension for provenance

**Route modules — three routers:**

| Module | Handles |
|---|---|
| `main.py` (inline) | CRUD + search + history + archive + audit for ValueSet / CodeSystem / ConceptMap |
| `routes/fhir_operations.py` | All FHIR operations: `$expand`, `$validate-code`, `$lookup`, `$translate`, `$subsumes`, `$validate-batch`, `$diff`, `$stats` |
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

`_SYSTEM_URL_TO_SDO` maps canonical FHIR URLs **and** OID aliases to connector IDs so resources using `urn:oid:` notation route correctly.

---

## Running Services & Ports

| Service | URL | Notes |
|---|---|---|
| Web UI (Nginx) | http://localhost | Reverse proxy entry point |
| Frontend (Vite dev) | http://localhost:5173 | Direct Vite HMR server |
| Backend API | http://localhost:8000 | FastAPI; also at `/` via Nginx |
| API Docs (Swagger) | http://localhost:8000/docs | Auto-generated OpenAPI |
| PostgreSQL | localhost:5432 | DB: `flint`, User: `flint` |
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
flint/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, router registration, search_resources()
│   │   ├── routes/
│   │   │   ├── fhir_operations.py   # FHIR R4 ops: $expand, $validate-code, $lookup, $translate, etc.
│   │   │   ├── sdo_search.py        # GET /sdo/systems, /sdo/search, /sdo/lookup, /sdo/snomed/children/{id}
│   │   │   └── ai_assist.py         # POST /ai/suggest, /ai/describe, /ai/map, /ai/map-save, GET /ai/provider
│   │   └── services/
│   │       └── external_cs.py       # SDO connector (SNOMED, ICD-10-CM, LOINC, RxNorm, VSAC)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  # Main app shell; ValueSet/CodeSystem/ConceptMap browsers
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
- **Custom extension pattern:** `http://flint.local/StructureDefinition/source` tracks import provenance (e.g. `hl7`, `internal`). Same mechanism used for reading context tags from `useContext`.

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

FHIR R4 defines a `CodeSystem.content` field that controls how concepts are stored and how operations behave. Flint uses this to handle both small locally-stored code systems and large externally-delegated ones within a single unified API.

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

The mapping from FHIR system URL to SDO connector ID is in `_SYSTEM_URL_TO_SDO` at the top of `fhir_operations.py`. It includes both canonical URLs and OID aliases so ValueSets using `urn:oid:` notation route correctly:

```python
# Canonical URLs
"http://snomed.info/sct"                       → "snomed"
"http://loinc.org"                             → "loinc"
"http://hl7.org/fhir/sid/icd-10-cm"           → "icd10cm"
"http://hl7.org/fhir/sid/icd-9-cm"            → "icd9cm"
"http://www.nlm.nih.gov/research/umls/rxnorm" → "rxnorm"
"https://cts.nlm.nih.gov/fhir"                → "vsac"
# OID aliases
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

## Multi-Environment Deployment

Flint uses Docker Compose file layering + profiles + `.env` files to support dev, demo, and production from a single codebase.

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
3. Copy repo to VM: `rsync -av --exclude='.env' flint/ user@host:~/flint/`
4. Create secrets file on VM: `cp .env.demo.example .env.demo` and fill in values
5. Provision SSL: `sudo certbot certonly --standalone -d your-domain.com`
6. Edit `infrastructure/docker/nginx/nginx.prod.conf`: replace `YOUR_DOMAIN_HERE`
7. Backup local Postgres and restore on VM:
   ```bash
   # Local
   docker compose exec postgres pg_dump flint -U flint > flint-backup.sql
   # VM
   docker compose up -d postgres
   docker compose exec -T postgres psql flint -U flint < flint-backup.sql
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
- Prometheus scrapes `/metrics` every 15 s; Grafana dashboard **Flint Server Overview** shows request rates, latency, error rates, resource counts.
- Dashboard JSON: `grafana/dashboards/fhir_overview.json`
- Datasource UIDs are provisioned and auto-assigned by Grafana; the dashboard JSON must reference the actual UID. If panels show "No data" after a fresh volume, the UID may have changed — check `GET http://localhost:3001/api/datasources` and update the JSON.

### Logs — Loki + Promtail
- **Promtail** (`flint-promtail`) mounts `/var/run/docker.sock` and `/var/lib/docker/containers`, discovers all containers via Docker SD, ships logs to Loki.
- **Loki** (`flint-loki`) stores log streams; queryable via Grafana Explore (Loki datasource) or **Flint Logs** dashboard.
- Config files: `loki/loki-config.yml`, `promtail/promtail-config.yml`

**Useful LogQL queries:**
```logql
{service="backend"} |= "HTTP/1"                          # all API requests
{service="backend"} |~ " [45][0-9]{2} "                  # 4xx/5xx errors
{service="backend"} |= "/ValueSet/$expand"               # expand calls only
{compose_project="flint"} |~ "(?i)error|exception"      # errors, all containers
```

---

## Terminology Validation

Flint supports code validation for FHIR resources, HL7 v2 messages, and any
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
- **`GET /ValueSet?identifier=` silently ignored (fixed 2026-03-30)** — `identifier` was not wired up in `search_value_sets` or `search_resources`. The parameter was ignored and all results were returned. Fixed: `identifier` param added to endpoint; `search_resources` now queries `identifier[].value` JSONB array and strips `urn:oid:` prefix automatically.
- **HL7 v2 search returned "Unknown system"** — `hl7v2` was in the `SYSTEMS` dict but not in `_SEARCH_FNS`. Fixed by adding `_search_hl7v2_local()` which queries locally-imported HL7 v2 table CodeSystems in PostgreSQL directly.
- **LOINC fhir.loinc.org returns 401** — switched to NLM ClinicalTables as the LOINC source. `LOINC_USERNAME`/`LOINC_PASSWORD` are no longer used.
- **Gemini free tier quota** — `gemini-2.0-flash` requires billing enabled on the Google Cloud project. The free tier limit is 0 RPM for this model.
- **Vite HMR on Windows Docker** — requires `usePolling: true` in `vite.config.ts`. This is already set.
- **`google-generativeai` is deprecated** — the project uses `google-genai>=1.0.0` (new SDK) with `from google import genai` import style.
- **HL7 core import: `meta.lastUpdated` datetime error** — HL7 package resources contain `meta.lastUpdated` which causes JSON serialization failures; `import_hl7_core.py` strips `meta` before POST.
- **HL7 core import: partial datetime 422 errors** — `concept[].property[].valueDateTime` can contain `"2000-11"` (year-month only) which Pydantic rejects; `import_hl7_core.py` strips all `concept[].property` arrays.
- **Elasticsearch nested objects limit** — large CodeSystems can hit the default 10 k nested object limit. Fix: `PUT /fhir_resources/_settings {"index.mapping.nested_objects.limit": 100000}`
- **ES nested object limit** — Raised to 50,000 via `PUT /fhir_resources/_settings {"index.mapping.nested_objects.limit": 50000}` for large ValueSets. Default is 10,000. If the setting resets after an ES container restart, re-apply it before running large imports.
- **`update_resource()` did not update `source` column (fixed 2026-04-14)** — The UPDATE query in `DatabaseManager.update_resource()` (`main.py`) omitted the `source` column, so a PUT with a corrected source extension would not update the DB column used for `?source=` filtering. Fixed: `_extract_source(data)` is now called and `source=$7` included in the UPDATE (parameter indices shifted).
- **`nul` file created in `backend/` directory (fixed 2026-04-15)** — Windows reserved device name (`nul` ≡ `/dev/null`) was created as a literal file when a migration script redirected output. Git refuses to commit files named after reserved device names. Deleted with `rm backend/nul`. If it reappears, check migration scripts for Windows-incompatible output redirection.
- **Empty ValueSet ghost records from import race conditions (fixed 2026-04-15)** — 13 completely empty ValueSet records (no URL, title, name, identifier, or concepts) existed in the DB from concurrent-POST race conditions during bulk import. Deleted via SQL. The frontend now handles missing-URL resources gracefully: expansion shows an error message instead of calling `$expand?url=`, and the "Raw $expand JSON" link is hidden.
- **AI chat code hallucinations (fixed 2026-04-15)** — The `/ai/chat` endpoint was answering questions about specific code numbers from training memory, producing wrong or invented displays (e.g. SNOMED 119297000 described as "COVID-19 vaccination" instead of "Blood specimen"). Fixed with two layers: (1) Pre-lookup injection — before each AI call, code patterns (SNOMED 6–12 digit, LOINC `##-#`, ICD-10-CM `A##.x`) are detected in the user's latest message and looked up against the live terminology server; authoritative results are injected into the system prompt. (2) Hard rules in the system prompt forbid the AI from stating code meanings from training memory and instruct it to say "I cannot confirm" when no live lookup result was provided. `/ai/suggest` also received a tightened prompt requiring exact candidate display names to be preserved verbatim.
