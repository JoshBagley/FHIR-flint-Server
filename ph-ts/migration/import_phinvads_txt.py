"""
import_phinvads_txt.py — Import PHIN VADS ValueSets from local .txt downloads.

Each .txt file is the structured export from PHIN VADS with two tab-separated
sections separated by a blank line:

  Section 1 (row 1 = headers, row 2 = values):
    Value Set Name | Value Set Code | Value Set OID | Value Set Version |
    Value Set Definition | Value Set Status | VS Last Updated Date | VS Release Comments

  Section 2 (row 1 = headers, rows 2+ = concepts):
    Concept Code | Concept Name | Preferred Concept Name | Preferred Alternate Code |
    Code System OID | Code System Name | Code System Code | Code System Version |
    HL7 Table 0396 Code

Usage:
    python migration/import_phinvads_txt.py --source-dir docs/PHINVADSValueSets \
        --target-url http://localhost

    python migration/import_phinvads_txt.py --source-dir docs/PHINVADSValueSets \
        --target-url http://localhost --dry-run

    # Limit to first N files (for testing)
    python migration/import_phinvads_txt.py --source-dir docs/PHINVADSValueSets \
        --target-url http://localhost --limit 10
"""

import argparse
import asyncio
import csv
import io
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TARGET = "http://localhost"
REQUEST_TIMEOUT = 30
CONCURRENT_POSTS = 10          # parallel POSTs to the target server
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 2.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OID → canonical FHIR URL map (mirrors phinvads_migrate.py)
# ---------------------------------------------------------------------------

