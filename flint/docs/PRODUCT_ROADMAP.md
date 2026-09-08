# Flint — Product Roadmap & Gap Tracker

This document tracks the gaps between Flint's current capabilities and a commercially viable, conformant FHIR R4 server. It is the authoritative source for implementation priorities. Update checkboxes as work is completed.

**Last updated:** 2026-09-08
**Analysis basis:** Gap analysis vs HAPI FHIR, Azure Health Data Services, Google Cloud Healthcare API, Medplum, and Smile CDR.

---

## Current State Summary

Flint currently supports **22 of 145 FHIR R4 resource types**: `ValueSet`, `CodeSystem`, `ConceptMap`, `Patient`, `Observation`, `Condition`, `Encounter`, `AllergyIntolerance`, `Immunization`, `Organization`, `Practitioner`, `PractitionerRole`, `Location`, `MedicationRequest`, `Procedure`, `DiagnosticReport`, `Questionnaire`, `QuestionnaireResponse`, `Claim`, `Coverage`, `ClaimResponse`, `ServiceRequest`, `StructureDefinition`.

**Where Flint leads:**
- Best-in-class terminology operations for public health vocabulary (SDO connectors, SNOMED ECL, VSAC, HL7 v2/v3, PHIN VADS)
- Embedded multi-provider AI (Anthropic / OpenAI / Gemini) with live code validation pre-injection to prevent hallucination
- Production-grade observability stack (Prometheus + Grafana + Loki) included out of the box
- Multi-tier code system storage (`complete` / `not-present` / `fragment`) with external delegation
- Da Vinci Prior Authorization Support (PAS) — `POST /Claim/$submit` PASRequestBundle workflow
- SMART on FHIR v2 via Keycloak 24 — PKCE public client, confidential backend client, three realm roles, custom login theme
- In-app user management — create/enable/disable clinicians, patients, and admins via AdminApp; audit logged

**Where Flint trails every major competitor:**
- Resource type coverage (22 vs 145)
- ~~SMART on FHIR authorization~~ (completed P2.1 — Keycloak 24)
- ~~Batch / transaction bundles~~ (completed P1.7)
- ~~Standard FHIR search pagination~~ (completed P0.1 — pagination, sort, Bundle.link)
- ~~Bulk Data Export~~ (completed P2.4)
- ~~Advanced search modifiers (`_has`, chained params)~~ (completed P2.2)
- ~~`_include:iterate` transitive includes~~ (completed P2.3 — 2026-09-08)
- ~~JSON Patch + FHIRPath Patch~~ (completed P2.7 — 2026-09-08)
- US Core must-support enforcement (deferred — P2.6 open item)
- ~~ONC Inferno test suite~~ (completed P2.6 — 2026-09-07, all US Core v6.1.0 sections passing)

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

### P1.10 — Da Vinci Prior Authorization Support (PAS) ✓

- [x] Define PAS Pydantic models: `Questionnaire`, `QuestionnaireResponse`, `Claim` (`class_` alias for `class`), `Coverage`, `ClaimResponse`, `ServiceRequest` — in `app/models/prior_auth.py`
- [x] Implement full CRUD + search for all 6 PAS resource types via `routes/prior_auth.py`
- [x] Implement `POST /Claim/$submit` — accepts PASRequestBundle, stores all resources atomically, returns PASResponseBundle with `ClaimResponse.outcome=queued`
- [x] Register all 6 types in Nginx regex, Vite proxy, CapabilityStatement, and SystemApp bulk export categories
- [x] QuestionnaireResponse detail modal in ClinicalApp (recursive `QRItemsView` for nested items)
- [x] Questionnaire detail modal in AdminApp (linkId, type badge, required flag per item)
- [ ] Real payer integration — X12 278 translation, clearinghouse or FHIR-native payer endpoint (CMS-0057-F mandates FHIR-native payers by 2027)
- [ ] CoverageEligibilityRequest/Response resource types (payer eligibility workflow)

