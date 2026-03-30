"""
tag_disease_views.py
====================
Tags ValueSets in PH-TS with PHIN VADS views using the exported view files as
the authoritative source of truth.

Each .txt file in PHINVADSViews is one PHIN VADS view.  This script:
  1. Parses every View_*.txt file in the PHINVADSViews directory.
  2. Derives a stable view ID (slug) directly from the filename.
  3. Resolves each OID listed in the file to a PH-TS resource ID via GET /ValueSet?identifier=...
  4. Calls POST /ValueSet/$tag-view for every (resource_id, view_id) pair.

The view catalogue (disease_views.json) is authoritative for which view IDs
are registered.  A view file whose slug does not appear in disease_views.json
is skipped with a warning — run --generate-views first if you add new view files.

Modes
-----
  --dry-run          Print proposed tags without writing anything (default).
  --apply            Write tags to the server.
  --generate-views   Regenerate backend/app/disease_views.json from the view
                     files and exit (no tagging).

Usage
-----
  # Preview what would be tagged
  python migration/tag_disease_views.py --dry-run

  # Apply tags
  python migration/tag_disease_views.py --apply --target-url http://localhost

  # Only process specific view files (substring match on slug)
  python migration/tag_disease_views.py --dry-run --filter covid influenza

  # Show OIDs in view files that were not found in PH-TS
  python migration/tag_disease_views.py --dry-run --show-unmatched

  # Regenerate disease_views.json (run after adding new view files)
  python migration/tag_disease_views.py --generate-views
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

VIEWS_DIR    = Path(__file__).parent.parent / "docs" / "PHINVADSViews"
VIEWS_JSON   = Path(__file__).parent.parent / "backend" / "app" / "disease_views.json"

# View files that are meta-collections, not specific program views.
SKIP_SLUGS = {"all-value-sets", "commonly-downloaded-value-sets"}

# System URI stored in the FHIR useContext coding for PHIN VADS view tags.
PHINVADS_VIEW_SYSTEM = "https://phinvads.cdc.gov/vads/view"


# ---------------------------------------------------------------------------
# Slug / view-ID derivation
# ---------------------------------------------------------------------------

def _make_slug(stem: str) -> str:
    """Derive a stable, URL-safe view ID from a view filename stem."""
    s = stem
    if s.startswith("View_"):
        s = s[5:]
    # Strip trailing version suffix _V{digits}
    s = re.sub(r"_V\d+$", "", s)
    # Remove URL-encoded chars
    s = re.sub(r"\{u[0-9A-Fa-f]+\}", "", s)
    # Normalize punctuation
    s = s.replace("&", "and").replace("\u2019", "").replace("'", "")
    s = re.sub(r"[^a-zA-Z0-9\-_\s]", "-", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-").lower()


# ---------------------------------------------------------------------------
# View file parsing
# ---------------------------------------------------------------------------

def _parse_view_name(path: Path) -> str:
    """Return the display name from the view metadata row."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""
    found_header = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("View Name\t"):
            found_header = True
            continue
        if found_header:
            parts = stripped.split("\t")
            if parts and parts[0].strip():
                return parts[0].strip()
    return ""


def _parse_view_file(path: Path) -> list[dict]:
    """
    Parse OID rows from a PHIN VADS view .txt file.

    Returns a list of dicts with keys: name, code, oid, version, status.
    """
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = []
    in_vs_section = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("View Name\t"):
            continue
        if stripped.startswith("Value Set Name\t"):
            in_vs_section = True
            continue
        if not in_vs_section:
            continue  # view metadata row — skip

        parts = stripped.split("\t")
        if len(parts) >= 3:
            rows.append({
                "name":    parts[0].strip(),
                "code":    parts[1].strip() if len(parts) > 1 else "",
                "oid":     parts[2].strip() if len(parts) > 2 else "",
                "version": parts[3].strip() if len(parts) > 3 else "",
                "status":  parts[5].strip() if len(parts) > 5 else "",
            })
    return rows


# ---------------------------------------------------------------------------
# --generate-views
# ---------------------------------------------------------------------------

