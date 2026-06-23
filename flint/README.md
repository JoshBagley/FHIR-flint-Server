# Flint

A general-purpose, production-ready FHIR R4 server. Supports 16 resource types, full CRUD + version history, batch/transaction bundles, terminology operations, AI-assisted concept mapping, and full observability via Prometheus, Grafana, and Loki.

## Features

### Clinical & Administrative Resources
- 16 FHIR R4 resource types with full CRUD, versioning, ETag enforcement, and paginated search
- `POST /` Bundle endpoint — batch (per-entry error isolation) and transaction (atomic rollback)
- `urn:uuid:` reference resolution within transaction bundles
- Version history (`/_history`) and named version read (`/_history/{vid}`) on every resource
- Optimistic locking via `If-Match: W/"N"` — 412 on conflict

### Terminology & Vocabulary
- FHIR R4 operations: `$expand`, `$validate-code`, `$validate-batch`, `$lookup`, `$translate`, `$subsumes`, `$diff`
- SNOMED CT ECL expansion via implicit ValueSet URLs (`fhir_vs=isa/{id}`, `fhir_vs=refset/{id}`)
- ConceptMap CRUD + `$translate` for cross-system code mapping (local + tx.fhir.org fallback)
- `$subsumes` hierarchy checks for SNOMED CT, LOINC, and local CodeSystems
- HL7 v2 table validation — offline (imported) or delegated to `tx.fhir.org`
- SDO connectors: SNOMED CT, ICD-10-CM, ICD-9-CM, LOINC, RxNorm, VSAC

### Platform
- Fast full-text search with Elasticsearch
- AI-powered concept search and mapping (Anthropic, OpenAI, or Gemini)
- Dynamic CapabilityStatement (`GET /metadata`) reflecting runtime auth config
- Prometheus metrics + Grafana dashboards + Loki log aggregation
- Modern React/TypeScript UI with Value Set Builder

## Supported Resource Types

| Category | Resources |
|---|---|
| Terminology | `ValueSet`, `CodeSystem`, `ConceptMap` |
| Clinical | `Patient`, `Observation`, `Condition`, `Encounter`, `AllergyIntolerance`, `Immunization` |
| Administrative | `Organization`, `Practitioner`, `PractitionerRole`, `Location` |
| Medications & Reports | `MedicationRequest`, `Procedure`, `DiagnosticReport` |

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
- Dashboard: **Flint Server Overview** at [http://localhost:3001](http://localhost:3001)
- Tracks: request rates, latency (p50/p95/p99), error rates, resource counts

### Logs (Loki + Grafana)
- Dashboard: **Flint Logs** at [http://localhost:3001](http://localhost:3001)
- Every container's stdout/stderr is collected by Promtail and queryable in Grafana Explore
- Use LogQL to filter: `{service="backend"} |= "POST /ValueSet"`

### Direct log access
```bash
docker compose logs backend -f
docker compose logs backend --tail=200 | grep "POST\|PUT\|DELETE"
```

## Clinical Resources

```bash
# Create a Patient
curl -X POST http://localhost/Patient -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"Patient","name":[{"family":"Smith","given":["John"]}],"gender":"male","birthDate":"1990-01-15"}'

# Search by name
curl "http://localhost/Patient?family=Smith&_count=20"

# Create an Observation linked to a Patient
curl -X POST http://localhost/Observation -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"Observation","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"85354-9"}]},"subject":{"reference":"Patient/{id}"},"valueQuantity":{"value":120,"unit":"mmHg"}}'

# Atomic transaction: Patient + Observation with urn:uuid reference
curl -X POST http://localhost/ -H "Content-Type: application/fhir+json" -d '{
  "resourceType": "Bundle", "type": "transaction",
  "entry": [
    {"fullUrl":"urn:uuid:pt","resource":{"resourceType":"Patient","name":[{"family":"Jones"}]},"request":{"method":"POST","url":"Patient"}},
    {"resource":{"resourceType":"Observation","status":"final","code":{"text":"BP"},"subject":{"reference":"urn:uuid:pt"}},"request":{"method":"POST","url":"Observation"}}
  ]
}'
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

- [Product Roadmap & Gap Tracker](docs/PRODUCT_ROADMAP.md) — capability gaps vs major FHIR servers, phased implementation plan, ONC certification pathway
- [FHIR API Reference](docs/FHIR_API_REFERENCE.md) — all endpoints, operations, MCP integration, and sample calls
- [Architecture](docs/ARCHITECTURE.md)
- [Development Setup](docs/DEVELOPMENT.md)
- [Local Setup Guide](docs/local_setup_guide.md)
- [Validation Guide](docs/validation_guide.md)
- [Troubleshooting](docs/troubleshooting_guide.md)
- [Deployment Guide](docs/deployment_guide.md)

## License

MIT License — see LICENSE file for details.