**Why it matters:** CMS Prior Authorization Rule (CMS-0057-F) requires FHIR-native payer APIs by 2027. Da Vinci PAS is the industry-standard IG for this workflow.

---

### P1.11 — Admin User Management ✓

- [x] `GET /admin/users` — list all Keycloak users with roles and status
- [x] `POST /admin/users/clinician` / `patient` / `admin` — create realm users via Keycloak Admin REST API
- [x] `PATCH /admin/users/{id}/enable` / `disable` — account enable/disable
- [x] `AdminApp.tsx` Users tab — list, search, create (modal), enable/disable
- [x] `ClinicalApp.tsx` New Patient modal — clinicians can register patients with their Practitioner pre-filled as `generalPractitioner`
- [x] Audit logging — all identity events logged to `audit_log` with `resource_type='KeycloakUser'`

---

## Phase 2 — Interoperability & Standards (3–6 months)

### P2.1 — SMART on FHIR v2 ✓

- [x] Implement `GET /.well-known/smart-configuration` returning SMART metadata
- [x] Implement `/authorize` OAuth 2.0 authorization endpoint — Keycloak 24 as provider; Nginx proxies `/auth/*`
- [x] Implement PKCE support (`code_challenge`, `code_challenge_method=S256`) — `flint-app` public client
- [x] Implement launch context: standalone launch — `LoginGate.tsx` → PKCE redirect → `AuthCallback.tsx`
- [x] Define SMART scopes: `patient/*.read`, `user/*.read`, `system/*.read` — full scope set on Keycloak realm
- [x] Enforce scopes on resource access in route middleware — `require_access` in `auth.py`; three roles: `fhir-patient`, `fhir-clinician`, `fhir-admin`
- [x] Register SMART in CapabilityStatement `rest.security` block
- [x] Test with Inferno SMART on FHIR test suite — all 1.x SMART sections pass locally (2026-09-07)

**Implementation notes:** Keycloak 24.0 realm `fhir` configured in `keycloak/flint-realm.json`. Public client `flint-app` (PKCE), confidential backend client `flint-backend` (`client_credentials`). Custom login theme at `keycloak/themes/flint/`. Seed users: alice/Alice123, dr-jones/Jones123, admin/Admin123. Clinician panel filtering (Option B) via `Patient.generalPractitioner`.

**Why it matters:** Required by ONC's 21st Century Cures Act for any server connected to patient data. Required for EHR app launch, patient-facing apps, and payer-to-payer exchange under CMS rules.

---

### P2.2 — Conditional Interactions + Advanced Search ✓

**Conditional interactions:**
- [x] Conditional create: `POST /{type}` with `If-None-Exist: {search-params}` header — search first; create only if no match; return existing if 1 match; error if multiple
- [x] Conditional update: `PUT /{type}?{search-params}` — search; update if 1 match; create if 0; error if multiple
- [x] Conditional delete: `DELETE /{type}?{search-params}` — delete all matching resources
- [x] Register in CapabilityStatement under `conditionalCreate`, `conditionalUpdate`, `conditionalDelete`

**Advanced search:**
- [x] `_has` — reverse chained search (e.g., `GET /Patient?_has:Observation:patient:code=1234-5`) — 21 resource+param combinations in `_HAS_BACK_REF`/`_HAS_CONDITION` tables
- [x] Chained parameters (e.g., `GET /Observation?patient.name=Jones`) — 18 combinations in `_CHAIN_REF`/`_CHAIN_TARGET_CONDITION` tables

**Why it matters:** Conditional operations are required for idempotent ETL pipelines. `_has` and chained params are used by EHR integrations and population health tools for cross-resource queries.

---

### P2.3 — `_include` and `_revinclude` Search Modifiers

