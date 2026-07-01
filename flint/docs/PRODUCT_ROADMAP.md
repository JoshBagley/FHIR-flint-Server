# Flint — Product Roadmap & Gap Tracker

This document tracks the gaps between Flint's current capabilities and a commercially viable, conformant FHIR R4 server. It is the authoritative source for implementation priorities. Update checkboxes as work is completed.

**Last updated:** 2026-07-01
**Analysis basis:** Gap analysis vs HAPI FHIR, Azure Health Data Services, Google Cloud Healthcare API, Medplum, and Smile CDR.

---

## Current State Summary

Flint currently supports **16 of 145 FHIR R4 resource types**: `ValueSet`, `CodeSystem`, `ConceptMap`, `Patient`, `Observation`, `Condition`, `Encounter`, `AllergyIntolerance`, `Immunization`, `Organization`, `Practitioner`, `PractitionerRole`, `Location`, `MedicationRequest`, `Procedure`, `DiagnosticReport`.

**Where Flint leads:**
- Best-in-class terminology operations for public health vocabulary (SDO connectors, SNOMED ECL, VSAC, HL7 v2/v3, PHIN VADS)
- Embedded multi-provider AI (Anthropic / OpenAI / Gemini) with live code validation pre-injection to prevent hallucination
- Production-grade observability stack (Prometheus + Grafana + Loki) included out of the box
- Multi-tier code system storage (`complete` / `not-present` / `fragment`) with external delegation

**Where Flint trails every major competitor:**
- Resource type coverage (3 vs 145)
- SMART on FHIR authorization (not implemented)
- Batch / transaction bundles (not implemented)
- ~~Standard FHIR search pagination~~ (completed P0.1 � pagination, sort, Bundle.link)
- Bulk Data Export (not implemented)

---

## Phase 0 — Quick Wins (1–2 weeks each)

Conformance fixes and low-hanging spec gaps. No architectural changes required.

### P0.1 — Standard Search Pagination

- [x] Add `_count` and `_offset` query parameters to all search endpoints
- [x] Return results wrapped in a `Bundle` with `type: searchset`
- [x] Add `Bundle.link` entries: `self`, `next`, `prev`, `first`, `last`
- [x] Remove hardcoded 5000-row ceiling; default `_count` to 20
- [x] Add `_sort` parameter with support for `name`, `url`, `status`, `date`, `-date`
- [x] Update CapabilityStatement `searchParam` entries for `_count`, `_offset`, `_sort`

**Why it matters:** Every FHIR client library (HAPI FHIR client, Microsoft FHIR SDK, Firely SDK, medplum-client) implements spec-compliant pagination. Without it, clients that follow `Bundle.link[rel=next]` break silently on large datasets.

---

### P0.2 — Named Version Read URL

- [x] Add routes `GET /ValueSet/{id}/_history/{vid}`, `GET /CodeSystem/{id}/_history/{vid}`, `GET /ConceptMap/{id}/_history/{vid}`
- [x] Map `vid` to the `version_number` column in `resource_versions` table (data already exists)
- [x] Return 404 with OperationOutcome if `vid` does not exist for that resource
- [x] Keep `?version=` query param for backward compatibility

**Why it matters:** The FHIR spec defines `GET /{type}/{id}/_history/{vid}` as the canonical URL for a specific historical version. It is the URL format embedded in `Bundle.entry.fullUrl` for versioned references.

---

### P0.3 — ETag Enforcement on Update

- [x] On `PUT /{type}/{id}`, read the `If-Match` request header
- [x] Parse the ETag value (format: `W/"N"`) and compare to `current_version` in the DB
- [x] Return `412 Precondition Failed` with OperationOutcome if mismatch
- [x] Return `428 Precondition Required` if `If-Match` header is absent and server is configured to require it (`REQUIRE_IF_MATCH=true`)
- [x] Add `Last-Modified` response header on all reads (currently only `ETag` is returned)

**Why it matters:** Prevents silent overwrite of concurrent edits. Required for conformant optimistic locking.

---

### P0.4 — `CodeSystem/$validate-code` Operation

