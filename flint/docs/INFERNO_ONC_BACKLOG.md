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

## Common Pitfalls (lessons from active testing)

### 1. Always include `Coding.display` — look it up, don't omit it

Always include `display` on every `Coding`. Omitting it limits UI rendering and client functionality. The FHIR validator treats a present-but-wrong display as an **ERROR** that blocks conformance — the solution is to verify, not omit.

**Lookup pattern:** `https://tx.fhir.org/r4/CodeSystem/$lookup?system=<system>&code=<code>&_format=json` — extract the `valueString` for the `display` parameter. For SNOMED, also verify the concept is what you think it is (e.g. 360129009 is "Cardiac pacemaker lead", not the device — 14106009 is "Cardiac pacemaker").

Before writing any `Coding.display` in seed data, look up the exact canonical display. Examples that burned us:

| System | Code | Wrong | Correct |
|--------|------|-------|---------|
| `http://hl7.org/fhir/us/core/CodeSystem/us-core-category` | `sdoh` | `"Social Determinants of Health"` | `"SDOH"` |
| `http://terminology.hl7.org/CodeSystem/v3-TribalEntityUS` | `187` | (any abbreviation) | `"Paiute-Shoshone Tribe of the Fallon Reservation and Colony, Nevada"` |

Rule: if the profile validator returns `"Wrong Display Name '...' for <system>#<code>. Valid display is '...'"` — update the display, it's not optional.

### 2. The `screening-assessment` category slice uses `us-core-category`, not `us-core-tags`

US Core 6.1.0 Condition Problems/Health Concerns has a `screening-assessment` must-support category slice. The correct binding is:

```json
{
  "system": "http://hl7.org/fhir/us/core/CodeSystem/us-core-category",
  "code": "sdoh",
  "display": "SDOH"
}
```

Other valid codes in this system: `functional-status`, `disability-status`, `cognitive-status`.

Do NOT use `http://hl7.org/fhir/us/core/CodeSystem/us-core-tags` with code `screening-assessment` — that system does not exist for this purpose.

### 3. Two separate Condition profiles with different category requirements

| Profile | Category system | Category code |
|---------|----------------|--------------|
| `us-core-condition-encounter-diagnosis` | `http://terminology.hl7.org/CodeSystem/condition-category` | `encounter-diagnosis` |
| `us-core-condition-problems-health-concerns` | `http://terminology.hl7.org/CodeSystem/condition-category` | `problem-list-item` |

Problems/health-concerns resources also need a **second** `category` entry for the `screening-assessment` slice (see above).

### 4. `http://example.org/` system URLs are rejected as errors

The FHIR validator treats any `identifier.system` (or similar URI field) from the `http://example.org/` domain as a hard ERROR that blocks profile conformance. Use a domain that looks real, e.g. `https://flinthealthsystem.org/coverage/member-id`. The warning about a code "not in the value set" for extensible bindings is a warning only and does not block conformance.

### 5. Resource types in patient compartment must be registered in `_PATIENT_COMPARTMENT`

Every resource type accessible via a patient-scoped SMART token needs an entry in `_PATIENT_COMPARTMENT` in `resource_factory.py`. Without it, the token's patient filter is skipped and the resource is either inaccessible or returns all records. Coverage uses `beneficiary` instead of `subject`:

```python
"Coverage": ("data->'beneficiary'->>'reference'", lambda r: (r.get("beneficiary") or {}).get("reference")),
```

After adding a new entry, rebuild the backend: `docker compose up -d --build backend`.

### 6. `fhir_resources` table schema — correct column names

```
id          uuid
resource_type text
data        jsonb    ← all FHIR content lives here
status      text
updated_at  timestamp   ← NOT "last_updated"
version     varchar     ← NOT "version_id"
created_at  timestamp
```

Verify with: `docker compose exec postgres psql -U flint -d flint -c '\d fhir_resources'`

### 7. Piping SQL files into Docker on Windows

`docker compose exec postgres psql -f /tmp/seed.sql` resolves `/tmp` to the Windows temp dir, not the container. Use stdin instead:

```bash
docker compose exec -T postgres psql -U flint -d flint < seed_file.sql
```

The `-T` flag disables pseudo-TTY allocation (required for stdin piping).

### 8. Surgical JSON updates with `jsonb_set`

To update a single field in a stored FHIR resource without rewriting the whole blob:

```sql
UPDATE fhir_resources SET
  data = jsonb_set(data, '{category,1,coding,0,display}', '"SDOH"'::jsonb)
WHERE id = '<uuid>' AND resource_type = 'Condition';
```

The path is an array of string keys/integer indices. The new value must be valid JSONB (string values need `'"value"'::jsonb`).

### 9. Direct DB seed scripts bypass Redis cache

When updating seed data directly via SQL or asyncpg (not through the FastAPI layer), the backend's Redis invalidation never fires. Subsequent API search responses are served stale from Redis (120s TTL). After any direct DB seed change, flush the cache:

```bash
docker compose exec -T redis redis-cli FLUSHDB
```

This is safe in dev — it only clears cached search results, not stored FHIR resources.

### 10. Blood pressure observations require LOINC `85354-9`, not `55284-4`

The base FHIR `bp` profile (`http://hl7.org/fhir/StructureDefinition/bp|4.0.1`) has a `BPCode` invariant requiring exactly code `85354-9` ("Blood pressure panel with all children optional"). Using `55284-4` ("Blood pressure systolic and diastolic") produces a validation **ERROR** (not warning), failing profile conformance. This was discovered in section 2.23 when Inferno re-validated previously-returned vital signs observations against the Simple Observation profile.

Always use `85354-9` for any blood pressure panel observation:

```json
"code": {
  "coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel with all children optional"}],
  "text": "Blood pressure panel with all children optional"
}
```

### 11. Simple Observation invariant — component-only observations need dataAbsentReason

The `us-core-simple-observation` invariant: `value.exists() or component.exists() or hasMember.exists() or dataAbsentReason.exists()`

Blood pressure observations only have `component` entries (systolic/diastolic) and no top-level `value[x]`. While `component.exists()` technically satisfies the invariant, adding `dataAbsentReason: not-applicable` makes it explicit and avoids ambiguity:

```json
"dataAbsentReason": {
  "coding": [{"system": "http://terminology.hl7.org/CodeSystem/data-absent-reason", "code": "not-applicable", "display": "Not Applicable"}]
}
```

### 12. Inferno section workflow

For each new section:
1. Run cold — read errors verbatim.
2. **Check seed data first** (meta.profile, display names, category systems, must-support elements).
3. **Check search hooks second** (`routes/clinical.py` / `routes/medications.py` / etc.).
4. If code changed: `docker compose up -d --build backend`, then re-run.
5. If only seed data changed: re-run immediately (no rebuild needed).

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
**Status:** See per-section table below
**Severity:** Required for ONC certification

| Section | Status |
|---------|--------|
| 2.1 CapabilityStatement | ✅ Pass |
| 2.2 Patient | ✅ Pass |
| 2.3 AllergyIntolerance | ✅ Pass |
| 2.4 Care Plan | ✅ Pass |
| 2.5 Care Team | ✅ Pass |
| 2.6 Condition (encounter-diagnosis) | ✅ Pass |
| 2.7 Condition (problems-health-concerns) | ✅ Pass |
| 2.8 Coverage | ✅ Pass |
| 2.9 Device | ✅ Pass |
| 2.10 DiagnosticReport (Note) | ✅ Pass |
| 2.11 DiagnosticReport (Lab) | ✅ Pass |
| 2.12 DocumentReference | ✅ Pass |
| 2.13 Encounter | ✅ Pass |
| 2.14 Goal | ✅ Pass |
| 2.15 Immunization | ✅ Pass |
| 2.16 Location | ✅ Pass |
| 2.17 Medication | ✅ Pass |
| 2.18 MedicationDispense | ✅ Pass |
| 2.19 MedicationRequest | ✅ Pass |
| 2.20 Observation (Clinical Result) | ✅ Pass |
| 2.21 Observation (Lab) | ✅ Pass |
| 2.22 Observation (Occupation) | ✅ Pass |
| 2.23 Observation (Simple) | ⏳ In progress — fixes applied 2026-07-12 |
| 2.24+ | ⏳ Not yet run |

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

#### Section 2.6 — Condition (Encounter Diagnosis) ✅ Pass