- [x] Parse `_include={type}:{searchParam}` from search requests
- [x] After primary search, resolve all referenced resources and add to Bundle as `include` entries
- [x] Support `_include:iterate` for chained includes — frontier-based transitive resolution, max 3 levels, shared `seen` set prevents cycles (2026-09-08)
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
- [ ] Implement must-support enforcement for US Core Patient, Observation (Lab), Condition, AllergyIntolerance, Immunization, Encounter, MedicationRequest (server-side rejection of non-conformant resources — deferred)
- [x] Pass Inferno US Core test suite (ONC certification prerequisite) — all sections 2.1–2.50 pass locally (2026-09-07)
- [x] Update CapabilityStatement `supportedProfile` entries after running the import script — all 13 clinical/admin/medication resource types now declare their US Core v6.1.0 profile URLs statically; no import run required

**Why it matters:** US Core conformance is required for ONC Health IT Certification and for EHR integration with Cerner, Epic, and Meditech (all require US Core from their app partners).

---

### P2.7 — PATCH Operations

- [x] Implement `PATCH /{type}/{id}` with `Content-Type: application/json-patch+json` (JSON Patch, RFC 6902)
- [x] Implement `PATCH /{type}/{id}` with `Content-Type: application/fhir+json` (FHIRPath Patch — custom path resolver, no `fhirpathpy` required; supports replace/add/insert/delete/move — 2026-09-08)
- [x] Apply patches atomically; validate result against resource schema before persisting
- [x] Register in CapabilityStatement under each resource's `interaction` list

---

### P2.8 — System-Level and Type-Level History

- [x] Implement `GET /_history` (system-level history): all changes across all resource types since `_since`
- [x] Implement `GET /{type}/_history` (type-level history): all changes for one resource type
- [x] Return as `Bundle` with `type: history`, paginated with `_count` and `_since`
- [x] Register in CapabilityStatement under `interaction[type=history-system]` and `interaction[type=history-type]`

---

## Phase 2.9 — Code Review, QA & Security Hardening ⚡ HIGH PRIORITY

Full code review and security audit before any production deployment or commercial use. Run all scans in CI on every PR.

### P2.9.1 — Static Analysis & Linting

- [ ] Run `ruff` (lint + format) and `mypy` (type checking) on entire `backend/` — fix all errors, enforce in CI
- [ ] Run `bandit -r backend/` — Python security linter (SQL injection, shell injection, hardcoded secrets, weak crypto); fix all HIGH/MEDIUM findings
- [ ] Run `npm audit --audit-level=moderate` in `frontend/` — fix all moderate+ vulnerabilities
- [ ] Run `eslint` with security plugin (`eslint-plugin-security`) on `frontend/src/`
- [ ] Enforce both linters as required CI gates (no merge on failure)

### P2.9.2 — Dependency Vulnerability Scanning

- [ ] Run `pip-audit` on `backend/requirements.txt` — identify CVEs in pinned packages; upgrade or mitigate
- [ ] Run `npm audit` on `frontend/package.json` — fix or document all critical/high CVEs
- [ ] Pin all dependency versions (no unpinned `>=` ranges in `requirements.txt`)
- [ ] Add Dependabot or Renovate to automate weekly dependency PRs

### P2.9.3 — Container Image Scanning

- [ ] Run `trivy image` on all Docker images (`backend`, `frontend`, `nginx`) — fix all CRITICAL/HIGH OS-layer CVEs
- [ ] Run `docker scout cves` as alternative or complement
- [ ] Integrate Trivy scan into CI pipeline (fail build on CRITICAL findings)
- [ ] Pin base images to digest (`python:3.12-slim@sha256:...`) to prevent supply-chain drift

### P2.9.4 — Secrets & Credential Scanning

- [ ] Run `detect-secrets scan .` or `truffleHog filesystem .` — ensure no API keys, passwords, or tokens committed to repo
- [ ] Audit `.env.example` files — confirm no real credentials present
- [ ] Add `detect-secrets` pre-commit hook to prevent future secret commits
- [ ] Verify Keycloak admin credentials are not hardcoded anywhere in source (only in `.env` / environment)

### P2.9.5 — OWASP Top 10 Review

