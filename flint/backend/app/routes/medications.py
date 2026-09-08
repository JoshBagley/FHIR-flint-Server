import json
from typing import Any

from fastapi import HTTPException

from app import state
from app.capability import register_resource
from app.fhir_utils import _date_condition, _patient_ref, _token_condition
from app.models.medications import (
    DiagnosticReport,
    MedicationDispense,
    MedicationRequest,
    Procedure,
)
from app.routes.resource_factory import create_resource_router


async def _check_codings(coding_list: list[dict[str, Any]], field: str) -> None:
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

        def _find(concepts: list[dict], target: str) -> bool:
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


async def _medication_validate(data: dict[str, Any]) -> None:
    codings = (data.get("medicationCodeableConcept") or {}).get("coding", [])
    await _check_codings(codings, "MedicationRequest.medicationCodeableConcept")


def _medication_request_search_hook(qp: dict[str, str]) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    base: dict[str, Any] = {}
    extra: list[tuple[str, Any]] = []
    if 'status' in qp:
        vals = [v.strip() for v in qp['status'].split(',')]
        if len(vals) == 1:
            base['status'] = vals[0]
        else:
            extra.append(("status = ANY(??)", vals))
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", _patient_ref(qp['patient'])))
    if 'medication' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'medicationCodeableConcept'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['medication']
        ))
    if 'intent' in qp:
        vals = [v.strip() for v in qp['intent'].split(',')]
        if len(vals) == 1:
            extra.append(("data->>'intent' = ??", vals[0]))
        else:
            extra.append(("data->>'intent' = ANY(??)", vals))
    if 'authoredon' in qp:
        extra.append(_date_condition("data->>'authoredOn'", qp['authoredon']))
    return base, extra


def _procedure_search_hook(qp: dict[str, str]) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    base: dict[str, Any] = {}
    extra: list[tuple[str, Any]] = []
    if 'status' in qp:
        statuses = [s.strip() for s in qp['status'].split(',')]
        if len(statuses) == 1:
            extra.append(("data->>'status' = ??", statuses[0]))
        else:
            extra.append(("data->>'status' = ANY(??)", statuses))
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", _patient_ref(qp['patient'])))
    if 'code' in qp:
        extra.append(_token_condition("data->'code'->'coding'", qp['code']))
    if 'date' in qp:
        extra.append(_date_condition("data->>'performedDateTime'", qp['date']))
    return base, extra


def _diagnostic_report_search_hook(qp: dict[str, str]) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    base: dict[str, Any] = {}
    extra: list[tuple[str, Any]] = []
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", _patient_ref(qp['patient'])))
    if 'code' in qp:
        extra.append(_token_condition("data->'code'->'coding'", qp['code']))
    if 'category' in qp:
        cat_val = qp['category']
        if '|' in cat_val:
            sys_part, _, code_part = cat_val.partition('|')
            obj = {k: v for k, v in [("system", sys_part), ("code", code_part)] if v}
        else:
            obj = {"code": cat_val}
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'category', '[]'::jsonb)) cat WHERE cat->'coding' @> ??::jsonb)",
            json.dumps([obj])
        ))
    if 'date' in qp:
        extra.append(_date_condition("data->>'effectiveDateTime'", qp['date']))
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
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-medicationrequest",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "medication", "type": "token"},
        {"name": "intent", "type": "token"},
        {"name": "authoredon", "type": "date"},
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
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-procedure",
    ],
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
    "searchRevInclude": ["Provenance:target"],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-diagnosticreport-lab",
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-diagnosticreport-note",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "code", "type": "token"},
        {"name": "category", "type": "token"},
        {"name": "date", "type": "date"},
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

def _medication_dispense_search_hook(qp: dict[str, str]) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    base: dict[str, Any] = {}
    extra: list[tuple[str, Any]] = []
    if 'status' in qp:
        base['status'] = qp['status']
    if 'patient' in qp:
        extra.append(("data->'subject'->>'reference' = ??", _patient_ref(qp['patient'])))
    if 'type' in qp:
        type_vals = [v.strip() for v in qp['type'].split(',')]
        if len(type_vals) == 1:
            extra.append(_token_condition("data->'type'->'coding'", type_vals[0]))
        else:
            codes = [v.partition('|')[2] if '|' in v else v for v in type_vals]
            extra.append((
                "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'type'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ANY(??))",
                codes
            ))
    return base, extra


medication_dispense_router = create_resource_router("MedicationDispense", MedicationDispense, _medication_dispense_search_hook)

register_resource({
    "type": "MedicationDispense",
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
    "searchRevInclude": ["Provenance:target"],
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-medicationdispense",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "type", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_revinclude", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

routers = [medication_request_router, procedure_router, diagnostic_report_router, medication_dispense_router]
