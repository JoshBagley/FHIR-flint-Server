"""Seed US Core PractitionerRole (section 2.44).

Updates PractitionerRole 55c1335e to add:
  - telecom (phone, must-support + mandatory child elements)
  - endpoint (display-only reference, must-support)

Updates DiagnosticReport Note and Lab to add PractitionerRole as a second
performer so Inferno collects PractitionerRole resources during those tests
(is_delayed: true means it's discovered via performer references).
"""
import asyncio
import json
import asyncpg

ROLE_ID    = "55c1335e-f946-4fbf-8f21-99cdbb91946c"
PRAC_ID    = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"
ORG_ID     = "7320bbf0-8257-4486-99d0-3d547a08ab46"
LOC_ID     = "5c144c48-57e0-4c3a-93fc-185dd58996d5"

DR_NOTE_ID = "e6f7a8b9-c0d1-2345-e6f7-a8b9c0d12345"
DR_LAB_ID  = "1a2b3c4d-5e6f-7890-1a2b-3c4d5e6f7890"

PRACTITIONER_ROLE = {
    "resourceType": "PractitionerRole",
    "id": ROLE_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitionerrole"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Dr. Sarah Jones - Family Medicine at General Hospital</div>"
    },
    "active": True,
    "practitioner": {
        "reference": f"Practitioner/{PRAC_ID}",
        "display": "Dr. Sarah Jones"
    },
    "organization": {
        "reference": f"Organization/{ORG_ID}",
        "display": "General Hospital"
    },
    "code": [
        {
            "coding": [
                {
                    "system": "http://nucc.org/provider-taxonomy",
                    "code": "207Q00000X",
                    "display": "Family Medicine"
                }
            ]
        }
    ],
    "specialty": [
        {
            "coding": [
                {
                    "system": "http://nucc.org/provider-taxonomy",
                    "code": "207Q00000X",
                    "display": "Family Medicine"
                }
            ]
        }
    ],
    "location": [
        {
            "reference": f"Location/{LOC_ID}",
            "display": "Flint Family Practice - Main Office"
        }
    ],
    "telecom": [
        {
            "system": "phone",
            "value": "555-555-1234",
            "use": "work"
        }
    ],
    "endpoint": [
        {
            "display": "Flint FHIR R4 Endpoint"
        }
    ]
}


async def get_current_data(conn, resource_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT data FROM fhir_resources WHERE id=$1", resource_id
    )
    if not row:
        raise ValueError(f"Resource {resource_id} not found")
    return json.loads(row["data"])


async def upsert(conn, resource_type: str, resource_id: str, data: dict):
    data_json = json.dumps(data)
    existing = await conn.fetchrow(
        "SELECT id FROM fhir_resources WHERE id=$1", resource_id
    )
    if existing:
        await conn.execute(
            "UPDATE fhir_resources SET data=$1, updated_at=NOW() WHERE id=$2",
            data_json, resource_id
        )
        print(f"  Updated {resource_type}/{resource_id}")
    else:
        await conn.execute(
            "INSERT INTO fhir_resources (id, resource_type, data) VALUES ($1,$2,$3)",
            resource_id, resource_type, data_json
        )
        await conn.execute(
            "INSERT INTO resource_versions (resource_id, version_number, data) VALUES ($1,1,$2)",
            resource_id, data_json
        )
        print(f"  Inserted {resource_type}/{resource_id}")


async def add_practitioner_role_performer(conn, dr_id: str, dr_label: str):
    """Add PractitionerRole/55c1335e as a performer if not already present."""
    dr = await get_current_data(conn, dr_id)
    performers = dr.get("performer") or []
    role_ref = f"PractitionerRole/{ROLE_ID}"
    if any(p.get("reference") == role_ref for p in performers):
        print(f"  {dr_label} already has PractitionerRole performer — skipping")
        return
    performers.append({"reference": role_ref, "display": "Dr. Sarah Jones"})
    dr["performer"] = performers
    await upsert(conn, "DiagnosticReport", dr_id, dr)


async def main():
    conn = await asyncpg.connect(
        host="postgres", port=5432, database="flint",
        user="flint", password="flint_dev_password"
    )
    try:
        print("Updating PractitionerRole (add telecom + endpoint + NUCC codes)...")
        await upsert(conn, "PractitionerRole", ROLE_ID, PRACTITIONER_ROLE)

        print("Adding PractitionerRole performer to DiagnosticReport Note...")
        await add_practitioner_role_performer(conn, DR_NOTE_ID, "DiagnosticReport Note")

        print("Adding PractitionerRole performer to DiagnosticReport Lab...")
        await add_practitioner_role_performer(conn, DR_LAB_ID, "DiagnosticReport Lab")

        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
