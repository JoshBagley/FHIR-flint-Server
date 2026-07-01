from typing import Dict, List, Any, Tuple

from fastapi import HTTPException, Body
from app import state
from app.capability import register_resource
from app.fhir_utils import _date_condition
from app.models.clinical import Patient, Observation, Condition, Encounter, AllergyIntolerance, Immunization
from app.routes.resource_factory import create_resource_router


# ---------------------------------------------------------------------------
# Shared helper: validate codings against complete local CodeSystems.
# Raises 422 only when a system is locally stored as content=complete and the
# code is explicitly absent. Unknown or stub/fragment systems are skipped.
# ---------------------------------------------------------------------------
async def _check_codings(coding_list: List[Dict[str, Any]], field: str) -> None:
    for coding in coding_list:
        system = coding.get("system")
        code = coding.get("code")
        if not system or not code:
            continue
        _, cs_results = await state.db.search_resources("CodeSystem", {"url": system})
        if not cs_results:
            continue
        cs = cs_results[0]
        if cs.get("content") != "complete":
            continue

        def _find(concepts: List[Dict], target: str) -> bool:
            for c in concepts:
                if c.get("code") == target:
                    return True
                if _find(c.get("concept", []), target):
                    return True
            return False

        if not _find(cs.get("concept", []), code):
            raise HTTPException(
                status_code=422,
                detail=f"Unknown code '{code}' in system '{system}' for {field}"
            )


# ---------------------------------------------------------------------------
# Search hooks
# ---------------------------------------------------------------------------

def _patient_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if '_id' in qp:
        extra.append(("data->>'id' = ??", qp['_id']))
    if 'name' in qp:
        base['name'] = qp['name']
    if 'family' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'name', '[]'::jsonb)) n WHERE n->>'family' ILIKE ??)",
            f"%{qp['family']}%"
        ))
    if 'given' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'name', '[]'::jsonb)) n, jsonb_array_elements_text(COALESCE(n->'given', '[]'::jsonb)) g WHERE g ILIKE ??)",
            f"%{qp['given']}%"
        ))
    if 'birthdate' in qp:
        extra.append(("data->>'birthDate' = ??", qp['birthdate']))
    if 'gender' in qp:
        extra.append(("data->>'gender' = ??", qp['gender']))
    if 'identifier' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'identifier', '[]'::jsonb)) id WHERE id->>'value' = ??)",
            qp['identifier']
        ))
    if 'telecom' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'telecom', '[]'::jsonb)) t WHERE t->>'value' ILIKE ??)",
            f"%{qp['telecom']}%"
        ))
    return base, extra


def _observation_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", qp['patient']))
    if 'code' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['code']
        ))
    if 'category' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'category', '[]'::jsonb)) cat, jsonb_array_elements(COALESCE(cat->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['category']
        ))
    if 'date' in qp:
        extra.append(_date_condition("data->>'effectiveDateTime'", qp['date']))
    return base, extra


def _condition_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", qp['patient']))
    if 'clinical-status' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'clinicalStatus'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['clinical-status']
        ))
    if 'category' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'category', '[]'::jsonb)) cat, jsonb_array_elements(COALESCE(cat->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['category']
        ))
    if 'code' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['code']
        ))
    if 'onset-date' in qp:
        extra.append(_date_condition("data->>'onsetDateTime'", qp['onset-date']))
    if 'recorded-date' in qp:
        extra.append(_date_condition("data->>'recordedDate'", qp['recorded-date']))
    return base, extra


def _encounter_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if '_id' in qp:
        extra.append(("data->>'id' = ??", qp['_id']))
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", qp['patient']))
    if 'class' in qp:
        extra.append(("data->'class'->>'code' = ??", qp['class']))
    if 'date' in qp:
        extra.append(_date_condition("data->'period'->>'start'", qp['date']))
    if 'identifier' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'identifier', '[]'::jsonb)) id WHERE id->>'value' = ??)",
            qp['identifier']
        ))
    if 'type' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'type', '[]'::jsonb)) t, jsonb_array_elements(COALESCE(t->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['type']
        ))
    return base, extra


