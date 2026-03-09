"""
PHIN VADS → PH-TS Migration Tool
==================================
Pulls ValueSets and CodeSystems from the PHIN VADS FHIR STU3 API,
converts them to FHIR R4, and imports them into the custom PH-TS server.

Usage:
    python phinvads_migrate.py [OPTIONS]

Options:
    --target-url    PH-TS server base URL (default: http://localhost)
    --batch-size    Resources per batch (default: 50)
    --resource      Resource type to migrate: valueset, codesystem, or all (default: all)
    --oid           Pull and import a single ValueSet by OID (e.g. 2.16.840.1.113883.1.11.1)
    --resume        Resume from a previous checkpoint file
    --dry-run       Fetch and convert but do not POST to target server
    --output-dir    Save converted resources as JSON files to this directory
    --log-level     Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)

Examples:
    python phinvads_migrate.py
    python phinvads_migrate.py --target-url http://myserver --batch-size 25
    python phinvads_migrate.py --resource valueset --dry-run --output-dir ./exported
    python phinvads_migrate.py --resume checkpoint.json
    python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1
    python phinvads_migrate.py --oid 2.16.840.1.113883.1.11.1 --dry-run --output-dir ./exported
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PHINVADS_BASE = "https://phinvads.cdc.gov/baseStu3"
DEFAULT_TARGET = "http://localhost"
REQUEST_TIMEOUT = 60          # seconds per HTTP call
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 2.0           # seconds, doubles on each retry
PAGE_SIZE = 100               # _count per PHIN VADS page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("phinvads_migrate")


# ---------------------------------------------------------------------------
# FHIR STU3 → R4 Conversion helpers
# ---------------------------------------------------------------------------

def _fix_status(status: Optional[str]) -> str:
    """Map STU3 status values to R4 equivalents."""
    mapping = {
        "active": "active",
        "draft": "draft",
        "retired": "retired",
        "unknown": "unknown",
    }
    return mapping.get((status or "").lower(), "unknown")


def _fix_contact(contacts: List[Dict]) -> List[Dict]:
    """STU3 contact.telecom is same shape in R4 — pass through."""
    return contacts or []


def _fix_identifier(identifiers: List[Dict]) -> List[Dict]:
    """STU3 identifier is same shape in R4."""
    return identifiers or []


def _fix_use_context(use_contexts: List[Dict]) -> List[Dict]:
    """
    STU3 useContext.valueCodeableConcept → R4 value.valueCodeableConcept.
    STU3 already uses valueCodeableConcept/valueQuantity/valueRange keys —
    pass through as-is since R4 is backwards-compatible here.
    """
    return use_contexts or []


def _convert_valueset_stu3_to_r4(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a PHIN VADS STU3 ValueSet to a minimal FHIR R4 ValueSet.

    Key STU3→R4 differences handled:
    - extensibility context  (no structural change needed for ValueSet)
    - status normalisation
    - compose.include.filter.op:  STU3 uses string, R4 same — no change
    - expansion.contains: nested includes allowed in R4 same as STU3
    """
    r4: Dict[str, Any] = {
        "resourceType": "ValueSet",
        "url": raw.get("url"),
        "version": raw.get("version"),
        "name": raw.get("name"),
        "title": raw.get("title"),
        "status": _fix_status(raw.get("status")),
        "experimental": raw.get("experimental", False),
        "date": raw.get("date"),
        "publisher": raw.get("publisher"),
        "contact": _fix_contact(raw.get("contact", [])),
        "description": raw.get("description"),
        "useContext": _fix_use_context(raw.get("useContext", [])),
        "jurisdiction": raw.get("jurisdiction", []),
        "immutable": raw.get("immutable"),
        "purpose": raw.get("purpose"),
        "copyright": raw.get("copyright"),
    }

    # Preserve original PHIN VADS id as an identifier so we can trace provenance
    phinvads_id = raw.get("id")
    if phinvads_id:
        r4["identifier"] = [
            {
                "system": "https://phinvads.cdc.gov/vads/ViewValueSet.action?id=",
                "value": phinvads_id,
            }
        ]

    # compose block — structurally identical STU3/R4
    if "compose" in raw:
        r4["compose"] = raw["compose"]

    # expansion — pass through if present
    if "expansion" in raw:
        r4["expansion"] = raw["expansion"]

    # Strip None top-level keys so they don't confuse the server validator
    return {k: v for k, v in r4.items() if v is not None}


