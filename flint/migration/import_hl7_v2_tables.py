"""
import_hl7_v2_tables.py
=======================
Downloads the hl7.terminology.r4 FHIR package from packages.fhir.org and
imports every HL7 v2 table CodeSystem resource into the local Flint-FHIR server.

HL7 v2 tables (e.g., Table 0001 Administrative Sex, Table 0076 Message Type)
are stored as content="complete" CodeSystems in the hl7.terminology.r4 package.
Importing them locally enables offline $validate-code and $lookup for any code
extracted from an HL7 v2 message field.

Usage
-----
    python migration/import_hl7_v2_tables.py [--target-url URL] [--dry-run] [--version VER]

Options
-------
    --target-url  Base URL of the running Flint-FHIR server (default: http://localhost)
    --dry-run     Parse and list resources without POSTing to the server
    --version     hl7.terminology.r4 package version (default: 5.5.0)

Requirements
------------
    pip install httpx  (already in migration venv)

Notes
-----
- The hl7.terminology.r4 package is ~80-120 MB. Download takes 30-90 seconds
  depending on connection speed.
- Only files whose url starts with http://terminology.hl7.org/CodeSystem/v2-
  are extracted. All other resources in the package are ignored.
- meta blocks and concept-level property arrays are stripped before import
  (same workarounds as import_hl7_core.py).
- Re-runs are safe: the server deduplicates by url+version.
"""

import argparse
import io
import json
import sys
import tarfile
import time

import httpx

PACKAGE_BASE = "https://packages.fhir.org/hl7.terminology.r4"
DEFAULT_VERSION = "5.5.0"
HEADERS = {"Accept": "application/json, */*"}

# Only import CodeSystems for HL7 v2 tables
_V2_URL_PREFIX = "http://terminology.hl7.org/CodeSystem/v2-"


def download_package(client: httpx.Client, version: str) -> bytes:
    url = f"{PACKAGE_BASE}/{version}"
    print(f"Downloading hl7.terminology.r4 v{version} from {url} â€¦", flush=True)
    print("  (This package is ~80-120 MB â€” please wait)", flush=True)
    resp = client.get(url, headers=HEADERS, follow_redirects=True, timeout=300)
    resp.raise_for_status()
    size_mb = len(resp.content) / (1024 * 1024)
    print(f"  Downloaded {size_mb:.1f} MB", flush=True)
    return resp.content


def extract_v2_code_systems(tarball: bytes) -> list[dict]:
    """Extract all HL7 v2 table CodeSystem resources from the package tarball."""
    resources = []
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tf:
        members = tf.getmembers()
        print(f"  Scanning {len(members)} files in package â€¦", flush=True)
        for member in members:
            name = member.name.split("/")[-1]
            # v2 table files follow the pattern CodeSystem-v2-XXXX.json
            if not (name.startswith("CodeSystem-v2-") and name.endswith(".json")):
                continue
            f = tf.extractfile(member)
            if f is None:
                continue
            try:
                data = json.loads(f.read())
            except json.JSONDecodeError:
                continue
            if data.get("resourceType") != "CodeSystem":
                continue
            cs_url = data.get("url", "")
            if not cs_url.startswith(_V2_URL_PREFIX):
                continue

            # Apply the same cleanups as import_hl7_core.py
            data.pop("meta", None)
            for concept in data.get("concept", []):
                concept.pop("property", None)

            resources.append(data)

    return resources


def resource_exists(client: httpx.Client, base_url: str, cs_url: str) -> bool:
    """Return True if a CodeSystem with this URL is already on the server."""
    try:
        resp = client.get(
            f"{base_url.rstrip('/')}/CodeSystem",
            params={"url": cs_url},
            timeout=10,
        )
        if resp.status_code == 200:
            bundle = resp.json()
            return (bundle.get("total") or len(bundle.get("entry", []))) > 0
    except Exception:
        pass
    return False


def post_resource(client: httpx.Client, base_url: str, resource: dict) -> str:
    """POST a CodeSystem to the server. Returns 'created', 'exists', or 'error:...'."""
    cs_url = resource.get("url", "")
    if cs_url and resource_exists(client, base_url, cs_url):
        return "exists"

    api_url = f"{base_url.rstrip('/')}/CodeSystem"
    resource_copy = {k: v for k, v in resource.items() if k != "id"}
    resource_copy["extension"] = [
        *[e for e in resource_copy.get("extension", []) if e.get("url") != "http://flint-fhir.local/StructureDefinition/source"],
        {"url": "http://flint-fhir.local/StructureDefinition/source", "valueCode": "hl7v2"},
    ]
    try:
        resp = client.post(
            api_url,
            json=resource_copy,
            headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return "created"
        if resp.status_code == 409:
            return "exists"
        return f"error:{resp.status_code}"
    except Exception as e:
        return f"error:{e}"


def main():
    parser = argparse.ArgumentParser(description="Import HL7 v2 table CodeSystems into Flint-FHIR")
    parser.add_argument("--target-url", default="http://localhost", help="Flint-FHIR server base URL")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, do not POST")
    parser.add_argument("--version", default=DEFAULT_VERSION, help=f"Package version (default: {DEFAULT_VERSION})")
    args = parser.parse_args()

    with httpx.Client() as client:
        tarball = download_package(client, args.version)

    print("\nExtracting HL7 v2 table CodeSystem resources â€¦", flush=True)
    resources = extract_v2_code_systems(tarball)
    print(f"  Found {len(resources)} v2 table CodeSystems\n", flush=True)

    if not resources:
        print("No v2 table CodeSystems found. Check the package version or URL prefix.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("DRY RUN â€” listing resources only:\n")
        for r in resources:
            table_num = r.get("url", "").split("v2-")[-1]
            concept_count = len(r.get("concept", []))
            print(f"  Table {table_num:10s}  {r.get('title', r.get('name', '')):50s}  {concept_count} concepts")
        print(f"\nTotal: {len(resources)} tables")
        return

    counts = {"created": 0, "exists": 0, "error": 0}
    with httpx.Client() as client:
        for i, resource in enumerate(resources, 1):
            cs_url = resource.get("url", "")
            table_num = cs_url.split("v2-")[-1] if "v2-" in cs_url else "?"
            result = post_resource(client, args.target_url, resource)

            status_label = {"created": "+", "exists": "="}.get(result, "!")
            category = result if result in ("created", "exists") else "error"
            counts[category] += 1

            concept_count = len(resource.get("concept", []))
            print(
                f"  [{i:3d}/{len(resources)}] {status_label} Table {table_num:8s}"
                f"  {resource.get('title', resource.get('name', ''))[:45]:45s}"
                f"  ({concept_count} codes)  {result}",
                flush=True,
            )
            time.sleep(0.05)

    print(f"\nDone.")
    print(f"  Created : {counts['created']}")
    print(f"  Skipped : {counts['exists']}")
    print(f"  Errors  : {counts['error']}")

    if counts["error"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

