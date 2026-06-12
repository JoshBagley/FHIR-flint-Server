# Development Guide

## Stack Overview

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| ORM / DB driver | SQLAlchemy 2 + asyncpg (async) |
| FHIR standard | R4 (4.0.1) |
| Search | Elasticsearch 8.11 (async client) |
| Cache | Redis 7 |
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS |
| Proxy | Nginx (alpine) |
| Observability | Prometheus + Grafana |

---

## Prerequisites

- Docker Desktop 20.10+ with Compose v2
- Python 3.11+ (migration tool only)
- Node.js 18+ (local frontend work outside Docker, optional)

---

## Project Structure

```
flint/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, startup/shutdown
│   │   ├── models.py            # Pydantic + SQLAlchemy models
│   │   ├── database.py          # Async DB connection pool
│   │   └── routes/
│   │       ├── fhir_resources.py   # CRUD: ValueSet, CodeSystem
│   │       └── fhir_operations.py  # $expand, $validate-code, $lookup, $diff
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   └── App.tsx              # Single-page React app
│   ├── Dockerfile.dev
│   ├── vite.config.ts           # Vite + vitest config (polling enabled)
│   └── package.json
├── infrastructure/
│   └── docker/nginx/nginx.conf  # Reverse proxy config
├── migration/
│   ├── phinvads_migrate.py      # PHIN VADS → FHIR R4 importer
│   └── requirements.txt
├── docs/                        # This directory
├── prometheus/prometheus.yml
├── grafana/
├── docker-compose.yml
└── .env
```

---

## Running Locally

```bash
# Core services only
make start

# Core + observability (Prometheus, Grafana, Loki, Promtail) + Adminer
make start-obs

# Everything including pgAdmin and Kibana
make start-full

# Check health
docker compose ps
curl http://localhost/health
```

See [local_setup_guide.md](local_setup_guide.md) for full setup details including service profiles and endpoints.

---

## Backend Development

### Auto-reload

Uvicorn runs with `--reload`. Saving any file under `backend/app/` restarts the server within 1–2 seconds.

### Adding a new route

1. Create or edit a file in `backend/app/routes/`
2. Register the router in `backend/app/main.py` with `app.include_router(...)`
3. The Swagger UI at http://localhost/docs updates automatically

### Environment variables

All backend config is driven by `pydantic-settings` reading from `.env`. Key vars:

```
DATABASE_URL        postgresql://flint_fhir:<password>@postgres:5432/flint_fhir
ELASTICSEARCH_HOSTS http://elasticsearch:9200
REDIS_URL           redis://redis:6379
ENABLE_AUTH         false
CORS_ORIGINS        http://localhost,http://localhost:5173
SECRET_KEY          <random hex>
LOG_LEVEL           debug
```

### Running backend tests

```bash
docker compose exec backend pytest tests/ -v
docker compose exec backend pytest tests/ --cov=app
```

### Database access (CLI)

```bash
docker compose exec postgres psql -U flint_fhir -d flint_fhir
```

Or open **Adminer** at http://localhost:8181 (server: `postgres`, user: `flint_fhir`).

---

## Frontend Development

### Tech stack

- **React 18** with hooks (no class components)
- **TypeScript** — strict mode
- **Tailwind CSS** — utility-first styling
- **Vite 5** — dev server + bundler
- **Vitest + jsdom** — unit tests

### HMR on Windows Docker

Vite is configured with filesystem polling (`usePolling: true, interval: 500`) in `vite.config.ts`. This is required because Docker on Windows uses NTFS mounts that don't trigger inotify events. Changes to files in `frontend/src/` will be reflected in the browser within ~1 second.

Changes to files **outside** `frontend/src/` (e.g. `vite.config.ts`, `package.json`) are baked into the Docker image. After editing them:

```bash
docker compose up -d --build frontend
```

### Running frontend tests

```bash
docker compose exec frontend npm test
```

### Adding a dependency

```bash
# On the host (outside Docker), from frontend/
npm install <package>

# Then rebuild the image to install it inside the container
docker compose up -d --build frontend
```

---

## FHIR API Reference

All FHIR endpoints are accessible via the Nginx proxy at `http://localhost`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ValueSet` | Search value sets (supports `?name=`, `?url=`, `?status=`) |
| GET | `/ValueSet/{id}` | Get a specific ValueSet by ID |
| POST | `/ValueSet` | Create a ValueSet |
| PUT | `/ValueSet/{id}` | Update a ValueSet |
| DELETE | `/ValueSet/{id}` | Delete a ValueSet |
| GET | `/ValueSet/$expand` | Expand a ValueSet (`?url=...&count=N`) |
| GET | `/ValueSet/$validate-code` | Validate a code against a ValueSet |
| GET | `/ValueSet/$diff` | Diff two versions of a ValueSet |
| GET | `/CodeSystem` | Search code systems |
| GET | `/CodeSystem/{id}` | Get a specific CodeSystem |
| POST | `/CodeSystem` | Create a CodeSystem |
| GET | `/CodeSystem/$lookup` | Look up a code in a CodeSystem |
| GET | `/metadata` | FHIR CapabilityStatement |
| GET | `/analytics/summary` | Counts of resources and versions |
| GET | `/health` | Health check |

Interactive docs: http://localhost/docs

---

## Data Migration

To populate the server from PHIN VADS:

```bash
cd migration
python -m venv .venv && .venv/Scripts/activate  # Windows
pip install -r requirements.txt

# Single OID
python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1

# Full bulk import with resume support
python phinvads_migrate.py --resume checkpoint.json --log-level INFO
```

See [migration/README.md](../migration/README.md) for all flags.

---

## Observability

Start with `make start-obs` to include these services.

| Tool | URL | Purpose |
|------|-----|---------|
| Grafana | http://localhost:3001 | Dashboards (admin/admin by default) |
| Prometheus | http://localhost:9090 | Raw metrics scrape |
| Loki | http://localhost:3100 | Log aggregation API |
| Backend metrics | http://localhost:8000/metrics | Prometheus endpoint |

---

## Useful Commands

```bash
# Tail logs for a service
docker compose logs -f backend

# Open a shell in a container
docker compose exec backend bash
docker compose exec frontend sh

# Check DB schema
docker compose exec postgres psql -U flint_fhir -d flint_fhir -c "\dt"

# Flush Redis cache
docker compose exec redis redis-cli FLUSHALL

# Full rebuild
docker compose down && docker compose up -d --build

# Remove all data (nuclear reset)
docker compose down -v
```
