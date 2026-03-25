"""
repair_empty_phinvads_valuesets.py
===================================
Re-fetches compose.include concepts from the PHIN VADS STU3 API for ValueSets
that were imported with empty compose.include arrays, then PATCHes them back
into PH-TS via PUT /ValueSet/{id}.

Usage:
    python migration/repair_empty_phinvads_valuesets.py
    python migration/repair_empty_phinvads_valuesets.py --dry-run
    python migration/repair_empty_phinvads_valuesets.py --target-url http://localhost
"""

import argparse
import json
import re
import sys
import time
import httpx

DEFAULT_TARGET_URL = "http://localhost"
PHINVADS_BASE = "https://phinvads.cdc.gov/baseStu3"
REQUEST_TIMEOUT = 60
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds between retries

# OID → canonical FHIR URL (mirrors phinvads_migrate.py _OID_TO_CANONICAL)
_OID_TO_CANONICAL = {
    "2.16.840.1.113883.6.1":   "http://loinc.org",
    "2.16.840.1.113883.6.96":  "http://snomed.info/sct",
    "2.16.840.1.113883.6.90":  "http://hl7.org/fhir/sid/icd-10-cm",
    "2.16.840.1.113883.6.103": "http://hl7.org/fhir/sid/icd-9-cm",
    "2.16.840.1.113883.6.88":  "http://www.nlm.nih.gov/research/umls/rxnorm",
    "2.16.840.1.113883.5.1":   "http://terminology.hl7.org/CodeSystem/v3-AdministrativeGender",
    "2.16.840.1.113883.5.2":   "http://terminology.hl7.org/CodeSystem/v3-MaritalStatus",
    "2.16.840.1.113883.5.14":  "http://terminology.hl7.org/CodeSystem/v3-ActStatus",
    "2.16.840.1.113883.5.83":  "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
    "2.16.840.1.113883.12.1":  "http://terminology.hl7.org/CodeSystem/v2-0001",
    "2.16.840.1.113883.12.2":  "http://terminology.hl7.org/CodeSystem/v2-0002",
    "2.16.840.1.113883.12.3":  "http://terminology.hl7.org/CodeSystem/v2-0003",
    "2.16.840.1.113883.12.4":  "http://terminology.hl7.org/CodeSystem/v2-0004",
    "2.16.840.1.113883.12.61": "http://terminology.hl7.org/CodeSystem/v2-0061",
    "2.16.840.1.113883.12.63": "http://terminology.hl7.org/CodeSystem/v2-0063",
    "2.16.840.1.113883.12.74": "http://terminology.hl7.org/CodeSystem/v2-0074",
    "2.16.840.1.113883.12.78": "http://terminology.hl7.org/CodeSystem/v2-0078",
    "2.16.840.1.113883.12.80": "http://terminology.hl7.org/CodeSystem/v2-0080",
    "2.16.840.1.113883.12.85": "http://terminology.hl7.org/CodeSystem/v2-0085",
    "2.16.840.1.113883.12.443":"http://terminology.hl7.org/CodeSystem/v2-0443",
}

_OID_PATTERN = re.compile(r"urn:oid:([\d.]+)")


def _normalize_system(system: str) -> str:
    """Convert urn:oid:X to canonical URL where known; pass through otherwise."""
    m = _OID_PATTERN.match(system or "")
    if m:
        return _OID_TO_CANONICAL.get(m.group(1), system)
    return system


def _extract_oid(phinvads_url: str) -> str | None:
    """Extract OID from a PHIN VADS URL like .../ValueSet/2.16.840.1.114222.4.11.856"""
    m = re.search(r"/ValueSet/([\d.]+)$", phinvads_url)
    return m.group(1) if m else None


