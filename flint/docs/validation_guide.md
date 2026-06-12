# Terminology Validation Guide

PH-TS implements FHIR R4 terminology validation operations that can be used
standalone or as the validation back-end for HL7 v2 messages, FHIR resources,
CDA documents, or any system that needs to confirm a code is valid.

---

## Table of Contents

1. [Validation Operations Overview](#1-validation-operations-overview)
2. [Single Code Validation — $validate-code](#2-single-code-validation----validate-code)
3. [Single Code Lookup — $lookup](#3-single-code-lookup----lookup)
4. [Batch Validation — $validate-batch](#4-batch-validation----validate-batch)
5. [HL7 v2 Message Validation](#5-hl7-v2-message-validation)
6. [Loading HL7 v2 Tables](#6-loading-hl7-v2-tables)
7. [Supported Code Systems](#7-supported-code-systems)
8. [Integration Patterns](#8-integration-patterns)
9. [Response Reference](#9-response-reference)
10. [ConceptMap CRUD — Cross-System Translation Maps](#10-conceptmap-crud----cross-system-translation-maps)
11. [Code Translation — $translate](#11-code-translation----translate)
12. [Hierarchy — $subsumes](#12-hierarchy----subsumes)
13. [SNOMED CT ECL in $expand](#13-snomed-ct-ecl-in-expand)
14. [LOINC Hierarchy via $lookup Properties](#14-loinc-hierarchy-via-lookup-properties)

---

## 1. Validation Operations Overview

| Operation | Endpoint | Use when… |
|---|---|---|
| `$validate-code` | `GET/POST /ValueSet/$validate-code` | You need to confirm a code is a member of a specific ValueSet |
| `$lookup` | `GET/POST /CodeSystem/$lookup` | You need to confirm a code exists in a CodeSystem and get its display name |
| `$validate-batch` | `POST /ValueSet/$validate-batch` | You have many codes to validate at once (e.g., all fields in an HL7 v2 message) |
| `$expand` | `GET/POST /ValueSet/$expand` | You want to retrieve the full list of valid codes in a ValueSet |
| `$translate` | `GET/POST /ConceptMap/$translate` | You need to map a code from one code system to an equivalent in another |
| `$subsumes` | `GET /CodeSystem/$subsumes` | You need to check hierarchy — does code A subsume (contain) code B? |
| ECL `$expand` | `GET /ValueSet/$expand?url=...fhir_vs=isa/...` | Expand all descendants of a SNOMED CT concept |
| `$lookup` + properties | `GET /CodeSystem/$lookup?property=parent&property=child` | Retrieve LOINC hierarchy properties for a code |

All endpoints are available at `http://localhost` (via Nginx) or directly at
`http://localhost:8000`.

---

## 2. Single Code Validation — `$validate-code`

Checks whether a code belongs to a specific ValueSet. Returns `true` or `false`
plus the expected display name.

### GET

```bash
GET /ValueSet/$validate-code?url=<valueSetUrl>&code=<code>[&system=<system>][&display=<display>]
```

**Parameters**

| Parameter | Required | Description |
|---|---|---|
| `url` | Yes | Canonical URL of the ValueSet to validate against |
| `code` | Yes | The code value to validate |
| `system` | No | Code system URL — disambiguates if the ValueSet spans multiple systems |
| `display` | No | Expected display name — if provided, a mismatch returns a warning message |

**Examples**

```bash
# Validate administrative sex code against FHIR core ValueSet
curl "http://localhost/ValueSet/\$validate-code?url=http://hl7.org/fhir/ValueSet/administrative-gender&code=M"

# Validate with system and display check
curl "http://localhost/ValueSet/\$validate-code?url=http://hl7.org/fhir/ValueSet/administrative-gender&code=M&system=http://hl7.org/fhir/administrative-gender&display=Male"

# Validate a LOINC code against a lab result ValueSet
curl "http://localhost/ValueSet/\$validate-code?url=http://loinc.org/vs/LL379-9&code=LA6626-1"

# Validate a SNOMED code
curl "http://localhost/ValueSet/\$validate-code?url=http://snomed.info/sct?fhir_vs&code=73211009"
```

### POST (FHIR Parameters format)

```bash
curl -X POST http://localhost/ValueSet/\$validate-code \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Parameters",
    "parameter": [
      { "name": "url",     "valueUri":    "http://hl7.org/fhir/ValueSet/administrative-gender" },
      { "name": "code",    "valueCode":   "M" },
      { "name": "system",  "valueUri":    "http://hl7.org/fhir/administrative-gender" },
      { "name": "display", "valueString": "Male" }
    ]
  }'
```

### Response

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "result",  "valueBoolean": true },
    { "name": "display", "valueString":  "Male" },
    { "name": "message", "valueString":  "Code is valid" }
  ]
}
```

When invalid:

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "result",  "valueBoolean": false },
    { "name": "message", "valueString":  "Code not found in ValueSet" }
  ]
}
```

---

## 3. Single Code Lookup — `$lookup`

Confirms a code exists in a CodeSystem and returns its display name and
definition. Does not require a ValueSet — useful when you only know the
code system URL (e.g., from an OBX-3 LOINC code in an HL7 v2 message).

### GET

```bash
GET /CodeSystem/$lookup?system=<systemUrl>&code=<code>[&version=<version>]
```

**Examples**

```bash
# Look up a LOINC code
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6"

# Look up an ICD-10-CM diagnosis code
curl "http://localhost/CodeSystem/\$lookup?system=http://hl7.org/fhir/sid/icd-10-cm&code=J12.82"

# Look up an HL7 v2 administrative sex code (Table 0001)
curl "http://localhost/CodeSystem/\$lookup?system=http://terminology.hl7.org/CodeSystem/v2-0001&code=M"

# Look up a SNOMED concept
curl "http://localhost/CodeSystem/\$lookup?system=http://snomed.info/sct&code=73211009"

# Look up an RxNorm drug
curl "http://localhost/CodeSystem/\$lookup?system=http://www.nlm.nih.gov/research/umls/rxnorm&code=1049502"
```

### POST (FHIR Parameters format)

```bash
curl -X POST http://localhost/CodeSystem/\$lookup \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Parameters",
    "parameter": [
      { "name": "system", "valueUri":  "http://loinc.org" },
      { "name": "code",   "valueCode": "94500-6" }
    ]
  }'
```

### Response

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "name",       "valueString": "LOINC" },
    { "name": "version",    "valueString": "2.76" },
    { "name": "display",    "valueString": "SARS-CoV-2 (COVID-19) RNA [Presence] in Respiratory specimen by NAA with probe detection" },
    { "name": "definition", "valueString": "" }
  ]
}
```

---

## 4. Batch Validation — `$validate-batch`

Validates up to **200 codes in a single request**. All items are validated
concurrently. This is the primary endpoint for validating all coded fields
in an HL7 v2 message in one call.

```bash
POST /ValueSet/$validate-batch
Content-Type: application/json
```

### Request body

```json
{
  "items": [
    {
      "code":        "<code value>",
      "system":      "<code system URL>",
      "valueSetUrl": "<ValueSet URL>",
      "display":     "<expected display — optional>"
    }
  ]
}
```

**Item fields**

| Field | Required | Description |
|---|---|---|
| `code` | Yes | The code value to validate |
| `system` | Situational | Code system URL. Required when `valueSetUrl` is absent |
| `valueSetUrl` | Situational | Validate membership in this ValueSet. When absent, falls back to CodeSystem $lookup |
| `display` | No | Triggers a display mismatch warning if the stored display differs |

**Routing logic per item:**
- `valueSetUrl` present → `$validate-code` (ValueSet membership check)
- Only `system` present → `$lookup` (code existence in CodeSystem)

### Example — validating HL7 v2 message fields

```bash
curl -X POST http://localhost/ValueSet/\$validate-batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "code": "M",
        "system": "http://terminology.hl7.org/CodeSystem/v2-0001",
        "valueSetUrl": "http://hl7.org/fhir/ValueSet/administrative-gender"
      },
      {
        "code": "94500-6",
        "system": "http://loinc.org"
      },
      {
        "code": "J12.82",
        "system": "http://hl7.org/fhir/sid/icd-10-cm"
      },
      {
        "code": "INVALID",
        "system": "http://terminology.hl7.org/CodeSystem/v2-0001"
      }
    ]
  }'
```

### Response

```json
{
  "results": [
    {
      "code": "M",
      "system": "http://terminology.hl7.org/CodeSystem/v2-0001",
      "valueSetUrl": "http://hl7.org/fhir/ValueSet/administrative-gender",
      "result": true,
      "display": "Male",
      "message": "Code is valid"
    },
    {
      "code": "94500-6",
      "system": "http://loinc.org",
      "valueSetUrl": null,
      "result": true,
      "display": "SARS-CoV-2 (COVID-19) RNA [Presence] in Respiratory specimen by NAA with probe detection",
      "message": "Code is valid"
    },
    {
      "code": "J12.82",
      "system": "http://hl7.org/fhir/sid/icd-10-cm",
      "valueSetUrl": null,
      "result": true,
      "display": "Pneumonia due to coronavirus disease 2019",
      "message": "Code is valid"
    },
    {
      "code": "INVALID",
      "system": "http://terminology.hl7.org/CodeSystem/v2-0001",
      "valueSetUrl": null,
      "result": false,
      "display": null,
      "message": "Code not found in CodeSystem"
    }
  ],
  "summary": {
    "total": 4,
    "valid": 3,
    "invalid": 1
  }
}
```

---

## 5. HL7 v2 Message Validation

PH-TS does not parse HL7 v2 message syntax — that is the responsibility of the
sending system or integration engine (e.g., Mirth Connect, HAPI, Rhapsody). The
pattern is:

1. **Parse** the HL7 v2 message to extract coded field values and their code systems
2. **Submit** those codes to PH-TS via `$validate-batch`
3. **Act** on the results — accept, reject, or flag the message

### HL7 v2 field → code system mapping

Common HL7 v2 fields and the code systems that apply:

| Segment | Field | Table / Code System | System URL |
|---|---|---|---|
| PID-8 | Administrative Sex | Table 0001 | `http://terminology.hl7.org/CodeSystem/v2-0001` |
| PID-22 | Ethnic Group | Table 0189 | `http://terminology.hl7.org/CodeSystem/v2-0189` |
| PID-10 | Race | CDC Race & Ethnicity | `urn:oid:2.16.840.1.113883.6.238` |
| OBX-3 | Observation Identifier | LOINC | `http://loinc.org` |
| OBX-5 | Observation Value | SNOMED / local | varies |
| DG1-3 | Diagnosis Code | ICD-10-CM | `http://hl7.org/fhir/sid/icd-10-cm` |
| RXA-5 | Administered Code | CVX | `http://hl7.org/fhir/sid/cvx` |
| RXA-17 | Substance Manufacturer | MVX | `http://hl7.org/fhir/sid/mvx` |
| MSH-21 | Message Profile Identifier | Table 0449 | `http://terminology.hl7.org/CodeSystem/v2-0449` |
| NK1-3 | Relationship | Table 0063 | `http://terminology.hl7.org/CodeSystem/v2-0063` |

### Example: validate coded fields from a VXU^V04 immunization message

```bash
# Fields extracted from the message:
# RXA-5  = 207 (CVX — COVID-19 mRNA vaccine)
# RXA-17 = MOD (MVX — Moderna)
# PID-8  = M (Administrative Sex)
# OBX-3  = 59781-5 (LOINC — Dose validity)

curl -X POST http://localhost/ValueSet/\$validate-batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      { "code": "207",     "system": "http://hl7.org/fhir/sid/cvx" },
      { "code": "MOD",     "system": "http://hl7.org/fhir/sid/mvx" },
      { "code": "M",       "system": "http://terminology.hl7.org/CodeSystem/v2-0001" },
      { "code": "59781-5", "system": "http://loinc.org" }
    ]
  }'
```

### Example: validate against specific ValueSets (stricter)

When you want to enforce that a code belongs to a specific constrained ValueSet
(not just that it exists in the code system):

```bash
curl -X POST http://localhost/ValueSet/\$validate-batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "code": "207",
        "system": "http://hl7.org/fhir/sid/cvx",
        "valueSetUrl": "http://phinvads.cdc.gov/fhir/ValueSet/2.16.840.1.114222.4.11.934"
      },
      {
        "code": "M",
        "system": "http://terminology.hl7.org/CodeSystem/v2-0001",
        "valueSetUrl": "http://hl7.org/fhir/ValueSet/administrative-gender"
      }
    ]
  }'
```

### Integration engine pattern (Mirth Connect / Rhapsody)

In your transformation script, after extracting field values:

```javascript
// JavaScript — Mirth Connect channel transformer example
var fields = [
  { code: msg['PID']['PID.8']['PID.8.1'].toString(), system: 'http://terminology.hl7.org/CodeSystem/v2-0001' },
  { code: msg['OBX']['OBX.3']['OBX.3.1'].toString(), system: 'http://loinc.org' },
  { code: msg['DG1']['DG1.3']['DG1.3.1'].toString(), system: 'http://hl7.org/fhir/sid/icd-10-cm' }
];

var response = HTTPUtil.post(
  'http://ph-ts-host/ValueSet/$validate-batch',
  JSON.stringify({ items: fields }),
  'application/json'
);

var result = JSON.parse(response);
if (result.summary.invalid > 0) {
  var invalid = result.results.filter(function(r) { return !r.result; });
  // Route to error queue or generate ACK with error codes
}
```

---

## 6. Loading HL7 v2 Tables

HL7 v2 table concepts can be loaded locally for fast offline validation, or
left unloaded to fall back to tx.fhir.org on demand.

### Option A — Import locally (recommended)

Run once after initial setup. Imports all ~200 HL7 v2 table CodeSystems from
the `hl7.terminology.r4` FHIR package (~80-120 MB download).

```bash
# From the flint/ directory, with the migration venv activated:
python migration/import_hl7_v2_tables.py --target-url http://localhost

# Preview without importing
python migration/import_hl7_v2_tables.py --dry-run

# Specify a different package version
python migration/import_hl7_v2_tables.py --version 5.5.0 --target-url http://localhost
```

After import, `$validate-code` and `$lookup` for any `http://terminology.hl7.org/CodeSystem/v2-*`
URL will resolve entirely from the local database with no external calls.

Re-runs are safe — already-imported tables are skipped automatically.

### Option B — On-demand delegation (no import required)

If the import has not been run, PH-TS automatically delegates v2 table lookups
to `tx.fhir.org`. This works out of the box but adds ~200-500 ms network
latency per lookup and requires an internet connection.

### Verifying what is loaded

```bash
# Search for all locally stored v2 table CodeSystems
curl "http://localhost/CodeSystem?name=HL7 Table" | jq '.total'

# Check a specific table
curl "http://localhost/CodeSystem?url=http://terminology.hl7.org/CodeSystem/v2-0001"

# See which code systems are referenced in ValueSets but not yet registered locally
curl "http://localhost/analytics/missing-codesystems" | jq '.missing[] | select(.url | startswith("http://terminology.hl7.org"))'
```

---

## 7. Supported Code Systems

### Locally stored (fast, offline)

After running the relevant import scripts:

| Code System | System URL | Import Script |
|---|---|---|
| HL7 v2 Tables (~200 tables) | `http://terminology.hl7.org/CodeSystem/v2-*` | `import_hl7_v2_tables.py` |
| HL7 v3 / FHIR core admin (~981 systems) | `http://terminology.hl7.org/CodeSystem/v3-*` | `import_hl7_core.py` |
| ICD-10-CM | `http://hl7.org/fhir/sid/icd-10-cm` | `import_hl7_core.py` |
| ICD-9-CM | `http://hl7.org/fhir/sid/icd-9-cm` | `import_icd9cm.py` |
| CVX (vaccine codes) | `http://hl7.org/fhir/sid/cvx` | `import_cvx.py` |
| MVX (vaccine manufacturers) | `http://hl7.org/fhir/sid/mvx` | `import_mvx.py` |
| ISO 3166-1 (countries) | `urn:iso:std:iso:3166` | `import_iso3166.py` |
| PHIN VADS ValueSets & CodeSystems | various | `phinvads_migrate.py` |

### Delegated to external services (real-time)

No import required — PH-TS calls the external API transparently:

| Code System | System URL | Delegated To |
|---|---|---|
| SNOMED CT | `http://snomed.info/sct` | tx.fhir.org |
| LOINC | `http://loinc.org` | NLM ClinicalTables (or fhir.loinc.org with credentials) |
| RxNorm | `http://www.nlm.nih.gov/research/umls/rxnorm` | NLM RxNav |
| HL7 v2 Tables (fallback) | `http://terminology.hl7.org/CodeSystem/v2-*` | tx.fhir.org |
| VSAC ValueSets | `https://cts.nlm.nih.gov/fhir` | VSAC (requires `UMLS_API_KEY`) |

---

## 8. Integration Patterns

### Pattern 1 — Pre-validation before message acceptance

Validate all coded fields before accepting an HL7 v2 message into your system.
Reject with ACK AA/AE based on the `summary.invalid` count.

```
Sending System  →  [HL7 v2 Message]  →  Integration Engine
                                                ↓
                                        Extract coded fields
                                                ↓
                                    POST /ValueSet/$validate-batch
                                                ↓
                                     summary.invalid == 0?
                                        ↓           ↓
                                      ACK AA      ACK AE + error detail
```

### Pattern 2 — Annotation / enrichment

Accept all messages but annotate coded fields with their validated display names
for downstream processing:

```bash
# $lookup returns the official display name regardless of what was sent
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6"
# → "SARS-CoV-2 (COVID-19) RNA [Presence] in Respiratory specimen..."
```

### Pattern 3 — Reporting / audit

Use `$validate-batch` on historical message archives to generate a conformance
report — which fields are valid, which are not, which code systems are in use.

### Pattern 4 — ValueSet-constrained validation

When a data exchange agreement requires specific ValueSets (e.g., a PHIN VADS
value set for notifiable conditions), pass `valueSetUrl` in each batch item for
strict membership checking rather than just code system existence.

---

## 9. Response Reference

### `$validate-code` success

| Field | Type | Description |
|---|---|---|
| `result` | boolean | `true` if code is in the ValueSet |
| `display` | string | Official display name for the code |
| `message` | string | `"Code is valid"` or display mismatch detail |

### `$validate-code` failure

| Field | Type | Description |
|---|---|---|
| `result` | boolean | `false` |
| `message` | string | Reason (e.g., `"Code not found in ValueSet"`) |

### `$lookup` success

| Field | Type | Description |
|---|---|---|
| `name` | string | CodeSystem name |
| `version` | string | CodeSystem version |
| `display` | string | Official display name for the code |
| `definition` | string | Definition text (when available) |

### `$validate-batch` result item

| Field | Type | Description |
|---|---|---|
| `code` | string | The submitted code |
| `system` | string or null | The submitted system URL |
| `valueSetUrl` | string or null | The submitted ValueSet URL |
| `result` | boolean | `true` if valid |
| `display` | string or null | Official display name (null if not found) |
| `message` | string | Outcome detail |

### `$validate-batch` summary

| Field | Type | Description |
|---|---|---|
| `total` | integer | Total items submitted |
| `valid` | integer | Items where `result == true` |
| `invalid` | integer | Items where `result == false` |

### HTTP error responses

All operations return FHIR `OperationOutcome` on error:

```json
{
  "resourceType": "OperationOutcome",
  "issue": [
    {
      "severity": "error",
      "code": "required",
      "diagnostics": "url and code parameters are required"
    }
  ]
}
```

| HTTP Status | Meaning |
|---|---|
| `400` | Missing required parameter |
| `404` | ValueSet or CodeSystem not found locally and not available via external connector |
| `500` | Unexpected server error |

---

---

## 10. ConceptMap CRUD — Cross-System Translation Maps

A `ConceptMap` resource defines mappings between codes in different code systems
(e.g., HL7 v2 administrative sex → FHIR administrative-gender). PH-TS stores
ConceptMaps locally and uses them to drive the `$translate` operation.

### Creating a ConceptMap

```bash
curl -X POST http://localhost/ConceptMap \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "ConceptMap",
    "url": "http://example.org/map/v2-sex-to-fhir",
    "name": "V2SexToFHIRGender",
    "title": "HL7 v2 Administrative Sex to FHIR Gender",
    "status": "active",
    "group": [
      {
        "source": "http://terminology.hl7.org/CodeSystem/v2-0001",
        "target": "http://hl7.org/fhir/administrative-gender",
        "element": [
          {
            "code": "M",
            "display": "Male",
            "target": [{ "code": "male",   "equivalence": "equivalent" }]
          },
          {
            "code": "F",
            "display": "Female",
            "target": [{ "code": "female", "equivalence": "equivalent" }]
          },
          {
            "code": "U",
            "display": "Unknown",
            "target": [{ "code": "unknown","equivalence": "equivalent" }]
          }
        ]
      }
    ]
  }'
```

### CRUD Operations

```bash
# Read a ConceptMap by ID
curl "http://localhost/ConceptMap/{id}"

# Update a ConceptMap (creates a new version)
curl -X PUT http://localhost/ConceptMap/{id} \
  -H "Content-Type: application/fhir+json" \
  -d '{ ... updated resource ... }'

# Delete a ConceptMap
curl -X DELETE http://localhost/ConceptMap/{id}

# Search ConceptMaps
curl "http://localhost/ConceptMap?name=V2Sex"
curl "http://localhost/ConceptMap?url=http://example.org/map/v2-sex-to-fhir"
curl "http://localhost/ConceptMap?status=active"
curl "http://localhost/ConceptMap?q=sex"

# Version history
curl "http://localhost/ConceptMap/{id}/_history"
```

### Equivalence values

| Value | Meaning |
|---|---|
| `equivalent` | Codes are semantically equivalent |
| `equal` | Codes are exactly the same |
| `wider` | The target concept is broader |
| `narrower` | The target concept is more specific |
| `subsumes` | The source concept subsumes the target |
| `relatedto` | Related concepts, not necessarily equivalent |
| `unmatched` | No applicable mapping exists |
| `disjoint` | Concepts are explicitly not related |

---

## 11. Code Translation — `$translate`

Maps a code from one system to an equivalent code in another system using a
stored ConceptMap. Falls back to tx.fhir.org if no matching local map exists.

### GET

```bash
GET /ConceptMap/$translate?url=<mapUrl>&system=<sourceSystem>&code=<code>&target=<targetSystem>
```

**Parameters**

| Parameter | Required | Description |
|---|---|---|
| `url` | No | Canonical URL of the ConceptMap to use. If absent, all maps are searched. |
| `system` | No | Code system URL of the source code |
| `code` | Yes | The source code to translate |
| `target` | No | Target system URL — used when delegating to tx.fhir.org |

### Examples

```bash
# Translate HL7 v2 sex code to FHIR gender using local map
curl "http://localhost/ConceptMap/\$translate?url=http://example.org/map/v2-sex-to-fhir&system=http://terminology.hl7.org/CodeSystem/v2-0001&code=M"

# Translate a SNOMED concept to ICD-10-CM (delegated to tx.fhir.org)
curl "http://localhost/ConceptMap/\$translate?system=http://snomed.info/sct&code=73211009&target=http://hl7.org/fhir/sid/icd-10-cm"

# Translate without specifying the map URL (searches all local maps)
curl "http://localhost/ConceptMap/\$translate?system=http://terminology.hl7.org/CodeSystem/v2-0001&code=F"
```

### POST (FHIR Parameters format)

```bash
curl -X POST http://localhost/ConceptMap/\$translate \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Parameters",
    "parameter": [
      { "name": "url",    "valueUri":  "http://example.org/map/v2-sex-to-fhir" },
      { "name": "system", "valueUri":  "http://terminology.hl7.org/CodeSystem/v2-0001" },
      { "name": "code",   "valueCode": "M" }
    ]
  }'
```

### Response

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "result",  "valueBoolean": true },
    { "name": "message", "valueString":  "Match found in local ConceptMap" },
    {
      "name": "match",
      "part": [
        { "name": "equivalence", "valueCode":   "equivalent" },
        { "name": "concept",     "valueCoding": {
          "system":  "http://hl7.org/fhir/administrative-gender",
          "code":    "male",
          "display": "Male"
        }}
      ]
    }
  ]
}
```

When no match is found:

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "result",  "valueBoolean": false },
    { "name": "message", "valueString":  "No match found" }
  ]
}
```

**Lookup order:**
1. Search local ConceptMaps matching the `url` (or all maps if `url` is omitted)
2. Find a group where `group.source == system`
3. Find an element where `element.code == code`
4. If not found locally → delegate to tx.fhir.org `GET /ConceptMap/$translate`
5. If still not found → return `result = false`

---

## 12. Hierarchy — `$subsumes`

Checks whether one code subsumes (contains) another within a code system
hierarchy. Returns the relationship between the two codes.

```bash
GET /CodeSystem/$subsumes?system=<systemUrl>&codeA=<codeA>&codeB=<codeB>
```

**Parameters**

| Parameter | Required | Description |
|---|---|---|
| `system` | Yes | Code system URL |
| `codeA` | Yes | The potential parent/ancestor code |
| `codeB` | Yes | The potential child/descendant code |

### Response

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "outcome", "valueCode": "subsumes" }
  ]
}
```

**Outcome values:**

| Value | Meaning |
|---|---|
| `equivalent` | `codeA` and `codeB` are the same concept |
| `subsumes` | `codeA` subsumes `codeB` (A is an ancestor of B) |
| `subsumed-by` | `codeA` is subsumed by `codeB` (A is a descendant of B) |
| `not-subsumed` | Neither code is an ancestor of the other |

### Examples

```bash
# SNOMED CT — is Diabetes mellitus (73211009) an ancestor of Type 2 DM (44054006)?
curl "http://localhost/CodeSystem/\$subsumes?system=http://snomed.info/sct&codeA=73211009&codeB=44054006"
# → outcome: subsumes

