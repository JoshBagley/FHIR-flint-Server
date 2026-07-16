"""Seed US Core Pediatric BMI for Age Observation (section 2.36) for Alice.

Two observations covering all must-support elements:
  - obs-alice-pedi-bmi-normal : valueQuantity (BMI percentile)
  - obs-alice-pedi-bmi-absent : dataAbsentReason
"""
import asyncio
import json
import asyncpg

ALICE_ID = "3e7c75f4-d87c-4648-bff5-89a3c5adbdb1"
ENCOUNTER_ID = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"
PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"

NORMAL_ID = "obs-alice-pedi-bmi-normal"
ABSENT_ID = "obs-alice-pedi-bmi-absent"
PROV_ID   = "prov-alice-pedi-bmi"

COMMON = {
    "resourceType": "Observation",
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/pediatric-bmi-for-age"
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
                "code": "59576-9",
                "display": "Body mass index (BMI) [Percentile] Per age and sex"
            }
        ],
        "text": "Body mass index (BMI) [Percentile] Per age and sex"
    },
    "subject": {"reference": f"Patient/{ALICE_ID}"},
    "encounter": {"reference": f"Encounter/{ENCOUNTER_ID}"},
    "performer": [{"reference": f"Practitioner/{PRACTITIONER_ID}"}],
}

# Normal observation — covers value[x], value[x].value, .unit, .system, .code
NORMAL = {
    **COMMON,
    "id": NORMAL_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">BMI percentile: 65%</div>"
    },
    "effectiveDateTime": "2024-01-15T08:00:00Z",
    "valueQuantity": {
        "value": 65,
        "unit": "%",
        "system": "http://unitsofmeasure.org",
        "code": "%"
    }
}

# Absent observation — covers dataAbsentReason
ABSENT = {
    **COMMON,
    "id": ABSENT_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">BMI percentile not performed</div>"
    },
    "effectiveDateTime": "2024-02-01T08:00:00Z",
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

PROVENANCE = {
    "resourceType": "Provenance",
    "id": PROV_ID,
    "target": [{"reference": f"Observation/{NORMAL_ID}"}],
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
        await upsert(conn, "Observation", NORMAL_ID, NORMAL)
        await upsert(conn, "Observation", ABSENT_ID, ABSENT)
        await upsert(conn, "Provenance", PROV_ID, PROVENANCE)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