All 2.6.x tests pass. Fixes applied:
- Wired `category`, `clinical-status`, `code`, `onset-date`, `abatement-date`, `recorded-date`, `asserted-date`, `encounter` search params in `_condition_search_hook` in `routes/clinical.py`
- `category` uses EXISTS + JSONB containment on `data->'category'` array (not simple equality)
- `asserted-date` queries the `condition-assertedDate` extension via `_extension_date_condition()`
- Seeded Encounter `a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890` (status=finished, class=AMB, type=SNOMED 185349003, subject=alice)
- Seeded active condition `d4e5f6a7` (I10 Essential hypertension) + updated `b1c2d3e4` (E11.9 resolved, with abatementDateTime, encounter ref)
- All conditions declare `meta.profile = us-core-condition-encounter-diagnosis`

---

#### Section 2.7 — Condition (Problems/Health Concerns) — Fixed, pending re-run

Fixes applied:
- Seeded two problems-health-concerns conditions for alice:
  - `e5f6a7b8` — F32.9 Major depressive disorder, active
  - `c2d3e4f5` — J06.9 Acute upper respiratory infection, resolved (with abatementDateTime)
- Both declare `meta.profile = us-core-condition-problems-health-concerns` and `category[0] = problem-list-item`
- `screening-assessment` must-support slice satisfied by `category[1]`:
  ```json
  {
    "system": "http://hl7.org/fhir/us/core/CodeSystem/us-core-category",
    "code": "sdoh",
    "display": "SDOH"
  }
  ```
  The display was initially `"Social Determinants of Health"` — corrected to `"SDOH"` via `jsonb_set` after the FHIR validator flagged it as an ERROR.
- All conditions reference Encounter `a1b2c3d4` (same encounter as section 2.6)

---

#### Section 2.23 — Observation (Simple) — Fixes applied 2026-07-12, pending re-run

Two failing tests:
- **2.23.08** — Resources do not conform to `us-core-simple-observation|6.1.0`
- **2.23.09** — `valueBoolean` and `derivedFrom` not found in returned resources (must-support)

Fixes applied:

1. **BP code corrected** — Both `obs-alice-bp-001` and `a9b0c1d2-e3f4-5678-a9b0-c1d2e3f45678` had LOINC `55284-4` (discouraged). Updated to `85354-9` ("Blood pressure panel with all children optional"). The `BPCode` invariant from the base `bp` profile requires this exact code — see pitfall #10 above.

2. **`dataAbsentReason` added to BP observations** — Both BP observations were component-only (no top-level `value[x]`). Added `dataAbsentReason: not-applicable` to satisfy the Simple Observation invariant explicitly.

3. **`derivedFrom` added to BMI** — `obs-alice-bmi-001` now references `Observation/obs-alice-height-001` and `Observation/obs-alice-weight-001` in `derivedFrom` (must-support element).

4. **New survey observation seeded** — `obs-alice-food-insecurity-001`: LOINC `88124-3` ("Food insecurity risk [HVS]"), category=survey, `valueBoolean: true`, `meta.profile=us-core-simple-observation`. Satisfies the `valueBoolean` must-support element.

5. **Redis flushed** — Seed script bypassed the API (direct asyncpg writes), so Redis cache was stale. Flushed with `FLUSHDB` after all DB changes.

**Note:** Section 2.23 tests re-validate ALL observations returned in previous sections (vital signs, lab, etc.) against the Simple Observation profile, not just observations explicitly profiled as `us-core-simple-observation`. Any non-conforming observation from earlier sections will surface here.

---

#### Section 2.3+ — Remaining Resource Types (not yet run)

Known gaps to address before running each section:
- **All types:** `meta.profile` with the correct US Core v6.1.0 profile URL; a Provenance resource per clinical resource
- **Observation (2.3):** `category=laboratory` (system: `http://terminology.hl7.org/CodeSystem/observation-category`); `meta.profile` must be the specific US Core Observation profile (e.g. `us-core-observation-lab`)
- **AllergyIntolerance:** `clinicalStatus` or `verificationStatus` required
- **MedicationRequest:** `requester` required
- **Encounter (2.11):** alice has Encounter `a1b2c3d4` seeded — verify all must-support elements before running