def _convert_codesystem_stu3_to_r4(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a PHIN VADS STU3 CodeSystem to FHIR R4.

    Key STU3→R4 differences handled:
    - content field: STU3 "complete"/"fragment"/etc → R4 same values
    - valueSet field: STU3 had no valueSet link; R4 allows it — skip
    - concept.property: same structure in both
    - hierarchyMeaning: new in R4, default to "is-a" for HL7 code systems
    """
    content = raw.get("content", "complete")
    if content not in ("not-present", "example", "fragment", "complete", "supplement"):
        content = "complete"

    r4: Dict[str, Any] = {
        "resourceType": "CodeSystem",
        "url": raw.get("url"),
        "identifier": _fix_identifier(raw.get("identifier", [])),
        "version": raw.get("version"),
        "name": raw.get("name"),
        "title": raw.get("title"),
        "status": _fix_status(raw.get("status")),
        "experimental": raw.get("experimental", False),
        "date": raw.get("date"),
        "publisher": raw.get("publisher"),
        "contact": _fix_contact(raw.get("contact", [])),
        "description": raw.get("description"),
        "useContext": _fix_use_context(raw.get("useContext", [])),
        "jurisdiction": raw.get("jurisdiction", []),
        "purpose": raw.get("purpose"),
        "copyright": raw.get("copyright"),
        "caseSensitive": raw.get("caseSensitive"),
        "hierarchyMeaning": raw.get("hierarchyMeaning", "is-a"),
        "compositional": raw.get("compositional"),
        "versionNeeded": raw.get("versionNeeded"),
        "content": content,
        "count": raw.get("count"),
        "filter": raw.get("filter", []),
        "property": raw.get("property", []),
        "concept": raw.get("concept", []),
    }

    phinvads_id = raw.get("id")
    if phinvads_id and not r4.get("identifier"):
        r4["identifier"] = [
            {
                "system": "https://phinvads.cdc.gov/vads/ViewCodeSystem.action?id=",
                "value": phinvads_id,
            }
        ]

    return {k: v for k, v in r4.items() if v is not None}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _get_json(client: httpx.AsyncClient, url: str, params: Dict = None) -> Dict:
    """GET with retry / back-off."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            if attempt == RETRY_ATTEMPTS:
                raise
            wait = RETRY_BACKOFF * attempt
            logger.warning("Attempt %d/%d failed for %s — retrying in %.1fs: %s",
                           attempt, RETRY_ATTEMPTS, url, wait, exc)
            await asyncio.sleep(wait)


async def _post_resource(
    client: httpx.AsyncClient,
    target_base: str,
    resource_type: str,
    resource: Dict,
    dry_run: bool,
) -> Tuple[bool, str]:
    """
    POST a resource to the target server.
    Returns (success, detail_message).
    """
    if dry_run:
        return True, "dry-run"

    url = f"{target_base}/{resource_type}"
    try:
        resp = await client.post(
            url,
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            body = resp.json()
            server_id = body.get("id", "?")
            return True, f"id={server_id}"
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except httpx.RequestError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint(path: str) -> Dict:
    if path and os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        logger.info("Loaded checkpoint: %s", data)
        return data
    return {"valueset_offset": 0, "codesystem_offset": 0,
            "valueset_done": False, "codesystem_done": False}


def _save_checkpoint(path: str, state: Dict):
    if path:
        with open(path, "w") as f:
            json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Single-OID fetch
# ---------------------------------------------------------------------------

def _normalise_oid(oid: str) -> str:
    """Strip leading 'urn:oid:' prefix if the user included it."""
    return oid.removeprefix("urn:oid:").strip()


async def fetch_by_oid(
    client: httpx.AsyncClient,
    oid: str,
) -> Optional[Dict]:
    """
    Fetch a single ValueSet from PHIN VADS by OID.

    PHIN VADS stores OIDs two ways:
      1. As the logical resource id  → GET /ValueSet/{oid}
      2. As an identifier            → GET /ValueSet?identifier=urn:oid:{oid}

    We try strategy 1 first (cheaper), then fall back to strategy 2.
    Returns the raw STU3 resource dict, or None if not found.
    """
    oid = _normalise_oid(oid)

    # Strategy 1: direct read by logical id
    try:
        logger.info("Trying direct read: GET /ValueSet/%s", oid)
        data = await _get_json(client, f"{PHINVADS_BASE}/ValueSet/{oid}",
                               params={"_format": "json"})
        if data.get("resourceType") == "ValueSet":
            logger.info("Found ValueSet via direct read (id=%s)", oid)
            return data
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        logger.debug("Direct read returned 404, trying identifier search…")

    # Strategy 2: identifier search with urn:oid: prefix
    logger.info("Trying identifier search: GET /ValueSet?identifier=urn:oid:%s", oid)
    bundle = await _get_json(
        client,
        f"{PHINVADS_BASE}/ValueSet",
        params={"identifier": f"urn:oid:{oid}", "_format": "json"},
    )
    entries = bundle.get("entry", [])
    if entries:
        resource = entries[0].get("resource")
        if resource:
            logger.info("Found ValueSet via identifier search (total=%d)", bundle.get("total", 1))
            return resource

    # Strategy 3: bare OID without urn:oid: prefix (some servers store it this way)
    logger.info("Trying bare OID identifier search: GET /ValueSet?identifier=%s", oid)
    bundle = await _get_json(
        client,
        f"{PHINVADS_BASE}/ValueSet",
        params={"identifier": oid, "_format": "json"},
    )
    entries = bundle.get("entry", [])
    if entries:
        resource = entries[0].get("resource")
        if resource:
            logger.info("Found ValueSet via bare OID search (total=%d)", bundle.get("total", 1))
            return resource

    logger.error("ValueSet with OID %s not found in PHIN VADS", oid)
    return None


async def migrate_single_oid(
    phinvads_client: httpx.AsyncClient,
    target_client: httpx.AsyncClient,
    oid: str,
    target_base: str,
    dry_run: bool,
    output_dir: Optional[Path],
) -> Dict:
    """Fetch one ValueSet by OID, convert it, and import it."""
    stats = {"fetched": 0, "converted": 0, "imported": 0, "errors": 0}

    raw = await fetch_by_oid(phinvads_client, oid)
    if raw is None:
        stats["errors"] += 1
        return stats
    stats["fetched"] = 1

    try:
        r4 = _convert_valueset_stu3_to_r4(raw)
        stats["converted"] = 1
    except Exception as exc:
        logger.error("Conversion failed for OID %s: %s", oid, exc)
        stats["errors"] += 1
        return stats

    if output_dir:
        safe = _normalise_oid(oid).replace(".", "_")
        out_path = output_dir / f"ValueSet_{safe}.json"
        out_path.write_text(json.dumps(r4, indent=2, default=str))
        logger.info("Saved converted resource → %s", out_path)

    success, detail = await _post_resource(
        target_client, target_base, "ValueSet", r4, dry_run
    )
    if success:
        stats["imported"] = 1
        logger.info("✓ Imported ValueSet OID=%s  %s", oid, detail)
    else:
        stats["errors"] += 1
        logger.error("✗ Import failed for OID=%s: %s", oid, detail)

    return stats


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------

async def fetch_all_pages(
    client: httpx.AsyncClient,
    resource_type: str,      # "ValueSet" or "CodeSystem"
    start_offset: int = 0,
) -> List[Dict]:
    """
    Page through PHIN VADS FHIR bundle for the given resource type.
    Returns a flat list of raw STU3 resource dicts.
    """
    resources = []
    offset = start_offset
    page = 0

    while True:
        params = {"_count": PAGE_SIZE, "_offset": offset, "_format": "json"}
        logger.info("Fetching %s page %d (offset=%d)…", resource_type, page + 1, offset)

        bundle = await _get_json(
            client,
            f"{PHINVADS_BASE}/{resource_type}",
            params=params,
        )

        entries = bundle.get("entry", [])
        for entry in entries:
            res = entry.get("resource")
            if res:
                resources.append(res)

        total = bundle.get("total", 0)
        logger.info("  Got %d/%d %s resources so far", len(resources) + start_offset, total, resource_type)

        # Check for a 'next' link in the bundle
        next_url = None
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                next_url = link.get("url")
                break

        if not entries or not next_url:
            break

        offset += len(entries)
        page += 1

        # Small delay to be polite to the PHIN VADS API
        await asyncio.sleep(0.2)

    return resources


async def migrate_resource_type(
    phinvads_client: httpx.AsyncClient,
    target_client: httpx.AsyncClient,
    resource_type: str,           # "ValueSet" or "CodeSystem"
    target_base: str,
    start_offset: int,
    batch_size: int,
    dry_run: bool,
    output_dir: Optional[Path],
    checkpoint_path: Optional[str],
    checkpoint: Dict,
) -> Dict:
    """
    Fetch, convert, and import all resources of the given type.
    Returns updated stats dict.
    """
    converter = (
        _convert_valueset_stu3_to_r4
        if resource_type == "ValueSet"
        else _convert_codesystem_stu3_to_r4
    )
    ck_offset_key = f"{resource_type.lower()}_offset"
    ck_done_key = f"{resource_type.lower()}_done"

    stats = {"fetched": 0, "converted": 0, "imported": 0, "skipped": 0, "errors": 0}

    logger.info("=== Starting %s migration (offset=%d) ===", resource_type, start_offset)
    raw_resources = await fetch_all_pages(phinvads_client, resource_type, start_offset)
    stats["fetched"] = len(raw_resources)
    logger.info("Fetched %d %s resources from PHIN VADS", stats["fetched"], resource_type)

    for i in range(0, len(raw_resources), batch_size):
        batch = raw_resources[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        logger.info("Processing %s batch %d (%d resources)…",
                    resource_type, batch_num, len(batch))

        for raw in batch:
            pv_id = raw.get("id", "unknown")
            pv_url = raw.get("url", "")

            # Convert STU3 → R4
            try:
                r4 = converter(raw)
                stats["converted"] += 1
            except Exception as exc:
                logger.error("Convert error for %s %s: %s", resource_type, pv_id, exc)
                stats["errors"] += 1
                continue

            # Optionally write to disk
            if output_dir:
                safe_name = pv_id.replace("/", "_").replace(":", "_")
                out_path = output_dir / f"{resource_type}_{safe_name}.json"
                out_path.write_text(json.dumps(r4, indent=2, default=str))

            # POST to target
            success, detail = await _post_resource(
                target_client, target_base, resource_type, r4, dry_run
            )
            if success:
                stats["imported"] += 1
                logger.debug("  ✓ %s %s → %s", resource_type, pv_url or pv_id, detail)
            else:
                stats["errors"] += 1
                logger.warning("  ✗ %s %s: %s", resource_type, pv_url or pv_id, detail)

        # Update checkpoint after each batch
        checkpoint[ck_offset_key] = start_offset + i + len(batch)
        _save_checkpoint(checkpoint_path, checkpoint)

    checkpoint[ck_done_key] = True
    _save_checkpoint(checkpoint_path, checkpoint)
    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace):
    start_time = time.monotonic()

    # Output directory
    output_dir: Optional[Path] = None
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Saving converted resources to: %s", output_dir)

    # Checkpoint
    checkpoint = _load_checkpoint(args.resume)

    # HTTP clients — separate for source and target
    phinvads_headers = {
        "Accept": "application/fhir+json",
        "User-Agent": "PH-TS-Migration/1.0",
    }
    target_headers = {
        "Accept": "application/fhir+json",
        "Content-Type": "application/fhir+json",
    }

    async with (
        httpx.AsyncClient(base_url=PHINVADS_BASE, headers=phinvads_headers,
                          follow_redirects=True) as phinvads_client,
        httpx.AsyncClient(headers=target_headers, follow_redirects=True) as target_client,
    ):
        # Quick connectivity check on target (skip for dry-run)
        if not args.dry_run:
            try:
                health = await target_client.get(
                    f"{args.target_url}/health", timeout=10
                )
                logger.info("Target server health: HTTP %d", health.status_code)
            except httpx.RequestError as exc:
                logger.error("Cannot reach target server at %s: %s", args.target_url, exc)
                sys.exit(1)

        all_stats: Dict[str, Dict] = {}

        # ── Single-OID mode ────────────────────────────────────────────────
        if args.oid:
            oid_stats = await migrate_single_oid(
                phinvads_client=phinvads_client,
                target_client=target_client,
                oid=args.oid,
                target_base=args.target_url,
                dry_run=args.dry_run,
                output_dir=output_dir,
            )
            all_stats[f"ValueSet (OID={args.oid})"] = oid_stats

        # ── Bulk mode ──────────────────────────────────────────────────────
        else:
            do_vs = args.resource in ("all", "valueset")
            do_cs = args.resource in ("all", "codesystem")

            if do_vs and not checkpoint.get("valueset_done"):
                vs_stats = await migrate_resource_type(
                    phinvads_client=phinvads_client,
                    target_client=target_client,
                    resource_type="ValueSet",
                    target_base=args.target_url,
                    start_offset=checkpoint.get("valueset_offset", 0),
                    batch_size=args.batch_size,
                    dry_run=args.dry_run,
                    output_dir=output_dir,
                    checkpoint_path=args.resume,
                    checkpoint=checkpoint,
                )
                all_stats["ValueSet"] = vs_stats
            elif do_vs:
                logger.info("ValueSet migration already complete (checkpoint). Skipping.")

            if do_cs and not checkpoint.get("codesystem_done"):
                cs_stats = await migrate_resource_type(
                    phinvads_client=phinvads_client,
                    target_client=target_client,
                    resource_type="CodeSystem",
                    target_base=args.target_url,
                    start_offset=checkpoint.get("codesystem_offset", 0),
                    batch_size=args.batch_size,
                    dry_run=args.dry_run,
                    output_dir=output_dir,
                    checkpoint_path=args.resume,
                    checkpoint=checkpoint,
                )
                all_stats["CodeSystem"] = cs_stats
            elif do_cs:
                logger.info("CodeSystem migration already complete (checkpoint). Skipping.")

    # Print summary
    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Completed in {elapsed:.1f}s  |  dry-run={args.dry_run}")
    for rtype, s in all_stats.items():
        print(f"\n  {rtype}")
        print(f"    Fetched   : {s['fetched']}")
        print(f"    Converted : {s['converted']}")
        print(f"    Imported  : {s['imported']}")
        print(f"    Errors    : {s['errors']}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate PHIN VADS ValueSets/CodeSystems to PH-TS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--target-url", default=DEFAULT_TARGET,
                        help="PH-TS base URL (default: http://localhost)")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Resources per batch (default: 50)")
    parser.add_argument("--resource", choices=["all", "valueset", "codesystem"],
                        default="all", help="Resource type to migrate (default: all)")
    parser.add_argument("--oid", metavar="OID",
                        help="Import a single ValueSet by OID (e.g. 2.16.840.1.113883.1.11.1). "
                             "Skips bulk migration. urn:oid: prefix is optional.")
    parser.add_argument("--resume", metavar="CHECKPOINT_FILE",
                        help="Path to checkpoint JSON file for resuming")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and convert but do not POST to the target server")
    parser.add_argument("--output-dir", metavar="DIR",
                        help="Save converted R4 JSON files to this directory")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging verbosity (default: INFO)")

    args = parser.parse_args()
    logging.getLogger().setLevel(args.log_level)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
