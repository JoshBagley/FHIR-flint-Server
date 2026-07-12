"""
Seed script for US Core 2.23 (Simple Observation) fixes:
1. Add dataAbsentReason to both blood pressure observations (satisfy Simple Observation invariant)
2. Add derivedFrom to BMI (must-support)
3. Add new survey observation with valueBoolean: true (must-support)
"""
import asyncio
import json
import asyncpg

PATIENT_ID = "3e7c75f4-d87c-4648-bff5-89a3c5adbdb1"
DR_JONES = "2c419e4d-0f6c-458b-b6a5-2eda3b3a9d6a"

DATA_ABSENT_REASON = {
    "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
        "code": "not-applicable",
        "display": "Not Applicable"
    }]
}

DERIVED_FROM_BMI = [
    {"reference": "Observation/obs-alice-height-001"},
    {"reference": "Observation/obs-alice-weight-001"}
]

NEW_BOOLEAN_OBS_ID = "obs-alice-food-insecurity-001"
NEW_BOOLEAN_OBS = {
    "resourceType": "Observation",
    "id": NEW_BOOLEAN_OBS_ID,
    "meta": {
        "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-simple-observation"]
    },
    "status": "final",
    "category": [{
        "coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "survey",
            "display": "Survey"
        }]
    }],
    "code": {
        "coding": [{
            "system": "http://loinc.org",
            "code": "88124-3",
            "display": "Food insecurity risk [HVS]"
        }]
    },
    "subject": {
        "reference": f"Patient/{PATIENT_ID}",
        "display": "Alice Smith"
    },
    "effectiveDateTime": "2024-01-15T08:00:00Z",
    "performer": [{
        "reference": f"Practitioner/{DR_JONES}",
        "display": "Dr. Jones"
    }],
    "valueBoolean": True
}


async def main():
    conn = await asyncpg.connect(
        host="postgres", port=5432,
        user="flint", password="flint_dev_password", database="flint"
    )

    # 1. Add dataAbsentReason to both BP observations
    for obs_id in ("a9b0c1d2-e3f4-5678-a9b0-c1d2e3f45678", "obs-alice-bp-001"):
        row = await conn.fetchrow("SELECT data FROM fhir_resources WHERE id = $1", obs_id)
        if not row:
            print(f"  WARN: {obs_id} not found")
            continue
        data = json.loads(row["data"]) if isinstance(row["data"], str) else dict(row["data"])
        data["dataAbsentReason"] = DATA_ABSENT_REASON
        await conn.execute(
            "UPDATE fhir_resources SET data = $1 WHERE id = $2",
            json.dumps(data), obs_id
        )
        # Update or insert version
        ver = await conn.fetchval(
            "SELECT MAX(version_number) FROM resource_versions WHERE resource_id = $1", obs_id
        )
        if ver is not None:
            await conn.execute(
                "INSERT INTO resource_versions (resource_id, version_number, data) "
                "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                obs_id, ver + 1, json.dumps(data)
            )
        print(f"  Updated BP obs {obs_id}: added dataAbsentReason")

    # 2. Add derivedFrom to BMI
    row = await conn.fetchrow("SELECT data FROM fhir_resources WHERE id = 'obs-alice-bmi-001'")
    if row:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else dict(row["data"])
        data["derivedFrom"] = DERIVED_FROM_BMI
        await conn.execute(
            "UPDATE fhir_resources SET data = $1 WHERE id = 'obs-alice-bmi-001'",
            json.dumps(data)
        )
        ver = await conn.fetchval(
            "SELECT MAX(version_number) FROM resource_versions WHERE resource_id = 'obs-alice-bmi-001'"
        )
        if ver is not None:
            await conn.execute(
                "INSERT INTO resource_versions (resource_id, version_number, data) "
                "VALUES ('obs-alice-bmi-001', $1, $2) ON CONFLICT DO NOTHING",
                ver + 1, json.dumps(data)
            )
        print("  Updated obs-alice-bmi-001: added derivedFrom")
    else:
        print("  WARN: obs-alice-bmi-001 not found")

    # 3. Insert new boolean survey observation
    existing = await conn.fetchval(
        "SELECT id FROM fhir_resources WHERE id = $1", NEW_BOOLEAN_OBS_ID
    )
    if existing:
        await conn.execute(
            "UPDATE fhir_resources SET data = $1, status = 'final' WHERE id = $2",
            json.dumps(NEW_BOOLEAN_OBS), NEW_BOOLEAN_OBS_ID
        )
        print(f"  Updated {NEW_BOOLEAN_OBS_ID} (already existed)")
    else:
        await conn.execute(
            "INSERT INTO fhir_resources (id, resource_type, status, data) "
            "VALUES ($1, 'Observation', 'final', $2)",
            NEW_BOOLEAN_OBS_ID, json.dumps(NEW_BOOLEAN_OBS)
        )
        await conn.execute(
            "INSERT INTO resource_versions (resource_id, version_number, data) "
            "VALUES ($1, 1, $2)",
            NEW_BOOLEAN_OBS_ID, json.dumps(NEW_BOOLEAN_OBS)
        )
        print(f"  Inserted {NEW_BOOLEAN_OBS_ID} with valueBoolean: true")

    await conn.close()
    print("Done.")


asyncio.run(main())