# SNOMED CT — are both codes the same concept?
curl "http://localhost/CodeSystem/\$subsumes?system=http://snomed.info/sct&codeA=73211009&codeB=73211009"
# → outcome: equivalent

# LOINC — requires fhir.loinc.org credentials (LOINC_USERNAME / LOINC_PASSWORD in .env)
curl "http://localhost/CodeSystem/\$subsumes?system=http://loinc.org&codeA=LP29693-6&codeB=94500-6"

# Local CodeSystem (complete content stored in PH-TS)
curl "http://localhost/CodeSystem/\$subsumes?system=http://terminology.hl7.org/CodeSystem/v2-0001&codeA=M&codeB=M"
```

### System-specific behaviour

| System | Backend |
|---|---|
| `http://snomed.info/sct` | Delegates to `tx.fhir.org/CodeSystem/$subsumes` (Snowstorm) |
| `http://loinc.org` | Delegates to `fhir.loinc.org` — requires credentials; returns 422 if absent |
| Any locally stored CodeSystem | Walks the local `concept[].concept[]` tree to find ancestor/descendant relationships |

---

## 13. SNOMED CT ECL in `$expand`

PH-TS supports SNOMED CT Expression Constraint Language (ECL) in `$expand`
to retrieve concept expansions without needing a pre-built ValueSet. Expansion
is performed by tx.fhir.org and results are returned transparently.

