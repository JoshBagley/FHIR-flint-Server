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
| PostgreSQL | localhost:5432 | DB: `phts_dev`, User: `phts` |
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

---

## PHIN VADS Migration Tool

**Script:** `migration/phinvads_migrate.py`
**Source API:** `https://phinvads.cdc.gov/baseStu3` — FHIR **STU3** (conversion to R4 is handled by the script)

### WAF / Connectivity Quirks
- The PHIN VADS WAF **blocks** `Accept: application/fhir+json` — use `Accept: application/json, */*`
- The WAF **blocks custom User-Agent** strings — use the default httpx User-Agent
- Direct OID path reads (`GET /ValueSet/{oid}`) may be blocked — use identifier search instead

### OID Lookup Order (most → least reliable)
1. `GET /ValueSet?identifier={bare-oid}&_format=json`
2. `GET /ValueSet?identifier=urn:oid:{oid}&_format=json`
3. `GET /ValueSet/{oid}?_format=json` (fallback, may fail via WAF)

### STU3 → R4 Conversion Notes
- `status` values are normalised (`active/draft/retired/unknown`)
- CodeSystem `content` field: valid R4 values are `not-present`, `example`, `fragment`, `complete`, `supplement`
- CodeSystem `hierarchyMeaning` defaults to `is-a` when absent
- Original PHIN VADS `id` is preserved as an `identifier` for provenance tracing
- `compose` and `expansion` blocks are structurally identical STU3/R4 — passed through unchanged

### Usage Examples
```bash
# Full bulk migration
python migration/phinvads_migrate.py --target-url http://localhost

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

## Known Issues / History

- **LOINC fhir.loinc.org returns 401** — switched to NLM ClinicalTables as the LOINC source. `LOINC_USERNAME`/`LOINC_PASSWORD` are no longer used.
- **Gemini free tier quota** — `gemini-2.0-flash` requires billing enabled on the Google Cloud project. The free tier limit is 0 RPM for this model.
- **Vite HMR on Windows Docker** — requires `usePolling: true` in `vite.config.ts`. This is already set.
- **`google-generativeai` is deprecated** — the project uses `google-genai>=1.0.0` (new SDK) with `from google import genai` import style.