- [x] Implement `GET /CodeSystem/$validate-code?url={url}&code={code}&display={display}`
- [x] Implement `GET /CodeSystem/{id}/$validate-code?code={code}&display={display}`
- [x] Return a `Parameters` resource with `result` (boolean), `display` (string), `message` (string)
- [x] Delegate to external SDO connector when `content=not-present` (via shared `_perform_lookup` path)
- [x] Register in CapabilityStatement under CodeSystem operations

**Why it matters:** The largest gap in the CodeSystem operation surface. Many clients use this explicitly rather than `$lookup`. It is a SHALL operation for servers that claim CodeSystem support in their CapabilityStatement.

---

### P0.5 — Dynamic CapabilityStatement

- [x] Generate CapabilityStatement dynamically at request time rather than returning a hardcoded object
- [x] Reflect actual runtime auth mode (`ENABLE_AUTH`, `OIDC_ISSUER_URL`) in the `security` block
- [x] Add all implemented non-standard operations: `$validate-batch`, `$diff`, `$concept-search`, `$archive`, `$audit`
- [x] Add missing search parameters: `identifier` and `content` on CodeSystem; `identifier` on ValueSet and ConceptMap
- [x] Correct `interaction` lists: `DELETE /CodeSystem/{id}` implemented; added `delete` to CodeSystem interactions
- [x] Add `GET /metadata?mode=terminology` endpoint returning `TerminologyCapabilities` resource
- [x] Add `TerminologyCapabilities` to `rest.resource` list in the main CapabilityStatement
- [ ] Pass ONC / FHIR conformance test tool checks (Inferno, TouchStone)

**Why it matters:** The CapabilityStatement is the first thing every FHIR conformance testing tool checks. Inaccuracies cause false test failures and erode client trust.

---

### P0.6 — `_format` Parameter and Content Negotiation

- [x] Support `_format=json`, `_format=application/fhir+json`, `_format=xml` query parameter
- [x] Return `406 Not Acceptable` when `Accept` header requires XML only (no JSON fallback)
- [x] Return `415 Unsupported Media Type` for unsupported format requests (XML can return a "not supported" OperationOutcome)
- [x] Support `Prefer: return=minimal` (return 200 with no body) and `Prefer: return=representation` (default, return full resource)
- [x] Support `Prefer: return=OperationOutcome` on create/update (returns informational OperationOutcome)

**Why it matters:** Required by the FHIR spec. Many clients set these headers by default.

---

## Phase 1 — Core FHIR R4 Resources (1–3 months)

Extending Flint to support the most critical clinical and administrative FHIR resource types. The DB schema already uses generic JSONB storage — the work per resource is: Pydantic model, route wiring, and search parameter indexing.

### P1.1 — Patient Resource

- [x] Define `Patient` Pydantic model (R4-compliant: `identifier`, `name`, `birthDate`, `gender`, `address`, `telecom`, `active`, `link`)
- [x] Implement `POST /Patient`, `GET /Patient/{id}`, `PUT /Patient/{id}`, `DELETE /Patient/{id}`
- [x] Implement `GET /Patient` search: `identifier`, `name`, `family`, `given`, `birthdate`, `gender`
- [x] Add `GET /Patient/{id}/_history` and named version read
- [x] Register in CapabilityStatement
- [x] Implement basic `Patient/$match` (probabilistic matching on name + birthdate + identifier)

**Why it matters:** Patient is the cornerstone of every clinical FHIR implementation. Without it, Flint cannot participate in any patient-centric workflow, EHR integration, or US Core-compliant data exchange.

---

### P1.2 — Observation Resource

- [x] Define `Observation` Pydantic model (R4: `status`, `category`, `code`, `subject`, `effective`, `value[x]`, `component`, `interpretation`)
- [x] Implement full CRUD + search: `patient`, `category`, `code`, `status`
- [x] Register in CapabilityStatement
- [x] Support `_include=Observation:subject` to pull referenced Patient in one request
- [x] Validate `code` against known CodeSystems using the existing `$lookup` path

**Why it matters:** Lab results, vitals, and social history all use Observation. Required for CDC surveillance reporting, USCDI, CQL quality measures, and essentially every clinical data exchange scenario.

---

### P1.3 — Condition Resource

