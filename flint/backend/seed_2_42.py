"""Seed US Core Organization (section 2.42) for Alice.

Updates the existing Organization 7320bbf0 (General Hospital) to be
US Core v6.1.0 compliant: meta.profile, identifier, active, address, telecom.
Also adds a Provenance.
"""
import asyncio
import json
import asyncpg

ORG_ID  = "7320bbf0-8257-4486-99d0-3d547a08ab46"
PROV_ID = "prov-org-7320bbf0"
PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"

ORGANIZATION = {
    "resourceType": "Organization",
    "id": ORG_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-organization"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">General Hospital</div>"
    },
    "identifier": [
        {
            "system": "http://hl7.org/fhir/sid/us-npi",
            "value": "1234567893"
        }
    ],
    "active": True,
    "type": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/organization-type",
                    "code": "prov",
                    "display": "Healthcare Provider"
                }
            ]
        }
    ],
    "name": "General Hospital",
    "telecom": [
        {
            "system": "phone",
            "value": "+1-217-555-1000",
            "use": "work"
        }
    ],
    "address": [
        {
            "use": "work",
            "line": ["500 Medical Center Drive"],
            "city": "Springfield",
            "state": "IL",
            "postalCode": "62701",
            "country": "US"
        }
    ]
}

PROVENANCE = {
    "resourceType": "Provenance",
    "id": PROV_ID,
    "target": [{"reference": f"Organization/{ORG_ID}"}],
    "recorded": "2024-01-01T00:00:00Z",
    "agent": [
        {
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                        "code": "author",
                        "display": "Author"
                    }
                ]
            },
            "who": {"reference": f"Practitioner/{PRACTITIONER_ID}"}
        }
    ]
}


async def upsert(conn, resource_type, resource_id, data):
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


async def main():
    conn = await asyncpg.connect(
        host="postgres", port=5432, database="flint", user="flint", password="flint_dev_password"
    )
    try:
        await upsert(conn, "Organization", ORG_ID, ORGANIZATION)
        await upsert(conn, "Provenance", PROV_ID, PROVENANCE)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