**How to test:**
Run each section in Inferno with alice's patient-scoped SMART token. Check the Common Pitfalls section at the top of this file before starting each one.

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
| `us-core-tribal-affiliation` display name wrong for code `187` | Changed display to `"Paiute-Shoshone Tribe of the Fallon Reservation and Colony, Nevada"` — validator rejects mismatched display names as errors |
| `_revinclude=Provenance:target` not supported — `Provenance.target` is an array | Added `Provenance:target` to `_INCLUDE_REFERENCE_MAP` with EXISTS condition; fixed `_revinclude` handlers to support full condition templates |
| No Provenance resource for alice's Patient (test 2.2.10) | Created US Core-compliant Provenance resource in DB (`agent.type=author`, `meta.profile=us-core-provenance`) |
| Condition 2.6: category/clinical-status/code search returned 0 results | Rewrote category search to use EXISTS + JSONB containment on `data->'category'` array; `clinical-status` uses `_token_condition` on `data->'clinicalStatus'->'coding'` |
| Condition 2.6: `asserted-date` search not wired | Added `_extension_date_condition("http://hl7.org/fhir/StructureDefinition/condition-assertedDate", ...)` to `_condition_search_hook` |
| Condition 2.6: no Encounter reference or active/resolved pair for alice | Seeded Encounter `a1b2c3d4` + active condition `d4e5f6a7` (I10) + updated `b1c2d3e4` (E11.9 resolved with abatementDateTime) |
| Condition 2.7: `screening-assessment` slice not found (test 2.7.14) | Added `category[1]` with system `us-core-category` / code `sdoh` to both problems-health-concerns conditions |
| Condition 2.7: validator ERROR wrong display `"Social Determinants of Health"` (test 2.7.13) | Fixed to canonical display `"SDOH"` via `jsonb_set(data, '{category,1,coding,0,display}', '"SDOH"'::jsonb)` |
| Coverage 2.8: no Coverage resources returned for alice (all 2.8.x tests) | Added `Coverage` to `_PATIENT_COMPARTMENT` in `resource_factory.py` (path: `data->'beneficiary'->>'reference'`); applied `_patient_ref()` in `_coverage_search_hook`; seeded Coverage + Provenance |
| Coverage 2.8: `identifier:memberid` slice not found (test 2.8.05) | Added `identifier[0]` with `type.coding[0] = {system: v2-0203, code: MB, display: "Member Number"}` |
| Coverage 2.8: validator ERROR `identifier.system` uses `http://example.org/` domain (test 2.8.04) | Changed to `https://flinthealthsystem.org/coverage/member-id` — example.org URLs are explicitly rejected by the FHIR validator |
| SMART well-known capabilities missing `context-standalone-patient`, `permission-patient` | Added to `auth_routes.py` |
| Token response missing `patient` and `fhirUser` claims | Token proxy (`/auth/token-proxy`) promotes JWT claims into response body |
| Token response missing `Cache-Control: no-store` | Added to token proxy response headers |
| Granular `patient/<Resource>.rs` scopes not accepted by Keycloak | 29 scopes created and linked to `flint-app` |
| `offline_access` scope rejected — users lacked `offline_access` role | Role added to alice, dr-jones, admin |
| `fhirUser` absolute URL broke `get_patient_context` in `auth.py` | `_extract_fhir_id` helper handles both relative and absolute URLs |
| SMART v2 `.rs` scope not recognised by `has_fhir_scope` | Updated to handle single-char SMART v2 access codes |
| Keycloak healthcheck used `curl` (not available in UBI9 image) | Replaced with bash TCP check |
| Inferno redirect URI pointed to unexposed port 4567 | Set `INFERNO_HOST=http://localhost:8081` in Inferno docker-compose |
| BP obs 2.23.08: ERROR `BPCode` invariant — LOINC `55284-4` not accepted | Changed both BP observations to `85354-9` ("Blood pressure panel with all children optional") — base `bp` profile requires this exact code |
| BP obs 2.23.08: Simple Observation invariant failed (no value[x] or dataAbsentReason) | Added `dataAbsentReason: not-applicable` to both BP observations (`obs-alice-bp-001`, `a9b0c1d2-e3f4-5678-a9b0-c1d2e3f45678`) |
| 2.23.09: `derivedFrom` not found in any returned observation | Added `derivedFrom: [height, weight]` to `obs-alice-bmi-001` |
| 2.23.09: `valueBoolean` not found in any returned observation | Seeded `obs-alice-food-insecurity-001` (LOINC 88124-3, survey, `valueBoolean: true`, profile=us-core-simple-observation) |
| 2.23 fixes not reflected after seed script ran — stale Redis | Flushed cache with `docker compose exec -T redis redis-cli FLUSHDB` — direct DB writes bypass API cache invalidation |
