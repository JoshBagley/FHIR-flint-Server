"""Seed US Core ServiceRequest (section 2.41) for Alice.

Resources:
  - sr-alice-cardiology-001      : ServiceRequest (cardiology referral, active, occurrenceDateTime)
  - prov-sr-alice-cardiology-001 : Provenance
  - sr-alice-physio-001          : ServiceRequest (physical therapy, completed, occurrencePeriod)
  - prov-sr-alice-physio-001     : Provenance
"""
import asyncio
import json
import asyncpg

ALICE_ID        = "3e7c75f4-d87c-4648-bff5-89a3c5adbdb1"
ENCOUNTER_ID    = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"
PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"
ORGANIZATION_ID = "7320bbf0-8257-4486-99d0-3d547a08ab46"
CONDITION_I10_ID = "d4e5f6a7-b8c9-0123-d4e5-f6a7b8c90123"

SR_ID    = "sr-alice-cardiology-001"
PROV_ID  = "prov-sr-alice-cardiology-001"
SR2_ID   = "sr-alice-physio-001"
PROV2_ID = "prov-sr-alice-physio-001"

SERVICE_REQUEST = {
    "resourceType": "ServiceRequest",
    "id": SR_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-servicerequest"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Referral to cardiology for hypertension evaluation</div>"
    },
    "identifier": [
        {
            "value": "SR-2024-001"
        }
    ],
    "status": "active",
    "intent": "order",
    "category": [
        {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "386053000",
                    "display": "Evaluation procedure"
                }
            ]
        }
    ],
    "priority": "routine",
    "code": {
        "coding": [
            {
                "system": "http://snomed.info/sct",
                "code": "306206005",
                "display": "Referral to service"
            }
        ],
        "text": "Referral to cardiology"
    },
    "subject": {"reference": f"Patient/{ALICE_ID}"},
    "encounter": {"reference": f"Encounter/{ENCOUNTER_ID}"},
    "occurrenceDateTime": "2024-04-15",
    "authoredOn": "2024-03-10",
    "requester": {"reference": f"Practitioner/{PRACTITIONER_ID}"},
    "performer": [
        {"reference": f"Organization/{ORGANIZATION_ID}"}
    ],
    "reasonCode": [
        {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/icd-10-cm",
                    "code": "I10",
                    "display": "Essential (primary) hypertension"
                }
            ]
        }
    ],
    "reasonReference": [
        {"reference": f"Condition/{CONDITION_I10_ID}"}
    ],
    "note": [
        {"text": "Referral for cardiology evaluation due to uncontrolled hypertension."}
    ],
    "patientInstruction": "Please schedule your cardiology appointment within 2 weeks."
}

# Second ServiceRequest: completed status + occurrencePeriod (covers 2.41.04 and 2.41.11)
SERVICE_REQUEST_2 = {
    "resourceType": "ServiceRequest",
    "id": SR2_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-servicerequest"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">Physical therapy evaluation - completed</div>"
    },
    "status": "completed",
    "intent": "order",
    "category": [
        {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "386053000",
                    "display": "Evaluation procedure"
                }
            ]
        }
    ],
    "code": {
        "coding": [
            {
                "system": "http://snomed.info/sct",
                "code": "91251008",
                "display": "Physical therapy procedure"
            }
        ],
        "text": "Physical therapy evaluation"
    },
    "subject": {"reference": f"Patient/{ALICE_ID}"},
    "occurrencePeriod": {
        "start": "2024-01-10",
        "end": "2024-01-24"
    },
    "authoredOn": "2024-01-08",
    "requester": {"reference": f"Practitioner/{PRACTITIONER_ID}"},
    "performer": [
        {"reference": f"Organization/{ORGANIZATION_ID}"}
    ],
    "reasonReference": [
        {"reference": f"Condition/{CONDITION_I10_ID}"}
    ],
    "note": [
        {"text": "Physical therapy evaluation completed successfully."}
    ]
}

PROVENANCE = {
    "resourceType": "Provenance",
    "id": PROV_ID,
    "target": [{"reference": f"ServiceRequest/{SR_ID}"}],
    "recorded": "2024-03-10T10:00:00Z",
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

PROVENANCE_2 = {
    "resourceType": "Provenance",
    "id": PROV2_ID,
    "target": [{"reference": f"ServiceRequest/{SR2_ID}"}],
    "recorded": "2024-01-08T09:00:00Z",
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
        await upsert(conn, "ServiceRequest", SR_ID, SERVICE_REQUEST)
        await upsert(conn, "Provenance", PROV_ID, PROVENANCE)
        await upsert(conn, "ServiceRequest", SR2_ID, SERVICE_REQUEST_2)
        await upsert(conn, "Provenance", PROV2_ID, PROVENANCE_2)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
