# Flint FHIR API Reference

Flint is a general-purpose FHIR R4 server built on FastAPI. Base URL: `http://localhost:8000`  
All responses use `Content-Type: application/fhir+json`.

---

## Table of Contents

1. [Metadata & Health](#1-metadata--health)
2. [ValueSet — Search & Read](#2-valueset--search--read)
3. [ValueSet — FHIR Operations](#3-valueset--fhir-operations)
4. [ValueSet — Flint Extensions](#4-valueset--flint-extensions)
5. [CodeSystem — Search & Read](#5-codesystem--search--read)
6. [CodeSystem — FHIR Operations](#6-codesystem--fhir-operations)
7. [ConceptMap](#7-conceptmap)
7b. [Clinical & Administrative Resources](#7b-clinical--administrative-resources) — including Patch, Conditional, $validate, History, $match
7c. [Bundle — Batch & Transaction](#7c-bundle--batch--transaction)
8. [SDO / External Vocabulary Search](#8-sdo--external-vocabulary-search)
9. [AI Assist](#9-ai-assist)
10. [MCP Chat](#10-mcp-chat)
11. [Admin / Sync](#11-admin--sync)
12. [CRUD — Create, Update, Delete](#12-crud--create-update-delete)
13. [MCP Integration (Claude Code / Claude Desktop)](#13-mcp-integration-claude-code--claude-desktop)

---

## 1. Metadata & Health

```http
GET /health
```
Returns `200 OK` when the service is up.

```http
GET /metadata
```
FHIR R4 CapabilityStatement — lists supported resource types, operations, and server info.

```http
GET /analytics/summary
```
Returns server-wide counts: total ValueSets, CodeSystems, archived resources, total versions.

---

## 2. ValueSet — Search & Read

### List / Search

```http
GET /ValueSet
```

All list requests default to `_summary=true` (metadata only — no concept arrays). Append `_summary=false` for full resources.

#### Search Parameters

| Parameter | Description | Example |
|---|---|---|
| `name` | Searches name, title, url, and identifier values (multi-word aware) | `?name=Reporting Source` |
| `status` | `active`, `draft`, `retired`, `unknown` | `?status=active` |
| `source` | Import source: `phinvads`, `vsac`, `hl7`, `hl7v2`, `icd9cm`, `internal` | `?source=phinvads` |
| `context-value-code` | Disease/condition view slug | `?context-value-code=covid-19-case-notification` |
| `identifier` | OID (bare or `urn:oid:` prefix); also matches OID in URL path | `?identifier=2.16.840.1.114222.4.11.836` |
| `_archived` | `true` to return archived resources only | `?_archived=true` |
| `_count` | Page size | `?_count=20` |
| `_offset` | Page offset | `?_offset=40` |

> **Search note:** The `name` parameter searches four fields simultaneously — FHIR `name` (machine-readable), `title` (human-readable, supports multi-word), `url`, and `identifier[].value`. Typing a full or partial OID in `name` will match resources by OID.

```bash
# All active ValueSets
curl "http://localhost:8000/ValueSet?status=active"

# Multi-word title search (matches "Reporting Source Type")
curl "http://localhost:8000/ValueSet?name=Reporting+Source"

# Search by partial OID
curl "http://localhost:8000/ValueSet?name=2.16.840.1.114222"

# Filter by disease view
curl "http://localhost:8000/ValueSet?context-value-code=influenza"

# Filter by source
curl "http://localhost:8000/ValueSet?source=phinvads"

# Exact OID lookup
curl "http://localhost:8000/ValueSet?identifier=2.16.840.1.114222.4.11.836"
```

### Read a Single Resource

```http
GET /ValueSet/{id}
```

```bash
curl "http://localhost:8000/ValueSet/{id}"
```

Returns the full FHIR R4 ValueSet including `compose.include` with all concepts.

---

## 3. ValueSet — FHIR Operations

### `$expand`

Expands a ValueSet and returns all codes in `expansion.contains`.

```http
GET /ValueSet/$expand?url={canonical_url}&count={n}&filter={text}
```

```bash
# Expand by canonical URL
curl "http://localhost:8000/ValueSet/\$expand?url=https://phinvads.cdc.gov/vads/ViewValueSet.action?id=2.16.840.1.114222.4.11.836"

# With text filter
curl "http://localhost:8000/ValueSet/\$expand?url={url}&filter=fever&count=20"

# SNOMED CT — all descendants of a concept (implicit ValueSet, isa)
curl "http://localhost:8000/ValueSet/\$expand?url=http://snomed.info/sct?fhir_vs=isa/73211009&count=50"

# SNOMED CT — ECL subsumption shorthand (delegates to tx.fhir.org)
curl "http://localhost:8000/ValueSet/\$expand?url=http://snomed.info/sct?fhir_vs=ecl/%3C%3C73211009&count=50"

# SNOMED CT — refset membership
curl "http://localhost:8000/ValueSet/\$expand?url=http://snomed.info/sct?fhir_vs=refset/723264001&count=50"
```

> **SNOMED ECL scope:** Simple subsumption (`<`/`<<`) and refset (`^`) patterns are supported. Complex ECL (attribute refinement, `AND`/`OR`/`MINUS`, post-coordination) is not yet supported — a Snowstorm backend is required for those expressions.

### `$validate-code`

Checks whether a given code is a member of a ValueSet.

```http
GET /ValueSet/$validate-code?url={url}&system={system}&code={code}
```

```bash
curl "http://localhost:8000/ValueSet/\$validate-code?url={url}&system=http://snomed.info/sct&code=840539006"
```

### `$validate-batch`

Validates multiple codes in a single call (optimized for HL7 v2 message validation).

```http
POST /ValueSet/$validate-batch
Content-Type: application/json
```

```bash
curl -X POST http://localhost:8000/ValueSet/\$validate-batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"code": "M",       "system": "http://terminology.hl7.org/CodeSystem/v2-0001"},
      {"code": "94500-6", "system": "http://loinc.org"},
      {"code": "J12.82",  "system": "http://hl7.org/fhir/sid/icd-10-cm"}
    ]
  }'
```

### `$concept-search`

Full-text search across concepts in all stored ValueSets.

```http
GET /ValueSet/$concept-search?q={term}&limit={n}
```

```bash
curl "http://localhost:8000/ValueSet/\$concept-search?q=sepsis&limit=10"
```

### `$diff`

Compares two versions of a ValueSet.

```http
GET /ValueSet/{id}/$diff?v1={version}&v2={version}
```

---

## 4. ValueSet — Flint Extensions

These endpoints are Flint-specific and not part of the FHIR spec.

### Disease / Condition Views

PHIN VADS "program views" are modeled as `useContext` entries. 107 views are configured in `backend/app/disease_views.json`.

```bash
# List all 107 views with live ValueSet counts
curl "http://localhost:8000/ValueSet/\$views"

# Add a view tag to a ValueSet
curl -X POST "http://localhost:8000/ValueSet/\$tag-view?resource_id={id}&view_id=covid-19-case-notification"

# Remove a view tag
curl -X DELETE "http://localhost:8000/ValueSet/\$tag-view?resource_id={id}&view_id=covid-19-case-notification"
```

### Version History & Audit

```bash
# Version history
curl "http://localhost:8000/ValueSet/{id}/_history"

# Audit log (all actions on this resource)
curl "http://localhost:8000/ValueSet/{id}/\$audit"
```

### Archive / Restore

```bash
# Archive (soft delete)
curl -X PATCH "http://localhost:8000/ValueSet/{id}/\$archive"

# Restore from archive
curl -X PATCH "http://localhost:8000/ValueSet/{id}/\$archive?restore=true"
```

---

## 5. CodeSystem — Search & Read

Supports the same `name` multi-field search as ValueSet (name, title, url, identifier). The `identifier` parameter also resolves PHIN VADS CodeSystems whose OID is embedded in the URL path.

```bash
# List all
curl "http://localhost:8000/CodeSystem"

# Search by name or title (multi-word aware)
curl "http://localhost:8000/CodeSystem?name=Notifiable+Event"

# Search by partial OID (matches url field)
curl "http://localhost:8000/CodeSystem?name=2.16.840.1.114222.4.5"

# Exact OID lookup — works even when OID is in URL path, not identifier[]
curl "http://localhost:8000/CodeSystem?identifier=2.16.840.1.114222.4.5.277"

# Filter by content type
curl "http://localhost:8000/CodeSystem?content=complete"
curl "http://localhost:8000/CodeSystem?content=fragment"

# Read a single CodeSystem
curl "http://localhost:8000/CodeSystem/{id}"
```

---

## 6. CodeSystem — FHIR Operations

### `$lookup`

Retrieves display name and properties for a specific code.

```http
GET /CodeSystem/$lookup?system={system_url}&code={code}
```

```bash
# SNOMED CT
curl "http://localhost:8000/CodeSystem/\$lookup?system=http://snomed.info/sct&code=840539006"

# LOINC
curl "http://localhost:8000/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6"

# ICD-10-CM
curl "http://localhost:8000/CodeSystem/\$lookup?system=http://hl7.org/fhir/sid/icd-10-cm&code=U07.1"

# RxNorm
curl "http://localhost:8000/CodeSystem/\$lookup?system=http://www.nlm.nih.gov/research/umls/rxnorm&code=1049502"

# LOINC hierarchy properties (requires LOINC credentials)
curl "http://localhost:8000/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6&property=parent&property=child"
```

### `$subsumes`

Tests whether one code is subsumed by (a child of) another in a hierarchy.

```http
GET /CodeSystem/$subsumes?system={system}&codeA={code}&codeB={code}
```

---

## 7. ConceptMap

ConceptMaps enable cross-system code translation. Can be created manually or generated by the AI mapping tool.

### Demo ConceptMaps (pre-loaded)

| Name | URL | Mappings |
|---|---|---|
| HL7 v2 Sex → FHIR Administrative Gender | `http://flint.local/ConceptMap/v2-sex-to-fhir-gender` | M/F/U/A/N/O → male/female/unknown/other |
| SNOMED CT → ICD-10-CM Notifiable Conditions | `http://flint.local/ConceptMap/snomed-to-icd10cm-notifiable` | COVID-19, Influenza, Measles, Mumps, Pertussis, Tetanus, Yellow Fever, Brucellosis, West Nile, Gastroenteritis |

```bash
# List all ConceptMaps
curl "http://localhost:8000/ConceptMap"

# Read by ID
curl "http://localhost:8000/ConceptMap/{id}"

# Translate v2 sex code to FHIR gender
curl "http://localhost:8000/ConceptMap/\$translate?url=http://flint.local/ConceptMap/v2-sex-to-fhir-gender&system=http://terminology.hl7.org/CodeSystem/v2-0001&code=F"

# Translate SNOMED condition code to ICD-10-CM
curl "http://localhost:8000/ConceptMap/\$translate?url=http://flint.local/ConceptMap/snomed-to-icd10cm-notifiable&system=http://snomed.info/sct&code=840539006"

# Translate without specifying a map (searches all ConceptMaps for a match)
curl "http://localhost:8000/ConceptMap/\$translate?code=840539006&system=http://snomed.info/sct&target=http://hl7.org/fhir/sid/icd-10-cm"
```

---

## 7b. Clinical & Administrative Resources

All 13 clinical/admin resource types share the same FHIR-standard HTTP interface. Every resource supports:

| Operation | HTTP |
|---|---|
| Create | `POST /{Type}` → 201 + `Location` + `ETag` |
| Conditional create | `POST /{Type}` with `If-None-Exist: {search-params}` header |
| Read | `GET /{Type}/{id}` → 200 + `ETag` + `Last-Modified` |
| Update | `PUT /{Type}/{id}` → 200 (use `If-Match: W/"N"` for optimistic locking; 412 on conflict) |
| Conditional update | `PUT /{Type}?{search-params}` — update if 1 match; create if 0; 412 if multiple |
| Patch | `PATCH /{Type}/{id}` with JSON Patch ops (RFC 6902) — partial update, validated before persist |
| Delete | `DELETE /{Type}/{id}` → 204 |
| Conditional delete | `DELETE /{Type}?{search-params}` — deletes all matching resources |
| Search | `GET /{Type}?{params}&_count=20&_offset=0&_sort=date` → Bundle searchset |
| Instance history | `GET /{Type}/{id}/_history` → Bundle history |
| Type history | `GET /{Type}/_history?_since=&_count=` → all changes for that resource type |
| System history | `GET /_history?_since=&_count=` → all changes across all resource types |
| Versioned read | `GET /{Type}/{id}/_history/{vid}` → specific version |
| Validate | `POST /{Type}/$validate` → OperationOutcome (structural validation via Pydantic) |
| Audit log | `GET /{Type}/{id}/$audit` → Flint audit entries |

### Supported types and search parameters

| Resource | Key search parameters |
|---|---|
| `Patient` | `family`, `given`, `name`, `birthdate`, `gender`, `identifier` |
| `Observation` | `patient`, `code`, `category`, `status` |
| `Condition` | `patient`, `code`, `clinical-status`, `category` |
| `Encounter` | `patient`, `status`, `class` |
| `AllergyIntolerance` | `patient`, `code`, `clinical-status`, `criticality` |
| `Immunization` | `patient`, `vaccine-code`, `date`, `status` |
| `Organization` | `name`, `type` |
| `Practitioner` | `name`, `family`, `given`, `gender` |
| `PractitionerRole` | `practitioner`, `organization`, `role`, `specialty` |
| `Location` | `name`, `status` |
| `MedicationRequest` | `patient`, `status`, `intent`, `medication-code` |
| `Procedure` | `patient`, `code`, `status` |
| `DiagnosticReport` | `patient`, `code`, `category`, `status` |

All search endpoints support `_count`, `_offset`, and `_sort` (values: `name`, `-name`, `date`, `-date`, `status`, `-status`). Results are wrapped in a `Bundle` with `link[rel=next/prev/first]` for pagination.

```bash
# Create a Patient
curl -X POST http://localhost/Patient \
  -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"Patient","name":[{"family":"Smith","given":["John"]}],"gender":"male","birthDate":"1990-01-15"}'

# Search by family name (paginated)
curl "http://localhost/Patient?family=Smith&_count=10&_offset=0"

# Create an Observation referencing a Patient
curl -X POST http://localhost/Observation \
  -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"Observation","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"85354-9","display":"Blood pressure panel"}]},"subject":{"reference":"Patient/{id}"},"valueQuantity":{"value":120,"unit":"mmHg"}}'

# Get all Observations for a patient, including the referenced Patient resource
curl "http://localhost/Observation?patient=Patient/{id}&_include=Observation:subject"

# Update with optimistic locking
curl -X PUT http://localhost/Patient/{id} \
  -H "Content-Type: application/fhir+json" \
  -H "If-Match: W/\"1\"" \
  -d '{"resourceType":"Patient","id":"{id}","name":[{"family":"Smith"}],"active":true}'

# Read instance history
curl "http://localhost/Patient/{id}/_history"

# Read a specific version
curl "http://localhost/Patient/{id}/_history/1"
```

### JSON Patch (RFC 6902)

Partial updates using a list of patch operations. The result is validated against the resource schema before persisting.

```bash
# Patch Patient — change gender and mark active
curl -X PATCH http://localhost/Patient/{id} \
  -H "Content-Type: application/json-patch+json" \
  -H "If-Match: W/\"1\"" \
  -d '[
    {"op": "replace", "path": "/gender", "value": "female"},
    {"op": "add",     "path": "/active", "value": true}
  ]'

# Patch Observation — update status
curl -X PATCH http://localhost/Observation/{id} \
  -H "Content-Type: application/json-patch+json" \
  -d '[{"op": "replace", "path": "/status", "value": "amended"}]'
```

### Conditional Interactions

```bash
# Conditional create — only create if no Patient with this identifier exists
curl -X POST http://localhost/Patient \
  -H "Content-Type: application/fhir+json" \
  -H "If-None-Exist: identifier=MRN-12345" \
  -d '{"resourceType":"Patient","identifier":[{"value":"MRN-12345"}],"name":[{"family":"Jones"}]}'

# Conditional update — update the Patient matching this identifier (creates if none exist)
curl -X PUT "http://localhost/Patient?identifier=MRN-12345" \
  -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"Patient","identifier":[{"value":"MRN-12345"}],"name":[{"family":"Jones","given":["Alice"]}],"active":true}'

# Conditional delete — delete all Observations with this status
curl -X DELETE "http://localhost/Observation?status=entered-in-error"
```

### `$validate`

Validates a resource body against the Pydantic R4 schema. Returns `OperationOutcome` — no data is persisted.

```bash
# Validate a Patient resource
curl -X POST http://localhost/Patient/\$validate \
  -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"Patient","gender":"male","birthDate":"1990-01-15"}'

# Validate an Observation (will error if status is missing)
curl -X POST http://localhost/Observation/\$validate \
  -H "Content-Type: application/fhir+json" \
  -d '{"resourceType":"Observation","code":{"text":"BP"}}'
# → 200 with OperationOutcome.issue[].severity = "error" for missing required field
```

### `Patient/$match`

Probabilistic patient matching. Score breakdown: identifier match (+0.5), birthDate match (+0.3), family name match (+0.2). Match grade: `certain` (≥0.8), `probable` (≥0.5), `possible` (<0.5).

```bash
curl -X POST http://localhost/Patient/\$match \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Parameters",
    "parameter": [
      {
        "name": "resource",
        "resource": {
          "resourceType": "Patient",
          "identifier": [{"value": "MRN-12345"}],
          "name": [{"family": "Smith"}],
          "birthDate": "1990-01-15"
        }
      },
      {"name": "count", "valueInteger": 5},
      {"name": "onlyCertainMatches", "valueBoolean": false}
    ]
  }'
```

Response includes `search.score` and a `match-grade` extension (`certain`/`probable`/`possible`) on each Bundle entry.

### History Endpoints

```bash
# All changes to a specific Patient instance
curl "http://localhost/Patient/{id}/_history"

# All changes to any Patient (type-level history)
curl "http://localhost/Patient/_history?_count=50&_since=2026-01-01T00:00:00Z"

# All changes across all resource types (system history)
curl "http://localhost/_history?_count=100&_since=2026-06-01T00:00:00Z"
```

All history endpoints return a `Bundle` with `type: history`. Each entry includes `request` (method + URL) and `response` (status + ETag) alongside the resource snapshot.

---

## 7c. Bundle — Batch & Transaction

`POST /` accepts a FHIR R4 Bundle with `type: "batch"` or `type: "transaction"`.

- **batch** — entries are processed independently; one failure does not affect others; response is a `batch-response` Bundle with one entry per input entry, each containing `response.status`
- **transaction** — all entries execute under a single PostgreSQL transaction; any entry failure rolls back the entire bundle and returns a top-level `OperationOutcome`

### `urn:uuid:` reference resolution

Assign a temporary `fullUrl` of `urn:uuid:{temp-id}` to POST entries. Later entries can reference `urn:uuid:{temp-id}` in any string field (e.g. `subject.reference`) and Flint will replace it with the actual `ResourceType/{assigned-id}` before saving.

### Per-entry conditional behavior

| Header in `entry.request` | Effect |
|---|---|
| `ifNoneExist: {search-params}` | On POST: search first; return existing if exactly 1 match; 412 if multiple |
| `ifMatch: W/"N"` | On PUT: 412 if server version does not match |

```bash
# Batch: create two independent resources
curl -X POST http://localhost/ \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Bundle", "type": "batch",
    "entry": [
      {"resource":{"resourceType":"Organization","name":"Acme Clinic"},"request":{"method":"POST","url":"Organization"}},
      {"resource":{"resourceType":"Location","name":"Main Clinic","status":"active"},"request":{"method":"POST","url":"Location"}}
    ]
  }'

# Transaction: Patient + linked Observation with urn:uuid: reference
curl -X POST http://localhost/ \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Bundle", "type": "transaction",
    "entry": [
      {
        "fullUrl": "urn:uuid:pt-1",
        "resource": {"resourceType":"Patient","name":[{"family":"Jones","given":["Sarah"]}],"gender":"female"},
        "request": {"method":"POST","url":"Patient"}
      },
      {
        "resource": {
          "resourceType":"Observation","status":"final",
          "code":{"coding":[{"system":"http://loinc.org","code":"8302-2","display":"Body height"}]},
          "subject":{"reference":"urn:uuid:pt-1"},
          "valueQuantity":{"value":165,"unit":"cm"}
        },
        "request": {"method":"POST","url":"Observation"}
      }
    ]
  }'

# Idempotent create: only creates if no match found
curl -X POST http://localhost/ \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType":"Bundle","type":"batch",
    "entry":[{
      "resource":{"resourceType":"Organization","name":"Regional Lab"},
      "request":{"method":"POST","url":"Organization","ifNoneExist":"name=Regional Lab"}
    }]
  }'
```

---

## 8. SDO / External Vocabulary Search

Live search against external code systems via Flint connectors.

```bash
# List available systems and their availability
curl "http://localhost:8000/sdo/systems"
```

```bash
# SNOMED CT (via Snowstorm public server)
curl "http://localhost:8000/sdo/search?system=snomed&q=sepsis&limit=10"

# LOINC (via fhir.loinc.org or NLM ClinicalTables fallback)
curl "http://localhost:8000/sdo/search?system=loinc&q=glucose&limit=10"

# ICD-10-CM (via NLM ClinicalTables)
curl "http://localhost:8000/sdo/search?system=icd10cm&q=pneumonia&limit=10"

# RxNorm (via NLM RxNav)
curl "http://localhost:8000/sdo/search?system=rxnorm&q=amoxicillin&limit=10"

# VSAC (requires UMLS_API_KEY in .env)
curl "http://localhost:8000/sdo/search?system=vsac&q=diabetes&limit=10"

# PHIN VADS (CDC)
curl "http://localhost:8000/sdo/search?system=phinvads&q=race&limit=10"
```

### SNOMED CT Hierarchy

```bash
# Direct children of a concept (uses ECL <!{id})
curl "http://localhost:8000/sdo/snomed/children/840539006"
```

---

## 9. AI Assist

AI-powered terminology operations. Provider is configured via `AI_PROVIDER` env var (`anthropic`, `openai`, or `gemini`).

### Provider Info

```bash
curl "http://localhost:8000/ai/provider"
# → {"provider": "gemini", "model": "gemini-2.0-flash", "configured": true}
```

### Suggest Codes

Natural language → ranked code candidates from one or more SDOs.

```bash
curl -X POST http://localhost:8000/ai/suggest \
  -H "Content-Type: application/json" \
  -d '{
    "description": "codes for COVID-19 diagnosis and laboratory confirmation",
    "systems": ["snomed", "icd10cm", "loinc"],
    "limit": 10
  }'
```

### Generate ValueSet Metadata

Given a list of selected codes, generate `name`, `title`, `description`, and `purpose`.

```bash
curl -X POST http://localhost:8000/ai/describe \
  -H "Content-Type: application/json" \
  -d '{
    "codes": [
      {"code": "840539006", "display": "COVID-19", "system": "http://snomed.info/sct"},
      {"code": "U07.1",     "display": "COVID-19",  "system": "http://hl7.org/fhir/sid/icd-10-cm"}
    ],
    "context": "public health case reporting"
  }'
```

### Cross-System Mapping

Map codes from one system to another; returns FHIR equivalence values.

```bash
curl -X POST http://localhost:8000/ai/map \
  -H "Content-Type: application/json" \
  -d '{
    "codes": [
      {"code": "840539006", "display": "COVID-19", "system": "http://snomed.info/sct"}
    ],
    "source_system": "snomed",
    "target_system": "icd10cm"
  }'
```

Equivalence values: `equivalent`, `wider`, `narrower`, `inexact`, `unmatched`.

### Save Mapping as ConceptMap

```bash
curl -X POST http://localhost:8000/ai/map-save \
  -H "Content-Type: application/json" \
  -d '{
    "mappings": [...],
    "source_system_url": "http://snomed.info/sct",
    "target_system": "icd10cm",
    "name": "SnomedToIcd10CmCovid",
    "title": "SNOMED → ICD-10-CM COVID-19 Mapping",
    "status": "draft"
  }'
```

### Multi-Turn Chat (ValueSet Builder)

AI assistant with full context of the current ValueSet being built. Returns `reply` + structured `suggested_codes`.

```bash
curl -X POST http://localhost:8000/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What SNOMED codes represent COVID-19 and its variants?"}
    ],
    "valueset_context": {
      "name": "CovidDiagnosisCodes",
      "description": "SNOMED codes for COVID-19 case reporting"
    }
  }'
```

---

## 10. MCP Chat

AI chat backed by six FHIR tool functions, mirroring the [xSoVx/fhir-mcp](https://github.com/xSoVx/fhir-mcp) tool set. The AI autonomously decides which tools to call to answer a question, then returns its answer along with a full trace of every tool invocation.

### Available Tools

| Tool | Description |
|---|---|
| `fhir_capabilities` | Server capability statement |
| `fhir_search` | Search ValueSets, CodeSystems, or ConceptMaps |
| `fhir_read` | Read a resource by type + ID |
| `terminology_lookup` | Look up a code in a CodeSystem |
| `terminology_expand` | Expand a ValueSet |
| `terminology_translate` | Translate codes via a ConceptMap |

```bash
# List tools
curl "http://localhost:8000/mcp-chat/tools"
```

### Chat Examples

```bash
# Simple fact query (triggers fhir_capabilities + fhir_search)
curl -X POST http://localhost:8000/mcp-chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "How many ValueSets does this server have?"}
    ]
  }'

# Multi-step query (AI chains fhir_search → terminology_expand)
curl -X POST http://localhost:8000/mcp-chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Find ValueSets related to race and ethnicity, then expand the first one"}
    ]
  }'

# Code lookup
curl -X POST http://localhost:8000/mcp-chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is SNOMED code 840539006?"}
    ]
  }'

# Multi-turn conversation
curl -X POST http://localhost:8000/mcp-chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user",      "content": "Find ValueSets for influenza"},
      {"role": "assistant", "content": "I found 12 ValueSets related to influenza..."},
      {"role": "user",      "content": "Expand the first one and show me the codes"}
    ]
  }'
```

### Response Format

```json
{
  "reply": "The server contains 1,998 ValueSets...",
  "tool_calls": [
    {
      "tool": "fhir_search",
      "args": {"resource_type": "ValueSet", "count": 1},
      "result": {"total": 1998, "resources": [...]}
    }
  ],
  "provider": "gemini",
  "model": "gemini-2.0-flash"
}
```

The **MCP Chat** tab in the UI provides an interactive version with a collapsible tool trace for each response.

---

## 11. Admin / Sync

PHIN VADS incremental sync — checks for new resources on phinvads.cdc.gov and imports them.

```bash
# Preview what would be imported (dry run — safe to run anytime)
curl -X POST "http://localhost:8000/admin/sync/phinvads?preview=true" \
  -H "Content-Type: application/json" \
  -d '{"resource_type": "all"}'

# Trigger a real sync (ValueSets only)
curl -X POST http://localhost:8000/admin/sync/phinvads \
  -H "Content-Type: application/json" \
  -d '{"resource_type": "valueset"}'

# List last 10 sync runs
curl "http://localhost:8000/admin/sync/status"

# Detail for a specific run
curl "http://localhost:8000/admin/sync/status/{run_id}"
```

Resource types: `all`, `valueset`, `codesystem`

---

## 12. CRUD — Create, Update, Delete

Standard FHIR REST operations. Same pattern for `ValueSet`, `CodeSystem`, and `ConceptMap`.

### Create

```bash
curl -X POST http://localhost:8000/ValueSet \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "ValueSet",
    "name": "TestValueSet",
    "title": "Test Value Set",
    "status": "draft",
    "description": "Created for API testing",
    "compose": {
      "include": [{
        "system": "http://snomed.info/sct",
        "concept": [
          {"code": "840539006", "display": "COVID-19"},
          {"code": "407479009", "display": "Influenza A"}
        ]
      }]
    }
  }'
```

### Update (full replace)

```bash
curl -X PUT http://localhost:8000/ValueSet/{id} \
  -H "Content-Type: application/fhir+json" \
  -d '{ ...full FHIR resource... }'
```

### Delete

```bash
curl -X DELETE "http://localhost:8000/ValueSet/{id}"
```

---

## 13. MCP Integration (Claude Code / Claude Desktop)

Flint can be connected to Claude Code or Claude Desktop via the [xSoVx/fhir-mcp](https://github.com/xSoVx/fhir-mcp) MCP server, giving Claude direct access to all FHIR operations via natural language.

### Configuration

The following is already written to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "fhir-flint": {
      "command": "npx",
      "args": ["-y", "fhir-mcp@latest"],
      "env": {
        "FHIR_BASE_URL": "http://localhost:8000",
        "TERMINOLOGY_BASE_URL": "http://localhost:8000",
        "PHI_MODE": "trusted",
        "ENABLE_AUDIT": "true"
      }
    }
  }
}
```

Flint must be running (`docker compose up -d`) before Claude Code will be able to connect.

### What Claude Can Do via MCP

Once connected, Claude Code can answer questions like:

- *"How many active ValueSets are on Flint?"*
- *"Find ValueSets tagged to the COVID-19 case notification view"*
- *"Expand the race and ethnicity ValueSet"*
- *"Look up LOINC code 94500-6"*
- *"What ConceptMaps does the server have?"*

### Tools Exposed

| MCP Tool | Operation |
|---|---|
| `fhir.capabilities` | `GET /metadata` |
| `fhir.search` | `GET /ValueSet`, `/CodeSystem`, `/ConceptMap` |
| `fhir.read` | `GET /{type}/{id}` |
| `terminology.lookup` | `GET /CodeSystem/$lookup` |
| `terminology.expand` | `GET /ValueSet/$expand` |
| `terminology.translate` | `GET /ConceptMap/$translate` |

### In-App MCP Chat

The **MCP Chat** tab in the Flint web UI (`http://localhost`) provides a browser-based test interface for the same tool set — no external tooling required. Each AI response shows which tools were called, with full input/output JSON visible in a collapsible trace panel.

---

## Common Code System URLs

| System | Canonical URL |
|---|---|
| SNOMED CT | `http://snomed.info/sct` |
| LOINC | `http://loinc.org` |
| ICD-10-CM | `http://hl7.org/fhir/sid/icd-10-cm` |
| ICD-9-CM | `http://hl7.org/fhir/sid/icd-9-cm` |
| RxNorm | `http://www.nlm.nih.gov/research/umls/rxnorm` |
| CVX (vaccines) | `http://hl7.org/fhir/sid/cvx` |
| CPT | `http://www.ama-assn.org/go/cpt` |
| NDC | `http://hl7.org/fhir/sid/ndc` |
| HL7 v2 tables | `http://terminology.hl7.org/CodeSystem/v2-{table}` |

---

## Interactive API Documentation

FastAPI auto-generates full interactive docs at:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`
