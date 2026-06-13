"""
Tests that verify SNOMED CT and LOINC codes are correctly stored and returned
by $lookup, $validate-code, $expand, and $validate-batch.

Seed data is driven by tests/fixtures/golden_codes.json — a file of
authoritative code→display pairs verified once against live public APIs:
  - SNOMED CT : CSIRO Ontoserver / Snowstorm FHIR R4 (international edition)
  - LOINC     : NLM ClinicalTables LONG_COMMON_NAME (the same API Flint uses)

Re-verify the golden file at any time:
    python tests/fixtures/verify_golden_codes.py

SNOMED display comparisons are case-insensitive (preferred-term wording can
vary slightly between international and US editions).  LOINC comparisons are
exact (LONG_COMMON_NAME is edition-independent and stable).
"""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Load golden codes
# ---------------------------------------------------------------------------

_GOLDEN_FILE = Path(__file__).parent.parent / "fixtures" / "golden_codes.json"
_GOLDEN = json.loads(_GOLDEN_FILE.read_text())

SNOMED_CODES: list[dict] = _GOLDEN["snomed"]
LOINC_CODES:  list[dict] = _GOLDEN["loinc"]

# Convenience subsets for focused tests
_SNOMED_CONDITIONS = [e for e in SNOMED_CODES if e["category"] in ("condition", "finding")]
_LOINC_LABS  = [e for e in LOINC_CODES  if e["category"] == "lab"]
_LOINC_VITALS = [e for e in LOINC_CODES if e["category"] == "vital"]

# ---------------------------------------------------------------------------
# Helpers: build and seed CodeSystem resources from golden entries
# ---------------------------------------------------------------------------

def _build_codesystem(system_url: str, name: str, version: str, entries: list[dict]) -> dict:
    """Build a complete CodeSystem payload from a list of golden entries."""
    return {
        "resourceType": "CodeSystem",
        "url": system_url,
        "name": name,
        "title": name,
        "status": "active",
        "version": version,
        "content": "complete",
        "concept": [{"code": e["code"], "display": e["display"]} for e in entries],
    }


async def _seed_snomed(client: AsyncClient) -> None:
    r = await client.post(
        "/CodeSystem",
        json=_build_codesystem(
            "http://snomed.info/sct", "SNOMEDCT", "20240901", SNOMED_CODES
        ),
    )
    assert r.status_code == 201, f"SNOMED seed failed: {r.text}"


async def _seed_loinc(client: AsyncClient) -> None:
    r = await client.post(
        "/CodeSystem",
        json=_build_codesystem(
            "http://loinc.org", "LOINC", "2.77", LOINC_CODES
        ),
    )
    assert r.status_code == 201, f"LOINC seed failed: {r.text}"


# ===========================================================================
# SNOMED CT — $lookup (parameterized over every golden SNOMED entry)
# ===========================================================================

@pytest.mark.parametrize("entry", SNOMED_CODES, ids=[e["code"] for e in SNOMED_CODES])
async def test_snomed_lookup_golden_code(client: AsyncClient, entry: dict):
    """
    Each SNOMED code in the golden file must be found and its display must
    match the authoritative preferred term (case-insensitive).
    """
    await _seed_snomed(client)
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": "http://snomed.info/sct", "code": entry["code"]},
    )
    assert resp.status_code == 200, f"Expected 200 for {entry['code']}, got {resp.status_code}"
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert "display" in params, f"No display parameter returned for {entry['code']}"
    returned = params["display"]["valueString"]
    assert returned.lower() == entry["display"].lower(), (
        f"SNOMED {entry['code']}: expected {entry['display']!r}, got {returned!r}\n"
        f"  (ph_use: {entry.get('ph_use', '')})"
    )


# ===========================================================================
# LOINC — $lookup (parameterized over every golden LOINC entry)
# ===========================================================================

@pytest.mark.parametrize("entry", LOINC_CODES, ids=[e["code"] for e in LOINC_CODES])
async def test_loinc_lookup_golden_code(client: AsyncClient, entry: dict):
    """
    Each LOINC code in the golden file must be found and its display must
    exactly match the NLM LONG_COMMON_NAME (the same API Flint uses).
    """
    await _seed_loinc(client)
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": "http://loinc.org", "code": entry["code"]},
    )
    assert resp.status_code == 200, f"Expected 200 for {entry['code']}, got {resp.status_code}"
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert "display" in params, f"No display parameter returned for {entry['code']}"
    returned = params["display"]["valueString"]
    assert returned == entry["display"], (
        f"LOINC {entry['code']}: expected {entry['display']!r}, got {returned!r}\n"
        f"  (ph_use: {entry.get('ph_use', '')})"
    )


# ===========================================================================
# Negative cases — codes not in the golden set must not be found
# ===========================================================================

