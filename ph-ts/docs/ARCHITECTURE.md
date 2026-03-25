# Architecture

> For a visual Mermaid diagram of the full stack (all services, data flows, external SDOs, AI providers, and migration scripts), see [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md).

## System Overview

PH-TS is a containerised FHIR R4 terminology server. All components run via Docker Compose and communicate over an internal bridge network (`phts-network`). External traffic enters through Nginx on port 80.

```
Browser / API Client
        │
        ▼
  ┌─────────────────────────────────┐
  │  Nginx  :80                     │
  │  - Rate limiting                │
  │  - WebSocket upgrade (HMR)      │
  └──────────┬──────────────────────┘
             │
    ┌────────┴─────────┐
    ▼                  ▼
Backend :8000     Frontend :5173
(FastAPI)         (Vite / React)
    │
    ├──► PostgreSQL :5432  (primary store)
    ├──► Elasticsearch :9200 (search index)
    └──► Redis :6379         (cache / rate-limit)
```

---

## Components

### Nginx (Reverse Proxy)

- Listens on port **80**
- Routes FHIR API paths (`/ValueSet`, `/CodeSystem`, `/metadata`, etc.) to the backend
- Routes `/$expand` with a tighter rate limit (expensive operation)
- Proxies everything else to the Vite frontend dev server
- Passes WebSocket `Upgrade` headers for Vite HMR
- Adds security headers (`X-Frame-Options`, `X-Content-Type-Options`, etc.)

Config: `infrastructure/docker/nginx/nginx.conf`

### Backend (FastAPI)

- Python 3.11, FastAPI 0.104, Uvicorn with `--reload`
- Implements **FHIR R4** resource operations:
  - CRUD for `ValueSet`, `CodeSystem`, and `ConceptMap`
  - `$expand` — expands a ValueSet to its full list of concepts; supports SNOMED CT ECL via `isa/{id}` and `refset/{id}` implicit ValueSet URLs
  - `$validate-code` — checks whether a code belongs to a ValueSet/CodeSystem
  - `$validate-batch` — validates up to 200 codes concurrently in one request (HL7 v2 message validation)
  - `$lookup` — looks up display name and properties for a code; supports LOINC hierarchy properties (`parent`, `child`, `COMPONENT`, etc.) via fhir.loinc.org when credentials are set
  - `$translate` — maps a code from one system to another using a stored ConceptMap; falls back to tx.fhir.org
  - `$subsumes` — hierarchy check (subsumes / subsumed-by / equivalent / not-subsumed); delegates to tx.fhir.org for SNOMED CT and fhir.loinc.org for LOINC
  - `$diff` — compares two versions of a resource
  - `$stats` / `/analytics/summary` — aggregate counts
- **HL7 v2 table support** — any `http://terminology.hl7.org/CodeSystem/v2-*` URL is
  resolved locally (after running `migration/import_hl7_v2_tables.py`) or delegated
  to `tx.fhir.org` as a fallback; no explicit routing entry needed per table
- Versioning: every PUT creates a new version row; `/_history` returns all versions
- Auth: optional JWT bearer token auth (controlled by `ENABLE_AUTH` env var)
- Metrics: Prometheus client exposed at `/metrics`

Source: `backend/app/`

### PostgreSQL (Primary Store)

- Version: **15-alpine**
- Stores all FHIR resources as JSONB in a `resources` table
- Separate `resource_versions` table for full version history
- Connection pool managed by **asyncpg** via SQLAlchemy 2 async engine
- Data persisted in Docker volume `postgres_data`

### Elasticsearch (Search Index)

- Version: **8.11.0**, single-node, no TLS, no auth (dev mode)
- Resources are indexed on write for fast full-text search
- Used by `/ValueSet?name=...` and `/CodeSystem?name=...`
- Client: `elasticsearch[async]` with `aiohttp` transport
- Data persisted in Docker volume `elasticsearch_data`

### Redis (Cache)

- Version: **7-alpine**, append-only persistence, 256 MB max, LRU eviction
- Caches expensive `$expand` results (key: `expand:{url}:{version}`)
- Also used for rate-limit counters (via Nginx `limit_req_zone`)
- Data persisted in Docker volume `redis_data`

### Frontend (React + Vite)

- React 18, TypeScript, Tailwind CSS
- Single-page app (`frontend/src/App.tsx`) — no router, view state managed in React
- Features:
  - Browse ValueSets and CodeSystems (grid / list view)
  - Search by name (debounced)
  - Resource detail slide-out panel with version history
  - Full-page `$expand` viewer with filter, pagination, and CSV export
  - Analytics dashboard (resource counts, server status)
