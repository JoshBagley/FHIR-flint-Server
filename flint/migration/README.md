# Flint Migration Scripts

Import standard terminology code systems into your local Flint server.

---

## Prerequisites

- Python 3.11+
- Flint Docker stack running (`docker compose up -d`)
- Internet access (most scripts fetch from public APIs)

---

## Setup

```bash
cd flint/migration

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Available Scripts

### Synthea Synthetic Patient Data

Imports 10 (or more) synthetic FHIR R4 patients with full clinical history via the Bundle endpoint.
Each patient bundle includes Encounters, Observations, Conditions, AllergyIntolerances, Immunizations, etc.

```bash
# Import 10 patients (default)
python seed_synthea.py --target-url http://localhost

# Import more patients
python seed_synthea.py --target-url http://localhost --count 25

# Dry run — list what would be imported
python seed_synthea.py --dry-run
```

---

### HL7 FHIR R4 Core Code Systems

~981 administrative code systems from the official HL7 FHIR R4 package. No license required.

```bash
python import_hl7_core.py --target-url http://localhost

# Dry run — lists all resources without importing
python import_hl7_core.py --dry-run
```

---

### HL7 v2 Table Code Systems

~200 v2 table CodeSystems (~80–120 MB download). Enables offline HL7 v2 message validation.

```bash
python import_hl7_v2_tables.py --target-url http://localhost

# Dry run
python import_hl7_v2_tables.py --dry-run
```

---

### ICD-9-CM

~14k codes from NLM ClinicalTables. Takes ~10 min due to API rate limiting.

```bash
python import_icd9cm.py --target-url http://localhost

# Dry run — writes icd9cm_codesystem.json without importing
python import_icd9cm.py --dry-run
```

---

### ISO 3166 Country Codes

```bash
python import_iso3166.py --target-url http://localhost
```

---

### CDC CVX Vaccine Codes

289 CVX vaccine codes from CDC Excel file (preferred) or NLM ClinicalTables fallback.

```bash
# Primary: requires openpyxl
python import_cvx.py --target-url http://localhost

# Dry run
python import_cvx.py --dry-run

# Fallback to NLM (fewer codes, no status/notes)
python import_cvx.py --source nlm --target-url http://localhost
```

---

### CDC MVX Vaccine Manufacturer Codes

```bash
python import_mvx.py --target-url http://localhost
```

---

### Fix System URLs

Repairs any `urn:oid:` system URLs that should be canonical FHIR URLs. Safe to re-run.

```bash
python fix_system_urls.py --target-url http://localhost
```

---

## Verifying the Server is Ready

```bash
curl http://localhost/health
```

Expected: `{"status": "healthy", "database": "connected", "search": "connected", "cache": "connected"}`
