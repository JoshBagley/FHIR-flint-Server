"""Seed US Core Head Circumference observation (section 2.30) for Alice."""
import asyncio
import json
import asyncpg

ALICE_ID = "3e7c75f4-d87c-4648-bff5-89a3c5adbdb1"
ENCOUNTER_ID = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"
PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"
OBS_ID = "obs-alice-head-circ-001"
PROV_ID = "prov-alice-head-circ-001"

OBSERVATION = {
    "resourceType": "Observation",
    "id": OBS_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-head-circumference"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Head circumference: 56 cm</div>"
    },
    "status": "final",
    "category": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "vital-signs",
                    "display": "Vital Signs"
                }
            ],
            "text": "Vital Signs"
        }
    ],
    "code": {
        "coding": [
            {
                "system": "http://loinc.org",
                "code": "9843-4",
                "display": "Head Occipital-frontal circumference"
            }
        ],
        "text": "Head Occipital-frontal circumference"
    },
    "subject": {"reference": f"Patient/{ALICE_ID}"},
    "encounter": {"reference": f"Encounter/{ENCOUNTER_ID}"},
    "effectiveDateTime": "2024-01-15T08:00:00Z",
    "performer": [{"reference": f"Practitioner/{PRACTITIONER_ID}"}],
    "valueQuantity": {
        "value": 56,
        "unit": "cm",
        "system": "http://unitsofmeasure.org",
        "code": "cm"
    }
}

PROVENANCE = {
    "resourceType": "Provenance",
    "id": PROV_ID,
    "target": [{"reference": f"Observation/{OBS_ID}"}],
    "recorded": "2024-01-15T08:00:00Z",
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
        await upsert(conn, "Observation", OBS_ID, OBSERVATION)
        await upsert(conn, "Provenance", PROV_ID, PROVENANCE)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