def _allergy_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'patient' in qp:
        extra.append(("data->'patient'->>'reference' = ??", qp['patient']))
    if 'clinical-status' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'clinicalStatus'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['clinical-status']
        ))
    if 'criticality' in qp:
        extra.append(("data->>'criticality' = ??", qp['criticality']))
    if 'code' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['code']
        ))
    return base, extra


def _immunization_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'patient'->>'reference' = ??", qp['patient']))
    if 'vaccine-code' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'vaccineCode'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['vaccine-code']
        ))
    if 'date' in qp:
        extra.append(("data->>'occurrenceDateTime' = ??", qp['date']))
    return base, extra


# ---------------------------------------------------------------------------
# Validate hooks
# ---------------------------------------------------------------------------

async def _observation_validate(data: Dict[str, Any]) -> None:
    codings = (data.get("code") or {}).get("coding", [])
    await _check_codings(codings, "Observation.code")


async def _immunization_validate(data: Dict[str, Any]) -> None:
    codings = (data.get("vaccineCode") or {}).get("coding", [])
    await _check_codings(codings, "Immunization.vaccineCode")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

patient_router = create_resource_router("Patient", Patient, _patient_search_hook)
observation_router = create_resource_router(
    "Observation", Observation, _observation_search_hook,
    validate_hook=_observation_validate,
    include_config={"Observation:subject": ("subject", "Patient")},
)
condition_router = create_resource_router("Condition", Condition, _condition_search_hook)
encounter_router = create_resource_router("Encounter", Encounter, _encounter_search_hook)
allergy_router = create_resource_router("AllergyIntolerance", AllergyIntolerance, _allergy_search_hook)
immunization_router = create_resource_router(
    "Immunization", Immunization, _immunization_search_hook,
    validate_hook=_immunization_validate,
)


# ---------------------------------------------------------------------------
# Patient/$match — probabilistic patient matching
# ---------------------------------------------------------------------------

@patient_router.post("/Patient/$match")
async def patient_match(body: Dict[str, Any] = Body(...)):
    params = {p["name"]: p for p in body.get("parameter", [])}
    patient_data: Dict[str, Any] = params.get("resource", {}).get("resource") or {}
    if not patient_data:
        raise HTTPException(status_code=400, detail="Parameters.resource (Patient) is required")

    max_count = int(params.get("count", {}).get("valueInteger", 3))
    only_certain = bool(params.get("onlyCertainMatches", {}).get("valueBoolean", False))

    extra_pairs: List[Tuple[str, Any]] = []
    names = patient_data.get("name", [])
    if names and names[0].get("family"):
        extra_pairs.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'name', '[]'::jsonb)) n WHERE n->>'family' ILIKE ??)",
            f"%{names[0]['family']}%"
        ))
    identifiers = patient_data.get("identifier", [])
    if identifiers and identifiers[0].get("value"):
        extra_pairs.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'identifier', '[]'::jsonb)) id WHERE id->>'value' = ??)",
            identifiers[0]["value"]
        ))
    if patient_data.get("birthDate"):
        extra_pairs.append(("data->>'birthDate' = ??", patient_data["birthDate"]))

    if not extra_pairs:
        raise HTTPException(
            status_code=400,
            detail="Must supply at least one of: name, identifier, birthDate"
        )

    _, candidates = await state.db.search_resources_ex(
        "Patient", {}, extra_pairs, limit=max_count * 5, offset=0
    )

    def _score(candidate: Dict[str, Any]) -> float:
        s = 0.0
        for ident in identifiers:
            for ci in candidate.get("identifier", []):
                if ci.get("value") == ident.get("value"):
                    s += 0.5
        if patient_data.get("birthDate") and patient_data["birthDate"] == candidate.get("birthDate"):
            s += 0.3
        for n in names:
            for cn in candidate.get("name", []):
                if n.get("family", "").lower() == cn.get("family", "").lower():
                    s += 0.2
        return min(s, 1.0)

    def _grade(s: float) -> str:
        if s >= 0.8:
            return "certain"
        if s >= 0.5:
            return "probable"
        return "possible"

    entries = []
    for r in candidates:
        s = _score(r)
        if only_certain and s < 0.8:
            continue
        entries.append({
            "resource": r,
            "search": {
                "mode": "match",
                "score": round(s, 2),
                "extension": [{
                    "url": "http://hl7.org/fhir/StructureDefinition/match-grade",
                    "valueCode": _grade(s)
                }]
            }
        })

    entries.sort(key=lambda e: e["search"]["score"], reverse=True)
    entries = entries[:max_count]
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(entries),
        "entry": entries,
    }


