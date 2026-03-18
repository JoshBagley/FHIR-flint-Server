"""
import_hl7_core.py
==================
Downloads the hl7.fhir.r4.core FHIR package from packages.fhir.org and
imports every CodeSystem resource into the local PH-TS server.

The package is a gzipped tar archive (~40 MB). All files named
CodeSystem-*.json inside it are valid FHIR R4 CodeSystem resources with
content="complete" — small administrative code systems that are freely
available with no license restrictions.

Usage
-----
    python migration/import_hl7_core.py [--target-url URL] [--dry-run]

Options
-------
    --target-url  Base URL of the running PH-TS server (default: http://localhost)
    --dry-run     Parse and report without POSTing to the server

Requirements
------------
    pip install httpx  (already in migration venv)
"""

import argparse
import io
import json
import sys
import tarfile
import time

import httpx

PACKAGE_URL = "https://packages.fhir.org/hl7.fhir.r4.core/4.0.1"
HEADERS = {"Accept": "application/json, */*"}


def download_package(client: httpx.Client) -> bytes:
    print(f"Downloading hl7.fhir.r4.core from {PACKAGE_URL} …", flush=True)
    resp = client.get(PACKAGE_URL, headers=HEADERS, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    size_kb = len(resp.content) // 1024
    print(f"  Downloaded {size_kb:,} KB", flush=True)
    return resp.content


def extract_code_systems(tarball: bytes) -> list[dict]:
    """Extract all CodeSystem-*.json entries from the package tarball."""
    resources = []
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tf:
        for member in tf.getmembers():
            name = member.name.split("/")[-1]
            if not (name.startswith("CodeSystem-") and name.endswith(".json")):
                continue
            f = tf.extractfile(member)
            if f is None:
                continue
            try:
                data = json.loads(f.read())
            except json.JSONDecodeError:
                continue
            if data.get("resourceType") == "CodeSystem":
                # Strip meta — lastUpdated causes datetime serialization errors
                data.pop("meta", None)
                # Strip concept-level property arrays — they can contain partial
                # dates like "2000-11" that Pydantic rejects as invalid datetimes.
                # The code/display values are preserved; properties are supplementary.
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
    """POST a CodeSystem to the server. Returns 'created', 'exists', or 'error'."""
    cs_url = resource.get("url", "")
    if cs_url and resource_exists(client, base_url, cs_url):
        return "exists"

    api_url = f"{base_url.rstrip('/')}/CodeSystem"
    # Remove the id so the server assigns a fresh one — avoids duplicate key on re-run
    resource_copy = {k: v for k, v in resource.items() if k != "id"}
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
    parser = argparse.ArgumentParser(description="Import HL7 FHIR R4 core CodeSystems")
    parser.add_argument("--target-url", default="http://localhost", help="PH-TS server base URL")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, do not POST")
    args = parser.parse_args()

    with httpx.Client() as client:
        tarball = download_package(client)

    print("Extracting CodeSystem resources …", flush=True)
    resources = extract_code_systems(tarball)
    print(f"  Found {len(resources)} CodeSystem resources in package\n", flush=True)

    if args.dry_run:
        print("DRY RUN — listing resources only:\n")
        for r in resources:
            print(f"  {r.get('id', '?'):50s}  {r.get('url', '')}")
        return

    counts = {"created": 0, "exists": 0, "error": 0}
    with httpx.Client() as client:
        for i, resource in enumerate(resources, 1):
            cs_id = resource.get("id", "unknown")
            cs_url = resource.get("url", "")
            result = post_resource(client, args.target_url, resource)

            status_label = {
                "created": "+",
                "exists":  "=",
            }.get(result, "!")

            category = result if result in ("created", "exists") else "error"
            counts[category] += 1

            print(f"  [{i:3d}/{len(resources)}] {status_label} {cs_id:50s} {result}", flush=True)
            time.sleep(0.05)  # gentle rate limiting

    print(f"\nDone.")
    print(f"  Created : {counts['created']}")
    print(f"  Skipped : {counts['exists']}")
    print(f"  Errors  : {counts['error']}")


if __name__ == "__main__":
    main()
