"""
import_cvx.py
============
Imports CDC CVX (Vaccine Administered) codes as a FHIR R4 CodeSystem into Flint.

Primary source: local CDC Excel file (docs/cvx_codes/web_cvx.xlsx)
Fallback source: NLM ClinicalTables API (less complete â€” no status, notes, or non-vaccine flag)

The CDC spreadsheet is the authoritative source and includes:
  - 289 codes (vs ~200 from NLM)
  - VaccineStatus: Active / Inactive / Non-US / Never Active
  - Notes / definitions per concept
  - Non-vaccine flag
  - Update date

FHIR concept properties defined on the CodeSystem:
  - status     (code)    â€” Active | Inactive | Non-US | Never Active
  - nonVaccine (boolean) â€” true if this is a placeholder/non-vaccine code

Usage
-----
    # From CDC Excel file (recommended)
    python migration/import_cvx.py [--target-url URL] [--dry-run]

    # Force NLM fallback (no Excel file required)
    python migration/import_cvx.py --source nlm [--target-url URL] [--dry-run]

    # Delete existing CVX CodeSystem then re-import
    python migration/import_cvx.py --delete-first [--target-url URL]

Options
-------
    --target-url   Base URL of the running Flint server (default: http://localhost)
    --dry-run      Build the resource without POSTing to the server
    --source       xlsx (default) | nlm
    --delete-first Delete existing CVX CodeSystem before importing

Requirements
------------
    pip install httpx openpyxl
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

XLSX_PATH = Path(__file__).parent.parent / "docs" / "cvx_codes" / "web_cvx.xlsx"
NLM_URL = "https://clinicaltables.nlm.nih.gov/api/cvx/v3/search"
CS_URL = "http://hl7.org/fhir/sid/cvx"


# ---------------------------------------------------------------------------
# Source: CDC Excel file
# ---------------------------------------------------------------------------

def fetch_from_xlsx() -> list[dict]:
    """Parse concepts from the CDC CVX Excel file."""
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl is required to read the Excel file.")
        print("       Run: pip install openpyxl")
        sys.exit(1)

    if not XLSX_PATH.exists():
        print(f"ERROR: Excel file not found at {XLSX_PATH}")
        print("       Use --source nlm to fall back to NLM ClinicalTables.")
        sys.exit(1)

    wb = openpyxl.load_workbook(str(XLSX_PATH))
    ws = wb.active
    concepts = []
    seen: set[str] = set()

    for row in ws.iter_rows(min_row=2, values_only=True):
        raw_code, short_desc, full_name, note, status, _, nonvaccine, _update_date, _ = (
            row + (None,) * (9 - len(row))
        )
        if not raw_code:
            continue
        code = str(raw_code).strip()
        if not code or code in seen:
            continue
        seen.add(code)

        display = str(full_name).strip() if full_name else (str(short_desc).strip() if short_desc else code)
        concept: dict = {"code": code, "display": display}

        # Short description as alternate designation
        if short_desc and str(short_desc).strip() and str(short_desc).strip() != display:
            concept["designation"] = [{
                "use": {
                    "system": "http://terminology.hl7.org/CodeSystem/designation-usage",
                    "code": "display"
                },
                "value": str(short_desc).strip()
            }]

        # Note as definition
        if note and str(note).strip():
            concept["definition"] = str(note).strip()

        # Properties: status + nonVaccine
        props = []
        if status:
            props.append({"code": "status", "valueCode": str(status).strip()})
        if str(nonvaccine).lower() == "true":
            props.append({"code": "nonVaccine", "valueBoolean": True})
        if props:
            concept["property"] = props

        concepts.append(concept)

    print(f"  Parsed {len(concepts)} CVX codes from {XLSX_PATH.name}")
    status_counts: dict = {}
    for c in concepts:
        for p in c.get("property", []):
            if p["code"] == "status":
                v = p["valueCode"]
                status_counts[v] = status_counts.get(v, 0) + 1
    for s, n in sorted(status_counts.items()):
        print(f"    {s}: {n}")
    return concepts


# ---------------------------------------------------------------------------
# Source: NLM ClinicalTables (fallback)
# ---------------------------------------------------------------------------

def fetch_from_nlm(client: httpx.Client) -> list[dict]:
    """Fetch CVX codes from NLM ClinicalTables (less complete)."""
    params = {"sf": "cvx_code,short_description,full_vaccine_name", "terms": "", "maxList": 1000}
    resp = client.get(NLM_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    pairs = data[3] if len(data) > 3 and data[3] else []
    seen: set[str] = set()
    concepts = []
    for p in pairs:
        code = str(p[0]).strip()
        short_desc = str(p[1]).strip() if len(p) > 1 else code
        full_name = str(p[2]).strip() if len(p) > 2 else short_desc
        if code and code not in seen:
            seen.add(code)
            concept: dict = {"code": code, "display": full_name or short_desc}
            if full_name and full_name != short_desc:
                concept["definition"] = short_desc
            concepts.append(concept)
    print(f"  Fetched {len(concepts)} CVX codes from NLM ClinicalTables")
    return concepts


# ---------------------------------------------------------------------------
# Build FHIR CodeSystem
# ---------------------------------------------------------------------------

def build_codesystem(concepts: list[dict]) -> dict:
    has_status_prop = any(
        p["code"] == "status" for c in concepts for p in c.get("property", [])
    )
    has_nonvaccine_prop = any(
        p["code"] == "nonVaccine" for c in concepts for p in c.get("property", [])
    )

    property_defs = []
    if has_status_prop:
        property_defs.append({
            "code": "status",
            "uri": "http://hl7.org/fhir/concept-properties#status",
            "description": "Vaccine status: Active, Inactive, Non-US, or Never Active",
            "type": "code"
        })
    if has_nonvaccine_prop:
        property_defs.append({
            "code": "nonVaccine",
            "description": "True if this code represents a non-vaccine product or placeholder",
            "type": "boolean"
        })

    cs: dict = {
        "resourceType": "CodeSystem",
        "url": CS_URL,
        "version": str(datetime.now().year),
        "name": "CVX",
        "title": "CVX Vaccine Administered Codes",
        "status": "active",
        "experimental": False,
        "description": (
            "CDC/HL7 Vaccine Administered (CVX) codes. Maintained by the CDC Immunization "
            "Information System (IIS) Support Branch. Used in vaccination records to identify "
            "the type of vaccine administered. Canonical FHIR URI: http://hl7.org/fhir/sid/cvx"
        ),
        "content": "complete",
        "count": len(concepts),
        "publisher": "CDC / HL7",
        "extension": [
            {"url": "http://flint.local/StructureDefinition/source", "valueCode": "internal"}
        ],
        "concept": sorted(concepts, key=lambda c: c["code"].zfill(4)),
    }
    if property_defs:
        cs["property"] = property_defs

    return cs


# ---------------------------------------------------------------------------
# Find existing CVX CodeSystem ID (for PUT update)
# ---------------------------------------------------------------------------

def find_existing_id(client: httpx.Client, target_url: str) -> str | None:
    resp = client.get(
        f"{target_url}/CodeSystem?url={CS_URL}",
        headers={"Accept": "application/fhir+json"},
        timeout=30
    )
    resp.raise_for_status()
    entries = resp.json().get("entry", [])
    return entries[0]["resource"]["id"] if entries else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import CDC CVX vaccine codes as FHIR R4 CodeSystem")
    parser.add_argument("--target-url", default="http://localhost")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=["xlsx", "nlm"], default="xlsx")
    args = parser.parse_args()

    target = args.target_url.rstrip("/")

    # Fetch concepts
    if args.source == "xlsx":
        print(f"Reading CVX codes from {XLSX_PATH.name}â€¦")
        concepts = fetch_from_xlsx()
    else:
        print("Fetching CVX codes from NLM ClinicalTablesâ€¦")
        with httpx.Client() as client:
            concepts = fetch_from_nlm(client)

    resource = build_codesystem(concepts)

    if args.dry_run:
        out = "cvx_codesystem.json"
        with open(out, "w") as f:
            json.dump(resource, f, indent=2)
        print(f"\nDRY RUN â€” written to {out}")
        return

    with httpx.Client() as client:
        existing_id = find_existing_id(client, target)

        if existing_id:
            print(f"\nExisting CVX CodeSystem found (id: {existing_id}) â€” updating via PUTâ€¦")
            resource["id"] = existing_id
            resp = client.put(
                f"{target}/CodeSystem/{existing_id}",
                json=resource,
                headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
                timeout=60,
            )
            action = "Updated"
        else:
            print(f"\nNo existing CVX CodeSystem found â€” creating via POSTâ€¦")
            resp = client.post(
                f"{target}/CodeSystem",
                json=resource,
                headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
                timeout=60,
            )
            action = "Created"

    if resp.status_code in (200, 201):
        print(f"  + {action} â€” id: {resp.json().get('id', '?')} ({len(concepts)} concepts)")
    else:
        print(f"  ! Failed â€” HTTP {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)


if __name__ == "__main__":
    main()

