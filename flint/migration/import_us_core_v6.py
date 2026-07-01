"""
Import US Core v6.1.0 StructureDefinition resources into Flint.

Downloads the US Core IG package from packages.fhir.org and POSTs each
StructureDefinition to the Flint /StructureDefinition endpoint.

Usage:
    python migration/import_us_core_v6.py --target-url http://localhost
    python migration/import_us_core_v6.py --dry-run

After import, the following profile URLs become available for $validate?profile=:
    http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient
    http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation-lab
    http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition
    ... (67 profiles total in US Core v6.1.0)

Requirements:
    pip install httpx
"""
import argparse
import io
import json
import sys
import tarfile
import urllib.request


_PACKAGE_URL = "https://packages.fhir.org/hl7.fhir.us.core/6.1.0"
_US_CORE_PROFILES = [
    "us-core-patient",
    "us-core-observation-lab",
    "us-core-condition-encounter-diagnosis",
    "us-core-condition-problems-health-concerns",
    "us-core-allergyintolerance",
    "us-core-immunization",
    "us-core-encounter",
    "us-core-medicationrequest",
    "us-core-procedure",
    "us-core-diagnosticreport-lab",
    "us-core-diagnosticreport-note",
    "us-core-organization",
    "us-core-practitioner",
    "us-core-practitionerrole",
    "us-core-location",
]


def main():
    parser = argparse.ArgumentParser(description="Import US Core v6.1.0 StructureDefinitions")
    parser.add_argument("--target-url", default="http://localhost", help="Flint base URL")
    parser.add_argument("--dry-run", action="store_true", help="List profiles without importing")
    args = parser.parse_args()

    print(f"Downloading US Core v6.1.0 package from {_PACKAGE_URL} ...")
    try:
        with urllib.request.urlopen(_PACKAGE_URL) as resp:
            pkg_bytes = resp.read()
    except Exception as e:
        print(f"ERROR: Could not download package: {e}", file=sys.stderr)
        sys.exit(1)

    imported = 0
    skipped = 0

    with tarfile.open(fileobj=io.BytesIO(pkg_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith("package/StructureDefinition-"):
                continue
            f = tar.extractfile(member)
            if not f:
                continue
            sd = json.loads(f.read())
            if sd.get("resourceType") != "StructureDefinition":
                continue

            name = sd.get("name", member.name)
            url = sd.get("url", "")

            if args.dry_run:
                print(f"  [dry-run] {name}  ({url})")
                skipped += 1
                continue

            import httpx
            target = f"{args.target_url}/StructureDefinition"
            try:
                r = httpx.post(target, json=sd, headers={"Content-Type": "application/fhir+json"}, timeout=30)
                if r.status_code in (200, 201):
                    print(f"  OK  {name}")
                    imported += 1
                else:
                    print(f"  ERR {name}: {r.status_code} {r.text[:120]}", file=sys.stderr)
                    skipped += 1
            except Exception as e:
                print(f"  ERR {name}: {e}", file=sys.stderr)
                skipped += 1

    if args.dry_run:
        print(f"\nDry run complete. Found {skipped} StructureDefinitions.")
    else:
        print(f"\nDone. Imported: {imported}  Skipped/errors: {skipped}")
        if imported:
            print("\nAfter import, validate against US Core with:")
            print(f'  curl -X POST "{args.target_url}/Patient/$validate?profile=http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient" \\')
            print('    -H "Content-Type: application/fhir+json" -d @patient.json')


if __name__ == "__main__":
    main()
