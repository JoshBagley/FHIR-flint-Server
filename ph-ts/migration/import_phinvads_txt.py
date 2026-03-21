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
    "2.16.840.1.113883.5.7":    "http://terminology.hl7.org/CodeSystem/v3-ActMood",
    "2.16.840.1.113883.5.8":    "http://terminology.hl7.org/CodeSystem/v3-ActReason",
    "2.16.840.1.113883.5.14":   "http://terminology.hl7.org/CodeSystem/v3-ActStatus",
    "2.16.840.1.113883.5.25":   "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
    "2.16.840.1.113883.5.43":   "http://terminology.hl7.org/CodeSystem/v3-EntityNamePartQualifier",
    "2.16.840.1.113883.5.45":   "http://terminology.hl7.org/CodeSystem/v3-EntityNameUse",
    "2.16.840.1.113883.5.60":   "http://terminology.hl7.org/CodeSystem/v3-LanguageAbilityMode",
    "2.16.840.1.113883.5.63":   "http://terminology.hl7.org/CodeSystem/v3-LivingArrangement",
    "2.16.840.1.113883.5.74":   "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",
    "2.16.840.1.113883.5.1008": "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",
    "2.16.840.1.113883.5.83":   "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
    "2.16.840.1.113883.5.1001": "http://terminology.hl7.org/CodeSystem/v3-ActMood",
    "2.16.840.1.113883.5.1119": "http://terminology.hl7.org/CodeSystem/v3-AddressUse",
    "2.16.840.1.113883.5.111":  "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
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


def _oid_to_system(oid: str) -> str:
    """Normalize a code system OID to a canonical FHIR URL, or keep as urn:oid:."""
    if not oid:
        return ""
    canonical = _OID_TO_CANONICAL.get(oid)
    if canonical:
        return canonical
    if oid.startswith("urn:oid:"):
        inner = oid[len("urn:oid:"):]
        canonical = _OID_TO_CANONICAL.get(inner)
        if canonical:
            return canonical
        return oid
    return f"urn:oid:{oid}"


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

def parse_phinvads_txt(path: Path) -> Optional[Dict]:
    """
    Parse a PHIN VADS .txt export file into an R4 ValueSet dict.
    Returns None on parse error.
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

    description = definition
    if release_notes:
        description = f"{description}\n\nRelease Notes: {release_notes}" if description else f"Release Notes: {release_notes}"

    vs_url = f"https://phinvads.cdc.gov/baseStu3/ValueSet/{oid}" if oid else None

    # --- Parse concepts (section 2) ---
    concept_section = "\r\n".join(lines[blank_idx + 1:])
    concept_reader = csv.DictReader(io.StringIO(concept_section), delimiter="\t")

    # Group concepts by code system OID → compose.include entries
    includes: Dict[str, Dict] = {}  # key: (system_url, version)

    for row in concept_reader:
        code = (row.get("Concept Code") or "").strip()
        display = (row.get("Concept Name") or "").strip()
        preferred = (row.get("Preferred Concept Name") or "").strip()
        cs_oid = (row.get("Code System OID") or "").strip()
        cs_version = (row.get("Code System Version") or "").strip()

        if not code or not cs_oid:
            continue

        system_url = _oid_to_system(cs_oid)
        key = (system_url, cs_version)

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
    return {k: v for k, v in r4.items() if v is not None}


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

async def import_all(
    source_dir: Path,
    target_base: str,
    dry_run: bool,
    limit: Optional[int],
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

        async def process_file(path: Path) -> None:
            resource = parse_phinvads_txt(path)
            if resource is None:
                stats["parse_errors"] += 1
                return
            stats["parsed"] += 1

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
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_absolute():
        # Resolve relative to the repo root (one level up from migration/)
        script_dir = Path(__file__).parent
        source_dir = (script_dir.parent / source_dir).resolve()

    if not source_dir.exists():
        logger.error("Source directory not found: %s", source_dir)
        sys.exit(1)

    asyncio.run(import_all(source_dir, args.target_url, args.dry_run, args.limit))


if __name__ == "__main__":
    main()
