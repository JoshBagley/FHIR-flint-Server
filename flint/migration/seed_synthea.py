"""
seed_synthea.py
===============
Seed the Flint FHIR server with synthetic patients from Synthea sample data.

Downloads pre-generated FHIR R4 transaction bundles from the public Synthea
sample-data repository and imports them via the Bundle endpoint (POST /).

Each file is one patient with all their clinical history (Encounters,
Observations, Conditions, AllergyIntolerances, Immunizations, etc.).

Usage
-----
    python migration/seed_synthea.py
    python migration/seed_synthea.py --target-url http://localhost --count 10
    python migration/seed_synthea.py --dry-run

Options
-------
    --target-url   Base URL of the running Flint server (default: http://localhost)
    --count        Max number of patient bundles to import (default: 10)
    --dry-run      List what would be imported without posting
    --skip-errors  Continue on per-bundle errors instead of stopping

Requirements
------------
    pip install httpx
"""

import argparse
import io
import json
import sys
import zipfile

import httpx

# Synthea publishes periodic FHIR R4 sample datasets here.
# If this URL is stale, check: https://github.com/synthetichealth/synthea-sample-data/tree/main/downloads
SAMPLE_ZIP_URL = (
    "https://raw.githubusercontent.com/synthetichealth/synthea-sample-data/main/"
    "downloads/synthea_sample_data_fhir_r4_nov2021.zip"
)


def download_zip(url: str) -> bytes:
    print(f"Downloading Synthea sample data from:\n  {url}\n")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        chunks = []
        received = 0
        for chunk in resp.iter_bytes(chunk_size=65536):
            chunks.append(chunk)
            received += len(chunk)
            if total:
                pct = received * 100 // total
                print(f"\r  {received:,} / {total:,} bytes ({pct}%)", end="", flush=True)
        print()
    return b"".join(chunks)


def patient_name(bundle: dict) -> str:
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") == "Patient":
            names = res.get("name", [])
            if names:
                n = names[0]
                given = " ".join(n.get("given", []))
                family = n.get("family", "")
                return f"{given} {family}".strip()
    return "(unknown)"


def resource_counts(bundle: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in bundle.get("entry", []):
        rt = entry.get("resource", {}).get("resourceType", "Unknown")
        counts[rt] = counts.get(rt, 0) + 1
    return counts


def post_bundle(client: httpx.Client, target_url: str, bundle: dict) -> dict:
    url = target_url.rstrip("/") + "/"
    resp = client.post(
        url,
        content=json.dumps(bundle),
        headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Flint with Synthea FHIR R4 sample patients")
    parser.add_argument("--target-url", default="http://localhost",
                        help="Base URL of the Flint server (default: http://localhost)")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of patient bundles to import (default: 10)")
    parser.add_argument("--admin-only", action="store_true",
                        help="Import only hospital and practitioner info bundles (Organization/Location/Practitioner/PractitionerRole)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List bundles without importing")
    parser.add_argument("--skip-errors", action="store_true",
                        help="Continue on per-bundle errors instead of stopping")
    args = parser.parse_args()

    # Download and open zip
    raw = download_zip(SAMPLE_ZIP_URL)
    zf = zipfile.ZipFile(io.BytesIO(raw))
    all_files = zf.namelist()

    if args.admin_only:
        target_files = sorted(
            name for name in all_files
            if name.endswith(".json")
            and ("hospitalInformation" in name or "practitionerInformation" in name)
        )
        print(f"Found {len(target_files)} admin bundle(s) to import\n")
    else:
        # Patient bundles only
        target_files = sorted(
            name for name in all_files
            if name.endswith(".json")
            and "hospitalInformation" not in name
            and "practitionerInformation" not in name
        )[: args.count]

    patient_files = target_files  # reuse variable name below

    total_available = sum(
        1 for n in all_files
        if n.endswith(".json")
        and "hospitalInformation" not in n
        and "practitionerInformation" not in n
    )

    if not args.admin_only:
        print(f"Found {total_available} patient bundle(s) in zip — importing up to {args.count}\n")

    if args.dry_run:
        for name in patient_files:
            bundle = json.loads(zf.read(name))
            name_str = patient_name(bundle)
            counts = resource_counts(bundle)
            summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
            print(f"  [dry-run]  {name_str:<30}  {summary}")
        print(f"\n{len(patient_files)} bundle(s) would be imported.")
        return

    ok = err = 0
    with httpx.Client() as client:
        # Verify server is reachable before starting
        try:
            ping = client.get(f"{args.target_url.rstrip('/')}/ready", timeout=5)
            ping.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach {args.target_url} — is the server running?\n  {exc}",
                  file=sys.stderr)
            sys.exit(1)

        for i, name in enumerate(patient_files, 1):
            bundle = json.loads(zf.read(name))
            name_str = patient_name(bundle)
            entry_count = len(bundle.get("entry", []))
            print(f"[{i:2}/{len(patient_files)}] {name_str} ({entry_count} entries) ... ", end="", flush=True)
            try:
                result = post_bundle(client, args.target_url, bundle)
                imported = len(result.get("entry", []))
                print(f"OK ({imported} imported)")
                ok += 1
            except httpx.HTTPStatusError as exc:
                msg = exc.response.text[:200]
                print(f"FAILED — HTTP {exc.response.status_code}: {msg}", file=sys.stderr)
                err += 1
                if not args.skip_errors:
                    print("Stopping. Use --skip-errors to continue on failures.", file=sys.stderr)
                    break
            except Exception as exc:
                print(f"FAILED — {exc}", file=sys.stderr)
                err += 1
                if not args.skip_errors:
                    print("Stopping. Use --skip-errors to continue on failures.", file=sys.stderr)
                    break

    print(f"\nDone: {ok} imported, {err} failed")
    if err and not args.skip_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