### Pathway 1 — Inline ECL URL (no stored ValueSet required)

Use SNOMED CT implicit ValueSet URL notation directly in the `url` parameter:

```bash
# All descendants of Diabetes mellitus (73211009)
curl "http://localhost/ValueSet/\$expand?url=http://snomed.info/sct?fhir_vs=isa/73211009&count=50"

# SNOMED reference set (e.g., UK drug refset)
curl "http://localhost/ValueSet/\$expand?url=http://snomed.info/sct?fhir_vs=refset/999000801000001108&count=100"
```

**Supported URL patterns:**

| URL pattern | Meaning |
|---|---|
| `http://snomed.info/sct?fhir_vs=isa/{conceptId}` | Self + all descendants of the concept |
| `http://snomed.info/sct?fhir_vs=refset/{refsetId}` | All members of a reference set |
| `http://snomed.info/sct?fhir_vs` | All SNOMED CT concepts (use with `count` + `filter`) |

### Pathway 2 — ECL filter in a stored ValueSet

Create a ValueSet with a SNOMED `compose.include` filter, then expand it normally:

```bash
# Create a ValueSet using ECL-equivalent FHIR filters
curl -X POST http://localhost/ValueSet \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "ValueSet",
    "url": "http://example.org/vs/diabetes",
    "name": "DiabetesMellitusConcepts",
    "status": "active",
    "compose": {
      "include": [
        {
          "system": "http://snomed.info/sct",
          "filter": [
            { "property": "concept", "op": "is-a", "value": "73211009" }
          ]
        }
      ]
    }
  }'

# Expand the ValueSet (ECL filter is detected and delegated to tx.fhir.org)
curl "http://localhost/ValueSet/\$expand?url=http://example.org/vs/diabetes&count=50"
```