- [x] Define `Condition` Pydantic model (R4: `clinicalStatus`, `verificationStatus`, `category`, `code`, `subject`, `encounter`, `onset[x]`, `recordedDate`)
- [x] Implement full CRUD + search: `patient`, `category`, `code`, `clinical-status`
- [x] Register in CapabilityStatement

**Why it matters:** Diagnoses. Required for clinical decision support, population health, and all EHR→FHIR data exchange.

---

### P1.4 — Encounter Resource

- [x] Define `Encounter` Pydantic model (R4: `status`, `class`, `type`, `subject`, `participant`, `period`, `reasonCode`, `diagnosis`, `hospitalization`, `location`)
- [x] Implement full CRUD + search: `patient`, `status`, `class`
- [x] Register in CapabilityStatement

---

### P1.5 — AllergyIntolerance Resource

- [x] Define `AllergyIntolerance` Pydantic model
- [x] Implement full CRUD + search: `patient`, `code`, `clinical-status`, `criticality`
- [x] Register in CapabilityStatement

**Why it matters:** Listed as SHALL in US Core. Required for any clinical summary or care coordination workflow.

---

### P1.6 — Immunization Resource

- [x] Define `Immunization` Pydantic model (R4: `status`, `vaccineCode`, `patient`, `occurrence[x]`, `primarySource`, `lotNumber`, `site`, `route`, `doseQuantity`)
- [x] Implement full CRUD + search: `patient`, `vaccine-code`, `date`, `status`
- [x] Register in CapabilityStatement
- [x] Wire vaccine code validation against CVX `CodeSystem` (already imported)

**Why it matters:** CDC immunization registry integration. Flint already has CVX codes but no Immunization resource to hold records.

---

### P1.7 — Bundle Support (Batch + Transaction)

- [x] Implement `POST /` accepting a `Bundle` with `type: batch` or `type: transaction`
- [x] Batch: process each entry independently; collect individual success/failure per entry
- [x] Transaction: wrap all entries in a DB transaction; roll back entire bundle on any error
- [x] Handle `ifNoneExist` (conditional create), `ifMatch` (conditional update) per entry
- [x] Return a response `Bundle` with one entry per input entry containing the outcome
- [x] Handle internal references (`urn:uuid:` temporary IDs) within a transaction bundle
- [x] Register in CapabilityStatement under `interaction[type=transaction]` and `interaction[type=batch]`

**Why it matters:** Every EHR system, integration engine (Mirth, Azure Data Factory, Rhapsody), and bulk import tool sends data as Bundles. Without this, Flint cannot accept data in the standard FHIR mode.

---

### P1.8 — Administrative Resources

- [x] `Organization` — CRUD + search (`name`, `type`)
- [x] `Practitioner` — CRUD + search (`name`, `family`, `given`, `gender`)
- [x] `PractitionerRole` — CRUD + search (`practitioner`, `organization`, `role`, `specialty`)
- [x] `Location` — CRUD + search (`name`, `status`)

**Why it matters:** Provider directory resources are required by CMS interoperability rules (Provider Directory API) and are foundational references in clinical resources.

---

### P1.9 — MedicationRequest + Procedure + DiagnosticReport

- [x] `MedicationRequest` — CRUD + search (`patient`, `status`, `intent`, `medication-code`)
- [x] `Procedure` — CRUD + search (`patient`, `code`, `status`)
- [x] `DiagnosticReport` — CRUD + search (`patient`, `category`, `code`, `status`)
- [x] Validate medication code against RxNorm connector on `MedicationRequest` create

---

## Phase 2 — Interoperability & Standards (3–6 months)

### P2.1 — SMART on FHIR v2

- [ ] Implement `GET /.well-known/smart-configuration` returning SMART metadata
- [ ] Implement `/authorize` OAuth 2.0 authorization endpoint (or configure Keycloak/Auth0 as provider)
- [ ] Implement PKCE support (`code_challenge`, `code_challenge_method=S256`)
- [ ] Implement launch context: standalone launch (`launch/patient`) and EHR launch
- [ ] Define SMART scopes: `patient/*.read`, `user/*.read`, `system/*.read`, resource-level scopes
- [ ] Enforce scopes on resource access in route middleware
- [ ] Register SMART in CapabilityStatement `rest.security` block
- [ ] Test with Inferno SMART on FHIR test suite

