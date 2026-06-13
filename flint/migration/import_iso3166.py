"""
import_iso3166.py
================
Fetches ISO 3166-1 country codes from the NLM ClinicalTables API and
imports them as a FHIR R4 CodeSystem into Flint.

The canonical FHIR URI for ISO 3166-1 is urn:iso:std:iso:3166.
Alpha-2 codes (e.g. US, CA, GB) are used as the concept codes.

Usage
-----
    python migration/import_iso3166.py [--target-url URL] [--dry-run]

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

NLM_URL = "https://clinicaltables.nlm.nih.gov/api/countries/v3/search"
CS_URL = "urn:iso:std:iso:3166"


def fetch_country_codes(client: httpx.Client) -> list[dict]:
    """Fetch all ISO 3166-1 country codes from NLM ClinicalTables."""
    params = {"sf": "code,name", "terms": "", "maxList": 500}
    resp = client.get(NLM_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Response: [total, [codes], null, [[code, name], ...]]
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
        "name": "ISO3166",
        "title": "ISO 3166-1 Country Codes",
        "status": "active",
        "experimental": False,
        "description": (
            "ISO 3166-1 alpha-2 country codes. Published by the International Organization "
            "for Standardization (ISO). Used in FHIR resources to represent countries and "
            "territories. The canonical FHIR URI is urn:iso:std:iso:3166."
        ),
        "content": "complete",
        "count": len(concepts),
        "publisher": "ISO",
        "concept": sorted(concepts, key=lambda c: c["code"]),
        "extension": [
            {"url": "http://flint.local/StructureDefinition/source", "valueCode": "internal"}
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Import ISO 3166-1 country codes as FHIR R4 CodeSystem")
    parser.add_argument("--target-url", default="http://localhost")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Fetching ISO 3166-1 country codes from NLM ClinicalTablesâ€¦", flush=True)
    with httpx.Client() as client:
        concepts = fetch_country_codes(client)
    print(f"  Fetched {len(concepts)} country codes", flush=True)

    resource = build_codesystem(concepts)

    if args.dry_run:
        out = "iso3166_codesystem.json"
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

