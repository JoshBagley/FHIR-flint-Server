"""Seed US Core QuestionnaireResponse (section 2.40) for Alice.

Resources:
  - questionnaire-phq9-alice  : Questionnaire (PHQ-9 depression screen)
  - qr-alice-phq9             : QuestionnaireResponse (completed, authored 2024-03-10)
  - prov-alice-qr-phq9        : Provenance

Must-support elements demonstrated:
  identifier, questionnaire + _questionnaire extension (questionnaireDisplay),
  status, subject, encounter, authored, author,
  item.linkId, item.answer.valueCoding, item.answer.valueDecimal,
  item.answer.valueString, item.item (nested group), item.answer.item
"""
import asyncio
import json
import asyncpg

ALICE_ID = "3e7c75f4-d87c-4648-bff5-89a3c5adbdb1"
ENCOUNTER_ID = "a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890"
PRACTITIONER_ID = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"

Q_ID     = "questionnaire-phq9-alice"
Q_URL    = "http://loinc.org/q/44249-1"
QR_ID    = "qr-alice-phq9"
PROV_ID  = "prov-alice-qr-phq9"

QUESTIONNAIRE = {
    "resourceType": "Questionnaire",
    "id": Q_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-questionnaireresponse"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">PHQ-9 Depression Screening</div>"
    },
    "url": Q_URL,
    "title": "Patient Health Questionnaire 9 item (PHQ-9)",
    "status": "active",
    "subjectType": ["Patient"],
    "code": [
        {
            "system": "http://loinc.org",
            "code": "44249-1",
            "display": "PHQ-9 quick depression assessment panel"
        }
    ],
    "item": [
        {
            "linkId": "44250-9",
            "text": "Little interest or pleasure in doing things in the past 2 weeks",
            "type": "choice",
            "answerOption": [
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6568-5", "display": "Not at all"}},
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6569-3", "display": "Several days"}},
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6570-1", "display": "More than half the days"}},
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6571-9", "display": "Nearly every day"}}
            ]
        },
        {
            "linkId": "44255-8",
            "text": "Feeling down, depressed, or hopeless in the past 2 weeks",
            "type": "choice",
            "answerOption": [
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6568-5", "display": "Not at all"}},
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6569-3", "display": "Several days"}},
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6570-1", "display": "More than half the days"}},
                {"valueCoding": {"system": "http://loinc.org", "code": "LA6571-9", "display": "Nearly every day"}}
            ]
        },
        {
            "linkId": "44261-6",
            "text": "PHQ-9 total score [Reported]",
            "type": "decimal"
        },
        {
            "linkId": "phq9-scoring",
            "text": "PHQ-9 Scoring Panel",
            "type": "group",
            "item": [
                {
                    "linkId": "phq9-severity",
                    "text": "Depression severity category",
                    "type": "string"
                }
            ]
        },
        {
            "linkId": "phq9-additional",
            "text": "Additional clinical notes",
            "type": "text"
        }
    ]
}

QUESTIONNAIRE_RESPONSE = {
    "resourceType": "QuestionnaireResponse",
    "id": QR_ID,
    "meta": {
        "profile": [
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-questionnaireresponse"
        ]
    },
    "text": {
        "status": "generated",
        "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\">PHQ-9 completed by Alice, 2024-03-10</div>"
    },
    "identifier": {
        "value": "QR-PHQ9-ALICE-001"
    },
    "questionnaire": Q_URL,
    "_questionnaire": {
        "extension": [
            {
                "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-extension-questionnaire-uri",
                "valueUri": Q_URL
            },
            {
                "url": "http://hl7.org/fhir/StructureDefinition/display",
                "valueString": "Patient Health Questionnaire 9 item (PHQ-9)"
            }
        ]
    },
    "status": "completed",
    "subject": {"reference": f"Patient/{ALICE_ID}"},
    "encounter": {"reference": f"Encounter/{ENCOUNTER_ID}"},
    "authored": "2024-03-10T10:00:00Z",
    "author": {"reference": f"Practitioner/{PRACTITIONER_ID}"},
    "item": [
        {
            "linkId": "44250-9",
            "text": "Little interest or pleasure in doing things in the past 2 weeks",
            "answer": [
                {
                    "valueCoding": {
                        "system": "http://loinc.org",
                        "code": "LA6569-3",
                        "display": "Several days"
                    }
                }
            ]
        },
        {
            "linkId": "44255-8",
            "text": "Feeling down, depressed, or hopeless in the past 2 weeks",
            "answer": [
                {
                    "valueCoding": {
                        "system": "http://loinc.org",
                        "code": "LA6568-5",
                        "display": "Not at all"
                    }
                }
            ]
        },
        {
            "linkId": "44261-6",
            "text": "PHQ-9 total score [Reported]",
            "answer": [
                {
                    "valueDecimal": 1
                }
            ]
        },
        {
            "linkId": "phq9-scoring",
            "text": "PHQ-9 Scoring Panel",
            "item": [
                {
                    "linkId": "phq9-severity",
                    "text": "Depression severity category",
                    "answer": [
                        {
                            "valueString": "Minimal"
                        }
                    ]
                }
            ]
        },
        {
            "linkId": "phq9-additional",
            "text": "Additional clinical notes",
            "answer": [
                {
                    "valueString": "Patient reports mild symptoms. No suicidal ideation.",
                    "item": [
                        {
                            "linkId": "phq9-followup",
                            "text": "Recommended follow-up",
                            "answer": [
                                {
                                    "valueString": "Rescreen in 3 months"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
}

PROVENANCE = {
    "resourceType": "Provenance",
    "id": PROV_ID,
    "target": [{"reference": f"QuestionnaireResponse/{QR_ID}"}],
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
        await upsert(conn, "Questionnaire", Q_ID, QUESTIONNAIRE)
        await upsert(conn, "QuestionnaireResponse", QR_ID, QUESTIONNAIRE_RESPONSE)
        await upsert(conn, "Provenance", PROV_ID, PROVENANCE)
        print("Done.")
    finally:
        await conn.close()


asyncio.run(main())