def _fetch_from_phinvads(client: httpx.Client, oid: str) -> dict | None:
    """
    Fetch a ValueSet from PHIN VADS by OID using identifier search.
    Returns the STU3 resource dict or None if not found.
    """
    urls_to_try = [
        f"{PHINVADS_BASE}/ValueSet?identifier={oid}&_format=json",
        f"{PHINVADS_BASE}/ValueSet?identifier=urn:oid:{oid}&_format=json",
        f"{PHINVADS_BASE}/ValueSet/{oid}?_format=json",
    ]

    for attempt_url in urls_to_try:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                r = client.get(attempt_url, timeout=REQUEST_TIMEOUT)
                if r.status_code == 404:
                    break  # try next URL pattern
                if r.status_code != 200:
                    print(f"    WARN: {r.status_code} from {attempt_url} (attempt {attempt})")
                    time.sleep(RETRY_DELAY)
                    continue
                body = r.json()
                # Bundle response (identifier search)
                if body.get("resourceType") == "Bundle":
                    entries = body.get("entry", [])
                    if entries:
                        return entries[0].get("resource")
                    break  # empty bundle — try next pattern
                # Direct resource response
                if body.get("resourceType") == "ValueSet":
                    return body
                break
            except Exception as e:
                print(f"    ERROR: {e} (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    time.sleep(RETRY_DELAY)
    return None


def _extract_compose_include(vs_stu3: dict) -> list:
    """
    Pull compose.include from STU3 resource and normalise system URLs.
    Returns a list of include objects ready for FHIR R4.
    """
    includes = vs_stu3.get("compose", {}).get("include", [])
    normalised = []
    for inc in includes:
        inc_copy = dict(inc)
        if "system" in inc_copy:
            inc_copy["system"] = _normalize_system(inc_copy["system"])
        # Normalise designation.use if it's a plain string (STU3 quirk)
        for concept in inc_copy.get("concept", []):
            for desig in concept.get("designation", []):
                if isinstance(desig.get("use"), str):
                    desig["use"] = {"code": desig["use"]}
        normalised.append(inc_copy)
    return normalised


def _put_valueset(client: httpx.Client, target_url: str, vs_id: str, vs_data: dict, dry_run: bool) -> bool:
    """PUT the updated ValueSet back to PH-TS."""
    if dry_run:
        print(f"    [dry-run] Would PUT /ValueSet/{vs_id}")
        return True
    r = client.put(
        f"{target_url}/ValueSet/{vs_id}",
        json=vs_data,
        headers={"Content-Type": "application/fhir+json"},
        timeout=120,
    )
    if r.status_code in (200, 201):
        return True
    print(f"    FAIL: PUT /ValueSet/{vs_id} → {r.status_code}: {r.text[:200]}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Repair empty PHIN VADS ValueSet imports")
    parser.add_argument("--target-url", default=DEFAULT_TARGET_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target_url = args.target_url.rstrip("/")

    # Fetch the specific empty-compose ValueSets from PH-TS by ID.
    # These IDs were identified by querying the DB:
    #   SELECT id FROM fhir_resources
    #   WHERE resource_type='ValueSet'
    #     AND jsonb_array_length(COALESCE(data->'compose'->'include','[]'::jsonb))=0
    #     AND url IS NOT NULL;
    EMPTY_VS_IDS = [
        "27018b77-6a6b-4e04-bac3-99216d26462a",
        "4ad9af68-6444-4d81-a92e-f5b2121071b8",
        "bd5ce829-1a07-4231-aacb-e7eccf5fb834",
        "a25e651d-111a-4960-9c10-06117fb3fa7c",
        "8e6a4e69-4eb6-44b0-baac-5ca49a0acf7c",
        "fcffcd06-f42a-408f-8192-193a0e64d7fd",
        "2cb67e97-9031-4859-98a4-137de35ad873",
        "578db64b-1e02-4189-a78a-59efc9ec4766",
        "57a897c1-ccd2-4749-96ff-783ec67aef33",
        "6acde393-cdff-4179-9937-89483c0be1dc",
        "082e958f-78f0-4bf9-96d3-de4f9242ebc5",
        "9945434a-04e0-435d-bed4-f9a665715ac8",
        "f7eab2bb-1297-4bab-9e2d-7c6e7bc72106",
        "efa8f9e1-53d7-47ae-896e-78df8ff7df1a",
        "3ebb4c43-4fa9-4ee2-b324-5066e8bed95d",
        "dda122cc-92cb-4c5b-82d3-71925f604410",
        "fe6287a8-17a4-46b6-aa02-29035e5084df",
        "d3443ace-c001-46f9-b9fa-d7876dd2470c",
        "d43f0759-34ac-4c06-8330-2d46269610b5",
        "245b47ed-742a-4eb6-80af-88c4a5bc6205",
        "00443257-490d-4d63-a6d0-f5a4a128073e",
        "a162e382-ab18-40ce-82d1-0e56c267bdfc",
        "43f49d77-2fbf-4026-b84e-6a46e4263615",
        "d2900c8f-50f5-4ebb-8a17-62420f634b6c",
        "350b826b-4417-4315-aafe-d1adeb395b50",
        "9ee00f35-5936-4de6-83bb-2543b0b7b2f4",
        "b0565208-b46a-4f52-aa62-788dcad1aa74",
        "9c425e7e-d1f1-4661-88a9-61043a0102b2",
        "be3c1c28-5097-4798-bc27-53dcd0477243",
        "b7fa1cb4-ab64-4601-865f-8c104fcb045f",
        "560d1c97-c821-4bb3-8eec-0223b38c9294",
        "89c971a0-4472-4d2c-bfc1-1f51a9b1cdbb",
        "9a9e781e-cd69-4dc9-a703-df24d08a46c3",
        "f4c1694b-fec4-4f61-b5fb-295e7e17b09a",
        "7814220b-1078-4897-9316-20d6b73b7015",
        "bdcec99a-be2a-419a-886c-5a3aa1d05aa6",
        "2836799b-ec64-4b05-bc35-5b69f1342f99",
        "39ccb8d0-307d-4e52-a412-6b7f2d03915c",
        "c364927f-7f93-4ccb-a94e-68b5e218b850",
        "2bdff081-9a65-4790-a39c-9912f89c99fe",
        "ad5e6ccd-b191-4ec1-aa2d-b0306af16b78",
        "96e63fda-59cb-412a-8ab3-f5e597ae43e8",
        "c8e67185-c19c-4abd-b389-a5732ebf69fa",
        "c159e188-8f76-45c0-b7f5-21b8512ce704",
        "888d06ab-b984-4f98-a4bf-e649b495185e",
        "cb4105c6-fa8b-49f9-84f9-4a6dd8d6c16f",
        "1f979bca-3ab4-43b7-b946-c9f3d164abb6",
    ]

    print(f"Processing {len(EMPTY_VS_IDS)} known empty-compose ValueSets\n")

    # Fetch each by ID from PH-TS
    empty = []
    with httpx.Client() as client:
        for vs_id in EMPTY_VS_IDS:
            r = client.get(f"{target_url}/ValueSet/{vs_id}", timeout=15)
            if r.status_code == 200:
                empty.append(r.json())
            else:
                print(f"  WARN: GET /ValueSet/{vs_id} → {r.status_code}")

    stats = {"recovered": 0, "no_concepts_upstream": 0, "fetch_failed": 0, "put_failed": 0}

    with httpx.Client() as client:
        for vs in empty:
            vs_id = vs["id"]
            vs_url = vs["url"]
            vs_name = vs.get("name") or vs_id
            oid = _extract_oid(vs_url)

            if not oid:
                print(f"[SKIP] {vs_name}: cannot extract OID from URL {vs_url}")
                continue

            print(f"[{vs_name}]")
            print(f"  OID: {oid}")

            stu3 = _fetch_from_phinvads(client, oid)
            if not stu3:
                print(f"  RESULT: not found in PHIN VADS")
                stats["fetch_failed"] += 1
                continue

            new_includes = _extract_compose_include(stu3)
            concept_count = sum(len(i.get("concept", [])) for i in new_includes)

            if concept_count == 0:
                print(f"  RESULT: PHIN VADS returned {len(new_includes)} include block(s) but 0 concepts — skipping")
                stats["no_concepts_upstream"] += 1
                continue

            print(f"  Fetched {concept_count} concepts across {len(new_includes)} include block(s)")

            # Merge new concepts into existing resource (preserves all other fields)
            vs["compose"]["include"] = new_includes
            # Also clear exclude if it was a ghost empty list
            if vs["compose"].get("exclude") == []:
                del vs["compose"]["exclude"]

            ok = _put_valueset(client, target_url, vs_id, vs, args.dry_run)
            if ok:
                print(f"  {'[dry-run] ' if args.dry_run else ''}Updated OK")
                stats["recovered"] += 1
            else:
                stats["put_failed"] += 1

            time.sleep(0.5)  # be polite to PHIN VADS

    print("\n--- Summary ---")
    print(f"  Recovered (concepts restored): {stats['recovered']}")
    print(f"  No concepts in PHIN VADS API:  {stats['no_concepts_upstream']}")
    print(f"  PHIN VADS fetch failed:        {stats['fetch_failed']}")
    print(f"  PH-TS PUT failed:              {stats['put_failed']}")
    print("---------------")

    if stats["no_concepts_upstream"] > 0:
        print("\nNOTE: ValueSets with 0 concepts upstream are likely in PHIN VADS Excel-only.")
        print("      They cannot be recovered via the STU3 API.")


if __name__ == "__main__":
    main()