# ---------------------------------------------------------------------------
# CapabilityStatement registrations
# ---------------------------------------------------------------------------

register_resource({
    "type": "Patient",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"}, {"code": "patch"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
        {"code": "history-type"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "conditionalCreate": True,
    "conditionalUpdate": True,
    "conditionalDelete": "multiple",
    "searchRevInclude": [
        "Observation:subject", "Condition:subject", "Encounter:subject",
        "AllergyIntolerance:patient", "Immunization:patient",
        "MedicationRequest:subject", "Procedure:subject", "DiagnosticReport:subject",
    ],
    "searchParam": [
        {"name": "_id", "type": "token"},
        {"name": "family", "type": "string"},
        {"name": "given", "type": "string"},
        {"name": "birthdate", "type": "date"},
        {"name": "gender", "type": "token"},
        {"name": "identifier", "type": "token"},
        {"name": "name", "type": "string"},
        {"name": "telecom", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_revinclude", "type": "string"},
    ],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient",
    ],
    "operation": [
        {"name": "match", "definition": "http://hl7.org/fhir/OperationDefinition/Patient-match"},
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
        {"name": "export", "definition": "http://hl7.org/fhir/uv/bulkdata/OperationDefinition/patient-export"},
    ],
})

register_resource({
    "type": "Observation",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"}, {"code": "patch"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
        {"code": "history-type"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "conditionalCreate": True,
    "conditionalUpdate": True,
    "conditionalDelete": "multiple",
    "searchInclude": ["Observation:subject", "Observation:encounter"],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation-lab",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "code", "type": "token"},
        {"name": "category", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "date", "type": "date"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

register_resource({
    "type": "Condition",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"}, {"code": "patch"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
        {"code": "history-type"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "conditionalCreate": True,
    "conditionalUpdate": True,
    "conditionalDelete": "multiple",
    "searchInclude": ["Condition:subject", "Condition:encounter"],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition-encounter-diagnosis",
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition-problems-health-concerns",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "clinical-status", "type": "token"},
        {"name": "category", "type": "token"},
        {"name": "code", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "onset-date", "type": "date"},
        {"name": "recorded-date", "type": "date"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

register_resource({
    "type": "Encounter",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"}, {"code": "patch"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
        {"code": "history-type"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "conditionalCreate": True,
    "conditionalUpdate": True,
    "conditionalDelete": "multiple",
    "searchInclude": ["Encounter:subject"],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-encounter",
    ],
    "searchRevInclude": [
        "Observation:encounter", "Condition:encounter", "MedicationRequest:encounter",
        "Procedure:encounter", "DiagnosticReport:encounter",
    ],
    "searchParam": [
        {"name": "_id", "type": "token"},
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "class", "type": "token"},
        {"name": "date", "type": "date"},
        {"name": "identifier", "type": "token"},
        {"name": "type", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
        {"name": "_revinclude", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

register_resource({
    "type": "AllergyIntolerance",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"}, {"code": "patch"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
        {"code": "history-type"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "conditionalCreate": True,
    "conditionalUpdate": True,
    "conditionalDelete": "multiple",
    "searchInclude": ["AllergyIntolerance:patient"],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-allergyintolerance",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "clinical-status", "type": "token"},
        {"name": "criticality", "type": "token"},
        {"name": "code", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

register_resource({
    "type": "Immunization",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"}, {"code": "patch"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
        {"code": "history-type"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "conditionalCreate": True,
    "conditionalUpdate": True,
    "conditionalDelete": "multiple",
    "searchInclude": ["Immunization:patient"],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-immunization",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "vaccine-code", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "date", "type": "date"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

routers = [patient_router, observation_router, condition_router, encounter_router, allergy_router, immunization_router]