@pytest.mark.parametrize("bad_code,system,label", [
    ("000000001", "http://snomed.info/sct",  "nonexistent SNOMED code"),
    ("99999-9",   "http://loinc.org",        "nonexistent LOINC code"),
    ("XXXXXX",    "http://snomed.info/sct",  "alpha-only non-SNOMED string"),
])
async def test_lookup_nonexistent_code_returns_false(
    client: AsyncClient, bad_code: str, system: str, label: str
):
    """Codes not in the seeded CodeSystem must return result=False, not 404."""
    await _seed_snomed(client)
    await _seed_loinc(client)
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": system, "code": bad_code},
    )
    assert resp.status_code == 200, f"Unexpected status for {label}"
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params.get("result", {}).get("valueBoolean") is False, (
        f"{label}: expected result=False but got {params}"
    )


async def test_lookup_unknown_system_returns_404(client: AsyncClient):
    """A system URL with no local record and no SDO mapping must return 404."""
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": "http://unknown.example.com/cs", "code": "ABC"},
    )
    assert resp.status_code == 404


# ===========================================================================
# ValueSet $validate-code — SNOMED condition codes in a disease ValueSet
# ===========================================================================

async def _seed_snomed_disease_vs(client: AsyncClient) -> str:
    """Seed a ValueSet containing the SNOMED condition codes from the golden file."""
    await _seed_snomed(client)
    vs = {
        "resourceType": "ValueSet",
        "url": "http://example.com/vs/snomed-conditions",
        "name": "GoldenSnomedConditions",
        "title": "Golden SNOMED Conditions",
        "status": "active",
        "version": "1.0",
        "compose": {
            "include": [
                {
                    "system": "http://snomed.info/sct",
                    "concept": [
                        {"code": e["code"], "display": e["display"]}
                        for e in _SNOMED_CONDITIONS
                    ],
                }
            ]
        },
    }
    r = await client.post("/ValueSet", json=vs)
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.parametrize(
    "entry",
    _SNOMED_CONDITIONS,
    ids=[e["code"] for e in _SNOMED_CONDITIONS],
)
async def test_snomed_validate_code_in_condition_valueset(
    client: AsyncClient, entry: dict
):
    """Every SNOMED condition code from the golden file must validate as True."""
    await _seed_snomed_disease_vs(client)
    resp = await client.get(
        "/ValueSet/$validate-code",
        params={
            "url": "http://example.com/vs/snomed-conditions",
            "code": entry["code"],
            "system": "http://snomed.info/sct",
        },
    )
    assert resp.status_code == 200
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params["result"]["valueBoolean"] is True, (
        f"SNOMED {entry['code']} ({entry['display']}) was not found in the condition ValueSet"
    )
    # Display must also come back matching the golden term (case-insensitive)
    returned_display = params.get("display", {}).get("valueString", "")
    assert returned_display.lower() == entry["display"].lower(), (
        f"SNOMED {entry['code']}: display mismatch — "
        f"expected {entry['display']!r}, got {returned_display!r}"
    )


async def test_snomed_validate_loinc_code_not_in_snomed_vs(client: AsyncClient):
    """A LOINC code must not validate as True against a SNOMED-only ValueSet."""
    await _seed_snomed_disease_vs(client)
    resp = await client.get(
        "/ValueSet/$validate-code",
        params={
            "url": "http://example.com/vs/snomed-conditions",
            "code": "94500-6",  # LOINC code — should not be found
        },
    )
    assert resp.status_code == 200
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params["result"]["valueBoolean"] is False


# ===========================================================================
# ValueSet $validate-code — LOINC lab codes in a lab panel ValueSet
# ===========================================================================

async def _seed_loinc_lab_vs(client: AsyncClient) -> str:
    """Seed a ValueSet containing the LOINC lab codes from the golden file."""
    await _seed_loinc(client)
    vs = {
        "resourceType": "ValueSet",
        "url": "http://example.com/vs/loinc-labs",
        "name": "GoldenLoincLabs",
        "title": "Golden LOINC Lab Codes",
        "status": "active",
        "version": "1.0",
        "compose": {
            "include": [
                {
                    "system": "http://loinc.org",
                    "concept": [
                        {"code": e["code"], "display": e["display"]}
                        for e in _LOINC_LABS
                    ],
                }
            ]
        },
    }
    r = await client.post("/ValueSet", json=vs)
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.parametrize(
    "entry",
    _LOINC_LABS,
    ids=[e["code"] for e in _LOINC_LABS],
)
async def test_loinc_validate_lab_code_in_lab_valueset(
    client: AsyncClient, entry: dict
):
    """Every LOINC lab code from the golden file must validate as True."""
    await _seed_loinc_lab_vs(client)
    resp = await client.get(
        "/ValueSet/$validate-code",
        params={
            "url": "http://example.com/vs/loinc-labs",
            "code": entry["code"],
            "system": "http://loinc.org",
        },
    )
    assert resp.status_code == 200
    params = {p["name"]: p for p in resp.json()["parameter"]}
    assert params["result"]["valueBoolean"] is True, (
        f"LOINC {entry['code']} ({entry['display'][:50]}) was not found in the lab ValueSet"
    )
    returned_display = params.get("display", {}).get("valueString", "")
    assert returned_display == entry["display"], (
        f"LOINC {entry['code']}: display mismatch — "
        f"expected {entry['display']!r}, got {returned_display!r}"
    )


