"""Seed US Core Blood Pressure Observation (section 2.34) for Alice.

Two observations covering all must-support elements:
  - obs-alice-bp-normal : systolic + diastolic valueQuantity
  - obs-alice-bp-absent : systolic + diastolic dataAbsentReason
"""
import asyncio
import json
import asyncpg

ALICE_ID = "3e7c75f4-d87c-4648-bff5-89a3c5adbdb1"
ENCOUNTER_ID = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"
PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"

NORMAL_ID = "obs-alice-bp-normal"
ABSENT_ID = "obs-alice-bp-absent"

COMMON = {
    "resourceType": "Observation",
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure"
        ]
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
                "code": "85354-9",
                "display": "Blood pressure panel with all children optional"
            }
        ],
        "text": "Blood pressure panel with all children optional"
    },
    "subject": {"reference": f"Patient/{ALICE_ID}"},
    "encounter": {"reference": f"Encounter/{ENCOUNTER_ID}"},
    "performer": [{"reference": f"Practitioner/{PRACTITIONER_ID}"}],
}

# Normal BP — covers component:systolic.value[x] and component:diastolic.value[x]
NORMAL = {
    **COMMON,
    "id": NORMAL_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Blood pressure 120/80 mmHg</div>"
    },
    "effectiveDateTime": "2024-01-15T08:00:00Z",
    "component": [
        {
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "8480-6",
                        "display": "Systolic blood pressure"
                    }
                ],
                "text": "Systolic blood pressure"
            },
            "valueQuantity": {
                "value": 120,
                "unit": "mmHg",
                "system": "http://unitsofmeasure.org",
                "code": "mm[Hg]"
            }
        },
        {
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "8462-4",
                        "display": "Diastolic blood pressure"
                    }
                ],
                "text": "Diastolic blood pressure"
            },
            "valueQuantity": {
                "value": 80,
                "unit": "mmHg",
                "system": "http://unitsofmeasure.org",
                "code": "mm[Hg]"
            }
        }
    ]
}

# BP with dataAbsentReason — covers component.dataAbsentReason,
# component:systolic.dataAbsentReason, component:diastolic.dataAbsentReason
ABSENT = {
    **COMMON,
    "id": ABSENT_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Blood pressure not performed</div>"
    },
    "effectiveDateTime": "2024-02-01T08:00:00Z",
    "component": [
        {
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "8480-6",
                        "display": "Systolic blood pressure"
                    }
                ],
                "text": "Systolic blood pressure"
            },
            "dataAbsentReason": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
                        "code": "not-performed",
                        "display": "Not Performed"
                    }
                ],
                "text": "Not Performed"
            }
        },
        {
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "8462-4",
                        "display": "Diastolic blood pressure"
                    }
                ],
                "text": "Diastolic blood pressure"
            },
            "dataAbsentReason": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
                        "code": "not-performed",
                        "display": "Not Performed"
                    }
                ],
                "text": "Not Performed"
            }
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
        await upsert(conn, "Observation", NORMAL_ID, NORMAL)
        await upsert(conn, "Observation", ABSENT_ID, ABSENT)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
