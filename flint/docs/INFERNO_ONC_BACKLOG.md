# Inferno / ONC Certification Backlog

Tracked issues discovered during local Inferno US Core v6.1.0 testing that require a production environment to verify or resolve. Items marked **local-only** cannot be addressed in a local HTTP setup.

---

## How to Run Inferno Against Production

Once deployed:

1. Open the Inferno instance (separate Docker stack, not part of Flint)
2. Select **US Core Server v6.1.0**
3. Set **FHIR Server URL** to `https://<your-domain>`
4. Set **SMART App Launch Version** to STU2
5. Set **Client ID** to `flint-app`
6. Set **Requested Scopes** to the full granular list (copy from Inferno's warning banner)
7. Run all groups — SMART Launch → OpenID Connect → Token Refresh → US Core Resources

---

## Open Items

---

### ONC-001 — TLS on OAuth2 Authorize Endpoint

**Inferno Test:** 1.3.2.01 — *OAuth 2.0 authorize endpoint secured by transport layer security*
**Status:** Fails locally (expected) · Will pass in production
**Severity:** Required for ONC certification

**What it checks:**
Inferno attempts a TLS handshake against the `authorization_endpoint` URL returned in the SMART well-known config. The endpoint must respond on `https://` — HTTP is rejected outright.

**Why it fails locally:**
The authorization endpoint is `http://host.docker.internal:8080/realms/fhir/protocol/openid-connect/auth`. Port 8080 is plain HTTP with no TLS.

**How to fix in production:**
1. Ensure Keycloak is accessible only via the nginx reverse proxy (do not expose port 8080 publicly)
2. In `docker-compose.prod.yml`, do **not** publish Keycloak's port 8080 to the host
3. Configure nginx with a valid TLS certificate (Let's Encrypt / Certbot):
   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;
       ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
       ssl_protocols TLSv1.2 TLSv1.3;
   }
   ```
4. In `.env.prod`, set:
   ```
   OIDC_PUBLIC_ISSUER_URL=https://your-domain.com/realms/fhir
   BASE_URL=https://your-domain.com
   ```
5. The `authorization_endpoint` in the SMART well-known config will then be `https://your-domain.com/realms/fhir/protocol/openid-connect/auth`, which Inferno will accept.

**Verification:**
```bash
curl -sv https://your-domain.com/.well-known/smart-configuration \
  | python3 -m json.tool | grep authorization_endpoint
# Should start with https://
```

---

### ONC-002 — TLS on OAuth2 Token Endpoint

**Inferno Test:** 1.3.2.04 — *OAuth 2.0 token endpoint secured by transport layer security*
**Status:** Fails locally (expected) · Will pass in production
**Severity:** Required for ONC certification

**What it checks:**
Inferno verifies that the `token_endpoint` in the SMART well-known config uses `https://` and that a valid TLS handshake completes.

**Why it fails locally:**
The token endpoint is `http://host.docker.internal/auth/token-proxy`, which is plain HTTP on port 80.

**How to fix in production:**
The fix is the same as ONC-001 — TLS termination at nginx. Once nginx serves HTTPS on port 443 and `BASE_URL=https://your-domain.com` is set, the token proxy URL advertised in the well-known config becomes:
```
https://your-domain.com/auth/token-proxy
```
This passes the TLS check automatically. No additional code changes needed.

**Verification:**
```bash
curl -sv https://your-domain.com/.well-known/smart-configuration \
  | python3 -m json.tool | grep token_endpoint
# Should be https://your-domain.com/auth/token-proxy
```

---

### ONC-003 — US Core Resource Validation

**Inferno Tests:** 2.x — *US Core Patient, Observation, Condition, Encounter, etc.*
**Status:** Section 2.1 (CapabilityStatement) ✅ · Section 2.2 (Patient) ✅ fixed, pending re-run · Sections 2.3+ not yet run
**Severity:** Required for ONC certification

**What it checks:**
Inferno queries Flint for each US Core profile resource type and validates:
- Required search parameters return results
- Resources conform to the profile (must-support elements present)
- Correct `meta.profile` URLs declared on resources

---

#### Section 2.1 — CapabilityStatement (complete as of 2026-07-11)

All 2.1.x tests pass. Fixes applied:
- Added `instantiates: ["http://hl7.org/fhir/us/core/CapabilityStatement/us-core-server"]` to CapabilityStatement in `main.py`
- Added `implementation: {description, url}` (derived from `BASE_URL` env var) to CapabilityStatement in `main.py`

---

#### Section 2.2 — Patient (fixed as of 2026-07-11, pending re-run confirmation)

Fixes applied:
- Rewrote `_patient_search_hook` in `routes/clinical.py` to use JSONB traversal for `name`/`family`/`given` (was using broken TEXT `name` column) and JSONB containment (`@>`) for `identifier` (previous `jsonb_array_elements` approach caused asyncpg type error)
- Added `POST /{type}/_search` handler (`_search_post`) to `routes/resource_factory.py` for FHIR search-by-POST (§3.2.2)
- Fixed scope enforcement in `main.py`: `POST /_search` is semantically a read; `effective_method = "GET"` when path ends with `/_search`
- Updated alice's Patient record with all US Core 6.1.0 must-support elements: race, ethnicity, birthsex, sex (`248152002` SNOMED), genderIdentity, tribal-affiliation, name variants (official + old with period), suffix, two addresses (home + old with period), `deceasedDateTime`, `communication.language`, `meta.profile`
- Fixed `us-core-sex` valueCode from `"female"` to `"248152002"` (SNOMED Female finding — required binding in `us-core-sex-for-clinical-use` ValueSet)
- Added `Provenance:target` to `_INCLUDE_REFERENCE_MAP` in `resource_factory.py` with EXISTS-based condition (handles array `target` field); fixed both `_revinclude` handlers to use sql_path as full condition template when it contains `??`
- Created US Core-compliant Provenance resource in DB targeting alice's Patient (`agent.type=author`, `meta.profile=us-core-provenance`)

**Test 2.2.08** (birthsex) — skipped by Inferno (optional element, not required for test to run)

---

#### Section 2.3+ — Remaining Resource Types (not yet run)

Known gaps to address before running:
- `Observation.category` must be `laboratory` (system: `http://terminology.hl7.org/CodeSystem/observation-category`) on lab observations; `meta.profile` must declare the specific US Core Observation profile (e.g. `us-core-observation-lab`)
- `Condition.clinicalStatus` must be populated (required by US Core); `meta.profile` pointing to correct Condition profile
- `MedicationRequest.requester` must be populated
- `AllergyIntolerance.clinicalStatus` or `verificationStatus` must be present
- All resources should declare `meta.profile` with the US Core v6.1.0 profile URL
- Seed data for alice must include resources for all tested types (Observation, Condition, Encounter, AllergyIntolerance, Immunization, MedicationRequest, Procedure, DiagnosticReport)

**How to test:**
Run Section 2.3 onward in Inferno with alice's patient-scoped SMART token. Work through failures one section at a time.

---

### ONC-004 — DocumentReference / Binary Support

**Inferno Tests:** US Core DocumentReference group
**Status:** Not implemented
**Severity:** Required for ONC certification (g10)

**What it checks:**
Servers must support `DocumentReference` resources with a `content.attachment.url` pointing to a `Binary` resource, and the Binary must be accessible with the patient's token.

**How to fix:**
- Implement `Binary` resource type (read + create)
- Ensure `DocumentReference.content.attachment.url` resolves to `/Binary/{id}`
- Add `Binary` to nginx routing regex
- Add to CapabilityStatement

---

### ONC-005 — Provenance Support

**Inferno Tests:** US Core Provenance group (also tested via `_revinclude=Provenance:target` on each resource type search)
**Status:** Partial — `_revinclude` wired and alice's Patient Provenance seeded; remaining clinical types need Provenance resources
**Severity:** Required for ONC certification

**What it checks:**
For each clinical resource returned, Inferno checks that a `Provenance` resource exists with a `target` reference pointing to that resource. The Provenance must include `agent.who` (the author) and `recorded` (timestamp).

**Done (2026-07-11):**
- `_revinclude=Provenance:target` now works — `Provenance:target` added to `_INCLUDE_REFERENCE_MAP` in `resource_factory.py` with an EXISTS-based condition (handles Provenance.target as a JSONB array)
- The `_revinclude` handler in both `_search` and `_search_post` now supports full condition templates (sql_path containing `??`) for array-type references
- Provenance resource seeded for alice's Patient (`target → Patient/alice`, `agent.type=author`, `agent.who → dr-jones Practitioner`, `meta.profile=us-core-provenance`)

**Still needed:**
- Seed Provenance resources for alice's Observation, Condition, Encounter, AllergyIntolerance, Immunization, MedicationRequest, Procedure, DiagnosticReport resources
- Add `Provenance` to `_PATIENT_COMPARTMENT` in `resource_factory.py` (needs special handling — `target` is an array, so the current `{sql_path} = ??` pattern doesn't apply directly)
- Register `GET /Provenance/{id}` route if Inferno reads Provenance resources directly by ID
- Ensure `agent.type` uses `http://terminology.hl7.org/CodeSystem/provenance-participant-type` with code `author`
- Declare `meta.profile` = `http://hl7.org/fhir/us/core/StructureDefinition/us-core-provenance` (already done for alice's Provenance)

---

## Completed / Resolved

| Item | Resolution |
|---|---|
| CapabilityStatement missing `instantiates` (test 2.1.06) | Added `"instantiates": ["http://hl7.org/fhir/us/core/CapabilityStatement/us-core-server"]` to `main.py` |
| CapabilityStatement missing `implementation.url` (test 2.1.02) | Added `"implementation": {"description": ..., "url": BASE_URL}` to `main.py` |
| `POST /Patient/_search` returned 403 | Added `_search_post` handler to `resource_factory.py`; fixed scope check to treat `/_search` path as read |
| Patient `name`/`family`/`given` search returned no results | Rewrote `_patient_search_hook` in `clinical.py` to use `jsonb_array_elements` traversal (was using broken TEXT `name` column) |
| Patient `identifier` search returned 500 | Switched from `jsonb_array_elements` to JSONB containment (`@>`) to avoid asyncpg type error |
| Alice missing US Core 6.1.0 must-support elements (test 2.2.12) | Added race, ethnicity, birthsex, sex, genderIdentity, tribal-affiliation, name variants, suffix, address variants with period, `deceasedDateTime`, `meta.profile` |
| `us-core-sex` used wrong value code (`"female"`) | Changed to SNOMED code `"248152002"` (Female finding) — required binding in `us-core-sex-for-clinical-use` ValueSet |
| `_revinclude=Provenance:target` not supported — `Provenance.target` is an array | Added `Provenance:target` to `_INCLUDE_REFERENCE_MAP` with EXISTS condition; fixed `_revinclude` handlers to support full condition templates |
| No Provenance resource for alice's Patient (test 2.2.10) | Created US Core-compliant Provenance resource in DB (`agent.type=author`, `meta.profile=us-core-provenance`) |
| SMART well-known capabilities missing `context-standalone-patient`, `permission-patient` | Added to `auth_routes.py` |
| Token response missing `patient` and `fhirUser` claims | Token proxy (`/auth/token-proxy`) promotes JWT claims into response body |
| Token response missing `Cache-Control: no-store` | Added to token proxy response headers |
| Granular `patient/<Resource>.rs` scopes not accepted by Keycloak | 29 scopes created and linked to `flint-app` |
| `offline_access` scope rejected — users lacked `offline_access` role | Role added to alice, dr-jones, admin |
| `fhirUser` absolute URL broke `get_patient_context` in `auth.py` | `_extract_fhir_id` helper handles both relative and absolute URLs |
| SMART v2 `.rs` scope not recognised by `has_fhir_scope` | Updated to handle single-char SMART v2 access codes |
| Keycloak healthcheck used `curl` (not available in UBI9 image) | Replaced with bash TCP check |
| Inferno redirect URI pointed to unexposed port 4567 | Set `INFERNO_HOST=http://localhost:8081` in Inferno docker-compose |