# ===========================================================================
# ValueSet $expand — confirm every golden code survives a round-trip
# ===========================================================================

async def test_expand_snomed_valueset_contains_all_golden_codes(client: AsyncClient):
    """$expand on a SNOMED ValueSet must return every code in the golden file."""
    await _seed_snomed_disease_vs(client)
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/snomed-conditions", "count": 100},
    )
    assert resp.status_code == 200
    returned_codes = {c["code"] for c in resp.json()["expansion"]["contains"]}
    missing = [e["code"] for e in _SNOMED_CONDITIONS if e["code"] not in returned_codes]
    assert not missing, f"Missing SNOMED codes in expansion: {missing}"


async def test_expand_loinc_valueset_contains_all_golden_codes(client: AsyncClient):
    """$expand on a LOINC ValueSet must return every lab code in the golden file."""
    await _seed_loinc_lab_vs(client)
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/loinc-labs", "count": 100},
    )
    assert resp.status_code == 200
    returned_codes = {c["code"] for c in resp.json()["expansion"]["contains"]}
    missing = [e["code"] for e in _LOINC_LABS if e["code"] not in returned_codes]
    assert not missing, f"Missing LOINC codes in expansion: {missing}"


async def test_expand_golden_codes_display_roundtrip(client: AsyncClient):
    """
    Expanded concepts must carry back the exact display strings from the
    golden file — both SNOMED (case-insensitive) and LOINC (exact).
    """
    await _seed_snomed_disease_vs(client)
    await _seed_loinc_lab_vs(client)

    # SNOMED
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/snomed-conditions", "count": 100},
    )
    assert resp.status_code == 200
    by_code = {c["code"]: c["display"] for c in resp.json()["expansion"]["contains"]}
    for entry in _SNOMED_CONDITIONS:
        assert entry["code"] in by_code, f"SNOMED {entry['code']} missing from expansion"
        assert by_code[entry["code"]].lower() == entry["display"].lower(), (
            f"SNOMED {entry['code']} display: expected {entry['display']!r}, "
            f"got {by_code[entry['code']]!r}"
        )

    # LOINC
    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/loinc-labs", "count": 100},
    )
    assert resp.status_code == 200
    by_code = {c["code"]: c["display"] for c in resp.json()["expansion"]["contains"]}
    for entry in _LOINC_LABS:
        assert entry["code"] in by_code, f"LOINC {entry['code']} missing from expansion"
        assert by_code[entry["code"]] == entry["display"], (
            f"LOINC {entry['code']} display: expected {entry['display']!r}, "
            f"got {by_code[entry['code']]!r}"
        )


# ===========================================================================
# $validate-batch — mixed SNOMED + LOINC using golden codes
# ===========================================================================