- Vite configured with `usePolling: true` for Windows Docker HMR compatibility
- `frontend/src/` is bind-mounted so edits hot-reload without container rebuild

### Adminer (Database UI)

- Lightweight single-container web-based PostgreSQL browser
- Available at **http://localhost:8181**
- Requires no configuration — pre-configured to connect to the `postgres` service

### Prometheus + Grafana (Metrics)

- Prometheus scrapes the backend `/metrics` endpoint every 15 s
- Grafana dashboards provisioned from `grafana/dashboards/` and `grafana/datasources/`
- Grafana at **http://localhost:3001** (default: admin / admin)
- Dashboard **PH-TS Overview**: request rates, latency (p50/p95/p99), error rates, resource counts

### Loki + Promtail (Log Aggregation)

- **Promtail** runs as a sidecar container, mounts the Docker socket, and ships every container's stdout/stderr to Loki
- **Loki** stores log streams indexed by labels: `service`, `container`, `stream`, `compose_project`
- Loki at **http://localhost:3100**; queryable via Grafana Explore (Loki datasource) or the **PH-TS Logs** dashboard
- Use LogQL in Grafana Explore to filter logs:
  - All API calls: `{service="backend"} |= "HTTP/1"`
  - Errors only: `{service="backend"} |~ " [45][0-9]{2} "`
  - Specific path: `{service="backend"} |= "/ValueSet/$expand"`
  - All containers, errors: `{compose_project="ph-ts"} |~ "(?i)error|exception"`

Config: `loki/loki-config.yml`, `promtail/promtail-config.yml`

---

## Port Reference

| Port | Service | Notes |
|------|---------|-------|
| 80 | Nginx | Primary entry point |
| 8000 | Backend | Direct FastAPI access |
| 5173 | Frontend | Vite dev server |
| 5432 | PostgreSQL | Direct DB access |
| 9200 | Elasticsearch | REST API |
| 6379 | Redis | CLI / direct access |
| 8181 | Adminer | Database browser UI |
| 3001 | Grafana | Metrics + log dashboards |
| 9090 | Prometheus | Metrics scrape UI |
| 3100 | Loki | Log aggregation API |

---

## Data Flow — ValueSet Search

```
GET /ValueSet?name=sex
    │
    ▼
Nginx → Backend
    │
    ├─► Redis: check cache key "search:ValueSet:sex"
    │         hit → return immediately
    │         miss ↓
    ├─► Elasticsearch: full-text search on name/title fields
    │         returns list of resource IDs
    ├─► PostgreSQL: fetch full JSONB documents by ID
    ├─► Redis: write result to cache (TTL 5 min)
    └─► Response: FHIR Bundle with matching resources
```

## Data Flow — $expand

```
GET /ValueSet/$expand?url=urn:oid:2.16.840.1.114222.4.11.800&count=1000
    │
    ▼
Nginx ($expand rate limit: 20r/s) → Backend
    │
    ├─► Redis: check cache key "expand:{url}:{version}"
    │         hit → return immediately
    │         miss ↓
    ├─► PostgreSQL: load ValueSet JSONB, extract compose.include
    ├─► Redis: cache expansion result
    └─► Response: FHIR Parameters with expansion.contains[]
```

---

## Security Notes

- **Authentication** is disabled by default (`ENABLE_AUTH=false`). Enable for production deployments.
- **CORS** origins are controlled via `CORS_ORIGINS` in `.env`.
- **Elasticsearch and Redis** have no authentication — do not expose ports 9200 or 6379 publicly.
- **Nginx** adds `X-Frame-Options`, `X-Content-Type-Options`, and `X-XSS-Protection` headers.
- **Rate limiting**: API at 100 r/s, `$expand` at 20 r/s (configured in nginx.conf).
- All services communicate over the internal `phts-network` bridge; only the ports listed above are exposed to the host.

---

## Volumes

| Volume | Service | Contains |
|--------|---------|---------|
| `postgres_data` | PostgreSQL | All FHIR resource data |
| `elasticsearch_data` | Elasticsearch | Search index |
| `redis_data` | Redis | Cached results (ephemeral — safe to delete) |
| `prometheus_data` | Prometheus | Metrics time-series |
| `grafana_data` | Grafana | Dashboard state, user settings |
| `loki_data` | Loki | Log streams and index (ephemeral — safe to delete) |

To reset all data:
```bash
docker compose down -v
```