_OID_TO_CANONICAL: Dict[str, str] = {
    "2.16.840.1.113883.6.1":    "http://loinc.org",
    "2.16.840.1.113883.6.96":   "http://snomed.info/sct",
    "2.16.840.1.113883.6.90":   "http://hl7.org/fhir/sid/icd-10-cm",
    "2.16.840.1.113883.6.103":  "http://hl7.org/fhir/sid/icd-9-cm",
    "2.16.840.1.113883.6.88":   "http://www.nlm.nih.gov/research/umls/rxnorm",
    "2.16.840.1.113883.6.8":    "http://unitsofmeasure.org",
    "2.16.840.1.113883.6.12":   "http://www.ama-assn.org/go/cpt",
    "2.16.840.1.113883.6.301":  "http://nucc.org/provider-taxonomy",
    "2.16.840.1.113883.5.1":    "http://terminology.hl7.org/CodeSystem/v3-AdministrativeGender",
    "2.16.840.1.113883.5.2":    "http://terminology.hl7.org/CodeSystem/v3-MaritalStatus",
    "2.16.840.1.113883.5.4":    "http://terminology.hl7.org/CodeSystem/v3-ActCode",
    "2.16.840.1.113883.5.6":    "http://terminology.hl7.org/CodeSystem/v3-ActClass",
    "2.16.840.1.113883.5.7":    "http://terminology.hl7.org/CodeSystem/v3-ActPriority",
    "2.16.840.1.113883.5.8":    "http://terminology.hl7.org/CodeSystem/v3-ActReason",
    "2.16.840.1.113883.5.14":   "http://terminology.hl7.org/CodeSystem/v3-ActStatus",
    "2.16.840.1.113883.5.25":   "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
    "2.16.840.1.113883.5.42":   "http://terminology.hl7.org/CodeSystem/v3-EntityHandling",
    "2.16.840.1.113883.5.43":   "http://terminology.hl7.org/CodeSystem/v3-EntityNamePartQualifier",
    "2.16.840.1.113883.5.45":   "http://terminology.hl7.org/CodeSystem/v3-EntityNameUse",
    "2.16.840.1.113883.5.53":   "http://nucc.org/provider-taxonomy",
    "2.16.840.1.113883.5.60":   "http://terminology.hl7.org/CodeSystem/v3-LanguageAbilityMode",
    "2.16.840.1.113883.5.61":   "http://terminology.hl7.org/CodeSystem/v3-LanguageAbilityProficiency",
    "2.16.840.1.113883.5.63":   "http://terminology.hl7.org/CodeSystem/v3-LivingArrangement",
    "2.16.840.1.113883.5.74":   "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",
    "2.16.840.1.113883.5.83":   "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
    "2.16.840.1.113883.5.84":   "http://terminology.hl7.org/CodeSystem/v3-ObservationMethod",
    "2.16.840.1.113883.5.88":   "http://terminology.hl7.org/CodeSystem/v3-ParticipationFunction",
    "2.16.840.1.113883.5.90":   "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
    "2.16.840.1.113883.5.110":  "http://terminology.hl7.org/CodeSystem/v3-RoleClass",
    "2.16.840.1.113883.5.111":  "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
    "2.16.840.1.113883.5.112":  "http://terminology.hl7.org/CodeSystem/v3-RouteOfAdministration",
    "2.16.840.1.113883.5.1001": "http://terminology.hl7.org/CodeSystem/v3-ActMood",
    "2.16.840.1.113883.5.1008": "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",
    "2.16.840.1.113883.5.1064": "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode",
    "2.16.840.1.113883.5.1076": "http://terminology.hl7.org/CodeSystem/v3-ReligiousAffiliation",
    "2.16.840.1.113883.5.1077": "http://terminology.hl7.org/CodeSystem/v3-EducationLevel",
    "2.16.840.1.113883.5.1119": "http://terminology.hl7.org/CodeSystem/v3-AddressUse",
    "2.16.840.1.113883.12.1":   "http://terminology.hl7.org/CodeSystem/v2-0001",
    "2.16.840.1.113883.12.2":   "http://terminology.hl7.org/CodeSystem/v2-0002",
    "2.16.840.1.113883.12.3":   "http://terminology.hl7.org/CodeSystem/v2-0003",
    "2.16.840.1.113883.12.7":   "http://terminology.hl7.org/CodeSystem/v2-0007",
    "2.16.840.1.113883.12.8":   "http://terminology.hl7.org/CodeSystem/v2-0008",
    "2.16.840.1.113883.12.23":  "http://terminology.hl7.org/CodeSystem/v2-0023",
    "2.16.840.1.113883.12.27":  "http://terminology.hl7.org/CodeSystem/v2-0027",
    "2.16.840.1.113883.12.38":  "http://terminology.hl7.org/CodeSystem/v2-0038",
    "2.16.840.1.113883.12.52":  "http://terminology.hl7.org/CodeSystem/v2-0052",
    "2.16.840.1.113883.12.61":  "http://terminology.hl7.org/CodeSystem/v2-0061",
    "2.16.840.1.113883.12.74":  "http://terminology.hl7.org/CodeSystem/v2-0074",
    "2.16.840.1.113883.12.78":  "http://terminology.hl7.org/CodeSystem/v2-0078",
    "2.16.840.1.113883.12.80":  "http://terminology.hl7.org/CodeSystem/v2-0080",
    "2.16.840.1.113883.12.85":  "http://terminology.hl7.org/CodeSystem/v2-0085",
    "2.16.840.1.113883.12.105": "http://terminology.hl7.org/CodeSystem/v2-0105",
    "2.16.840.1.113883.12.119": "http://terminology.hl7.org/CodeSystem/v2-0119",
    "2.16.840.1.113883.12.123": "http://terminology.hl7.org/CodeSystem/v2-0123",
    "2.16.840.1.113883.12.127": "http://terminology.hl7.org/CodeSystem/v2-0127",
    "2.16.840.1.113883.12.128": "http://terminology.hl7.org/CodeSystem/v2-0128",
    "2.16.840.1.113883.12.155": "http://terminology.hl7.org/CodeSystem/v2-0155",
    "2.16.840.1.113883.12.164": "http://terminology.hl7.org/CodeSystem/v2-0164",
    "2.16.840.1.113883.12.165": "http://terminology.hl7.org/CodeSystem/v2-0165",
    "2.16.840.1.113883.12.190": "http://terminology.hl7.org/CodeSystem/v2-0190",
    "2.16.840.1.113883.12.211": "http://terminology.hl7.org/CodeSystem/v2-0211",
    "2.16.840.1.113883.12.323": "http://terminology.hl7.org/CodeSystem/v2-0323",
    "2.16.840.1.113883.12.356": "http://terminology.hl7.org/CodeSystem/v2-0356",
    "2.16.840.1.113883.12.371": "http://terminology.hl7.org/CodeSystem/v2-0371",
    "2.16.840.1.113883.12.432": "http://terminology.hl7.org/CodeSystem/v2-0432",
    "2.16.840.1.113883.12.483": "http://terminology.hl7.org/CodeSystem/v2-0483",
    "2.16.840.1.113883.12.533": "http://terminology.hl7.org/CodeSystem/v2-0533",
    "2.16.840.1.114222.4.5.288": "https://phinvads.cdc.gov/baseStu3/CodeSystem/2.16.840.1.114222.4.5.288",
    "2.16.840.1.114222.4.5.274": "https://phinvads.cdc.gov/baseStu3/CodeSystem/2.16.840.1.114222.4.5.274",
    "2.16.840.1.114222.4.5.232": "https://phinvads.cdc.gov/baseStu3/CodeSystem/2.16.840.1.114222.4.5.232",
    "2.16.840.1.114222.4.5.314": "https://phinvads.cdc.gov/baseStu3/CodeSystem/2.16.840.1.114222.4.5.314",
    "2.16.840.1.114222.4.5.315": "https://phinvads.cdc.gov/baseStu3/CodeSystem/2.16.840.1.114222.4.5.315",
}


