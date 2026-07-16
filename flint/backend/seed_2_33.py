"""Seed US Core Observation Screening Assessment (section 2.33) for Alice.

Three PHQ-2 depression screening observations covering all must-support elements:
  - obs-alice-phq2-panel  : valueQuantity, hasMember
  - obs-alice-phq2-item1  : valueCodeableConcept
  - obs-alice-phq2-item2  : valueString, derivedFrom
"""
import asyncio
import json
import asyncpg

ALICE_ID = "3e7c75f4-d87c-4648-bff5-89a3c5adbdb1"
ENCOUNTER_ID = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"
PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"

PANEL_ID = "obs-alice-phq2-panel"
ITEM1_ID = "obs-alice-phq2-item1"
ITEM2_ID = "obs-alice-phq2-item2"
PROV_ID  = "prov-alice-phq2-panel"

SCREENING_CATEGORY = [
    {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "survey",
                "display": "Survey"
            }
        ],
        "text": "Survey"
    },
    {
        "coding": [
            {
                "system": "http://hl7.org/fhir/us/core/CodeSystem/us-core-category",
                "code": "cognitive-status",
                "display": "Cognitive Status"
            }
        ],
        "text": "Cognitive Status"
    }
]

COMMON = {
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation-screening-assessment"
        ]
    },
    "status": "final",
    "category": SCREENING_CATEGORY,
    "subject": {"reference": f"Patient/{ALICE_ID}"},
    "encounter": {"reference": f"Encounter/{ENCOUNTER_ID}"},
    "effectiveDateTime": "2024-01-15T08:00:00Z",
    "performer": [{"reference": f"Practitioner/{PRACTITIONER_ID}"}],
}

# PHQ-2 panel — covers: valueQuantity, hasMember, category:screening-assessment
PANEL = {
    **COMMON,
    "resourceType": "Observation",
    "id": PANEL_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">PHQ-2 Depression Screen total score: 0</div>"
    },
    "code": {
        "coding": [
            {
                "system": "http://loinc.org",
                "code": "55757-9",
                "display": "Patient Health Questionnaire 2 item (PHQ-2) [Reported]"
            }
        ],
        "text": "Patient Health Questionnaire 2 item (PHQ-2) [Reported]"
    },
    "valueQuantity": {
        "value": 0,
        "unit": "{score}",
        "system": "http://unitsofmeasure.org",
        "code": "{score}"
    },
    "hasMember": [
        {"reference": f"Observation/{ITEM1_ID}"},
        {"reference": f"Observation/{ITEM2_ID}"}
    ]
}

# PHQ-2 item 1 — covers: valueCodeableConcept
ITEM1 = {
    **COMMON,
    "resourceType": "Observation",
    "id": ITEM1_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Little interest or pleasure in doing things: Not at all</div>"
    },
    "code": {
        "coding": [
            {
                "system": "http://loinc.org",
                "code": "44250-9",
                "display": "Little interest or pleasure in doing things in last 2 weeks"
            }
        ],
        "text": "Little interest or pleasure in doing things in last 2 weeks"
    },
    "valueCodeableConcept": {
        "coding": [
            {
                "system": "http://loinc.org",
                "code": "LA6568-5",
                "display": "Not at all"
            }
        ],
        "text": "Not at all"
    }
}

# PHQ-2 item 2 — covers: valueString, derivedFrom
ITEM2 = {
    **COMMON,
    "resourceType": "Observation",
    "id": ITEM2_ID,
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Feeling down, depressed, or hopeless: Not at all</div>"
    },
    "code": {
        "coding": [
            {
                "system": "http://loinc.org",
                "code": "44255-8",
                "display": "Feeling down, depressed, or hopeless in last 2 weeks"
            }
        ],
        "text": "Feeling down, depressed, or hopeless in last 2 weeks"
    },
    "valueString": "Not at all",
    "derivedFrom": [
        {"reference": f"Observation/{ITEM1_ID}"}
    ]
}

PROVENANCE = {
    "resourceType": "Provenance",
    "id": PROV_ID,
    "target": [{"reference": f"Observation/{PANEL_ID}"}],
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
        await upsert(conn, "Observation", PANEL_ID, PANEL)
        await upsert(conn, "Observation", ITEM1_ID, ITEM1)
        await upsert(conn, "Observation", ITEM2_ID, ITEM2)
        await upsert(conn, "Provenance", PROV_ID, PROVENANCE)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
