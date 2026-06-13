"""
import_mvx.py
============
Fetches the CDC MVX (Vaccine Manufacturer) code list from the NLM
ClinicalTables API and imports it as a FHIR R4 CodeSystem into Flint.

MVX codes identify the manufacturer of a vaccine and are used alongside
CVX codes in immunization records. The canonical FHIR URI is
http://hl7.org/fhir/sid/mvx.

Usage
-----
    python migration/import_mvx.py [--target-url URL] [--dry-run]

Options
-------
    --target-url  Base URL of the running Flint server (default: http://localhost)
    --dry-run     Fetch and build the resource without POSTing to the server

Requirements
------------
    pip install httpx
"""

import argparse
import json
import sys

import httpx

NLM_URL = "https://clinicaltables.nlm.nih.gov/api/mvx/v3/search"
CS_URL = "http://hl7.org/fhir/sid/mvx"


def fetch_mvx_codes(client: httpx.Client) -> list[dict]:
    """Fetch all MVX codes from NLM ClinicalTables."""
    params = {"sf": "mvx_code,manufacturer_name", "terms": "", "maxList": 500}
    resp = client.get(NLM_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Response: [total, [codes], null, [[mvx_code, manufacturer_name], ...]]
    pairs = data[3] if len(data) > 3 and data[3] else []
    seen: set[str] = set()
    concepts = []
    for p in pairs:
        code = str(p[0]).strip()
        display = str(p[1]).strip() if len(p) > 1 else code
        if code and code not in seen:
            seen.add(code)
            concepts.append({"code": code, "display": display})
    return concepts


def build_codesystem(concepts: list[dict]) -> dict:
    return {
        "resourceType": "CodeSystem",
        "url": CS_URL,
        "version": "2024",
        "name": "MVX",
        "title": "MVX Vaccine Manufacturer Codes",
        "status": "active",
        "experimental": False,
        "description": (
            "CDC/HL7 Vaccine Manufacturer (MVX) codes. Identifies the manufacturer of a vaccine. "
            "Used alongside CVX codes in immunization records and immunization information systems."
        ),
        "content": "complete",
        "count": len(concepts),
        "publisher": "CDC / HL7",
        "concept": sorted(concepts, key=lambda c: c["code"]),
        "extension": [
            {"url": "http://flint.local/StructureDefinition/source", "valueCode": "internal"}
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Import CDC MVX vaccine manufacturer codes as FHIR R4 CodeSystem")
    parser.add_argument("--target-url", default="http://localhost")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Fetching MVX codes from NLM ClinicalTablesâ€¦", flush=True)
    with httpx.Client() as client:
        concepts = fetch_mvx_codes(client)
    print(f"  Fetched {len(concepts)} MVX codes", flush=True)

    resource = build_codesystem(concepts)

    if args.dry_run:
        out = "mvx_codesystem.json"
        with open(out, "w") as f:
            json.dump(resource, f, indent=2)
        print(f"DRY RUN â€” written to {out}")
        return

    url = f"{args.target_url.rstrip('/')}/CodeSystem"
    print(f"\nPOSTing CodeSystem to {url}â€¦", flush=True)
    with httpx.Client() as client:
        resp = client.post(
            url,
            json=resource,
            headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
            timeout=60,
        )
    if resp.status_code in (200, 201):
        print(f"  + Created â€” id: {resp.json().get('id', '?')}")
    else:
        print(f"  ! Failed â€” HTTP {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)


if __name__ == "__main__":
    main()