**Why it matters:** Required by ONC's 21st Century Cures Act for any server connected to patient data. Required for EHR app launch, patient-facing apps, and payer-to-payer exchange under CMS rules.

---

### P2.2 — Conditional Interactions

- [x] Conditional create: `POST /{type}` with `If-None-Exist: {search-params}` header — search first; create only if no match; return existing if 1 match; error if multiple
- [x] Conditional update: `PUT /{type}?{search-params}` — search; update if 1 match; create if 0; error if multiple
- [x] Conditional delete: `DELETE /{type}?{search-params}` — delete all matching resources
- [x] Register in CapabilityStatement under `conditionalCreate`, `conditionalUpdate`, `conditionalDelete`

**Why it matters:** All idempotent bulk import pipelines (ETL from EHRs, national registries) rely on conditional operations to avoid duplicates without requiring a GET-then-POST pattern.

---

### P2.3 — `_include` and `_revinclude` Search Modifiers

- [x] Parse `_include={type}:{searchParam}` from search requests
- [x] After primary search, resolve all referenced resources and add to Bundle as `include` entries
- [ ] Support `_include:iterate` for chained includes (deferred — complex; not required for MVP conformance)
- [x] Parse `_revinclude={type}:{searchParam}` — find resources of type `{type}` that reference any result
- [x] Add `_include` and `_revinclude` to CapabilityStatement (`searchInclude`, `searchRevInclude` per resource)

**Why it matters:** Cross-resource includes are the backbone of efficient FHIR queries. Without them, every client makes N+1 requests to resolve references.

---

### P2.4 — Bulk Data Export (FHIR Bulk Data IG v2)

- [x] Implement kick-off endpoint: `GET /$export`, `GET /Patient/$export` (`/Group/{id}/$export` deferred — Group resource not yet supported)
- [x] Return `202 Accepted` with `Content-Location` header pointing to a status endpoint
- [x] Implement async export job using asyncio background task (no Celery required)
- [x] Serialize resources to NDJSON files (one file per resource type, stored under `BULK_EXPORT_DIR`)
- [x] Implement status endpoint `GET /jobs/{id}` — returns 202 while in progress, 200 + manifest when complete
- [x] Implement file download endpoint `GET /bulk/{job_id}/{file}.ndjson` (local storage; configurable via `BULK_EXPORT_DIR`)
- [x] Implement `DELETE /jobs/{id}` to cancel an in-progress export
- [x] Support `_since` parameter (filter by `meta.lastUpdated >= _since`)
- [x] Support `_type` parameter (comma-separated resource types)
- [x] Register `$export` operation in CapabilityStatement (system-level and Patient)

**Why it matters:** Required by CMS interoperability rules for payer-side implementations. Required for population health analytics pipelines (feeding BigQuery, Databricks, Snowflake).

---

### P2.5 — `$validate` Operation (Structural + Profile Validation)

- [x] Implement `POST /{type}/$validate` accepting a resource body and optional `profile` parameter
- [x] Validate resource structure against R4 Pydantic models (already have models — wire the validation step)
- [x] Delegate profile validation to tx.fhir.org/r4/$validate for US Core and other published profiles
- [x] Cache validation results by profile URL + resource hash (Redis, TTL 1 hour)
- [x] Return `OperationOutcome` with structured issues (severity, location, details)
- [ ] Optionally store `StructureDefinition` resources locally and validate against them
- [x] Register in CapabilityStatement

---

### P2.6 — US Core v6 Profile Conformance

