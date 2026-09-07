"""Seed Endpoint resource and update PractitionerRole to reference it (section 2.44 fix).

Fixes 2.44.06: MustSupport references within PractitionerRole resources are valid.
The endpoint element was display-only; Inferno requires a resolvable reference.
"""
import asyncio
import json
import asyncpg

ROLE_ID = "55c1335e-f946-4fbf-8f21-99cdbb91946c"
ORG_ID  = "7320bbf0-8257-4486-99d0-3d547a08ab46"
EP_ID   = "endpoint-flint-fhir-r4"

ENDPOINT = {
    "resourceType": "Endpoint",
    "id": EP_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Flint FHIR R4 Endpoint</div>"
    },
    "status": "active",
    "connectionType": {
        "system": "http://terminology.hl7.org/CodeSystem/endpoint-connection-type",
        "code": "hl7-fhir-rest",
        "display": "HL7 FHIR"
    },
    "name": "Flint FHIR R4 Endpoint",
    "managingOrganization": {"reference": f"Organization/{ORG_ID}"},
    "payloadType": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/endpoint-payload-type",
                    "code": "any",
                    "display": "Any"
                }
            ]
        }
    ],
    "address": "http://localhost/fhir/r4"
}


async def get_current_data(conn, resource_id: str) -> dict:
    row = await conn.fetchrow("SELECT data FROM fhir_resources WHERE id=$1", resource_id)
    if not row:
        raise ValueError(f"Resource {resource_id} not found")
    return json.loads(row["data"])


async def upsert(conn, resource_type: str, resource_id: str, data: dict):
    data_json = json.dumps(data)
    existing = await conn.fetchrow("SELECT id FROM fhir_resources WHERE id=$1", resource_id)
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
        host="postgres", port=5432, database="flint",
        user="flint", password="flint_dev_password"
    )
    try:
        print("Inserting Endpoint resource...")
        await upsert(conn, "Endpoint", EP_ID, ENDPOINT)

        print("Updating PractitionerRole endpoint reference...")
        role = await get_current_data(conn, ROLE_ID)
        role["endpoint"] = [{"reference": f"Endpoint/{EP_ID}", "display": "Flint FHIR R4 Endpoint"}]
        await upsert(conn, "PractitionerRole", ROLE_ID, role)

        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
