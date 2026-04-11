#!/usr/bin/env python3
"""
verify_golden_codes.py
======================
Re-verifies every code in golden_codes.json against live public APIs and
reports any display-name drift.  Run this before committing updates to the
golden file.

Usage:
    python tests/fixtures/verify_golden_codes.py
    python tests/fixtures/verify_golden_codes.py --update   # overwrite displays in-place

APIs used (no authentication required):
  SNOMED CT  -- CSIRO Ontoserver FHIR R4  (r4.ontoserver.csiro.au)
  LOINC      -- NLM ClinicalTables v3     (clinicaltables.nlm.nih.gov)
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import httpx

GOLDEN_FILE = Path(__file__).parent / "golden_codes.json"

SNOMED_URL = (
    "https://r4.ontoserver.csiro.au/fhir/CodeSystem/$lookup"
    "?system=http://snomed.info/sct&code={code}&_format=json"
)
LOINC_URL = (
    "https://clinicaltables.nlm.nih.gov/api/loinc_items/v3/search"
    "?terms={code}&sf=LOINC_NUM&df=LOINC_NUM,LONG_COMMON_NAME&maxList=1"
)

TIMEOUT = 20.0


def _fetch_snomed_display(client: httpx.Client, code: str) -> str | None:
    try:
        r = client.get(SNOMED_URL.format(code=code), timeout=TIMEOUT)
        r.raise_for_status()
        params = {p["name"]: p for p in r.json().get("parameter", [])}
        return params.get("display", {}).get("valueString")
    except Exception as exc:
        print(f"  WARN  SNOMED {code}: {exc}", file=sys.stderr)
        return None


def _fetch_loinc_display(client: httpx.Client, code: str) -> str | None:
    try:
        r = client.get(LOINC_URL.format(code=code), timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()  # [total, [codes], null, [[code, display],...]]
        if data[0] and data[3]:
            return data[3][0][1]
        return None
    except Exception as exc:
        print(f"  WARN  LOINC {code}: {exc}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Verify golden_codes.json against live APIs")
    parser.add_argument("--update", action="store_true", help="Write API-returned displays back to the golden file")
    args = parser.parse_args()

    golden = json.loads(GOLDEN_FILE.read_text())
    changed: list[dict] = []
    errors: list[str] = []

    with httpx.Client() as client:
        print("\n--- SNOMED CT ---")
        for entry in golden["snomed"]:
            code = entry["code"]
            expected = entry["display"]
            actual = _fetch_snomed_display(client, code)
            if actual is None:
                errors.append(f"SNOMED {code}: no response")
                print(f"  ERROR  {code}")
            elif actual.lower() == expected.lower():
                print(f"  OK     {code}  {actual}")
            else:
                print(f"  DRIFT  {code}")
                print(f"         golden : {expected!r}")
                print(f"         live   : {actual!r}")
                changed.append({"system": "snomed", "code": code, "golden": expected, "live": actual})
                if args.update:
                    entry["display"] = actual

        print("\n--- LOINC ---")
        for entry in golden["loinc"]:
            code = entry["code"]
            expected = entry["display"]
            actual = _fetch_loinc_display(client, code)
            if actual is None:
                errors.append(f"LOINC {code}: no response")
                print(f"  ERROR  {code}")
            elif actual == expected:
                print(f"  OK     {code}  {actual[:60]}")
            else:
                print(f"  DRIFT  {code}")
                print(f"         golden : {expected!r}")
                print(f"         live   : {actual!r}")
                changed.append({"system": "loinc", "code": code, "golden": expected, "live": actual})
                if args.update:
                    entry["display"] = actual

    print()
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  {e}")

    if changed:
        print(f"DRIFT detected in {len(changed)} code(s).")
        if args.update:
            golden["_metadata"]["verified_date"] = str(date.today())
            GOLDEN_FILE.write_text(json.dumps(golden, indent=2, ensure_ascii=False) + "\n")
            print(f"Updated {GOLDEN_FILE}")
        else:
            print("Re-run with --update to overwrite the golden file.")
        sys.exit(1)
    else:
        if not errors:
            print("All codes verified — no drift detected.")
        sys.exit(0 if not errors else 2)


if __name__ == "__main__":
    main()