- [x] Add `StructureDefinition` resource type with full CRUD — profiles can now be stored locally (prerequisite for local profile validation)
- [x] Add `supportedProfile` array to Patient CapabilityStatement entry (populated after import)
- [x] Create `migration/import_us_core_v6.py` — downloads US Core v6.1.0 package from packages.fhir.org and imports all StructureDefinitions
- [x] Implement all US Core v6.1.0 SHALL search parameters (16 gaps across 8 resource types): `_id`/`telecom` on Patient; `date` on Observation/DiagnosticReport; `_id`/`date`/`identifier`/`type` on Encounter; `authoredon` on MedicationRequest; `_id` on Practitioner; `address` on Organization; `address`/`address-city`/`address-postalcode`/`address-state`/`organization` on Location. FHIR date prefix operators (`ge`, `le`, `gt`, `lt`) implemented via `_date_condition` helper in `fhir_utils.py`. SHOULD params `onset-date`/`recorded-date` on Condition also added.
- [ ] Implement must-support enforcement for US Core Patient, Observation (Lab), Condition, AllergyIntolerance, Immunization, Encounter, MedicationRequest
- [ ] Pass Inferno US Core test suite (ONC certification prerequisite)
- [x] Update CapabilityStatement `supportedProfile` entries after running the import script — all 13 clinical/admin/medication resource types now declare their US Core v6.1.0 profile URLs statically; no import run required

**Why it matters:** US Core conformance is required for ONC Health IT Certification and for EHR integration with Cerner, Epic, and Meditech (all require US Core from their app partners).

---

### P2.7 — PATCH Operations

- [x] Implement `PATCH /{type}/{id}` with `Content-Type: application/json-patch+json` (JSON Patch, RFC 6902)
- [ ] Implement `PATCH /{type}/{id}` with `Content-Type: application/fhir+json` (FHIRPath Patch — requires P4.4)
- [x] Apply patches atomically; validate result against resource schema before persisting
- [x] Register in CapabilityStatement under each resource's `interaction` list

---

### P2.8 — System-Level and Type-Level History

- [x] Implement `GET /_history` (system-level history): all changes across all resource types since `_since`
- [x] Implement `GET /{type}/_history` (type-level history): all changes for one resource type
- [x] Return as `Bundle` with `type: history`, paginated with `_count` and `_since`
- [x] Register in CapabilityStatement under `interaction[type=history-system]` and `interaction[type=history-type]`

---

## Phase 3 — Enterprise Features (6–12 months)

Required for commercial deployment, multi-customer SaaS, or regulated environments.

### P3.1 — Multi-Tenancy

- [ ] Partition all FHIR resources by tenant ID (add `tenant_id` column to `fhir_resources`)
- [ ] Enforce tenant isolation at the DB query level (never cross tenant boundaries)
- [ ] Support tenant-scoped auth tokens (JWT claim `tenant` maps to DB partition)
- [ ] Per-tenant Elasticsearch index or document-level `tenant_id` filtering
- [ ] Per-tenant Redis cache key namespacing
- [ ] Tenant management API (create/list/delete tenants, assign users)
- [ ] Tenant-scoped audit log

**Why it matters:** Required for any SaaS offering. Without it, all customers share one FHIR namespace.

---

### P3.2 — Role-Based Access Control (RBAC)

- [ ] Define roles: `admin`, `clinician`, `readonly`, `terminology-editor`, `bulk-export`
- [ ] Enforce resource-level permissions: which roles can read/write/delete which resource types
- [ ] Enforce instance-level permissions: restrict access to resources owned by the requesting patient or organization
- [ ] SMART scope enforcement (complements P2.1): `patient/Observation.read` limits to patient's own Observations
- [ ] Audit every access decision (allow or deny) to the audit log

---

### P3.3 — Consent Management

- [ ] Store and enforce FHIR `Consent` resources
- [ ] Implement consent-based data filtering: suppress resources in search results that are covered by an active opt-out Consent
- [ ] Support `42 CFR Part 2` (substance use disorder records) sensitivity labels
- [ ] Support data segmentation for privacy (DS4P) `Confidentiality` tags
- [ ] Log all consent decisions to the audit log

---

### P3.4 — Rate Limiting and Quotas

- [x] Per-client rate limiting on all endpoints (`RATE_LIMIT_PER_MINUTE`, default 600; identified by `X-API-Key` header or remote IP)
- [ ] Bulk export job concurrency limit per tenant
- [x] AI endpoint per-client quota (`RATE_LIMIT_AI_PER_MINUTE`, default 20; also applies to `$expand`)
- [x] Return `429 Too Many Requests` with `Retry-After` and `X-RateLimit-*` headers
- [x] Expose rate limit metrics in Prometheus (`fhir_rate_limit_exceeded_total` counter by client type)

