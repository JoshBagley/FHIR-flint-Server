"""
import_cvx.py
============
Fetches the CDC CVX (Vaccine Administered) code list from the NLM
ClinicalTables API and imports it as a FHIR R4 CodeSystem into PH-TS.

CVX codes are maintained by the CDC Immunization Information System (IIS)
Support Branch and published via HL7. They are used in vaccination records
and immunization information systems. The canonical FHIR URI is
http://hl7.org/fhir/sid/cvx.

Usage
-----
    python migration/import_cvx.py [--target-url URL] [--dry-run]

Options
-------
    --target-url  Base URL of the running PH-TS server (default: http://localhost)
    --dry-run     Fetch and build the resource without POSTing to the server

Requirements
------------
    pip install httpx
"""

import argparse
import json
import sys

import httpx

NLM_URL = "https://clinicaltables.nlm.nih.gov/api/cvx/v3/search"
CS_URL = "http://hl7.org/fhir/sid/cvx"


def fetch_cvx_codes(client: httpx.Client) -> list[dict]:
    """Fetch all CVX codes from NLM ClinicalTables."""
    params = {"sf": "cvx_code,short_description,full_vaccine_name", "terms": "", "maxList": 1000}
    resp = client.get(NLM_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Response: [total, [codes], null, [[cvx_code, short_desc, full_name], ...]]
    pairs = data[3] if len(data) > 3 and data[3] else []
    seen: set[str] = set()
    concepts = []
    for p in pairs:
        code = str(p[0]).strip()
        short_desc = str(p[1]).strip() if len(p) > 1 else code
        full_name = str(p[2]).strip() if len(p) > 2 else short_desc
        if code and code not in seen:
            seen.add(code)
            concept: dict = {"code": code, "display": short_desc}
            if full_name and full_name != short_desc:
                concept["definition"] = full_name
            concepts.append(concept)
    return concepts


def build_codesystem(concepts: list[dict]) -> dict:
    return {
        "resourceType": "CodeSystem",
        "url": CS_URL,
        "version": "2024",
        "name": "CVX",
        "title": "CVX Vaccine Administered Codes",
        "status": "active",
        "experimental": False,
        "description": (
            "CDC/HL7 Vaccine Administered (CVX) codes. Maintained by the CDC Immunization "
            "Information System (IIS) Support Branch. Used in vaccination records to identify "
            "the type of vaccine administered."
        ),
        "content": "complete",
        "count": len(concepts),
        "publisher": "CDC / HL7",
        "concept": sorted(concepts, key=lambda c: c["code"].zfill(4)),
        "extension": [
            {"url": "http://phts.local/StructureDefinition/source", "valueCode": "internal"}
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Import CDC CVX vaccine codes as FHIR R4 CodeSystem")
    parser.add_argument("--target-url", default="http://localhost")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Fetching CVX codes from NLM ClinicalTables…", flush=True)
    with httpx.Client() as client:
        concepts = fetch_cvx_codes(client)
    print(f"  Fetched {len(concepts)} CVX codes", flush=True)

    resource = build_codesystem(concepts)

    if args.dry_run:
        out = "cvx_codesystem.json"
        with open(out, "w") as f:
            json.dump(resource, f, indent=2)
        print(f"DRY RUN — written to {out}")
        return

    url = f"{args.target_url.rstrip('/')}/CodeSystem"
    print(f"\nPOSTing CodeSystem to {url}…", flush=True)
    with httpx.Client() as client:
        resp = client.post(
            url,
            json=resource,
            headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
            timeout=60,
        )
    if resp.status_code in (200, 201):
        print(f"  + Created — id: {resp.json().get('id', '?')}")
    else:
        print(f"  ! Failed — HTTP {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
