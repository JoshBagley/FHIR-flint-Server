"""
fix_system_urls.py
==================
Patches ValueSet resources in the PH-TS database that contain non-canonical
CodeSystem system URLs (typically PHIN VADS data-quality issues where a web
page URL was used instead of the proper FHIR canonical URI).

For each mapping, the script:
  1. Finds all ValueSets whose compose.include contains the bad system URL.
  2. Replaces every occurrence in-place using a PostgreSQL UPDATE with jsonb
     string replacement.
  3. Reports counts before/after.

Safe to re-run — rows with no remaining occurrences are simply not matched.

Usage
-----
    python migration/fix_system_urls.py [--target-dsn DSN] [--dry-run]

Options
-------
    --target-dsn  PostgreSQL DSN (default: postgresql://phts:phts@localhost:5432/phts)
    --dry-run     Report affected rows without applying changes

Requirements
------------
    pip install asyncpg
"""

import argparse
import asyncio
import json

import asyncpg

DEFAULT_DSN = "postgresql://phts:phts@localhost:5432/phts"

# ---------------------------------------------------------------------------
# URL remapping table
# ---------------------------------------------------------------------------
# Each entry: (bad_url, canonical_url, human_label)
# The script does a jsonb string-replace so any occurrence of bad_url inside
# the stored JSON blob is replaced with canonical_url.
URL_REMAPPINGS = [
    # SNOMED CT US Edition page URL → canonical SNOMED CT URI
    (
        "https://www.nlm.nih.gov/healthit/snomedct/us_edition.html",
        "http://snomed.info/sct",
        "SNOMED CT US Edition page → http://snomed.info/sct",
    ),
    # LOINC downloads page → canonical LOINC URI
    (
        "https://loinc.org/downloads/",
        "http://loinc.org",
        "LOINC downloads page → http://loinc.org",
    ),
    # UCUM website → canonical UCUM URI
    (
        "https://ucum.org",
        "http://unitsofmeasure.org",
        "UCUM website → http://unitsofmeasure.org",
    ),
    # HL7 v2 Table 0078 index page → canonical v2-0078 URI
    (
        "https://www.hl7.org/fhir/v2/0078/index.html",
        "http://terminology.hl7.org/CodeSystem/v2-0078",
        "HL7 v2-0078 page → http://terminology.hl7.org/CodeSystem/v2-0078",
    ),
    # HL7 data-absent-reason versioned page → canonical URI
    (
        "https://terminology.hl7.org/6.4.0/CodeSystem-data-absent-reason.html",
        "http://terminology.hl7.org/CodeSystem/data-absent-reason",
        "HL7 data-absent-reason page → http://terminology.hl7.org/CodeSystem/data-absent-reason",
    ),
    # CDC IIS CVX vaccine codes website → canonical FHIR CVX URI
    (
        "https://www2a.cdc.gov/vaccines/iis/iisstandards/vaccines.asp?rpt=cvx",
        "http://hl7.org/fhir/sid/cvx",
        "CDC CVX website → http://hl7.org/fhir/sid/cvx",
    ),
    # CDC IIS MVX manufacturer codes website → canonical FHIR MVX URI
    (
        "https://www2a.cdc.gov/vaccines/iis/iisstandards/vaccines.asp?rpt=mvx",
        "http://hl7.org/fhir/sid/mvx",
        "CDC MVX website → http://hl7.org/fhir/sid/mvx",
    ),
    # CDC IIS HL7 technical guidance page → canonical CVX URI (same codes)
    (
        "http://www.cdc.gov/vaccines/programs/iis/technical-guidance/hl7.html",
        "http://hl7.org/fhir/sid/cvx",
        "CDC IIS HL7 guidance page → http://hl7.org/fhir/sid/cvx",
    ),
    # PHIN VADS CDC code system action URLs → canonical urn:oid: form
    (
        "https://phinvads.cdc.gov/vads/ViewCodeSystem.action?id=2.16.840.1.114222.4.5.274#",
        "urn:oid:2.16.840.1.114222.4.5.274",
        "PHIN VADS CS 274 action URL → urn:oid:2.16.840.1.114222.4.5.274",
    ),
    (
        "https://phinvads.cdc.gov/vads/ViewCodeSystem.action?id=2.16.840.1.114222.4.5.327#",
        "urn:oid:2.16.840.1.114222.4.5.327",
        "PHIN VADS CS 327 action URL → urn:oid:2.16.840.1.114222.4.5.327",
    ),
    # CDC PHIN vocabulary page → canonical urn:oid: form (PHIN VADS vocabulary)
    (
        "http://www.cdc.gov/phin/resources/vocabulary/index.html",
        "urn:oid:2.16.840.1.114222.4.5.232",
        "CDC PHIN vocab page → urn:oid:2.16.840.1.114222.4.5.232",
    ),
    # ISO 3166-1 page → canonical FHIR URI
    (
        "http://www.iso.org/iso/country_codes/iso_3166_code_lists.htm",
        "urn:iso:std:iso:3166",
        "ISO 3166-1 page → urn:iso:std:iso:3166",
    ),
    # ISO 3166-3 page → canonical FHIR URI
    (
        "http://www.iso.org/iso/country_codes/background_on_iso_3166/iso_3166-3.htm#updates",
        "urn:iso:std:iso:3166:-3",
        "ISO 3166-3 page → urn:iso:std:iso:3166:-3",
    ),
    # ISO 639-2 page → HL7 canonical
    (
        "http://www.loc.gov/standards/iso639-2/",
        "urn:ietf:bcp:47",
        "ISO 639-2 page → urn:ietf:bcp:47",
    ),
    # ISO 639-3 SIL page → urn:iso:std:iso:639:-3
    (
        "https://iso639-3.sil.org/code_tables/download_tables",
        "urn:iso:std:iso:639:-3",
        "ISO 639-3 page → urn:iso:std:iso:639:-3",
    ),
    # FIPS 5-2 (US states) → HL7 FHIR canonical
    (
        "http://www.itl.nist.gov/fipspubs/fip5-2.htm#FORE_SEC",
        "https://www.usps.com/",
        "FIPS 5-2 page → https://www.usps.com/ (USPS state abbreviations)",
    ),
    # FIPS 10-4 (country codes) → urn:iso:std:iso:3166 (superseded by ISO 3166)
    (
        "http://www.itl.nist.gov/fipspubs/fip10-4.htm",
        "urn:iso:std:iso:3166",
        "FIPS 10-4 page → urn:iso:std:iso:3166 (superseded)",
    ),
    # USGS GNIS geographic names
    (
        "https://www.usgs.gov/core-science-systems/ngp/board-on-geographic-names/download-gnis-data",
        "http://www.usgs.gov/ontologies/usgs-thesaurus.owl",
        "USGS GNIS download page → USGS GNIS URI",
    ),
    # BLS SOC occupational codes
    (
        "http://www.bls.gov/soc/home.htm",
        "urn:oid:2.16.840.1.113883.6.243",
        "BLS SOC page → urn:oid:2.16.840.1.113883.6.243",
    ),
    # NAICS industry codes
    (
        "https://www.census.gov/naics",
        "urn:oid:2.16.840.1.113883.6.85",
        "NAICS page → urn:oid:2.16.840.1.113883.6.85",
    ),
    # NLM homepage (too generic — map to NLM MedlinePlus OID)
    (
        "http://www.nlm.nih.gov/",
        "urn:oid:2.16.840.1.113883.6.177",
        "NLM homepage → urn:oid:2.16.840.1.113883.6.177 (MeSH)",
    ),
    # HL7 v2.5 standards page (ambiguous — register as HL7 v2.5 URI)
    (
        "https://www.hl7.org/library/standards_non1.htm#HL7 Version 2.5",
        "http://terminology.hl7.org/CodeSystem/v2-tables",
        "HL7 v2.5 page → http://terminology.hl7.org/CodeSystem/v2-tables",
    ),
    # HL7 RIM 2.26.2 download URL (generic RIM reference)
    (
        "http://hl7projects.hl7.nscee.edu/frs/download.php/622/hl7_rimrepos-2.26.2.zip",
        "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
        "HL7 RIM 2.26.2 download → http://terminology.hl7.org/CodeSystem/v3-RoleCode",
    ),
    # ---------------------------------------------------------------------------
    # HL7 V3 vocabulary OIDs stored as urn:oid: in the DB (imported before OID
    # table was complete). Each maps to the canonical terminology.hl7.org URI.
    # ---------------------------------------------------------------------------
    ("urn:oid:2.16.840.1.113883.5.1",    "http://terminology.hl7.org/CodeSystem/v3-AdministrativeGender", "urn:oid: AdministrativeGender → v3-AdministrativeGender"),
    ("urn:oid:2.16.840.1.113883.5.2",    "http://terminology.hl7.org/CodeSystem/v3-MaritalStatus",        "urn:oid: MaritalStatus → v3-MaritalStatus"),
    ("urn:oid:2.16.840.1.113883.5.4",    "http://terminology.hl7.org/CodeSystem/v3-ActCode",               "urn:oid: ActCode → v3-ActCode"),
    ("urn:oid:2.16.840.1.113883.5.6",    "http://terminology.hl7.org/CodeSystem/v3-ActClass",              "urn:oid: ActClass → v3-ActClass"),
    ("urn:oid:2.16.840.1.113883.5.7",    "http://terminology.hl7.org/CodeSystem/v3-ActPriority",           "urn:oid: ActPriority → v3-ActPriority"),
    ("urn:oid:2.16.840.1.113883.5.8",    "http://terminology.hl7.org/CodeSystem/v3-ActReason",             "urn:oid: ActReason → v3-ActReason"),
    ("urn:oid:2.16.840.1.113883.5.14",   "http://terminology.hl7.org/CodeSystem/v3-ActStatus",             "urn:oid: ActStatus → v3-ActStatus"),
    ("urn:oid:2.16.840.1.113883.5.25",   "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",       "urn:oid: Confidentiality → v3-Confidentiality"),
    ("urn:oid:2.16.840.1.113883.5.42",   "http://terminology.hl7.org/CodeSystem/v3-EntityHandling",        "urn:oid: EntityHandling → v3-EntityHandling"),
    ("urn:oid:2.16.840.1.113883.5.43",   "http://terminology.hl7.org/CodeSystem/v3-EntityNamePartQualifier", "urn:oid: EntityNamePartQualifier → v3-EntityNamePartQualifier"),
    ("urn:oid:2.16.840.1.113883.5.45",   "http://terminology.hl7.org/CodeSystem/v3-EntityNameUse",         "urn:oid: EntityNameUse → v3-EntityNameUse"),
    ("urn:oid:2.16.840.1.113883.5.53",   "http://nucc.org/provider-taxonomy",                              "urn:oid: HL7 HealthcareProviderTaxonomy → http://nucc.org/provider-taxonomy"),
    ("urn:oid:2.16.840.1.113883.5.60",   "http://terminology.hl7.org/CodeSystem/v3-LanguageAbilityMode",   "urn:oid: LanguageAbilityMode → v3-LanguageAbilityMode"),
    ("urn:oid:2.16.840.1.113883.5.61",   "http://terminology.hl7.org/CodeSystem/v3-LanguageAbilityProficiency", "urn:oid: LanguageAbilityProficiency → v3-LanguageAbilityProficiency"),
    ("urn:oid:2.16.840.1.113883.5.63",   "http://terminology.hl7.org/CodeSystem/v3-LivingArrangement",     "urn:oid: LivingArrangement → v3-LivingArrangement"),
    ("urn:oid:2.16.840.1.113883.5.74",   "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",            "urn:oid: NullFlavor (alt OID .74) → v3-NullFlavor"),
    ("urn:oid:2.16.840.1.113883.5.83",   "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "urn:oid: ObservationInterpretation → v3-ObservationInterpretation"),
    ("urn:oid:2.16.840.1.113883.5.84",   "http://terminology.hl7.org/CodeSystem/v3-ObservationMethod",     "urn:oid: ObservationMethod → v3-ObservationMethod"),
    ("urn:oid:2.16.840.1.113883.5.88",   "http://terminology.hl7.org/CodeSystem/v3-ParticipationFunction", "urn:oid: ParticipationFunction → v3-ParticipationFunction"),
    ("urn:oid:2.16.840.1.113883.5.90",   "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",     "urn:oid: ParticipationType → v3-ParticipationType"),
    ("urn:oid:2.16.840.1.113883.5.110",  "http://terminology.hl7.org/CodeSystem/v3-RoleClass",             "urn:oid: RoleClass → v3-RoleClass"),
    ("urn:oid:2.16.840.1.113883.5.111",  "http://terminology.hl7.org/CodeSystem/v3-RoleCode",              "urn:oid: RoleCode → v3-RoleCode"),
    ("urn:oid:2.16.840.1.113883.5.112",  "http://terminology.hl7.org/CodeSystem/v3-RouteOfAdministration", "urn:oid: RouteOfAdministration → v3-RouteOfAdministration"),
    ("urn:oid:2.16.840.1.113883.5.1001", "http://terminology.hl7.org/CodeSystem/v3-ActMood",               "urn:oid: ActMood → v3-ActMood"),
    ("urn:oid:2.16.840.1.113883.5.1008", "http://terminology.hl7.org/CodeSystem/v3-NullFlavor",            "urn:oid: NullFlavor → v3-NullFlavor"),
    ("urn:oid:2.16.840.1.113883.5.1064", "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode",     "urn:oid: ParticipationMode → v3-ParticipationMode"),
    ("urn:oid:2.16.840.1.113883.5.1076", "http://terminology.hl7.org/CodeSystem/v3-ReligiousAffiliation",  "urn:oid: ReligiousAffiliation → v3-ReligiousAffiliation"),
    ("urn:oid:2.16.840.1.113883.5.1077", "http://terminology.hl7.org/CodeSystem/v3-EducationLevel",        "urn:oid: EducationLevel → v3-EducationLevel"),
    ("urn:oid:2.16.840.1.113883.5.1119", "http://terminology.hl7.org/CodeSystem/v3-AddressUse",            "urn:oid: AddressUse → v3-AddressUse"),
]


async def run(dsn: str, dry_run: bool) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        total_updated = 0
        for bad_url, canonical_url, label in URL_REMAPPINGS:
            # Count affected rows first
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM fhir_resources
                WHERE resource_type = 'ValueSet'
                  AND archived = FALSE
                  AND data::text LIKE $1
                """,
                f"%{bad_url}%",
            )
            if count == 0:
                print(f"  (no match) {label}")
                continue

            if dry_run:
                print(f"  DRY RUN — would update {count} row(s): {label}")
                continue

            # Replace the bad URL with the canonical URL in the JSON blob.
            # Cast via ::jsonb (not to_jsonb()) — to_jsonb() on a text value
            # creates a JSON string literal rather than a JSON object.
            updated = await conn.fetchval(
                """
                WITH updated AS (
                    UPDATE fhir_resources
                    SET data = replace(data::text, $1, $2)::jsonb
                    WHERE resource_type = 'ValueSet'
                      AND archived = FALSE
                      AND data::text LIKE $3
                    RETURNING 1
                )
                SELECT COUNT(*) FROM updated
                """,
                bad_url,
                canonical_url,
                f"%{bad_url}%",
            )
            print(f"  Updated {updated} row(s): {label}")
            total_updated += updated

        if not dry_run:
            print(f"\nTotal ValueSets patched: {total_updated}")
        else:
            print("\nDry run complete — no changes applied.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix non-canonical system URLs in ValueSet resources")
    parser.add_argument("--target-dsn", default=DEFAULT_DSN, help="PostgreSQL DSN")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not update")
    args = parser.parse_args()

    print("Scanning ValueSets for non-canonical system URLs…\n")
    asyncio.run(run(args.target_dsn, args.dry_run))


if __name__ == "__main__":
    main()