---

### P3.5 — Subscription Framework (R4B / R5 Topic-Based)

- [ ] Implement FHIR R4B/R5 `SubscriptionTopic` resources defining triggering criteria
- [ ] Implement `Subscription` resource CRUD for clients to register webhooks
- [ ] Trigger outbound webhook `POST` when a matching resource is created/updated/deleted
- [ ] Support REST-hook and WebSocket channel types
- [ ] Delivery retry with exponential backoff; dead-letter after N failures
- [ ] HMAC signature on webhook payloads for payload authenticity

**Why it matters:** Push-based notifications are essential for care coordination, real-time alerting, and replacing polling patterns in clinical workflows.

---

### P3.6 — HL7 v2 Ingest Pipeline

- [ ] Accept HL7 v2 messages via MLLP (TCP) and HTTP POST
- [ ] Parse HL7 v2 ADT, ORU, ORM, VXU message types
- [ ] Convert parsed v2 segments to FHIR resources (Patient from PID, Observation from OBX, Encounter from PV1)
- [ ] Persist converted resources as FHIR R4 via the standard FHIR API
- [ ] Validate codes (OBX-3, OBX-5 when coded) against local CodeSystems via `$lookup`
- [ ] Return ACK/NAK HL7 v2 response
- [ ] Expose pipeline metrics (messages received, converted, rejected) in Prometheus

**Why it matters:** The majority of clinical data in US healthcare still flows as HL7 v2. An ingest pipeline bridges legacy systems to FHIR without requiring sender-side changes.

---

### P3.7 — CDA / C-CDA to FHIR Conversion

- [ ] Implement `POST /cda/$convert` accepting a CDA XML document
- [ ] Parse CDA sections: Problems (→ Condition), Medications (→ MedicationRequest), Allergies (→ AllergyIntolerance), Immunizations (→ Immunization), Results (→ Observation, DiagnosticReport)
- [ ] Return a `Bundle` (transaction) of converted FHIR resources
- [ ] Optionally persist the Bundle directly
- [ ] Validate extracted codes against local CodeSystems

---

### P3.8 — Data Archival and Retention Policies

- [ ] Configurable retention policy per resource type (e.g., purge Observation records older than 7 years)
- [ ] Soft-delete with tombstone records (resource is `inactive`, not physically removed)
- [ ] Hard-delete job for purge-eligible records (with audit log entry)
- [ ] GDPR / HIPAA right-to-be-forgotten: delete all resources referencing a given Patient ID

---

## Phase 4 — Advanced Differentiators (12+ months)

Capabilities that would make Flint meaningfully better than existing commercial servers.

### P4.1 — Analytics Export to Data Warehouse

- [ ] Stream FHIR resource writes to a change data capture (CDC) topic (Kafka or AWS Kinesis)
- [ ] Provide a BigQuery connector: continuous export of all resources into a FHIR-native BigQuery dataset
- [ ] Provide a Parquet export: batch export in columnar format suitable for Spark / Databricks
- [ ] Ship a pre-built dbt model set for common analytics queries (patient cohorts, code frequency)

---

### P4.2 — AI-Assisted Data Quality

- [ ] Extend `/ai/describe` to evaluate a FHIR resource for completeness and clinical plausibility
- [ ] Flag Observations with out-of-range values for the given LOINC code
- [ ] Suggest missing must-support elements for US Core profiles
- [ ] Auto-suggest ConceptMap entries for un-mapped codes found during `$translate`
- [ ] Surface data quality scores on the Grafana dashboard

---

### P4.3 — CQL / FHIR Measure Evaluation

- [ ] Implement `POST /Measure/{id}/$evaluate-measure?periodStart=&periodEnd=&subject=`
- [ ] Integrate a CQL execution engine (translator + engine; reference: cql-execution JS library or HAPI CQL engine)
- [ ] Support HEDIS, CMS eCQM, and USNWR measure definitions stored as FHIR `Measure` resources
- [ ] Return `MeasureReport` resource with population counts and individual results

---

### P4.4 — FHIR Path / FHIRPath Evaluation API