**Supported FHIR filter operators for SNOMED CT:**

| FHIR `op` | ECL equivalent | Meaning |
|---|---|---|
| `is-a` | `<<{value}` | Self + all descendants |
| `descendent-of` | `<{value}` | Proper descendants only (excludes the concept itself) |
| `in` | `^{value}` | Members of the specified reference set |
| `generalizes` | `>>{value}` | Self + all ancestors |
| `=` | raw ECL | Pass-through ECL expression (advanced) |

> **Note:** Complex multi-clause ECL (e.g., `<<73211009 AND <<44054006`) is not
> supported. It returns a descriptive 400 error. Use single-clause expressions.

### Example response fragment

```json
{
  "resourceType": "ValueSet",
  "expansion": {
    "total": 42,
    "contains": [
      { "system": "http://snomed.info/sct", "code": "73211009",  "display": "Diabetes mellitus" },
      { "system": "http://snomed.info/sct", "code": "44054006",  "display": "Type 2 diabetes mellitus" },
      { "system": "http://snomed.info/sct", "code": "46635009",  "display": "Type 1 diabetes mellitus" }
    ]
  }
}
```

---

## 14. LOINC Hierarchy via `$lookup` Properties

LOINC has a multi-axial hierarchy. When LOINC credentials are configured
(`LOINC_USERNAME` / `LOINC_PASSWORD` in `.env`), you can request LOINC
hierarchy properties from fhir.loinc.org in a single `$lookup` call.

