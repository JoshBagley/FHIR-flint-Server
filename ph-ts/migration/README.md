# PH-TS Migration Tool

Migrates ValueSets and CodeSystems from the **PHIN VADS FHIR STU3 API** into your local **PH-TS FHIR R4 server**. Supports full bulk migration, single-OID targeted import, dry-run mode, and checkpoint-based resumption.

---

## Prerequisites

- Python 3.11+
- PH-TS Docker stack running (`docker compose up -d`)
- Internet access to `phinvads.cdc.gov`

---

## Setup

```bash
# From the project root
cd ph-ts/migration

# Create and activate a virtual environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install the single dependency
pip install -r requirements.txt
```

---

## Verifying the Target Server is Ready

Before running a migration, confirm the PH-TS server is healthy:

```bash
curl http://localhost/health
```

Expected response:

```json
{"status": "healthy", "database": "connected", "search": "connected", "cache": "connected"}
```

---

## Commands

### Import a Single ValueSet by OID

The fastest way to pull in one specific ValueSet. Use this when you know the OID from PHIN VADS.

```bash
python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1
```

The `urn:oid:` prefix is optional — both formats work:

```bash
python phinvads_migrate.py --oid urn:oid:2.16.840.1.113883.1.11.1
```

Preview what will be imported without writing to the server:

```bash
python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1 --dry-run --output-dir ./exported
```

---

### Bulk Migration — All ValueSets and CodeSystems

```bash
python phinvads_migrate.py
```

Migrate only ValueSets:

```bash
python phinvads_migrate.py --resource valueset
```

Migrate only CodeSystems:

```bash
python phinvads_migrate.py --resource codesystem
```

---

### Dry Run (No Changes to Server)

Fetches and converts everything but does **not** POST to the target server. Use this to validate conversion output before committing.

```bash
python phinvads_migrate.py --dry-run
```

Save the converted R4 JSON files to disk for inspection:

```bash
python phinvads_migrate.py --dry-run --output-dir ./exported
```

---

### Resume an Interrupted Migration

A checkpoint file is written after each batch. If the process is interrupted, resume from where it left off:

```bash
# Start with checkpoint tracking enabled
python phinvads_migrate.py --resume checkpoint.json

# If interrupted, rerun the same command — it picks up from the last completed batch
python phinvads_migrate.py --resume checkpoint.json
```

---

### Target a Different Server

Default target is `http://localhost`. Override with `--target-url`:

```bash
python phinvads_migrate.py --target-url http://myserver.example.com
```

---

### Adjust Batch Size

Lower the batch size if you hit rate limits or timeouts (default is 50):

```bash
python phinvads_migrate.py --batch-size 10
```

---

### Verbose Logging

```bash
python phinvads_migrate.py --log-level DEBUG
```

---

## All Options

| Flag | Default | Description |
|------|---------|-------------|
| `--target-url` | `http://localhost` | PH-TS server base URL |
| `--oid` | _(none)_ | Import a single ValueSet by OID. Skips bulk mode. |
| `--resource` | `all` | `all`, `valueset`, or `codesystem` |
| `--batch-size` | `50` | Resources processed per batch |
| `--resume` | _(none)_ | Path to checkpoint JSON file for resuming |
| `--dry-run` | `false` | Fetch and convert only — do not POST to server |
| `--output-dir` | _(none)_ | Save converted R4 JSON files to this directory |
| `--log-level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

---

## What the Tool Does

1. **Fetches** resources from `https://phinvads.cdc.gov/baseStu3` using paginated FHIR Bundle requests
2. **Converts** each resource from FHIR STU3 → R4:
   - Normalises `status` values
   - Sets required R4-only fields (`content`, `hierarchyMeaning` on CodeSystems)
   - Tags each resource with a provenance `identifier` linking back to the original PHIN VADS ID
3. **POSTs** each converted resource to your PH-TS server
4. **Checkpoints** progress after every batch

### OID Lookup Strategy

When using `--oid`, the tool tries three lookup methods in order:

1. Direct read: `GET /ValueSet/{oid}`
2. Identifier search: `GET /ValueSet?identifier=urn:oid:{oid}`
3. Bare OID search: `GET /ValueSet?identifier={oid}`

---

## Example Workflow

```bash
# 1. Start the PH-TS stack
docker compose up -d

# 2. Confirm it is healthy
curl http://localhost/health

# 3. Dry run to inspect one ValueSet first
python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1 --dry-run --output-dir ./exported

# 4. Import that one ValueSet for real
python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1

# 5. Run full bulk migration with resume support
python phinvads_migrate.py --resume checkpoint.json --log-level INFO

# 6. Verify the import via the PH-TS API
curl "http://localhost/ValueSet?url=urn:oid:2.16.840.1.113883.1.11.1"
```

---

## Troubleshooting

**`Cannot reach target server`**
The PH-TS stack is not running or not yet healthy. Run `docker compose up -d` and wait ~30 seconds for all services to initialise.

**`ValueSet with OID X not found in PHIN VADS`**
Verify the OID is correct at [PHIN VADS](https://phinvads.cdc.gov). Some legacy value sets may have been retired or use a different identifier format.

**HTTP 422 errors on import**
The converted resource failed R4 validation on the target server. Run with `--dry-run --output-dir ./exported` and inspect the generated JSON for missing required fields.

**Slow or timing out**
Reduce `--batch-size` to `10`–`25` and add `--resume checkpoint.json` so you can restart without losing progress.
