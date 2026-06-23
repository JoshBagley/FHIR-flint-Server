from typing import Dict, List, Any, Tuple

from app.capability import register_resource
from app.models.clinical import Patient, Observation, Condition, Encounter, AllergyIntolerance, Immunization
from app.routes.resource_factory import create_resource_router


def _patient_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
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
    return base, extra


def _encounter_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", qp['patient']))
    if 'class' in qp:
        extra.append(("data->'class'->>'code' = ??", qp['class']))
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


patient_router = create_resource_router("Patient", Patient, _patient_search_hook)
observation_router = create_resource_router("Observation", Observation, _observation_search_hook)
condition_router = create_resource_router("Condition", Condition, _condition_search_hook)
encounter_router = create_resource_router("Encounter", Encounter, _encounter_search_hook)
allergy_router = create_resource_router("AllergyIntolerance", AllergyIntolerance, _allergy_search_hook)
immunization_router = create_resource_router("Immunization", Immunization, _immunization_search_hook)

register_resource({
    "type": "Patient",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "searchParam": [
        {"name": "family", "type": "string"},
        {"name": "given", "type": "string"},
        {"name": "birthdate", "type": "date"},
        {"name": "gender", "type": "token"},
        {"name": "identifier", "type": "token"},
        {"name": "name", "type": "string"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
})

register_resource({
    "type": "Observation",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "code", "type": "token"},
        {"name": "category", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
})

register_resource({
    "type": "Condition",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "clinical-status", "type": "token"},
        {"name": "category", "type": "token"},
        {"name": "code", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
})

register_resource({
    "type": "Encounter",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "class", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
})

register_resource({
    "type": "AllergyIntolerance",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "clinical-status", "type": "token"},
        {"name": "criticality", "type": "token"},
        {"name": "code", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
})

register_resource({
    "type": "Immunization",
    "interaction": [
        {"code": "read"}, {"code": "create"}, {"code": "update"},
        {"code": "delete"}, {"code": "search-type"}, {"code": "history-instance"},
    ],
    "versioning": "versioned",
    "readHistory": True,
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "vaccine-code", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "date", "type": "date"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
})

routers = [patient_router, observation_router, condition_router, encounter_router, allergy_router, immunization_router]