async def test_validate_batch_all_golden_snomed_conditions_valid(client: AsyncClient):
    """
    Batch validate all SNOMED condition codes from the golden file against
    the condition CodeSystem.  Every result must be valid with correct display.
    """
    await _seed_snomed(client)
    payload = {
        "items": [
            {"code": e["code"], "system": "http://snomed.info/sct"}
            for e in _SNOMED_CONDITIONS
        ]
    }
    resp = await client.post("/ValueSet/$validate-batch", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    results_by_code = {r["code"]: r for r in body["results"]}

    failures = []
    for entry in _SNOMED_CONDITIONS:
        r = results_by_code.get(entry["code"])
        if not r:
            failures.append(f"{entry['code']}: not in results")
            continue
        if not r["result"]:
            failures.append(f"{entry['code']}: result=False (expected True)")
            continue
        if r["display"].lower() != entry["display"].lower():
            failures.append(
                f"{entry['code']}: display {r['display']!r} != golden {entry['display']!r}"
            )
    assert not failures, "SNOMED batch validation failures:\n" + "\n".join(failures)
    assert body["summary"]["valid"] == len(_SNOMED_CONDITIONS)


async def test_validate_batch_all_golden_loinc_labs_valid(client: AsyncClient):
    """
    Batch validate all LOINC lab codes from the golden file.
    Every result must be valid with exact display match.
    """
    await _seed_loinc(client)
    payload = {
        "items": [
            {"code": e["code"], "system": "http://loinc.org"}
            for e in _LOINC_LABS
        ]
    }
    resp = await client.post("/ValueSet/$validate-batch", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    results_by_code = {r["code"]: r for r in body["results"]}

    failures = []
    for entry in _LOINC_LABS:
        r = results_by_code.get(entry["code"])
        if not r:
            failures.append(f"{entry['code']}: not in results")
            continue
        if not r["result"]:
            failures.append(f"{entry['code']}: result=False (expected True)")
            continue
        if r["display"] != entry["display"]:
            failures.append(
                f"{entry['code']}: display {r['display']!r} != golden {entry['display']!r}"
            )
    assert not failures, "LOINC batch validation failures:\n" + "\n".join(failures)
    assert body["summary"]["valid"] == len(_LOINC_LABS)


async def test_validate_batch_mixed_golden_codes(client: AsyncClient):
    """
    Single batch containing both SNOMED and LOINC golden codes.
    Summary counts must reflect total golden codes used.
    """
    await _seed_snomed(client)
    await _seed_loinc(client)

    snomed_sample = SNOMED_CODES[:5]
    loinc_sample  = LOINC_CODES[:5]

    payload = {
        "items": [
            {"code": e["code"], "system": e["system"]}
            for e in snomed_sample + loinc_sample
        ]
    }
    resp = await client.post("/ValueSet/$validate-batch", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["total"] == 10
    assert body["summary"]["valid"] == 10
    assert body["summary"]["invalid"] == 0


# ===========================================================================
# OID alias routing — PHIN VADS urn:oid: notation
# ===========================================================================

async def test_loinc_oid_alias_expand_golden_code(client: AsyncClient):
    """
    A ValueSet using PHIN VADS OID notation (urn:oid:2.16.840.1.113883.6.1)
    for the LOINC system must still expand using the locally stored LOINC CS.
    Uses 8480-6 (Systolic blood pressure) from the golden file.
    """
    await _seed_loinc(client)

    golden_entry = next(e for e in LOINC_CODES if e["code"] == "8480-6")
    oid_vs = {
        "resourceType": "ValueSet",
        "url": "http://example.com/vs/loinc-oid-bp",
        "name": "LoincOidBP",
        "title": "LOINC Systolic BP via OID",
        "status": "active",
        "version": "1.0",
        "compose": {
            "include": [
                {
                    "system": "urn:oid:2.16.840.1.113883.6.1",
                    "concept": [{"code": "8480-6", "display": golden_entry["display"]}],
                }
            ]
        },
    }
    await client.post("/ValueSet", json=oid_vs)

    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/loinc-oid-bp"},
    )
    assert resp.status_code == 200
    codes = [c["code"] for c in resp.json()["expansion"]["contains"]]
    assert "8480-6" in codes


async def test_snomed_oid_alias_expand_golden_code(client: AsyncClient):
    """
    A ValueSet using urn:oid:2.16.840.1.113883.6.96 (SNOMED OID) must expand
    using the locally stored SNOMED CS.  Uses 840539006 (COVID-19).
    """
    await _seed_snomed(client)

    golden_entry = next(e for e in SNOMED_CODES if e["code"] == "840539006")
    oid_vs = {
        "resourceType": "ValueSet",
        "url": "http://example.com/vs/snomed-oid-covid",
        "name": "SnomedOidCovid",
        "title": "SNOMED COVID-19 via OID",
        "status": "active",
        "version": "1.0",
        "compose": {
            "include": [
                {
                    "system": "urn:oid:2.16.840.1.113883.6.96",
                    "concept": [{"code": "840539006", "display": golden_entry["display"]}],
                }
            ]
        },
    }
    await client.post("/ValueSet", json=oid_vs)

    resp = await client.get(
        "/ValueSet/$expand",
        params={"url": "http://example.com/vs/snomed-oid-covid"},
    )
    assert resp.status_code == 200
    codes = [c["code"] for c in resp.json()["expansion"]["contains"]]
    assert "840539006" in codes


# ===========================================================================
# Edge / guard cases
# ===========================================================================

async def test_validate_batch_empty_items_rejected(client: AsyncClient):
    resp = await client.post("/ValueSet/$validate-batch", json={"items": []})
    assert resp.status_code == 400


async def test_validate_batch_over_200_items_rejected(client: AsyncClient):
    items = [{"code": str(i), "system": "http://snomed.info/sct"} for i in range(201)]
    resp = await client.post("/ValueSet/$validate-batch", json={"items": items})
    assert resp.status_code == 400


async def test_lookup_missing_system_param_rejected(client: AsyncClient):
    resp = await client.get("/CodeSystem/$lookup", params={"code": "73211009"})
    assert resp.status_code == 400


async def test_lookup_missing_code_param_rejected(client: AsyncClient):
    resp = await client.get(
        "/CodeSystem/$lookup",
        params={"system": "http://snomed.info/sct"},
    )
    assert resp.status_code == 400
