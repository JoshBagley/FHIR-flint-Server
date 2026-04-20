# Custom FHIR Terminology Server - Complete Setup Guide

## Quick Start (5 Minutes)

### Prerequisites
```bash
docker --version    # 20.10 or higher
docker-compose --version  # 2.0 or higher
```

### Step 1: Configure Environment

```bash
# Copy and edit .env
cp .env.example .env
# Set POSTGRES_PASSWORD, SECRET_KEY, GRAFANA_PASSWORD
```

Generate a secret key:
```bash
openssl rand -hex 32
```

### Step 2: Start the Stack

```bash
# Core services
docker compose up -d

# With admin tools (pgAdmin, Kibana)
docker compose --profile admin up -d

# Watch logs
docker compose logs -f
```

### Step 3: Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8000/metadata
curl http://localhost:9200/_cluster/health
```

### Service URLs

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| FHIR Server | http://localhost:8000 | None |
| API Docs (Swagger) | http://localhost:8000/docs | - |
| Web UI | http://localhost | - |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | None |
| pgAdmin | http://localhost:5050 | admin@example.com / admin *(admin profile)* |
| Kibana | http://localhost:5601 | None *(admin profile)* |

---

## Development Workflow

### Running the backend locally (outside Docker)

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

export DATABASE_URL="postgresql://phts:phts_dev_password@localhost:5432/phts"
export ELASTICSEARCH_HOSTS="http://localhost:9200"
export REDIS_URL="redis://localhost:6379"

uvicorn app.main:app --reload --port 8000
```

### Rebuilding after code changes

```bash
# Backend auto-reloads via volume mount + --reload flag
# For dependency changes, rebuild:
docker compose up --build backend -d

# Frontend auto-reloads via Vite HMR
# For new packages, rebuild:
docker compose up --build frontend -d
```

### Running tests

```bash
docker compose exec backend pytest tests/ -v --cov=app
```

---

## API Usage Examples

### Create a ValueSet

```bash
curl -X POST http://localhost:8000/ValueSet \
  -H "Content-Type: application/json" \
  -d '{
    "resourceType": "ValueSet",
    "url": "http://example.org/fhir/ValueSet/example",
    "name": "ExampleValueSet",
    "title": "Example Value Set",
    "status": "active",
    "compose": {
      "include": [{
        "system": "http://snomed.info/sct",
        "concept": [
          {"code": "38341003", "display": "Hypertension"},
          {"code": "73211009", "display": "Diabetes"}
        ]
      }]
    }
  }'
```

### Expand a ValueSet

```bash
curl "http://localhost:8000/ValueSet/\$expand?url=http://example.org/fhir/ValueSet/example"
```

### Validate a Code

```bash
curl "http://localhost:8000/ValueSet/\$validate-code?url=http://example.org/fhir/ValueSet/example&code=38341003&system=http://snomed.info/sct"
```

### Look Up a Code

```bash
curl "http://localhost:8000/CodeSystem/\$lookup?system=http://snomed.info/sct&code=38341003"
```

### Full-text Search

```bash
curl "http://localhost:8000/ValueSet?q=diabetes"
```

### Analytics

```bash
curl http://localhost:8000/analytics/summary
curl http://localhost:8000/\$stats
```

---

## Security

### Authentication

PH-TS supports three auth modes controlled by environment variables. The default (`ENABLE_AUTH=false`) is safe for demos — no changes break until you flip the flag.

#### Mode 1 — No auth (demo default)

```bash
ENABLE_AUTH=false   # default — /admin and /ai use X-API-Key if ADMIN_API_KEY is set
```

#### Mode 2 — Built-in JWT (production testing)

```bash
ENABLE_AUTH=true
AUTH_USERNAME=admin
AUTH_PASSWORD=<strong-password>   # generate: openssl rand -hex 16
SECRET_KEY=<generated-secret>     # generate: openssl rand -hex 32
# OIDC_ISSUER_URL must be unset or empty
```

Obtain a token:
```bash
curl -X POST http://localhost:8000/auth/token \
  -d "username=admin&password=<password>"
# returns {"access_token": "...", "token_type": "bearer", "expires_in": 3600}
```

Use the token:
```bash
curl http://localhost:8000/admin/sync/status \
  -H "Authorization: Bearer <access_token>"

curl -X POST http://localhost:8000/ai/suggest \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "diabetes"}'
```

#### Mode 3 — External OIDC (Keycloak / Auth0 / Azure AD)