def generate_views_json() -> None:
    """Regenerate disease_views.json from the PHINVADSViews directory."""
    views = []
    seen: dict[str, str] = {}

    for vf in sorted(VIEWS_DIR.glob("View_*.txt")):
        slug = _make_slug(vf.stem)
        if slug in SKIP_SLUGS:
            continue
        if slug in seen:
            print(f"  WARNING: duplicate slug '{slug}' from {vf.name} (already from {seen[slug]}) - skipping")
            continue
        seen[slug] = vf.name

        display = _parse_view_name(vf)
        if not display:
            display = slug.replace("-", " ").title()

        views.append({
            "id":          slug,
            "display":     display,
            "system":      PHINVADS_VIEW_SYSTEM,
            "code":        slug,
            "description": display,
        })

    VIEWS_JSON.write_text(json.dumps(views, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Written {len(views)} views -> {VIEWS_JSON}")


# ---------------------------------------------------------------------------
# OID → PH-TS resource ID lookup
# ---------------------------------------------------------------------------

async def _lookup_resource_id(client: httpx.AsyncClient, base_url: str, oid: str) -> str | None:
    """
    Resolve a PHIN VADS OID to a PH-TS ValueSet resource ID.

    Tries in order:
      1. url = https://phinvads.cdc.gov/baseStu3/ValueSet/{oid}  (primary — matches how
         both importers store the canonical url field)
      2. identifier = {oid}  (bare OID, matches identifier[].value in the DB)
    """
    # Form 1: canonical PHIN VADS URL (url column — most reliable)
    try:
        resp = await client.get(
            f"{base_url}/ValueSet",
            params={"url": f"https://phinvads.cdc.gov/baseStu3/ValueSet/{oid}", "_summary": "true"},
            timeout=15,
        )
        if resp.status_code == 200:
            entries = resp.json().get("entry", [])
            if entries:
                return entries[0]["resource"]["id"]
    except Exception:
        pass

    # Form 2: bare OID in identifier[].value
    try:
        resp = await client.get(
            f"{base_url}/ValueSet",
            params={"identifier": oid, "_summary": "true"},
            timeout=15,
        )
        if resp.status_code == 200:
            entries = resp.json().get("entry", [])
            if entries:
                return entries[0]["resource"]["id"]
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------

async def _tag_resource(
    client: httpx.AsyncClient, base_url: str, resource_id: str, view_id: str
) -> bool:
    """Call POST /ValueSet/$tag-view. Returns True on success."""
    try:
        resp = await client.post(
            f"{base_url}/ValueSet/$tag-view",
            params={"resource_id": resource_id, "view_id": view_id},
            timeout=15,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    base_url = args.target_url.rstrip("/")
    dry_run = not args.apply
    filter_terms = [f.lower() for f in args.filter] if args.filter else []

    if dry_run:
        print("\n  DRY RUN - no changes will be written to the server.\n")
    else:
        print(f"\n  APPLY MODE -> {base_url}\n")

    # Load registered view IDs so we can warn about unknown slugs
    try:
        registered = {v["id"] for v in json.loads(VIEWS_JSON.read_text(encoding="utf-8"))}
    except FileNotFoundError:
        print(f"  WARNING: {VIEWS_JSON} not found - run --generate-views first.")
        registered = set()

    # ── 1. Collect all view files ─────────────────────────────────────────

    # (view_id, oid, vs_name, view_file_name)
    TagEntry = tuple[str, str, str, str]
    pending: list[TagEntry] = []
    skipped_files: list[str] = []
    unknown_slug_files: list[str] = []

    for vf in sorted(VIEWS_DIR.glob("View_*.txt")):
        slug = _make_slug(vf.stem)

        if slug in SKIP_SLUGS:
            skipped_files.append(vf.stem)
            continue

        if filter_terms and not any(ft in slug for ft in filter_terms):
            continue

        if registered and slug not in registered:
            unknown_slug_files.append(f"{vf.stem} -> '{slug}'")
            continue

        rows = _parse_view_file(vf)
        for row in rows:
            oid = row["oid"]
            if oid:
                pending.append((slug, oid, row["name"], vf.stem))

    view_files = sorted(VIEWS_DIR.glob("View_*.txt"))
    processable = len(view_files) - len(skipped_files)
    filtered = processable - len(unknown_slug_files) - len(
        [vf for vf in view_files
         if filter_terms and not any(ft in _make_slug(vf.stem) for ft in filter_terms)]
    )

    print(f"  View files found:    {len(view_files)}")
    print(f"  Catch-all skipped:   {len(skipped_files)}")
    if unknown_slug_files:
        print(f"  Unknown slugs:       {len(unknown_slug_files)} (run --generate-views to register)")
        for s in unknown_slug_files[:5]:
            print(f"    {s}")
    print(f"  (OID, view) pairs:   {len(pending)}\n")

    # ── 2. Resolve OIDs → PH-TS resource IDs ─────────────────────────────

    unique_oids = list({oid for _, oid, _, _ in pending})
    oid_to_id: dict[str, str | None] = {}

    print(f"  Resolving {len(unique_oids)} unique OIDs against {base_url} ...")

    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(10)

        async def _resolve(oid: str) -> None:
            async with semaphore:
                oid_to_id[oid] = await _lookup_resource_id(client, base_url, oid)

        await asyncio.gather(*[_resolve(oid) for oid in unique_oids])

    matched   = sum(1 for v in oid_to_id.values() if v)
    unmatched = len(unique_oids) - matched
    print(f"  Resolved: {matched} / {len(unique_oids)}  ({unmatched} OIDs not found in PH-TS)\n")

    # ── 3. Build final tag list ───────────────────────────────────────────

    tags: dict[tuple[str, str], tuple[str, str, str]] = {}  # (res_id, view_id) → (vs_name, oid, fname)
    unmatched_oids: list[tuple[str, str, str]] = []

    for view_id, oid, vs_name, fname in pending:
        resource_id = oid_to_id.get(oid)
        if not resource_id:
            unmatched_oids.append((oid, vs_name, fname))
            continue
        key = (resource_id, view_id)
        if key not in tags:
            tags[key] = (vs_name, oid, fname)

    # ── 4. Print dry-run table ────────────────────────────────────────────

    by_view: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for (res_id, view_id), (vs_name, oid, fname) in sorted(tags.items(), key=lambda x: x[1][0]):
        by_view[view_id].append((res_id, vs_name, oid, fname))

    print("  -- Proposed tags by view --\n")
    total_tags = 0
    for view_id in sorted(by_view):
        entries = by_view[view_id]
        print(f"  [{view_id}]  {len(entries)} value sets")
        for res_id, vs_name, oid, fname in sorted(entries, key=lambda x: x[1]):
            print(f"    {res_id[:12]}...  {vs_name[:55]:<55}  oid:{oid}")
        total_tags += len(entries)
        print()

    print(f"  Total tags to apply: {total_tags}")
    print(f"  (deduplicated across {len(pending)} raw (OID, view) pairs)\n")

    if args.show_unmatched and unmatched_oids:
        seen: set[str] = set()
        print("  -- OIDs not found in PH-TS --\n")
        for oid, vs_name, fname in sorted(unmatched_oids, key=lambda x: x[0]):
            if oid not in seen:
                print(f"    {oid}  {vs_name[:55]:<55}  ({fname})")
                seen.add(oid)
        print()

    if dry_run:
        print("  Dry run complete. Run with --apply to write tags.\n")
        return

    # ── 5. Apply tags ─────────────────────────────────────────────────────

    print("  Applying tags ...")
    applied = 0
    failed  = 0

    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(5)

        async def _apply(res_id: str, view_id: str) -> None:
            nonlocal applied, failed
            async with semaphore:
                ok = await _tag_resource(client, base_url, res_id, view_id)
                if ok:
                    applied += 1
                else:
                    failed += 1

        await asyncio.gather(*[_apply(rid, vid) for (rid, vid) in tags])

    print(f"\n  Done.  Applied: {applied}  Failed: {failed}  (already-tagged handled server-side)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tag PH-TS ValueSets with PHIN VADS views.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--target-url", default="http://localhost",
        help="PH-TS server base URL (default: http://localhost)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write tags to the server (default is dry-run)",
    )
    parser.add_argument(
        "--filter", nargs="+", metavar="TERM",
        help="Only process views whose slug contains one of these substrings",
    )
    parser.add_argument(
        "--show-unmatched", action="store_true",
        help="Print OIDs from view files that were not found in PH-TS",
    )
    parser.add_argument(
        "--generate-views", action="store_true",
        help="Regenerate disease_views.json from PHINVADSViews and exit",
    )
    args = parser.parse_args()

    if args.generate_views:
        generate_views_json()
        return

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
