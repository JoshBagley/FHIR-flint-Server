# CLAUDE.md — PH-TS FHIR Terminology Server

This file provides context and working conventions for Claude Code when operating in this repository.

---

## Project Overview

**PH-TS** (Public Health Terminology Service) is a FHIR R4 terminology server built for public health vocabulary management. It allows vocabulary SMEs to search, browse, create, and manage value sets backed by standard development organization (SDO) code systems.

**Stack:** FastAPI · PostgreSQL · Elasticsearch · Redis · React/Vite · Nginx · Docker Compose

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
| Grafana | http://localhost:3001 | Dashboards |
| Prometheus | http://localhost:9090 | Metrics scraper |
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
│   │   ├── main.py                  # FastAPI app, router registration
│   │   ├── routes/
│   │   │   ├── fhir_operations.py   # FHIR R4 ValueSet/CodeSystem endpoints
│   │   │   ├── sdo_search.py        # GET /sdo/systems, /sdo/search, /sdo/lookup
│   │   │   └── ai_assist.py         # POST /ai/suggest, /ai/describe, /ai/map, GET /ai/provider
│   │   └── services/
│   │       └── external_cs.py       # SDO connector (SNOMED, ICD-10-CM, LOINC, RxNorm, VSAC)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx                  # Main app shell; early-return pattern for full-page views
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
| `migration/phinvads_migrate.py` | PHIN VADS STU3 API | `complete` / `fragment` | 300 CodeSystems, ~4 k ValueSets |

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

# Import all PHIN VADS CodeSystems (CDC + public health vocabularies)
python migration/phinvads_migrate.py --resource codesystem --target-url http://localhost

# Import all PHIN VADS ValueSets
python migration/phinvads_migrate.py --resource valueset --target-url http://localhost
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

## Terminology Validation

PH-TS supports code validation for FHIR resources, HL7 v2 messages, and any
system that needs to confirm a code is valid in a given code system or ValueSet.

**Key endpoints:**

| Endpoint | Purpose |
|---|---|
| `GET /ValueSet/$validate-code?url=&code=` | Validate one code against a ValueSet |
| `GET /CodeSystem/$lookup?system=&code=` | Look up one code in a CodeSystem |
| `POST /ValueSet/$validate-batch` | Validate up to 200 codes concurrently |

**Quick validation examples:**

```bash
# Validate a code against a ValueSet
curl "http://localhost/ValueSet/\$validate-code?url=http://hl7.org/fhir/ValueSet/administrative-gender&code=M"

# Look up a LOINC code
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6"

# Look up an HL7 v2 Table 0001 code (Administrative Sex)
curl "http://localhost/CodeSystem/\$lookup?system=http://terminology.hl7.org/CodeSystem/v2-0001&code=M"

# Batch validate coded fields from an HL7 v2 message
curl -X POST http://localhost/ValueSet/\$validate-batch \
  -H "Content-Type: application/json" \
  -d '{"items":[
    {"code":"M",       "system":"http://terminology.hl7.org/CodeSystem/v2-0001"},
    {"code":"94500-6", "system":"http://loinc.org"},
    {"code":"J12.82",  "system":"http://hl7.org/fhir/sid/icd-10-cm"}
  ]}'
```

**Load HL7 v2 tables for offline validation (run once):**

```bash
python migration/import_hl7_v2_tables.py --target-url http://localhost
```

Full documentation: `docs/validation_guide.md`

---

## Known Issues / History

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