```bash
GET /CodeSystem/$lookup?system=http://loinc.org&code=<code>&property=<name>[&property=<name>...]
```

### Common LOINC properties

| Property | Description |
|---|---|
| `parent` | Immediate parent concept in the LOINC hierarchy |
| `child` | Direct child concepts |
| `COMPONENT` | The measured substance or entity |
| `PROPERTY` | Characteristics of the measured entity |
| `TIME_ASPCT` | Timing of the measurement |
| `SYSTEM` | Context or specimen type |
| `SCALE_TYP` | Scale (quantitative, ordinal, nominal, …) |
| `METHOD_TYP` | Method of measurement |
| `STATUS` | Current LOINC concept status |
| `CLASSTYPE` | Panel (1), Lab (2), or Clinical (3) |

### Examples

```bash
# Get the parent and component for a COVID LOINC code
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6&property=parent&property=COMPONENT&property=SYSTEM"

# Get LOINC hierarchy (parent + children)
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=LP29693-6&property=parent&property=child"

# Basic lookup without properties (no credentials needed; uses NLM ClinicalTables)
curl "http://localhost/CodeSystem/\$lookup?system=http://loinc.org&code=94500-6"
```

### Response with properties

```json
{
  "resourceType": "Parameters",
  "parameter": [
    { "name": "name",      "valueString": "LOINC" },
    { "name": "version",   "valueString": "2.76" },
    { "name": "display",   "valueString": "SARS-CoV-2 (COVID-19) RNA [Presence] in Respiratory specimen by NAA with probe detection" },
    { "name": "property",  "part": [
      { "name": "code",        "valueCode":   "parent" },
      { "name": "valueCode",   "valueCode":   "LP29693-6" }
    ]},
    { "name": "property",  "part": [
      { "name": "code",        "valueCode":   "COMPONENT" },
      { "name": "valueString", "valueString": "SARS-CoV-2 RNA" }
    ]},
    { "name": "property",  "part": [
      { "name": "code",        "valueCode":   "SYSTEM" },
      { "name": "valueString", "valueString": "Respiratory specimen" }
    ]}
  ]
}
```

> **Credentials:** Property lookups delegate to `fhir.loinc.org`. A free LOINC account is required.
> Register at [loinc.org](https://loinc.org/downloads/loinc/) and set `LOINC_USERNAME` / `LOINC_PASSWORD` in `.env`.
> Without credentials, `$lookup` still works via NLM ClinicalTables but hierarchy properties will be absent.

---

## See Also

- [Architecture Overview](ARCHITECTURE.md)
- [Development Guide](DEVELOPMENT.md)
- [PHIN VADS Migration](../CLAUDE.md) — section on `phinvads_migrate.py`
- [API Docs (Swagger)](http://localhost:8000/docs) — interactive testing
