"""Seed US Core Practitioner (section 2.43) for Dr. Jones.

Updates Practitioner 2c419e4d to be US Core v6.1.0 compliant:
meta.profile, NPI identifier, address.
Also updates PractitionerRole 55c1335e with US Core profile.
Adds a Provenance for the Practitioner.
"""
import asyncio
import json
import asyncpg

PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"
ROLE_ID         = "55c1335e-f946-4fbf-8f21-99cdbb91946c"
ORGANIZATION_ID = "7320bbf0-8257-4486-99d0-3d547a08ab46"
LOCATION_ID     = "5c144c48-57e0-4c3a-93fc-185dd58996d5"
PROV_ID         = "prov-prac-2c419e4d"

PRACTITIONER = {
    "resourceType": "Practitioner",
    "id": PRACTITIONER_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitioner"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Dr. Sarah Jones, MD</div>"
    },
    "identifier": [
        {
            "system": "http://hl7.org/fhir/sid/us-npi",
            "value": "1234567891"
        }
    ],
    "active": True,
    "name": [
        {
            "use": "official",
            "family": "Jones",
            "given": ["Sarah"],
            "prefix": ["Dr."]
        }
    ],
    "telecom": [
        {
            "system": "email",
            "value": "jones@example.com",
            "use": "work"
        }
    ],
    "address": [
        {
            "use": "work",
            "line": ["456 Medical Center Drive"],
            "city": "Springfield",
            "state": "IL",
            "postalCode": "62701",
            "country": "US"
        }
    ],
    "gender": "female"
}

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
        "reference": f"Practitioner/{PRACTITIONER_ID}",
        "display": "Dr. Sarah Jones"
    },
    "organization": {
        "reference": f"Organization/{ORGANIZATION_ID}",
        "display": "General Hospital"
    },
    "code": [
        {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "62247001",
                    "display": "Family medicine specialist"
                }
            ]
        }
    ],
    "specialty": [
        {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "394814009",
                    "display": "General practice"
                }
            ]
        }
    ],
    "location": [
        {
            "reference": f"Location/{LOCATION_ID}",
            "display": "Flint Family Practice - Main Office"
        }
    ]
}

PROVENANCE = {
    "resourceType": "Provenance",
    "id": PROV_ID,
    "target": [{"reference": f"Practitioner/{PRACTITIONER_ID}"}],
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
            "who": {"reference": f"Practitioner/{PRACTITIONER_ID}"},
            "onBehalfOf": {"reference": f"Organization/{ORGANIZATION_ID}"}
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
        await upsert(conn, "Practitioner", PRACTITIONER_ID, PRACTITIONER)
        await upsert(conn, "PractitionerRole", ROLE_ID, PRACTITIONER_ROLE)
        await upsert(conn, "Provenance", PROV_ID, PROVENANCE)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