```bash
ENABLE_AUTH=true
OIDC_ISSUER_URL=https://keycloak.example.com/realms/phts
# AUTH_USERNAME / AUTH_PASSWORD are ignored in this mode
# /auth/token endpoint is disabled — clients obtain tokens from the OIDC provider
```

SMART on FHIR discovery document (always available):
```bash
curl http://localhost:8000/auth/.well-known/smart-configuration
```

#### Auth testing checklist

**Local (built-in JWT):**
- [ ] Start stack with `ENABLE_AUTH=false` — confirm `/admin/sync/status` returns 200
- [ ] Set `ENABLE_AUTH=true`, `AUTH_USERNAME=admin`, `AUTH_PASSWORD=testpass` — confirm same endpoint returns 401
- [ ] `POST /auth/token` with correct credentials — confirm 200 + token returned
- [ ] Retry `/admin/sync/status` with `Authorization: Bearer <token>` — confirm 200
- [ ] Retry with expired/invalid token — confirm 401

**Production (`phts.informatixlabs.com`):**
- [ ] Confirm `ENABLE_AUTH=false` in `.env.demo` before go-live
- [ ] When ready: set `ENABLE_AUTH=true` + `AUTH_PASSWORD` in `.env.demo`, redeploy
- [ ] Run same checklist against `https://phts.informatixlabs.com`
- [ ] Confirm frontend AI assistant still works (it sends X-API-Key in demo mode; will need Bearer token wiring when ENABLE_AUTH=true)

> **Note — Keycloak (future):** For full SMART App Launch 2.0 compliance, SSO, and user management UI, consider replacing built-in JWT with a self-hosted Keycloak instance added as a Docker service. Set `OIDC_ISSUER_URL` to the Keycloak realm URL — no other backend changes required.

### Enable HTTPS (production)

```bash
# Generate self-signed cert for dev
mkdir -p infrastructure/docker/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout infrastructure/docker/nginx/ssl/key.pem \
  -out infrastructure/docker/nginx/ssl/cert.pem
```

Then uncomment the HTTPS server block in [nginx.conf](../infrastructure/docker/nginx/nginx.conf).

---

## Monitoring

### Prometheus Queries

```promql
# Request rate
rate(fhir_requests_total[5m])

# Average response time
rate(fhir_request_duration_seconds_sum[5m]) / rate(fhir_request_duration_seconds_count[5m])

# Error rate
rate(fhir_requests_total{status=~"5.."}[5m])
```

### Grafana Setup

1. Open http://localhost:3000
2. Datasources are auto-provisioned from [grafana/datasources/](../grafana/datasources/)
3. Add dashboards at Create → Import

---

## Backup & Recovery

### Database

```bash
# Backup
docker compose exec postgres pg_dump -U phts phts > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T postgres psql -U phts phts < backup_20260101.sql
```

### Elasticsearch

```bash
# Register snapshot repo
curl -X PUT "localhost:9200/_snapshot/backup_repo" \
  -H 'Content-Type: application/json' \
  -d '{"type":"fs","settings":{"location":"/backups"}}'

# Create snapshot
curl -X PUT "localhost:9200/_snapshot/backup_repo/snapshot_1"
```

---

## Troubleshooting

See [troubleshooting_guide.md](troubleshooting_guide.md) for detailed issue resolution.

### Quick checks

```bash
# All container statuses
docker compose ps

# Service-specific logs
docker compose logs backend -f
docker compose logs elasticsearch -f

# Elasticsearch cluster health
curl http://localhost:9200/_cluster/health?pretty

# Redis connectivity
docker compose exec redis redis-cli ping
```

### Common fixes

| Issue | Fix |
|-------|-----|
| Backend won't start | Check `docker compose logs backend` — usually a DB/ES connection timeout on first start |
| Elasticsearch yellow status | Normal for single-node; increase heap if OOM: `ES_JAVA_OPTS=-Xms1g -Xmx1g` |
| Out of memory | Increase Docker Desktop memory to 8GB+ (Settings → Resources) |
| 502 on localhost | Check `docker compose ps` — nginx, frontend, backend all need to be Up |

---

## Production Deployment

For cloud deployments, replace Docker services with managed equivalents:

| Docker service | AWS | Azure |
|---|---|---|
| postgres | RDS PostgreSQL | Azure Database for PostgreSQL |
| elasticsearch | OpenSearch Service | Azure Cognitive Search |
| redis | ElastiCache | Azure Cache for Redis |
| backend | ECS Fargate / EKS | AKS / App Service |