- [ ] **Injection (A03):** Audit all asyncpg queries — verify every parameter uses `$N` placeholders, no f-string SQL construction
- [ ] **Broken Authentication (A07):** Review JWT validation path (`auth.py`) — confirm algorithm whitelist, issuer check, expiry enforcement; test with expired/tampered tokens
- [ ] **Sensitive Data Exposure (A02):** Confirm PHI is never logged at INFO level (check `backend/` log calls); confirm Redis cache entries don't persist sensitive resources beyond TTL
- [ ] **SSRF (A10):** Audit all outbound HTTP calls (`external_cs.py`, `auth.py` JWKS fetch, `ai_assist.py`) — ensure URLs come from config, not user input
- [ ] **XSS (A03):** Audit React frontend — confirm no `dangerouslySetInnerHTML`; confirm API responses are not reflected into DOM without sanitization
- [ ] **Security Misconfiguration (A05):** Confirm CORS `allow_origins` is not `["*"]` in production config; confirm debug endpoints are disabled in prod
- [ ] **Broken Access Control (A01):** Verify clinician panel filter cannot be bypassed by crafting a JWT with a different `fhirUser` claim; verify patient cannot access another patient's resources
- [ ] Write one test per finding that would have caught it — add to `pytest` suite

### P2.9.6 — FHIR-Specific Security Review

- [ ] Verify `_revinclude` and `_include` cannot be used to pull resources outside the patient's compartment
- [ ] Verify Bulk Export (`$export`) enforces SMART `system/*.read` scope — patient-scoped tokens must not trigger system export
- [ ] Verify `DELETE /{type}/{id}` is gated behind `fhir-admin` role — clinicians and patients cannot delete records
- [ ] Verify audit log (`audit_log` table) cannot be modified via API — read-only from the FHIR layer
- [ ] Verify `POST /admin/users/*` endpoints require `fhir-admin` role and are not accessible with a patient or clinician token

### P2.9.7 — Backend Test Coverage

- [ ] Run `pytest --cov=app --cov-report=term-missing` — measure current coverage baseline
- [ ] Add integration tests for every auth middleware path (no token, expired token, wrong role, patient token on admin endpoint)
- [ ] Add integration tests for all search parameter combinations used by Inferno (regression guard)
- [ ] Add integration tests for Bundle batch + transaction (commit, rollback, `urn:uuid:` resolution)
- [ ] Target ≥ 70% line coverage on `routes/` and `app/` modules

**Why it matters:** Flint handles PHI. Any SQL injection or access control bypass in a healthcare FHIR server is a HIPAA breach event. This work is a prerequisite for any production deployment or commercial use, and directly supports ONC certification evidence requirements.

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

| Capability | Flint Now | Target | HAPI FHIR | Azure | Google | Medplum |
|---|---|---|---|---|---|---|
| Resource types | 22 | 30+ | 145 | 145 | 145 | 145 |
| SMART on FHIR | **Yes (Keycloak 24)** | ✓ | Plugin | Yes | Yes | v2 |
| Bulk Export | **Yes (IG v2)** | ✓ | Limited | ADLS2 | BigQuery | Limited |
| Da Vinci PAS | **Yes ($submit)** | Real payer | No | No | No | Partial |
| Terminology (SDO connectors) | **Excellent** | **Excellent** | External only | External only | External only | Basic |
| AI Integration | **Embedded** | **Extended** | None | Separate | Separate | Bots |
| Observability | **Included** | **Included** | Manual | Azure Monitor | Cloud Ops | Manual |
| Batch / Transaction | **Yes** | ✓ | Yes | Yes | Yes | Yes |
| US Core Conformance | **Inferno pass (local)** | Inferno pass (prod) | Yes | Yes | Yes | Yes (ONC) |
| Advanced Search (`_has`, chained, `_include:iterate`) | **Yes** | ✓ | Yes | Yes | Yes | Yes |
| CDA / HL7 v2 Ingest | No | P3.6/P3.7 | Plugin | Converter | Converter | None |
| Multi-tenancy | No | P3.1 | Partitioning | Native | Native | Native |
| Open source | Yes | Yes | Yes | No | No | Yes |