_HL7_V2_TABLE_PREFIX = "2.16.840.1.113883.12."


def _v2_table_oid_to_url(oid: str) -> Optional[str]:
    """
    Auto-generate a canonical FHIR URL for any HL7 v2 table OID.
    OID pattern: 2.16.840.1.113883.12.N  →  http://terminology.hl7.org/CodeSystem/v2-XXXX
    where XXXX is N zero-padded to 4 digits.
    Returns None if the OID does not match the pattern.
    """
    if not oid.startswith(_HL7_V2_TABLE_PREFIX):
        return None
    suffix = oid[len(_HL7_V2_TABLE_PREFIX):]
    if suffix.isdigit():
        return f"http://terminology.hl7.org/CodeSystem/v2-{int(suffix):04d}"
    return None


def _oid_to_system(oid: str) -> str:
    """Normalize a code system OID to a canonical FHIR URL, or keep as urn:oid:.

    Resolution order:
      1. Static well-known map (_OID_TO_CANONICAL)
      2. Auto-generated HL7 v2 table URL (2.16.840.1.113883.12.N → v2-XXXX)
      3. urn:oid: passthrough for unknown OIDs
    """
    if not oid:
        return ""
    bare = oid[len("urn:oid:"):] if oid.startswith("urn:oid:") else oid
    canonical = _OID_TO_CANONICAL.get(bare)
    if canonical:
        return canonical
    v2_url = _v2_table_oid_to_url(bare)
    if v2_url:
        return v2_url
    return f"urn:oid:{bare}"


def _normalize_status(raw: str) -> str:
    raw = (raw or "").strip().lower()
    if raw in ("published", "active"):
        return "active"
    if raw in ("draft", "under review"):
        return "draft"
    if raw in ("retired", "inactive", "deprecated"):
        return "retired"
    return "unknown"


