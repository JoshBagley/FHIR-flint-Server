# PH-TS Local Development Setup Guide

## Prerequisites

### Required Software

1. **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
   ```bash
   docker --version        # 20.10.0+
   docker compose version  # 2.0.0+
   ```

2. **Git**
   ```bash
   git --version  # 2.0+
   ```

3. **Python 3.11+** _(optional — migration tool only)_
   ```bash
   python --version
   ```

> **Windows users**: Make sure Docker Desktop is running before any `docker compose` commands. If you see `open //./pipe/dockerDesktopLinuxEngine`, start Docker Desktop and wait ~30 seconds.

---

## Quick Start

```bash
# 1. Clone / navigate to the project
cd ph-ts

# 2. Copy environment file (first time only)
cp .env.example .env   # edit values as needed

# 3. Start services (choose one)
make start          # Core services only
make start-obs      # Core + observability (Prometheus, Grafana, Loki, Promtail) + Adminer
make start-full     # Everything including pgAdmin and Kibana

# 4. Confirm everything is healthy (~60 s)
docker compose ps

# 5. Open the web UI
# http://localhost
```

---

## Service Endpoints

| Service | URL | Notes |
|---------|-----|-------|
| **Web UI** | http://localhost | Nginx reverse proxy |
| **API** | http://localhost/ValueSet | FHIR R4 endpoints |
| **API Docs** | http://localhost/docs | FastAPI Swagger UI |
| **Backend (direct)** | http://localhost:8000 | FastAPI dev port |
| **Frontend (direct)** | http://localhost:5173 | Vite dev server |
| **Adminer (DB UI)** | http://localhost:8181 | PostgreSQL browser |
| **Grafana** | http://localhost:3001 | Metrics dashboards |
| **Prometheus** | http://localhost:9090 | Raw metrics |
| **Elasticsearch** | http://localhost:9200 | Search engine API |
| **PostgreSQL** | localhost:5432 | Direct DB access |
| **Redis** | localhost:6379 | Cache / queue |

---

## Environment Configuration

The `.env` file controls all credentials and feature flags. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | `change_me_in_production` | PostgreSQL password |
| `SECRET_KEY` | _(generated)_ | JWT signing key |
| `ENABLE_AUTH` | `false` | Toggle API authentication |
| `CORS_ORIGINS` | `http://localhost,...` | Allowed frontend origins |
| `GRAFANA_USER` | `admin` | Grafana login |
| `GRAFANA_PASSWORD` | `admin` | Grafana login |

> **Change `POSTGRES_PASSWORD` and `SECRET_KEY` before any non-local deployment.**

---

## Adminer — Database Browser

Open http://localhost:8181 and log in:

| Field | Value |
|-------|-------|
| System | PostgreSQL |
| Server | `postgres` |
| Username | `phts` |
| Password | _(value of `POSTGRES_PASSWORD` in `.env`)_ |
| Database | `phts` |

---

## Verification

```bash
# All services healthy?
docker compose ps

# Backend health
curl http://localhost/health

# FHIR metadata
curl http://localhost/metadata

# Test a ValueSet search
curl "http://localhost/ValueSet?name=sex"

# Elasticsearch cluster
curl http://localhost:9200/_cluster/health

# Redis ping
docker compose exec redis redis-cli ping
```

---

## Loading Sample Data (Migration Tool)

The migration tool pulls ValueSets and CodeSystems from the public **PHIN VADS** FHIR STU3 API and imports them into your local server.

```bash
cd ph-ts/migration

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# Import a single ValueSet by OID
python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1

# Bulk import all ValueSets
python phinvads_migrate.py --resource valueset

# Dry run — no changes to server
python phinvads_migrate.py --dry-run --output-dir ./exported

# Resume an interrupted bulk run
python phinvads_migrate.py --resume checkpoint.json
```

See [migration/README.md](../migration/README.md) for full options.

---

## Development Workflow

### Backend changes

Backend source is volume-mounted into the container. Uvicorn runs with `--reload`, so changes to Python files in `backend/app/` are picked up automatically.

```bash
# View live backend logs
docker compose logs -f backend
```

### Frontend changes

`frontend/src/` is volume-mounted and Vite polls for changes every 500 ms (required for Windows Docker volume mounts). Most edits hot-reload in the browser automatically.

Changes to files **outside** `src/` — such as `vite.config.ts`, `package.json`, or `tailwind.config.js` — require a container rebuild:

```bash
docker compose up -d --build frontend
```

### Rebuild a single service

```bash
docker compose up -d --build backend
docker compose up -d --build frontend
```

### Rebuild everything from scratch

```bash
docker compose down
docker compose up -d --build
```

---

## Stopping and Cleanup

```bash
# Stop services, keep data volumes
docker compose down

# Stop services and delete all data (full reset)
docker compose down -v
```

---

## Logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f nginx
```

---

## Make Commands

The `Makefile` provides shortcuts for the most common workflows:

| Command | Description |
|---------|-------------|
| `make start` | Start core services (postgres, elasticsearch, redis, backend, frontend, nginx) |
| `make start-obs` | Core + observability (Prometheus, Grafana, Loki, Promtail) + Adminer |
| `make start-full` | All of the above + pgAdmin and Kibana |
| `make stop` | Stop all running services |
| `make restart` | Restart all services |
| `make logs` | Tail logs for all services |
| `make test` | Run backend test suite |
| `make migrate` | Run database migrations |
| `make clean` | Stop and remove all data volumes (full reset) |

---

## Optional Admin Services

pgAdmin and Kibana are included but disabled by default. Use `make start-full` to include them, or start them individually with the `admin` profile:

```bash
docker compose --profile admin up -d
```

| Service | URL | Credentials |
|---------|-----|-------------|
| pgAdmin | http://localhost:5050 | see `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` in `.env` |
| Kibana | http://localhost:5601 | no auth (dev mode) |
