from typing import Dict, List, Any, Tuple

from fastapi import HTTPException
from app import state
from app.capability import register_resource
from app.models.medications import MedicationRequest, Procedure, DiagnosticReport
from app.routes.resource_factory import create_resource_router


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


async def _medication_validate(data: Dict[str, Any]) -> None:
    codings = (data.get("medicationCodeableConcept") or {}).get("coding", [])
    await _check_codings(codings, "MedicationRequest.medicationCodeableConcept")


def _medication_request_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", qp['patient']))
    if 'medication' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'medicationCodeableConcept'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['medication']
        ))
    if 'intent' in qp:
        extra.append(("data->>'intent' = ??", qp['intent']))
    return base, extra


def _procedure_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
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
    if 'date' in qp:
        extra.append(("data->>'performedDateTime' = ??", qp['date']))
    return base, extra


def _diagnostic_report_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
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


medication_request_router = create_resource_router(
    "MedicationRequest", MedicationRequest, _medication_request_search_hook,
    validate_hook=_medication_validate,
)
procedure_router = create_resource_router("Procedure", Procedure, _procedure_search_hook)
diagnostic_report_router = create_resource_router("DiagnosticReport", DiagnosticReport, _diagnostic_report_search_hook)

register_resource({
    "type": "MedicationRequest",
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
    "searchInclude": ["MedicationRequest:subject", "MedicationRequest:encounter"],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "medication", "type": "token"},
        {"name": "intent", "type": "token"},
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
    "type": "Procedure",
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
    "searchInclude": ["Procedure:subject", "Procedure:encounter"],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "code", "type": "token"},
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
    "type": "DiagnosticReport",
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
    "searchInclude": ["DiagnosticReport:subject", "DiagnosticReport:encounter"],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "code", "type": "token"},
        {"name": "category", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

routers = [medication_request_router, procedure_router, diagnostic_report_router]
