"""
import_icd9cm.py
================
Fetches the complete ICD-9-CM diagnosis code set from the NLM ClinicalTables
API (no credentials required) and imports it as a single FHIR R4 CodeSystem
resource into the local Flint server.

ICD-9-CM was retired on 10/1/2015 but remains essential for historical
encounter data and legacy public health records.

Strategy
--------
The NLM API is a search endpoint, not a listing endpoint. To retrieve all
codes the script iterates over every 3-character prefix (001â€“999, V01â€“V91,
E000â€“E999) â€” each prefix returns up to 500 matching codes which are then
de-duplicated and assembled into a single CodeSystem.

Usage
-----
    python migration/import_icd9cm.py [--target-url URL] [--dry-run]

Options
-------
    --target-url  Base URL of the running Flint server (default: http://localhost)
    --dry-run     Fetch and build the resource without POSTing to the server

Requirements
------------
    pip install httpx  (already in migration venv)
"""

import argparse
import json
import sys
import time
from typing import Iterator

import httpx

NLM_URL = "https://clinicaltables.nlm.nih.gov/api/icd9cm_dx/v3/search"
CS_URL  = "http://hl7.org/fhir/sid/icd-9-cm"
CS_VERSION = "2015"  # last official release year


def _prefixes() -> Iterator[str]:
    """Yield every 3-character ICD-9-CM prefix to sweep the code space."""
    # Numeric codes: 001â€“999
    for n in range(1, 1000):
        yield f"{n:03d}"
    # V-codes: V01â€“V91
    for n in range(1, 92):
        yield f"V{n:02d}"
    # E-codes: E000â€“E999
    for n in range(0, 1000):
        yield f"E{n:03d}"


def fetch_prefix(client: httpx.Client, prefix: str) -> list[dict]:
    """Return up to 500 ICD-9-CM codes matching the given prefix."""
    params = {"sf": "code,name", "terms": prefix, "maxList": 500}
    try:
        resp = client.get(NLM_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  WARNING: prefix {prefix} failed â€” {e}", flush=True)
        return []

    # Response: [total, [codes], null, [[code, display], ...]]
    pairs = data[3] if len(data) > 3 and data[3] else []
    return [{"code": p[0], "display": p[1]} for p in pairs if p[0].startswith(prefix)]


def fetch_all_codes(client: httpx.Client) -> list[dict]:
    """Sweep all prefixes and return de-duplicated concept list."""
    seen: set[str] = set()
    concepts: list[dict] = []
    prefixes = list(_prefixes())
    total = len(prefixes)

    for i, prefix in enumerate(prefixes, 1):
        if i % 100 == 0 or i == 1:
            print(f"  Fetching prefix {i}/{total} ({prefix}) â€” {len(concepts):,} codes so far â€¦", flush=True)
        for concept in fetch_prefix(client, prefix):
            code = concept["code"]
            if code not in seen:
                seen.add(code)
                concepts.append(concept)
        time.sleep(0.05)  # respect NLM rate limits

    return concepts


def build_codesystem(concepts: list[dict]) -> dict:
    return {
        "resourceType": "CodeSystem",
        "url": CS_URL,
        "version": CS_VERSION,
        "name": "ICD9CM",
        "title": "ICD-9-CM Diagnosis Codes",
        "status": "retired",
        "experimental": False,
        "description": (
            "International Classification of Diseases, 9th Revision, Clinical Modification "
            "(ICD-9-CM). Retired October 1, 2015; superseded by ICD-10-CM. Retained for "
            "historical encounter data and legacy public health records."
        ),
        "content": "complete",
        "count": len(concepts),
        "publisher": "CDC / CMS",
        "concept": [
            {"code": c["code"], "display": c["display"]}
            for c in sorted(concepts, key=lambda x: x["code"])
        ],
    }


def post_codesystem(client: httpx.Client, base_url: str, resource: dict) -> None:
    url = f"{base_url.rstrip('/')}/CodeSystem"
    print(f"\nPOSTing CodeSystem to {url} â€¦", flush=True)
    resource = {**resource, "extension": [
        *[e for e in resource.get("extension", []) if e.get("url") != "http://flint.local/StructureDefinition/source"],
        {"url": "http://flint.local/StructureDefinition/source", "valueCode": "icd9cm"},
    ]}
    resp = client.post(
        url,
        json=resource,
        headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
        timeout=120,
    )
    if resp.status_code in (200, 201):
        result = resp.json()
        print(f"  + Created â€” id: {result.get('id', '?')}")
    else:
        print(f"  ! Failed â€” HTTP {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Import ICD-9-CM as a FHIR R4 CodeSystem")
    parser.add_argument("--target-url", default="http://localhost", help="Flint server base URL")
    parser.add_argument("--dry-run", action="store_true", help="Build resource without POSTing")
    args = parser.parse_args()

    print("Fetching ICD-9-CM codes from NLM ClinicalTables â€¦\n", flush=True)
    with httpx.Client() as client:
        concepts = fetch_all_codes(client)

    print(f"\nFetched {len(concepts):,} unique ICD-9-CM codes", flush=True)
    resource = build_codesystem(concepts)

    if args.dry_run:
        out_path = "icd9cm_codesystem.json"
        with open(out_path, "w") as f:
            json.dump(resource, f, indent=2)
        print(f"DRY RUN â€” resource written to {out_path} (not imported)")
        return

    with httpx.Client() as client:
        post_codesystem(client, args.target_url, resource)


if __name__ == "__main__":
    main()