def _parse_date(raw: str) -> Optional[str]:
    """Convert MM/DD/YYYY to YYYY-MM-DD."""
    raw = (raw or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return raw or None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_phinvads_txt(path: Path) -> Optional[Tuple[Dict, Dict[str, str]]]:
    """
    Parse a PHIN VADS .txt export file into an R4 ValueSet dict.

    Returns a (valueset, cs_names) tuple where cs_names maps
    system URL → PHIN VADS Code System Name for each system referenced by
    the ValueSet's concepts.  Returns None on parse error.
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        logger.warning("Cannot read %s: %s", path.name, exc)
        return None

    # Split on blank line separating header section from concept section
    lines = text.splitlines()

    # Find the blank line separator
    blank_idx = None
    for i, line in enumerate(lines):
        if i >= 1 and not line.strip():
            blank_idx = i
            break

    if blank_idx is None or blank_idx < 2:
        logger.warning("No blank separator found in %s — skipping", path.name)
        return None

    # --- Parse ValueSet metadata (section 1) ---
    vs_section = "\r\n".join(lines[:blank_idx])
    vs_reader = csv.DictReader(io.StringIO(vs_section), delimiter="\t")
    vs_rows = list(vs_reader)
    if not vs_rows:
        logger.warning("No ValueSet metadata row in %s — skipping", path.name)
        return None

    vs = vs_rows[0]
    oid = (vs.get("Value Set OID") or "").strip()
    name = (vs.get("Value Set Code") or "").strip()
    title = (vs.get("Value Set Name") or "").strip()
    version = (vs.get("Value Set Version") or "").strip()
    definition = (vs.get("Value Set Definition") or "").strip()
    release_notes = (vs.get("VS Release Comments") or "").strip()
    status_raw = (vs.get("Value Set Status") or "").strip()
    date_raw = (vs.get("VS Last Updated Date") or "").strip()

    # Some files split the metadata: the title is on its own line (no tabs) and the
    # OID/code/version appear on the following line with a leading tab. In that case
    # vs_rows[0] has the title but an empty OID — fall through to subsequent rows.
    if not oid and len(vs_rows) > 1:
        for extra_row in vs_rows[1:]:
            extra_oid = (extra_row.get("Value Set OID") or "").strip()
            if extra_oid:
                oid = extra_oid
                name = name or (extra_row.get("Value Set Code") or "").strip()
                title = title or (extra_row.get("Value Set Name") or "").strip()
                version = version or (extra_row.get("Value Set Version") or "").strip()
                definition = definition or (extra_row.get("Value Set Definition") or "").strip()
                release_notes = release_notes or (extra_row.get("VS Release Comments") or "").strip()
                status_raw = status_raw or (extra_row.get("Value Set Status") or "").strip()
                date_raw = date_raw or (extra_row.get("VS Last Updated Date") or "").strip()
                break

    description = definition
    if release_notes:
        description = f"{description}\n\nRelease Notes: {release_notes}" if description else f"Release Notes: {release_notes}"

    vs_url = f"https://phinvads.cdc.gov/baseStu3/ValueSet/{oid}" if oid else None

    # --- Parse concepts (section 2) ---
    # Skip any additional blank lines after the separator (some files have two)
    concept_start = blank_idx + 1
    while concept_start < len(lines) and not lines[concept_start].strip():
        concept_start += 1
    concept_section = "\r\n".join(lines[concept_start:])
    concept_reader = csv.DictReader(io.StringIO(concept_section), delimiter="\t")

    # Group concepts by code system OID → compose.include entries.
    # Also collect Code System Name from PHIN VADS for CodeSystem title enrichment.
    includes: Dict[str, Dict] = {}        # key: (system_url, version) → include entry
    cs_names: Dict[str, str] = {}         # system_url → PHIN VADS Code System Name

    for row in concept_reader:
        code = (row.get("Concept Code") or "").strip()
        display = (row.get("Concept Name") or "").strip()
        preferred = (row.get("Preferred Concept Name") or "").strip()
        cs_oid = (row.get("Code System OID") or "").strip()
        cs_name = (row.get("Code System Name") or "").strip()
        cs_version = (row.get("Code System Version") or "").strip()

        if not code or not cs_oid:
            continue

        system_url = _oid_to_system(cs_oid)
        key = (system_url, cs_version)

        if cs_name and system_url and system_url not in cs_names:
            cs_names[system_url] = cs_name

        if key not in includes:
            includes[key] = {
                "system": system_url,
                "version": cs_version or None,
                "concept": [],
            }

        concept_entry: Dict = {"code": code, "display": display or preferred}

        # Add Preferred Concept Name as a designation if different from display
        if preferred and preferred != display:
            concept_entry["designation"] = [{
                "use": {
                    "system": "http://terminology.hl7.org/CodeSystem/designation-usage",
                    "code": "display",
                },
                "value": preferred,
            }]

        includes[key]["concept"].append(concept_entry)

    # Clean up includes: remove version if None
    include_list = []
    for inc in includes.values():
        if inc["version"] is None:
            del inc["version"]
        include_list.append(inc)

    r4: Dict = {
        "resourceType": "ValueSet",
        "url": vs_url,
        "identifier": [
            {
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:oid:{oid}",
            }
        ] if oid else [],
        "version": version or None,
        "name": name or None,
        "title": title or None,
        "status": _normalize_status(status_raw),
        "description": description or None,
        "date": _parse_date(date_raw),
        "publisher": "CDC PHIN VADS",
        "compose": {
            "include": include_list,
        },
        "extension": [
            {
                "url": "http://phts.local/StructureDefinition/source",
                "valueCode": "phinvads",
            }
        ],
    }

    # Strip None-valued keys
    return {k: v for k, v in r4.items() if v is not None}, cs_names


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _resource_exists(
    client: httpx.AsyncClient,
    target_base: str,
    url: str,
    version: Optional[str],
) -> bool:
    if not url:
        return False
    params: Dict = {"url": url}
    if version:
        params["version"] = version
    try:
        resp = await client.get(f"{target_base}/ValueSet", params=params, timeout=15)
        if resp.status_code == 200:
            bundle = resp.json()
            return (bundle.get("total") or len(bundle.get("entry", []))) > 0
    except Exception:
        pass
    return False


async def _post_valueset(
    client: httpx.AsyncClient,
    target_base: str,
    resource: Dict,
    dry_run: bool,
) -> Tuple[bool, str]:
    if dry_run:
        return True, "dry-run"

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = await client.post(
                f"{target_base}/ValueSet",
                json=resource,
                headers={"Content-Type": "application/fhir+json"},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                return True, f"HTTP {resp.status_code}"
            return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS:
                return False, str(exc)
            await asyncio.sleep(RETRY_BACKOFF * attempt)

    return False, "max retries exceeded"


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

async def _update_codesystem_titles(
    client: httpx.AsyncClient,
    target_base: str,
    cs_names: Dict[str, str],
    dry_run: bool,
) -> None:
    """
    For each (system_url, phinvads_name) pair, fetch the CodeSystem from
    PH-TS and update its title to the PHIN VADS Code System Name if the
    current title is absent or less descriptive (shorter).

    This makes the PHIN VADS-friendly name (e.g. "Administrative sex (HL7)")
    the title returned by $expand for any ValueSet that references that system.
    """
    updated = skipped = errors = 0
    for system_url, phinvads_name in sorted(cs_names.items()):
        try:
            resp = await client.get(
                f"{target_base}/CodeSystem",
                params={"url": system_url},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("  CodeSystem lookup failed for %s: HTTP %d", system_url, resp.status_code)
                errors += 1
                continue

            bundle = resp.json()
            entries = bundle.get("entry", [])
            if not entries:
                logger.debug("  No CodeSystem found for %s — skipping title update", system_url)
                skipped += 1
                continue

            cs = entries[0]["resource"]
            current_title = cs.get("title") or ""

            # Only update if the PHIN VADS name is more descriptive
            if current_title == phinvads_name:
                skipped += 1
                continue
            if current_title and len(current_title) >= len(phinvads_name):
                logger.debug(
                    "  Keeping existing title %r over %r for %s",
                    current_title, phinvads_name, system_url,
                )
                skipped += 1
                continue

            if dry_run:
                logger.info(
                    "  [dry-run] Would update CodeSystem %r title: %r -> %r",
                    system_url, current_title, phinvads_name,
                )
                updated += 1
                continue

            cs["title"] = phinvads_name
            cs_id = cs.get("id")
            put_resp = await client.put(
                f"{target_base}/CodeSystem/{cs_id}",
                json=cs,
                headers={"Content-Type": "application/fhir+json"},
                timeout=30,
            )
            if put_resp.status_code in (200, 201):
                logger.info(
                    "  Updated CodeSystem %r title: %r -> %r",
                    system_url, current_title, phinvads_name,
                )
                updated += 1
            else:
                logger.warning(
                    "  Failed to update CodeSystem %r: HTTP %d %s",
                    system_url, put_resp.status_code, put_resp.text[:200],
                )
                errors += 1

        except Exception as exc:
            logger.warning("  Error updating CodeSystem %s: %s", system_url, exc)
            errors += 1

    print(f"\nCodeSystem title updates: {updated} updated, {skipped} skipped, {errors} errors")


def _match_includes_by_concepts(
    existing_includes: List[Dict],
    txt_includes: List[Dict],
) -> Dict[int, str]:
    """
    Match each existing compose.include to the txt include with the greatest
    concept-code overlap, then return a dict of {existing_index: correct_system_url}
    for any existing include whose system URL should change.

    Matching is skipped (no correction applied) when:
    - No txt include overlaps at all (Jaccard = 0)
    - The best-match txt include has the same system URL as the existing include
    """
    corrections: Dict[int, str] = {}

    # Pre-build sets of concept codes per txt include
    txt_code_sets = []
    for inc in txt_includes:
        codes = {c["code"] for c in inc.get("concept", [])}
        txt_code_sets.append((codes, inc.get("system", "")))

    for ei, existing_inc in enumerate(existing_includes):
        existing_system = existing_inc.get("system", "")
        existing_codes = {c["code"] for c in existing_inc.get("concept", [])}

        if not existing_codes or not txt_code_sets:
            continue

        # Find the txt include with the highest Jaccard similarity
        best_jaccard = 0.0
        best_system = existing_system
        for txt_codes, txt_system in txt_code_sets:
            if not txt_codes:
                continue
            intersection = len(existing_codes & txt_codes)
            union = len(existing_codes | txt_codes)
            jaccard = intersection / union if union else 0.0
            if jaccard > best_jaccard:
                best_jaccard = jaccard
                best_system = txt_system

        # Only correct if we found a clear match (>50% overlap) and system differs
        if best_jaccard >= 0.5 and best_system != existing_system:
            corrections[ei] = best_system

    return corrections


async def _repair_system_urls(
    client: httpx.AsyncClient,
    target_base: str,
    txt_files: List[Path],
    dry_run: bool,
) -> None:
    """
    For each txt file, parse the correct compose.include.system URLs (via OID mapping)
    and compare them against the existing ValueSet in PH-TS using concept-code overlap
    matching (not index-based).  Where a system URL differs and the match is unambiguous
    (>= 50% Jaccard similarity of concept codes), PUT the corrected ValueSet back,
    preserving all fields not in the txt file (useContext, disease view tags, etc.).
    """
    repaired = skipped = errors = not_found = 0

    for path in txt_files:
        result = parse_phinvads_txt(path)
        if result is None:
            continue
        txt_vs, _ = result

        vs_url = txt_vs.get("url")
        version = txt_vs.get("version")
        if not vs_url:
            continue

        # Fetch the existing ValueSet from PH-TS
        try:
            params: Dict = {"url": vs_url}
            if version:
                params["version"] = version
            resp = await client.get(f"{target_base}/ValueSet", params=params, timeout=15)
            if resp.status_code != 200:
                errors += 1
                continue
            bundle = resp.json()
            entries = bundle.get("entry", [])
            if not entries:
                not_found += 1
                continue
            existing = entries[0]["resource"]
        except Exception as exc:
            logger.warning("Fetch failed for %s: %s", vs_url, exc)
            errors += 1
            continue

        existing_includes = existing.get("compose", {}).get("include", [])
        txt_includes = txt_vs.get("compose", {}).get("include", [])

        corrections = _match_includes_by_concepts(existing_includes, txt_includes)
        if not corrections:
            skipped += 1
            continue

        # Apply corrections to the existing resource (preserves useContext, tags, etc.)
        corrected = dict(existing)
        corrected_includes = []
        title = existing.get("title") or vs_url
        for i, inc in enumerate(existing_includes):
            corrected_inc = dict(inc)
            if i in corrections:
                logger.info("  %s: system %r -> %r", title, inc.get("system"), corrections[i])
                corrected_inc["system"] = corrections[i]
            corrected_includes.append(corrected_inc)

        corrected.setdefault("compose", {})["include"] = corrected_includes

        if dry_run:
            repaired += 1
            continue

        vs_id = existing.get("id")
        try:
            put_resp = await client.put(
                f"{target_base}/ValueSet/{vs_id}",
                json=corrected,
                headers={"Content-Type": "application/fhir+json"},
                timeout=30,
            )
            if put_resp.status_code in (200, 201):
                repaired += 1
            else:
                logger.warning(
                    "  PUT failed for %s: HTTP %d %s",
                    vs_url, put_resp.status_code, put_resp.text[:200],
                )
                errors += 1
        except Exception as exc:
            logger.warning("  PUT error for %s: %s", vs_url, exc)
            errors += 1

    print(
        f"\nSystem URL repair: {repaired} updated, {skipped} already correct, "
        f"{not_found} not in PH-TS, {errors} errors"
    )


async def import_all(
    source_dir: Path,
    target_base: str,
    dry_run: bool,
    limit: Optional[int],
    update_cs_titles: bool,
    repair_system_urls: bool,
) -> None:
    txt_files = sorted(source_dir.glob("*.txt"))
    if limit:
        txt_files = txt_files[:limit]

    total_files = len(txt_files)
    logger.info("Found %d .txt files in %s", total_files, source_dir)

    stats = {"parsed": 0, "imported": 0, "skipped": 0, "errors": 0, "parse_errors": 0}

    headers = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # Health check
        try:
            resp = await client.get(f"{target_base}/health", timeout=10)
            logger.info("Target server health: HTTP %d", resp.status_code)
        except Exception as exc:
            logger.error("Cannot reach target server %s: %s", target_base, exc)
            sys.exit(1)

        sem = asyncio.Semaphore(CONCURRENT_POSTS)
        all_cs_names: Dict[str, str] = {}  # accumulated system_url → PHIN VADS name

        async def process_file(path: Path) -> None:
            result = parse_phinvads_txt(path)
            if result is None:
                stats["parse_errors"] += 1
                return
            resource, cs_names = result
            stats["parsed"] += 1

            # Accumulate code system names from every file
            all_cs_names.update(cs_names)

            vs_url = resource.get("url")
            version = resource.get("version")

            if not dry_run and vs_url:
                async with sem:
                    already = await _resource_exists(client, target_base, vs_url, version)
                if already:
                    stats["skipped"] += 1
                    logger.debug("  = %s (v%s) already exists — skipped", vs_url, version)
                    return

            async with sem:
                success, detail = await _post_valueset(client, target_base, resource, dry_run)

            title = resource.get("title") or resource.get("name") or path.stem
            if success:
                stats["imported"] += 1
                logger.info("  ✓ %s", title)
            else:
                stats["errors"] += 1
                logger.warning("  ✗ %s: %s", title, detail)

        # Process in concurrent batches
        batch_size = CONCURRENT_POSTS * 4
        for i in range(0, total_files, batch_size):
            batch = txt_files[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_files + batch_size - 1) // batch_size
            logger.info("Processing batch %d/%d (files %d–%d of %d)…",
                        batch_num, total_batches, i + 1, min(i + batch_size, total_files), total_files)
            await asyncio.gather(*[process_file(f) for f in batch])

        if update_cs_titles and all_cs_names:
            logger.info("\nUpdating CodeSystem titles from PHIN VADS names (%d unique systems)…",
                        len(all_cs_names))
            await _update_codesystem_titles(client, target_base, all_cs_names, dry_run)

        if repair_system_urls:
            logger.info("\nRepairing compose.include.system URLs in existing ValueSets…")
            await _repair_system_urls(client, target_base, txt_files, dry_run)

    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"{'dry-run=True' if dry_run else 'dry-run=False'}")
    print(f"  Source files   : {total_files}")
    print(f"  Parsed OK      : {stats['parsed']}")
    print(f"  Parse errors   : {stats['parse_errors']}")
    print(f"  Imported       : {stats['imported']}")
    print(f"  Skipped        : {stats['skipped']}")
    print(f"  Errors         : {stats['errors']}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Import PHIN VADS .txt ValueSet exports")
    parser.add_argument(
        "--source-dir",
        default="docs/PHINVADSValueSets",
        help="Directory containing PHIN VADS .txt files",
    )
    parser.add_argument(
        "--target-url",
        default=DEFAULT_TARGET,
        help="Base URL of the PH-TS server (default: http://localhost)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate files without POSTing to the server",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N files (for testing)",
    )
    parser.add_argument(
        "--update-cs-titles",
        action="store_true",
        help=(
            "After importing ValueSets, update the title of each referenced CodeSystem "
            "in PH-TS to the PHIN VADS 'Code System Name' (e.g. 'Administrative sex (HL7)'). "
            "Only updates when the PHIN VADS name is more descriptive than the current title."
        ),
    )
    parser.add_argument(
        "--repair-system-urls",
        action="store_true",
        help=(
            "For existing ValueSets, correct any compose.include.system URLs that were "
            "stored incorrectly (e.g. 'v2-tables' → 'v2-0001') using the OID mapping "
            "from the txt files. Preserves useContext, disease view tags, and all other "
            "metadata. Safe to re-run."
        ),
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_absolute():
        # Resolve relative to the repo root (one level up from migration/)
        script_dir = Path(__file__).parent
        source_dir = (script_dir.parent / source_dir).resolve()

    if not source_dir.exists():
        logger.error("Source directory not found: %s", source_dir)
        sys.exit(1)

    asyncio.run(import_all(
        source_dir, args.target_url, args.dry_run, args.limit,
        args.update_cs_titles, args.repair_system_urls,
    ))


if __name__ == "__main__":
    main()