- [ ] Implement `POST /fhirpath/$evaluate` accepting a resource and a FHIRPath expression
- [ ] Use `fhirpathpy` or `fhirpath.js` (via subprocess) for evaluation
- [ ] Enable FHIRPath-based subscription trigger criteria (P3.5 prerequisite)
- [ ] Enable FHIRPath Patch (P2.7 prerequisite)

---

### P4.5 — FHIR R5 / R4B Support

- [ ] Implement versioned API base URL: `/r4/`, `/r4b/`, `/r5/`
- [ ] Track resource version per-request via `Accept: application/fhir+json; fhirVersion=4.0`
- [ ] Maintain R4 as primary; add R5 resource aliases and new resource types as the ecosystem matures
- [ ] Support SubscriptionTopic (R4B/R5 native) while maintaining R4 compatibility

---

## Competitive Positioning

| Capability | Flint Now | Target (Phase 2) | HAPI FHIR | Azure | Google | Medplum |
|---|---|---|---|---|---|---|
| Resource types | 3 | 30+ | 145 | 145 | 145 | 145 |
| SMART on FHIR | No | P2.1 | Plugin | Yes | Yes | v2 |
| Bulk Export | No | P2.4 | Limited | ADLS2 | BigQuery | Limited |
| Terminology (SDO connectors) | **Excellent** | **Excellent** | External only | External only | External only | Basic |
| AI Integration | **Embedded** | **Extended** | None | Separate | Separate | Bots |
| Observability | **Included** | **Included** | Manual | Azure Monitor | Cloud Ops | Manual |
| Batch / Transaction | No | P1.7 | Yes | Yes | Yes | Yes |
| US Core Conformance | No | P2.6 | Yes | Yes | Yes | Yes (ONC) |
| CDA / HL7 v2 Ingest | No | P3.6/P3.7 | Plugin | Converter | Converter | None |
| Multi-tenancy | No | P3.1 | Partitioning | Native | Native | Native |
| Open source | Yes | Yes | Yes | No | No | Yes |

---

## ONC Certification Pathway

To qualify for ONC Health IT Certification (§170.315), Flint would need to complete at minimum:

- [ ] **P0.5** — Accurate CapabilityStatement
- [ ] **P1.1–P1.6** — Patient, Observation, Condition, AllergyIntolerance, Encounter, Immunization (US Core SHALL resources)
- [ ] **P2.1** — SMART on FHIR v2 (required by §170.315(g)(10))
- [ ] **P2.5** — `$validate` with US Core profile checking
- [ ] **P2.6** — US Core v6 profile conformance
- [ ] Pass Inferno ONC test suite (https://inferno.healthit.gov)

---

## UI / Design Backlog

- [ ] **Icon v2** — Redesign the Flint icon to show a literal flint-stone striking metal to produce sparks that ignite a fire. Current icon uses a FHIR-inspired flame with radiating sparks; the next version should make the "striking" moment more explicit (angular stone silhouette, impact point, sparks fanning outward into a nascent flame). Update all three locations: `frontend/public/favicon.svg`, `frontend/src/components/AppLogo.tsx`, `frontend/index.html` (data URI).

---

## Known Technical Debt (Non-Feature Gaps)

- [ ] `versionId` in resource Meta is the DB integer version, not a FHIR-compliant UUID or string — spec requires that this is opaque and stable
- [ ] FHIR extension URL `http://flint.local/StructureDefinition/source` is not resolvable; should register a real `StructureDefinition` resource at that URL or change to a URL the server can serve
- [ ] Elasticsearch index mapping has no explicit `@timestamp` field; Loki queries and time-series searches may behave unexpectedly
- [ ] Redis AOF persistence is configured but `appendfsync everysec` can lose up to 1 second of cache on crash — acceptable for a cache, but document the trade-off

---

## How to Use This Document

1. Pick a phase/item to work on
2. Create a branch named `feat/P{phase}.{item}-{short-description}` (e.g. `feat/P0.2-version-history-url`)
3. Check off sub-items as you implement them
4. Update the **Current State Summary** table at the top when a Phase completes
5. Add newly discovered gaps or technical debt to the appropriate section rather than creating separate tracking issues

For architectural decisions on any item, create an ADR (Architecture Decision Record) in `docs/adr/` before implementing.
