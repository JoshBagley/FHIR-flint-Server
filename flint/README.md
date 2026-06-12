# Flint-FHIR

A general-purpose, production-ready FHIR R4 terminology server. Supports value set authoring, code validation, AI-assisted concept mapping, HL7 v2 message validation, and full observability via Prometheus, Grafana, and Loki.

## Features

- Fast full-text search with Elasticsearch
- AI-powered concept search and mapping (Anthropic, OpenAI, or Gemini)
- FHIR R4 operations: `$expand`, `$validate-code`, `$validate-batch`, `$lookup`, `$translate`, `$subsumes`, `$diff`
- SNOMED CT ECL expansion via implicit ValueSet URLs (`fhir_vs=isa/{id}`, `fhir_vs=refset/{id}`)
- LOINC hierarchy properties via `$lookup?property=parent&property=child` (requires LOINC credentials)
- ConceptMap CRUD + `$translate` for cross-system code mapping (local + tx.fhir.org fallback)
- `$subsumes` hierarchy checks for SNOMED CT (tx.fhir.org), LOINC (fhir.loinc.org), and local CodeSystems
- HL7 v2 table validation — offline (imported) or delegated to `tx.fhir.org`
- SDO connectors: SNOMED CT, ICD-10-CM, ICD-9-CM, LOINC, RxNorm, VSAC
- Version history with git-style diffs for every resource
- Observability: Prometheus metrics + Grafana dashboards + Loki log aggregation
- Modern React/TypeScript UI with Value Set Builder

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env — set AI_PROVIDER and matching API key

# Start all services
docker compose up -d

# Access
# Web UI:       http://localhost
# API:          http://localhost:8000
# API Docs:     http://localhost:8000/docs
# Grafana:      http://localhost:3001   (admin / admin)
# Prometheus:   http://localhost:9090
# Adminer:      http://localhost:8181
```

## Service Ports

| Port | Service |
|------|---------|
| 80 | Nginx (primary entry point) |
| 8000 | FastAPI backend |
| 5173 | Vite frontend dev server |
| 5432 | PostgreSQL |
| 9200 | Elasticsearch |
| 6379 | Redis |
| 3001 | Grafana dashboards |
| 9090 | Prometheus metrics |
| 3100 | Loki log aggregation |
| 8181 | Adminer database UI |

## Observability

### Metrics (Prometheus + Grafana)
- Dashboard: **Flint-FHIR Server Overview** at [http://localhost:3001](http://localhost:3001)
- Tracks: request rates, latency (p50/p95/p99), error rates, resource counts

### Logs (Loki + Grafana)
- Dashboard: **Flint-FHIR Logs** at [http://localhost:3001](http://localhost:3001)
- Every container's stdout/stderr is collected by Promtail and queryable in Grafana Explore
- Use LogQL to filter: `{service="backend"} |= "POST /ValueSet"`

### Direct log access
```bash
docker compose logs backend -f
docker compose logs backend --tail=200 | grep "POST\|PUT\|DELETE"
```

## Terminology Validation

```bash
# Validate a code against a ValueSet
curl "http://localhost/ValueSet/\$validate-code?url=http://hl7.org/fhir/ValueSet/administrative-gender&code=M"

# Look up a LOINC code
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6"

# Batch validate codes from an HL7 v2 message
curl -X POST http://localhost/ValueSet/\$validate-batch \
  -H "Content-Type: application/json" \
  -d '{"items":[
    {"code":"M",       "system":"http://terminology.hl7.org/CodeSystem/v2-0001"},
    {"code":"94500-6", "system":"http://loinc.org"},
    {"code":"J12.82",  "system":"http://hl7.org/fhir/sid/icd-10-cm"}
  ]}'
```

See [docs/validation_guide.md](docs/validation_guide.md) for full documentation.

## Data Import

```bash
# HL7 FHIR R4 core code systems
python migration/import_hl7_core.py --target-url http://localhost

# HL7 v2 table code systems (enables offline v2 validation)
python migration/import_hl7_v2_tables.py --target-url http://localhost

# ICD-9-CM (~14k codes)
python migration/import_icd9cm.py --target-url http://localhost

# ISO 3166 country codes
python migration/import_iso3166.py --target-url http://localhost

# CDC CVX vaccine codes
python migration/import_cvx.py --target-url http://localhost
```

## Documentation

- [FHIR API Reference](docs/FHIR_API_REFERENCE.md) — all endpoints, operations, MCP integration, and sample calls
- [Architecture](docs/ARCHITECTURE.md)
- [Development Setup](docs/DEVELOPMENT.md)
- [Local Setup Guide](docs/local_setup_guide.md)
- [Validation Guide](docs/validation_guide.md)
- [Troubleshooting](docs/troubleshooting_guide.md)
- [Deployment Guide](docs/deployment_guide.md)

## License

MIT License — see LICENSE file for details.