---

## ONC Certification Pathway

To qualify for ONC Health IT Certification (§170.315), Flint would need to complete at minimum:

- [x] **P0.5** — Accurate CapabilityStatement ✓
- [x] **P1.1–P1.6** — Patient, Observation, Condition, AllergyIntolerance, Encounter, Immunization ✓
- [x] **P2.1** — SMART on FHIR v2 ✓ (Keycloak 24, §170.315(g)(10))
- [x] **P2.5** — `$validate` with US Core profile checking ✓ (delegates to tx.fhir.org)
- [x] **P2.6** — Inferno US Core test suite pass ✓ (2026-09-07, all 2.1–2.50 sections pass locally)
- [ ] **P2.6** — US Core v6 must-support enforcement (server-side rejection — not yet implemented, deferred)
- [x] **P2.2** — `_has` and chained search params ✓
- [x] Pass Inferno ONC test suite locally (2026-09-07)
- [ ] Pass Inferno ONC test suite at https://inferno.healthit.gov (requires production TLS deployment)

### Running Inferno Locally

Inferno is available as a Docker image. Add it to the dev stack:

```bash
# Pull and run the Inferno Framework test runner (US Core test suite)
docker run --rm -it \
  -p 4567:4567 \
  inferno-program/inferno:latest

# Or use the newer Inferno Framework (recommended):
docker run --rm -it \
  -p 4567:4567 \
  infernoframework/inferno:latest
```

Point Inferno at `http://host.docker.internal` (or your host IP) so it can reach the Flint stack on port 80.

**Key Inferno test suites for Flint:**
- **US Core v6.1.0** — tests Patient, Observation, Condition, AllergyIntolerance, Immunization, Encounter, MedicationRequest searches and must-support element handling
- **SMART App Launch** — tests PKCE flow, token exchange, scope enforcement (requires Keycloak running with `--profile smart`)
- **Bulk Data IG** — tests `$export`, async job status, NDJSON file download

**Inferno prerequisites for Flint:**
1. SMART profile running: `docker compose --profile smart up -d`
2. Test patients seeded (Flint has 21+ patients; ensure dr-jones panel is populated)
3. `_has` and chained search params implemented (several US Core test cases require these)

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

## Nice-to-Have Backlog

Features with real but non-critical use cases — no current roadmap slot. Revisit when core phases are complete.

| Feature | Description | Why deferred |
|---|---|---|
| `_filter` search parameter | Boolean filter expressions on any search (e.g., `?_filter=code eq 1234-5 and status eq final`) — FHIR R4 "trial use" feature | Minimal real-world adoption; no EHR or payer system requires it; Inferno does not test it |

---

## Deployment Options — Docker vs. Non-Containerized

Flint does not have to run in Docker. Docker Compose is the development default, but every component can run outside containers.

### What Docker is doing for you

| Service | Docker role | Non-container equivalent |
|---|---|---|
| `backend` | Runs FastAPI via `uvicorn` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` on any Python 3.12 host |
| `frontend` | Vite dev server (dev) or static files (prod) | `npm run build` → static files on any CDN / S3 / Nginx |
| `postgres` | PostgreSQL 15 | Any PostgreSQL 15+ instance (RDS, Azure DB, Cloud SQL, bare-metal) |
| `redis` | Redis 7 | Any Redis 7+ instance (ElastiCache, Redis Cloud, Azure Cache, bare-metal) |
| `elasticsearch` | ES 8.11 | Any ES 8.x instance (Elastic Cloud, OpenSearch Service, bare-metal) |
| `nginx` | Reverse proxy + TLS termination | Any Nginx, Apache, Caddy, AWS ALB, Azure Application Gateway |
| `keycloak` | OIDC / SMART auth provider | Auth0, Okta, Azure AD B2C, AWS Cognito, or Keycloak on a VM — anything that issues OIDC JWTs |

### Option 1 — Traditional VM (no containers)

Install dependencies directly on Ubuntu/RHEL:

```bash
# Python 3.12 + backend deps
apt install python3.12 python3.12-venv
python3.12 -m venv venv && source venv/bin/activate
pip install -r flint/backend/requirements.txt
uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000

# Frontend build (run once; serve static output via Nginx)
cd flint/frontend && npm ci && npm run build
# Copy dist/ to Nginx web root

# PostgreSQL, Redis, Elasticsearch installed via apt/yum or managed cloud services
# Keycloak: download keycloak-24.zip, configure realm, run standalone.sh
```

Use `systemd` service units for process supervision (auto-restart on crash).

**Best for:** Single-tenant on-premise hospital deployment, air-gapped environments, or situations where Docker is not permitted by IT policy.

### Option 2 — Cloud-Native Managed Services (recommended for SaaS)

Replace every infrastructure component with a managed equivalent — only the application code runs on your compute:

| Component | AWS | Azure | GCP |
|---|---|---|---|
| Backend (FastAPI) | ECS Fargate / App Runner / Lambda | Container Apps / App Service | Cloud Run |
| PostgreSQL | RDS for PostgreSQL | Azure Database for PostgreSQL | Cloud SQL |
| Redis | ElastiCache Serverless | Azure Cache for Redis | Memorystore |
| Elasticsearch | OpenSearch Service | Elastic on Azure Marketplace | Elastic on GCP |
| Auth (Keycloak replacement) | Cognito | Azure AD B2C | Firebase Auth / Identity Platform |
| Frontend | S3 + CloudFront | Static Web Apps | Firebase Hosting |
| TLS / Proxy | ALB | Application Gateway | Cloud Load Balancing |

The backend reads all service addresses from environment variables (`DATABASE_URL`, `REDIS_URL`, `ELASTICSEARCH_HOSTS`, `OIDC_ISSUER_URL`) — swapping cloud endpoints requires only `.env` changes, no code changes.

**Keycloak replacement note:** Replacing Keycloak with Auth0/Cognito/Azure AD requires that the new provider issues OIDC tokens with the SMART claims (`patient`, `fhirUser`, `launch/patient`). Standard enterprise IdPs support custom claims but need configuration. Keycloak is the easiest path for full SMART on FHIR v2 compliance today.

**Best for:** Multi-tenant SaaS, elastic scaling, no ops team to manage infrastructure.

### Option 3 — PaaS (Heroku, Railway, Render)

These platforms accept a `Dockerfile` or `Procfile` and abstract the container runtime away from you. You push code; the platform builds and runs it.

```
# Procfile (Railway / Heroku)
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Add-ons (Heroku Postgres, Redis Cloud, Elastic Cloud) supply the backing services. The frontend deploys as a static site.

**Limitation:** Keycloak is too heavy for hobby-tier PaaS. Use Auth0 or an external OIDC provider.

### Option 4 — Kubernetes (containerized but not Docker Compose)

The same Docker images used in development deploy to Kubernetes (EKS, AKS, GKE) with Helm charts or Kustomize manifests. This is containerized but operationally very different from Docker Compose — proper for high-availability production.

**Best for:** Large-scale multi-tenant SaaS or healthcare cloud platforms with existing k8s infrastructure.

### What genuinely requires containers or VMs

Elasticsearch does not have a serverless-tier that supports the custom index settings Flint uses (nested object limit, GIN-equivalent). You need either a managed ES instance (Elastic Cloud) or a VM-hosted one. Lambda/serverless-only environments won't work for ES.

---

## How to Use This Document

1. Pick a phase/item to work on
2. Create a branch named `feat/P{phase}.{item}-{short-description}` (e.g. `feat/P0.2-version-history-url`)
3. Check off sub-items as you implement them
4. Update the **Current State Summary** table at the top when a Phase completes
5. Add newly discovered gaps or technical debt to the appropriate section rather than creating separate tracking issues

For architectural decisions on any item, create an ADR (Architecture Decision Record) in `docs/adr/` before implementing.
