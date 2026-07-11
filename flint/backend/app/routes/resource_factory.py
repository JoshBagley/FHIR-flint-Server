"""
Generic FHIR resource router factory.
Generates standard CRUD + history + versioned read + audit routes for any resource type.
"""
from typing import Callable, Dict, List, Optional, Any, Tuple, Type, Set
from urllib.parse import parse_qs
import hashlib
import json
import logging

import aiohttp
import jsonpatch
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app import state
from app.fhir_utils import _check_etag, _bundle_links, _fhir_response, RESOURCE_COUNT

logger = logging.getLogger(__name__)

# SearchHook signature: (query_params_dict) -> (base_params, extra_condition_pairs)
SearchHook = Callable[
    [Dict[str, str]],
    Tuple[Dict[str, Any], List[Tuple[str, Any]]]
]

# ValidateHook: async callable receiving the resource dict; raises HTTPException to reject.
ValidateHook = Callable[[Dict[str, Any]], Any]

# IncludeConfig: maps _include param value → (reference_field_name, target_resource_type)
IncludeConfig = Dict[str, Tuple[str, str]]

# Global reference map used by _include and _revinclude across all resource types.
# Key: "{SourceType}:{searchParam}"  Value: (python_field, sql_json_path)
_INCLUDE_REFERENCE_MAP: Dict[str, Tuple[str, str]] = {
    "Observation:subject":           ("subject",       "data->'subject'->>'reference'"),
    "Observation:encounter":         ("encounter",     "data->'encounter'->>'reference'"),
    "Condition:subject":             ("subject",       "data->'subject'->>'reference'"),
    "Condition:encounter":           ("encounter",     "data->'encounter'->>'reference'"),
    "Encounter:subject":             ("subject",       "data->'subject'->>'reference'"),
    "AllergyIntolerance:patient":    ("patient",       "data->'patient'->>'reference'"),
    "Immunization:patient":          ("patient",       "data->'patient'->>'reference'"),
    "MedicationRequest:subject":     ("subject",       "data->'subject'->>'reference'"),
    "MedicationRequest:encounter":   ("encounter",     "data->'encounter'->>'reference'"),
    "Procedure:subject":             ("subject",       "data->'subject'->>'reference'"),
    "Procedure:encounter":           ("encounter",     "data->'encounter'->>'reference'"),
    "DiagnosticReport:subject":      ("subject",       "data->'subject'->>'reference'"),
    "DiagnosticReport:encounter":    ("encounter",     "data->'encounter'->>'reference'"),
    "PractitionerRole:practitioner": ("practitioner",  "data->'practitioner'->>'reference'"),
    "PractitionerRole:organization": ("organization",  "data->'organization'->>'reference'"),
    # Provenance.target is an array — sql_path is a full condition template (contains ??)
    "Provenance:target": ("target", "EXISTS (SELECT 1 FROM jsonb_array_elements(data->'target') t WHERE t->>'reference' = ANY(??))"),
}


# Maps resource types in the patient compartment to their SQL filter path and Python accessor.
# sql_path=None means the filter is on the resource's own 'id' field (Patient itself).
_PATIENT_COMPARTMENT: Dict[str, Tuple[Optional[str], Callable[[Dict[str, Any]], Optional[str]]]] = {
    "Patient":            (None,                                   lambda r: r.get("id")),
    "Observation":        ("data->'subject'->>'reference'",        lambda r: (r.get("subject") or {}).get("reference")),
    "Condition":          ("data->'subject'->>'reference'",        lambda r: (r.get("subject") or {}).get("reference")),
    "Encounter":          ("data->'subject'->>'reference'",        lambda r: (r.get("subject") or {}).get("reference")),
    "AllergyIntolerance": ("data->'patient'->>'reference'",        lambda r: (r.get("patient") or {}).get("reference")),
    "Immunization":       ("data->'patient'->>'reference'",        lambda r: (r.get("patient") or {}).get("reference")),
    "MedicationRequest":  ("data->'subject'->>'reference'",        lambda r: (r.get("subject") or {}).get("reference")),
    "Procedure":          ("data->'subject'->>'reference'",        lambda r: (r.get("subject") or {}).get("reference")),
    "DiagnosticReport":   ("data->'subject'->>'reference'",        lambda r: (r.get("subject") or {}).get("reference")),
}


# ---------------------------------------------------------------------------
# _has reverse-chained search tables
# ---------------------------------------------------------------------------

# Maps (LinkedType, refParam) -> SQL path in linked resource referencing the outer resource.
_HAS_BACK_REF: Dict[Tuple[str, str], str] = {
    ("Observation",        "patient"):      "lnk.data->'subject'->>'reference'",
    ("Observation",        "subject"):      "lnk.data->'subject'->>'reference'",
    ("Observation",        "encounter"):    "lnk.data->'encounter'->>'reference'",
    ("Condition",          "patient"):      "lnk.data->'subject'->>'reference'",
    ("Condition",          "subject"):      "lnk.data->'subject'->>'reference'",
    ("Condition",          "encounter"):    "lnk.data->'encounter'->>'reference'",
    ("Encounter",          "patient"):      "lnk.data->'subject'->>'reference'",
    ("Encounter",          "subject"):      "lnk.data->'subject'->>'reference'",
    ("AllergyIntolerance", "patient"):      "lnk.data->'patient'->>'reference'",
    ("Immunization",       "patient"):      "lnk.data->'patient'->>'reference'",
    ("MedicationRequest",  "patient"):      "lnk.data->'subject'->>'reference'",
    ("MedicationRequest",  "subject"):      "lnk.data->'subject'->>'reference'",
    ("MedicationRequest",  "encounter"):    "lnk.data->'encounter'->>'reference'",
    ("Procedure",          "patient"):      "lnk.data->'subject'->>'reference'",
    ("Procedure",          "subject"):      "lnk.data->'subject'->>'reference'",
    ("Procedure",          "encounter"):    "lnk.data->'encounter'->>'reference'",
    ("DiagnosticReport",   "patient"):      "lnk.data->'subject'->>'reference'",
    ("DiagnosticReport",   "subject"):      "lnk.data->'subject'->>'reference'",
    ("DiagnosticReport",   "encounter"):    "lnk.data->'encounter'->>'reference'",
}

# Maps (LinkedType, searchParam) -> SQL condition with ?? placeholder (lnk. prefix).
_HAS_CONDITION: Dict[Tuple[str, str], str] = {
    ("Observation",        "code"):            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("Observation",        "category"):        "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'category', '[]'::jsonb)) cat, jsonb_array_elements(COALESCE(cat->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("Observation",        "status"):          "lnk.data->>'status' = ??",
    ("Condition",          "code"):            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("Condition",          "category"):        "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'category', '[]'::jsonb)) cat, jsonb_array_elements(COALESCE(cat->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("Condition",          "clinical-status"): "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'clinicalStatus'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("Encounter",          "status"):          "lnk.data->>'status' = ??",
    ("Encounter",          "type"):            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'type', '[]'::jsonb)) t, jsonb_array_elements(COALESCE(t->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("AllergyIntolerance", "code"):            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("AllergyIntolerance", "clinical-status"): "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'clinicalStatus'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("Immunization",       "status"):          "lnk.data->>'status' = ??",
    ("Immunization",       "vaccine-code"):    "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'vaccineCode'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("MedicationRequest",  "status"):          "lnk.data->>'status' = ??",
    ("Procedure",          "code"):            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("Procedure",          "status"):          "lnk.data->>'status' = ??",
    ("DiagnosticReport",   "code"):            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(lnk.data->'code'->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
    ("DiagnosticReport",   "status"):          "lnk.data->>'status' = ??",
}


# ---------------------------------------------------------------------------
# Chained search tables
# ---------------------------------------------------------------------------

# Maps (SourceType, refParam) -> (targetType, sql_ref_path_in_source).
_CHAIN_REF: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("Observation",        "patient"):      ("Patient",      "data->'subject'->>'reference'"),
    ("Observation",        "subject"):      ("Patient",      "data->'subject'->>'reference'"),
    ("Observation",        "encounter"):    ("Encounter",    "data->'encounter'->>'reference'"),
    ("Condition",          "patient"):      ("Patient",      "data->'subject'->>'reference'"),
    ("Condition",          "subject"):      ("Patient",      "data->'subject'->>'reference'"),
    ("Condition",          "encounter"):    ("Encounter",    "data->'encounter'->>'reference'"),
    ("Encounter",          "patient"):      ("Patient",      "data->'subject'->>'reference'"),
    ("Encounter",          "subject"):      ("Patient",      "data->'subject'->>'reference'"),
    ("AllergyIntolerance", "patient"):      ("Patient",      "data->'patient'->>'reference'"),
    ("Immunization",       "patient"):      ("Patient",      "data->'patient'->>'reference'"),
    ("MedicationRequest",  "patient"):      ("Patient",      "data->'subject'->>'reference'"),
    ("MedicationRequest",  "subject"):      ("Patient",      "data->'subject'->>'reference'"),
    ("MedicationRequest",  "encounter"):    ("Encounter",    "data->'encounter'->>'reference'"),
    ("Procedure",          "patient"):      ("Patient",      "data->'subject'->>'reference'"),
    ("Procedure",          "subject"):      ("Patient",      "data->'subject'->>'reference'"),
    ("Procedure",          "encounter"):    ("Encounter",    "data->'encounter'->>'reference'"),
    ("DiagnosticReport",   "patient"):      ("Patient",      "data->'subject'->>'reference'"),
    ("DiagnosticReport",   "subject"):      ("Patient",      "data->'subject'->>'reference'"),
    ("DiagnosticReport",   "encounter"):    ("Encounter",    "data->'encounter'->>'reference'"),
    ("PractitionerRole",   "practitioner"): ("Practitioner", "data->'practitioner'->>'reference'"),
    ("PractitionerRole",   "organization"): ("Organization", "data->'organization'->>'reference'"),
}

# Maps (targetType, targetSearchParam) -> (sql_condition_with_??, value_transform).
# sql_condition uses tgt. prefix; value_transform is applied to the raw param value before binding.
_CHAIN_TARGET_CONDITION: Dict[Tuple[str, str], Tuple[str, Callable[[str], str]]] = {
    ("Patient",      "name"):       ("EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(tgt.data->'name', '[]'::jsonb)) n WHERE n->>'family' ILIKE ?? OR n->>'text' ILIKE ??)", lambda v: f"%{v}%"),
    ("Patient",      "family"):     ("EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(tgt.data->'name', '[]'::jsonb)) n WHERE n->>'family' ILIKE ??)", lambda v: f"%{v}%"),
    ("Patient",      "given"):      ("EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(tgt.data->'name', '[]'::jsonb)) n, jsonb_array_elements_text(COALESCE(n->'given', '[]'::jsonb)) g WHERE g ILIKE ??)", lambda v: f"%{v}%"),
    ("Patient",      "birthdate"):  ("tgt.data->>'birthDate' = ??", lambda v: v),
    ("Patient",      "gender"):     ("tgt.data->>'gender' = ??",    lambda v: v),
    ("Patient",      "identifier"): ("EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(tgt.data->'identifier', '[]'::jsonb)) id WHERE id->>'value' = ??)", lambda v: v),
    ("Encounter",    "status"):     ("tgt.data->>'status' = ??",    lambda v: v),
    ("Practitioner", "name"):       ("EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(tgt.data->'name', '[]'::jsonb)) n WHERE n->>'family' ILIKE ?? OR n->>'text' ILIKE ??)", lambda v: f"%{v}%"),
    ("Practitioner", "family"):     ("EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(tgt.data->'name', '[]'::jsonb)) n WHERE n->>'family' ILIKE ??)", lambda v: f"%{v}%"),
    ("Organization", "name"):       ("tgt.data->>'name' ILIKE ??",  lambda v: f"%{v}%"),
}


def _build_has_conditions(rt: str, query_params: Dict[str, str]) -> List[Tuple[str, Any]]:
    """Build EXISTS conditions for _has reverse-chained search params."""
    pairs: List[Tuple[str, Any]] = []
    for key, value in query_params.items():
        if not key.startswith("_has:"):
            continue
        parts = key[5:].split(":", 2)
        if len(parts) != 3:
            continue
        linked_type, ref_param, search_param = parts
        back_ref = _HAS_BACK_REF.get((linked_type, ref_param))
        cond = _HAS_CONDITION.get((linked_type, search_param))
        if not back_ref or not cond:
            continue
        sql = (
            f"EXISTS (SELECT 1 FROM fhir_resources AS lnk"
            f" WHERE lnk.resource_type = '{linked_type}'"
            f" AND lnk.archived = FALSE"
            f" AND {back_ref} = CONCAT('{rt}/', fhir_resources.data->>'id')"
            f" AND {cond})"
        )
        pairs.append((sql, value))
    return pairs


def _build_chained_conditions(rt: str, query_params: Dict[str, str]) -> List[Tuple[str, Any]]:
    """Build EXISTS conditions for chained search params (e.g., patient.family=Jones)."""
    pairs: List[Tuple[str, Any]] = []
    for key, value in query_params.items():
        if key.startswith("_") or "." not in key:
            continue
        ref_param, target_search_param = key.split(".", 1)
        chain_info = _CHAIN_REF.get((rt, ref_param))
        if not chain_info:
            continue
        target_type, src_ref_path = chain_info
        target_cond_info = _CHAIN_TARGET_CONDITION.get((target_type, target_search_param))
        if not target_cond_info:
            continue
        target_cond, value_transform = target_cond_info
        sql = (
            f"EXISTS (SELECT 1 FROM fhir_resources AS tgt"
            f" WHERE tgt.resource_type = '{target_type}'"
            f" AND tgt.archived = FALSE"
            f" AND fhir_resources.{src_ref_path} = CONCAT('{target_type}/', tgt.data->>'id')"
            f" AND {target_cond})"
        )
        pairs.append((sql, value_transform(value)))
    return pairs


# ---------------------------------------------------------------------------
# US Core must-support element checks (P2.6)
# ---------------------------------------------------------------------------

_US_CORE_MUST_SUPPORT: Dict[str, List[Tuple[str, Callable[[Dict[str, Any]], bool]]]] = {
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient": [
        ("Patient.identifier",            lambda r: bool(r.get("identifier"))),
        ("Patient.identifier.system",     lambda r: all(bool(i.get("system")) for i in (r.get("identifier") or []))),
        ("Patient.identifier.value",      lambda r: all(bool(i.get("value"))  for i in (r.get("identifier") or []))),
        ("Patient.name",                  lambda r: bool(r.get("name"))),
        ("Patient.name.family or .given", lambda r: any(n.get("family") or n.get("given") for n in (r.get("name") or []))),
        ("Patient.gender",                lambda r: bool(r.get("gender"))),
        ("Patient.birthDate",             lambda r: bool(r.get("birthDate"))),
    ],
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation-lab": [
        ("Observation.status",    lambda r: bool(r.get("status"))),
        ("Observation.category",  lambda r: bool(r.get("category"))),
        ("Observation.code",      lambda r: bool(r.get("code"))),
        ("Observation.subject",   lambda r: bool(r.get("subject"))),
        ("Observation.effective[x]", lambda r: bool(r.get("effectiveDateTime") or r.get("effectivePeriod") or r.get("effectiveInstant"))),
        ("Observation.value[x] or dataAbsentReason", lambda r: bool(
            r.get("valueQuantity") or r.get("valueCodeableConcept") or r.get("valueString") or
            r.get("valueBoolean") is not None or r.get("valueInteger") is not None or
            r.get("valueRange") or r.get("valueSampledData") or r.get("dataAbsentReason")
        )),
    ],
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition-problems-health-concerns": [
        ("Condition.clinicalStatus", lambda r: bool(r.get("clinicalStatus"))),
        ("Condition.category",       lambda r: bool(r.get("category"))),
        ("Condition.code",           lambda r: bool(r.get("code"))),
        ("Condition.subject",        lambda r: bool(r.get("subject"))),
    ],
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-allergyintolerance": [
        ("AllergyIntolerance.clinicalStatus", lambda r: bool(r.get("clinicalStatus"))),
        ("AllergyIntolerance.code",           lambda r: bool(r.get("code"))),
        ("AllergyIntolerance.patient",        lambda r: bool(r.get("patient"))),
    ],
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-immunization": [
        ("Immunization.status",       lambda r: bool(r.get("status"))),
        ("Immunization.vaccineCode",  lambda r: bool(r.get("vaccineCode"))),
        ("Immunization.patient",      lambda r: bool(r.get("patient"))),
        ("Immunization.occurrence[x]", lambda r: bool(r.get("occurrenceDateTime") or r.get("occurrenceString"))),
    ],
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-encounter": [
        ("Encounter.status",  lambda r: bool(r.get("status"))),
        ("Encounter.class",   lambda r: bool(r.get("class"))),
        ("Encounter.type",    lambda r: bool(r.get("type"))),
        ("Encounter.subject", lambda r: bool(r.get("subject"))),
    ],
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-medicationrequest": [
        ("MedicationRequest.status",        lambda r: bool(r.get("status"))),
        ("MedicationRequest.intent",        lambda r: bool(r.get("intent"))),
        ("MedicationRequest.medication[x]", lambda r: bool(r.get("medicationCodeableConcept") or r.get("medicationReference"))),
        ("MedicationRequest.subject",       lambda r: bool(r.get("subject"))),
        ("MedicationRequest.authoredOn",    lambda r: bool(r.get("authoredOn"))),
        ("MedicationRequest.requester",     lambda r: bool(r.get("requester"))),
    ],
}


def _owns_resource(rt: str, resource: Dict[str, Any], patient_id: str) -> bool:
    """Return True if the resource belongs to the given patient."""
    compartment = _PATIENT_COMPARTMENT.get(rt)
    if not compartment:
        return True
    _, accessor = compartment
    actual = accessor(resource)
    return actual == patient_id if rt == "Patient" else actual == f"Patient/{patient_id}"


# Resource types scoped to the clinician's organization membership.
_ORG_SCOPED: Set[str] = {"Organization", "Practitioner", "PractitionerRole", "Location"}


async def _get_panel_patient_refs(clinician_id: str) -> List[str]:
    gp_filter = json.dumps([{"reference": f"Practitioner/{clinician_id}"}])
    _, results = await state.db.search_resources_ex(
        "Patient", {}, [("data->'generalPractitioner' @> ??::jsonb", gp_filter)],
        limit=10000, offset=0
    )
    return [f"Patient/{r['id']}" for r in results if r.get("id")]


async def _check_clinician_panel(rt: str, resource: Dict[str, Any], clinician_id: str) -> None:
    """Raise 403 if the clinician is not authorized for the patient linked to this resource."""
    if rt == "Patient":
        gp_list = resource.get("generalPractitioner") or []
        gp_ref = f"Practitioner/{clinician_id}"
        if not any(isinstance(gp, dict) and gp.get("reference") == gp_ref for gp in gp_list):
            raise HTTPException(status_code=403, detail="This patient is not in your panel")
    else:
        compartment = _PATIENT_COMPARTMENT.get(rt)
        if not compartment:
            return
        _, accessor = compartment
        patient_ref = accessor(resource)
        if not patient_ref or not patient_ref.startswith("Patient/"):
            raise HTTPException(status_code=403, detail="Cannot determine patient context")
        patient = await state.db.get_resource(patient_ref[len("Patient/"):])
        if not patient:
            raise HTTPException(status_code=403, detail="Patient not found")
        gp_list = patient.get("generalPractitioner") or []
        gp_ref = f"Practitioner/{clinician_id}"
        if not any(isinstance(gp, dict) and gp.get("reference") == gp_ref for gp in gp_list):
            raise HTTPException(status_code=403, detail="This patient is not in your panel")


async def _get_clinician_org_context(clinician_id: str) -> Dict[str, List[str]]:
    """Return org_refs and loc_refs from the clinician's PractitionerRoles."""
    _, roles = await state.db.search_resources_ex(
        "PractitionerRole", {},
        [("data->'practitioner'->>'reference' = ??", f"Practitioner/{clinician_id}")],
        limit=100, offset=0,
    )
    org_refs: List[str] = []
    loc_refs: List[str] = []
    for role in roles:
        org_ref = (role.get("organization") or {}).get("reference")
        if org_ref:
            org_refs.append(org_ref)
        for loc in role.get("location") or []:
            ref = loc.get("reference")
            if ref:
                loc_refs.append(ref)
    return {"org_refs": list(set(org_refs)), "loc_refs": list(set(loc_refs))}


async def _get_org_practitioner_refs(org_refs: List[str]) -> List[str]:
    """Return all practitioner refs with a PractitionerRole in any of the given orgs."""
    if not org_refs:
        return []
    _, roles = await state.db.search_resources_ex(
        "PractitionerRole", {},
        [("data->'organization'->>'reference' = ANY(??)", org_refs)],
        limit=10000, offset=0,
    )
    return list({(role.get("practitioner") or {}).get("reference") for role in roles} - {None})


async def _check_clinician_org_access(rt: str, resource: Dict[str, Any], clinician_id: str) -> None:
    """Raise 403 if the resource is outside the clinician's organization scope."""
    ctx = await _get_clinician_org_context(clinician_id)
    org_refs = ctx["org_refs"]
    if not org_refs:
        raise HTTPException(status_code=403, detail="You have no organization membership")
    resource_id = resource.get("id", "")
    if rt == "Organization":
        if f"Organization/{resource_id}" not in org_refs:
            raise HTTPException(status_code=403, detail="This organization is not accessible")
    elif rt == "PractitionerRole":
        role_org = (resource.get("organization") or {}).get("reference")
        if role_org not in org_refs:
            raise HTTPException(status_code=403, detail="This role is not in your organization")
    elif rt == "Location":
        if f"Location/{resource_id}" not in ctx["loc_refs"]:
            mgmt_org = (resource.get("managingOrganization") or {}).get("reference")
            if mgmt_org not in org_refs:
                raise HTTPException(status_code=403, detail="This location is not in your organization")
    elif rt == "Practitioner":
        prac_refs = await _get_org_practitioner_refs(org_refs)
        if f"Practitioner/{resource_id}" not in prac_refs:
            raise HTTPException(status_code=403, detail="This practitioner is not in your organization")


def create_resource_router(
    resource_type: str,
    model_class: Type[BaseModel],
    search_hook: Optional[SearchHook] = None,
    allow_archive: bool = False,
    validate_hook: Optional[ValidateHook] = None,
    include_config: Optional[IncludeConfig] = None,
) -> APIRouter:
    router = APIRouter(tags=[resource_type])
    rt = resource_type

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _run_search(qp: Dict[str, str], limit: int, offset: int) -> Tuple[int, List[Dict]]:
        base_params: Dict[str, Any] = {}
        extra_pairs: List[Tuple[str, Any]] = []
        if search_hook:
            base_params, extra_pairs = search_hook(qp)
        return await state.db.search_resources_ex(rt, base_params, extra_pairs, limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # Standard CRUD
    # ------------------------------------------------------------------

    async def _create(request: Request, resource: model_class):
        patient_id = getattr(request.state, "fhir_patient_id", None)
        if patient_id and rt in _PATIENT_COMPARTMENT:
            data_check = resource.model_dump(exclude_none=True, by_alias=True)
            if rt == "Patient" or not _owns_resource(rt, data_check, patient_id):
                raise HTTPException(status_code=403, detail="patient-scoped token may only create resources for their own patient record")
        clinician_id = getattr(request.state, "fhir_clinician_id", None)
        if clinician_id and rt in _PATIENT_COMPARTMENT and rt != "Patient" and not patient_id:
            await _check_clinician_panel(rt, resource.model_dump(exclude_none=True, by_alias=True), clinician_id)
        # Conditional create: If-None-Exist header
        if_none_exist = request.headers.get("If-None-Exist")
        if if_none_exist and search_hook:
            qp = {k: v[0] for k, v in parse_qs(if_none_exist).items()}
            total, results = await _run_search(qp, limit=2, offset=0)
            if total == 1:
                return _fhir_response(results[0], status_code=200, request=request)
            if total > 1:
                raise HTTPException(status_code=412, detail="Conditional create matched multiple resources")

        data = resource.model_dump(exclude_none=True, by_alias=True)
        data['resourceType'] = rt
        if validate_hook:
            await validate_hook(data)
        resource_id = await state.db.create_resource(rt, data)
        await state.search_engine.index_resource(data)
        await state.cache.invalidate_pattern(f"{rt}:*")
        RESOURCE_COUNT.labels(resource_type=rt, operation="create").inc()
        created = await state.db.get_resource(resource_id)
        return _fhir_response(created, status_code=201, extra_headers={"Location": f"/{rt}/{resource_id}/_history/1"}, request=request)

    async def _read(resource_id: str, request: Request):
        cache_key = f"{rt}:{resource_id}:latest"
        cached = await state.cache.get(cache_key)
        resource = cached or await state.db.get_resource(resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        if not cached:
            await state.cache.set(cache_key, resource)
        patient_id = getattr(request.state, "fhir_patient_id", None)
        if patient_id and rt in _PATIENT_COMPARTMENT and not _owns_resource(rt, resource, patient_id):
            raise HTTPException(status_code=403, detail="Access to this resource is not permitted")
        clinician_id = getattr(request.state, "fhir_clinician_id", None)
        if clinician_id and rt in _PATIENT_COMPARTMENT and not patient_id:
            await _check_clinician_panel(rt, resource, clinician_id)
        if clinician_id and rt in _ORG_SCOPED:
            await _check_clinician_org_access(rt, resource, clinician_id)
        return _fhir_response(resource)

    async def _update(request: Request, resource_id: str, resource: model_class):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        patient_id = getattr(request.state, "fhir_patient_id", None)
        if patient_id and rt in _PATIENT_COMPARTMENT and not _owns_resource(rt, existing, patient_id):
            raise HTTPException(status_code=403, detail="Access to this resource is not permitted")
        clinician_id = getattr(request.state, "fhir_clinician_id", None)
        if clinician_id and rt in _PATIENT_COMPARTMENT and not patient_id:
            await _check_clinician_panel(rt, existing, clinician_id)
        _check_etag(request, existing)
        data = resource.model_dump(exclude_none=True, by_alias=True)
        data['id'] = resource_id
        data['resourceType'] = rt
        if validate_hook:
            await validate_hook(data)
        await state.db.update_resource(resource_id, data)
        await state.search_engine.index_resource(data)
        await state.cache.invalidate_pattern(f"{rt}:{resource_id}:*")
        RESOURCE_COUNT.labels(resource_type=rt, operation="update").inc()
        return _fhir_response(await state.db.get_resource(resource_id), request=request)

    async def _delete(resource_id: str, request: Request):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        patient_id = getattr(request.state, "fhir_patient_id", None)
        if patient_id and rt in _PATIENT_COMPARTMENT:
            if rt == "Patient" or not _owns_resource(rt, existing, patient_id):
                raise HTTPException(status_code=403, detail="Access to this resource is not permitted")
        clinician_id = getattr(request.state, "fhir_clinician_id", None)
        if clinician_id and rt in _PATIENT_COMPARTMENT and not patient_id:
            await _check_clinician_panel(rt, existing, clinician_id)
        await state.db.delete_resource(resource_id)
        await state.search_engine.delete_resource(resource_id)
        await state.cache.invalidate_pattern(f"{rt}:{resource_id}:*")
        await state.cache.invalidate_pattern(f"{rt}:*")

    # ------------------------------------------------------------------
    # P2.7 — JSON Patch
    # ------------------------------------------------------------------

    async def _patch(request: Request, resource_id: str, body: List[Dict[str, Any]] = Body(...)):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        patient_id = getattr(request.state, "fhir_patient_id", None)
        if patient_id and rt in _PATIENT_COMPARTMENT and not _owns_resource(rt, existing, patient_id):
            raise HTTPException(status_code=403, detail="Access to this resource is not permitted")
        clinician_id = getattr(request.state, "fhir_clinician_id", None)
        if clinician_id and rt in _PATIENT_COMPARTMENT and not patient_id:
            await _check_clinician_panel(rt, existing, clinician_id)
        _check_etag(request, existing)
        try:
            patched = jsonpatch.JsonPatch(body).apply(existing)
        except (jsonpatch.JsonPatchException, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid patch operation: {exc}")
        try:
            validated = model_class(**patched)
            data = validated.model_dump(exclude_none=True, by_alias=True)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=f"Patch result is invalid: {exc.errors()}")
        data['id'] = resource_id
        data['resourceType'] = rt
        if validate_hook:
            await validate_hook(data)
        await state.db.update_resource(resource_id, data)
        await state.search_engine.index_resource(data)
        await state.cache.invalidate_pattern(f"{rt}:{resource_id}:*")
        RESOURCE_COUNT.labels(resource_type=rt, operation="patch").inc()
        return _fhir_response(await state.db.get_resource(resource_id), request=request)

    # ------------------------------------------------------------------
    # P2.2 — Conditional update / delete
    # ------------------------------------------------------------------

    async def _conditional_update(request: Request, resource: model_class):
        qp = {k: v for k, v in request.query_params.items() if not k.startswith('_')}
        if not qp:
            raise HTTPException(status_code=400, detail="Conditional update requires search parameters in the URL")
        total, results = await _run_search(dict(request.query_params), limit=2, offset=0)
        if total > 1:
            raise HTTPException(status_code=412, detail="Conditional update matched multiple resources")

        if total == 1:
            resource_id = results[0].get('id')
            _check_etag(request, results[0])
            data = resource.model_dump(exclude_none=True, by_alias=True)
            data['id'] = resource_id
            data['resourceType'] = rt
            if validate_hook:
                await validate_hook(data)
            await state.db.update_resource(resource_id, data)
            await state.search_engine.index_resource(data)
            await state.cache.invalidate_pattern(f"{rt}:{resource_id}:*")
            RESOURCE_COUNT.labels(resource_type=rt, operation="update").inc()
            return _fhir_response(await state.db.get_resource(resource_id), request=request)
        else:
            data = resource.model_dump(exclude_none=True, by_alias=True)
            data['resourceType'] = rt
            if validate_hook:
                await validate_hook(data)
            resource_id = await state.db.create_resource(rt, data)
            await state.search_engine.index_resource(data)
            await state.cache.invalidate_pattern(f"{rt}:*")
            RESOURCE_COUNT.labels(resource_type=rt, operation="create").inc()
            created = await state.db.get_resource(resource_id)
            return _fhir_response(created, status_code=201, extra_headers={"Location": f"/{rt}/{resource_id}/_history/1"}, request=request)

    async def _conditional_delete(request: Request):
        if not request.query_params:
            raise HTTPException(status_code=400, detail="Conditional delete requires search parameters in the URL")
        total, results = await _run_search(dict(request.query_params), limit=1000, offset=0)
        for r in results:
            rid = r.get('id')
            if rid:
                await state.db.delete_resource(rid)
                await state.search_engine.delete_resource(rid)
                await state.cache.invalidate_pattern(f"{rt}:{rid}:*")
        if results:
            await state.cache.invalidate_pattern(f"{rt}:*")

    # ------------------------------------------------------------------
    # Search (with _include support)
    # ------------------------------------------------------------------

    async def _search(
        request: Request,
        _count: int = Query(20, alias="_count", ge=1, le=1000),
        _offset: int = Query(0, alias="_offset", ge=0),
        _sort: Optional[str] = Query(None, alias="_sort"),
        _include: Optional[str] = Query(None, alias="_include"),
        _revinclude: Optional[str] = Query(None, alias="_revinclude"),
    ):
        base_params: Dict[str, Any] = {}
        extra_pairs: List[Tuple[str, Any]] = []
        if search_hook:
            base_params, extra_pairs = search_hook(dict(request.query_params))
        extra_pairs = list(extra_pairs) + _build_has_conditions(rt, dict(request.query_params)) + _build_chained_conditions(rt, dict(request.query_params))

        # Patient-context filtering: restrict results to the token's patient
        patient_id = getattr(request.state, "fhir_patient_id", None)
        if patient_id and rt in _PATIENT_COMPARTMENT:
            sql_path, _ = _PATIENT_COMPARTMENT[rt]
            if sql_path is None:
                extra_pairs = [("data->>'id' = ??", patient_id)] + list(extra_pairs)
            else:
                extra_pairs = [(f"{sql_path} = ??", f"Patient/{patient_id}")] + list(extra_pairs)

        # Option B — Clinician panel filtering: restrict results to the clinician's panel.
        # Patient: JSONB containment on generalPractitioner.
        # Clinical resources: restrict to patients in the panel via = ANY(panel_refs).
        clinician_id = getattr(request.state, "fhir_clinician_id", None)
        if clinician_id and rt in _PATIENT_COMPARTMENT and not patient_id:
            if rt == "Patient":
                gp_ref = json.dumps([{"reference": f"Practitioner/{clinician_id}"}])
                extra_pairs = [("data->'generalPractitioner' @> ??::jsonb", gp_ref)] + list(extra_pairs)
            else:
                sql_path, _ = _PATIENT_COMPARTMENT[rt]
                if sql_path:
                    panel_refs = await _get_panel_patient_refs(clinician_id)
                    if not panel_refs:
                        return {
                            "resourceType": "Bundle", "type": "searchset", "total": 0,
                            "link": _bundle_links(request, 0, _count, _offset), "entry": [],
                        }
                    extra_pairs = [(f"{sql_path} = ANY(??)", panel_refs)] + list(extra_pairs)

        # Org-scope filtering: restrict admin resources to the clinician's organization(s).
        if clinician_id and rt in _ORG_SCOPED:
            ctx = await _get_clinician_org_context(clinician_id)
            org_refs = ctx["org_refs"]
            if not org_refs:
                return {
                    "resourceType": "Bundle", "type": "searchset", "total": 0,
                    "link": _bundle_links(request, 0, _count, _offset), "entry": [],
                }
            if rt == "Organization":
                org_ids = [r.split("/")[-1] for r in org_refs]
                extra_pairs = [("data->>'id' = ANY(??)", org_ids)] + list(extra_pairs)
            elif rt == "PractitionerRole":
                extra_pairs = [("data->'organization'->>'reference' = ANY(??)", org_refs)] + list(extra_pairs)
            elif rt == "Practitioner":
                prac_refs = await _get_org_practitioner_refs(org_refs)
                if not prac_refs:
                    return {
                        "resourceType": "Bundle", "type": "searchset", "total": 0,
                        "link": _bundle_links(request, 0, _count, _offset), "entry": [],
                    }
                prac_ids = [r.split("/")[-1] for r in prac_refs]
                extra_pairs = [("data->>'id' = ANY(??)", prac_ids)] + list(extra_pairs)
            elif rt == "Location":
                # Locations explicitly listed in PractitionerRole OR managed by the org
                loc_ids = [r.split("/")[-1] for r in ctx["loc_refs"]]
                _, org_locs = await state.db.search_resources_ex(
                    "Location", {},
                    [("data->'managingOrganization'->>'reference' = ANY(??)", org_refs)],
                    limit=10000, offset=0,
                )
                loc_ids += [r.get("id") for r in org_locs if r.get("id")]
                loc_ids = list(set(filter(None, loc_ids)))
                if not loc_ids:
                    return {
                        "resourceType": "Bundle", "type": "searchset", "total": 0,
                        "link": _bundle_links(request, 0, _count, _offset), "entry": [],
                    }
                extra_pairs = [("data->>'id' = ANY(??)", loc_ids)] + list(extra_pairs)

        total, results = await state.db.search_resources_ex(
            rt, base_params, extra_pairs,
            limit=_count, offset=_offset, sort=_sort
        )
        entries: List[Dict[str, Any]] = [{"resource": r} for r in results]

        # _include: resolve forward references from the primary result set
        if _include and results:
            include_key = _include if ":" in _include else f"{rt}:{_include}"
            ref_info = _INCLUDE_REFERENCE_MAP.get(include_key)
            if not ref_info and include_config and _include in include_config:
                field, _ = include_config[_include]
                ref_info = (field, None)
            if ref_info:
                py_field = ref_info[0]
                seen: set = set()
                for r in results:
                    ref_obj = r.get(py_field, {})
                    if isinstance(ref_obj, dict):
                        ref_str = ref_obj.get("reference", "")
                        if ref_str:
                            rid = ref_str.split("/")[-1]
                            if rid and rid not in seen:
                                seen.add(rid)
                                included = await state.db.get_resource(rid)
                                if included:
                                    entries.append({"search": {"mode": "include"}, "resource": included})

        # _revinclude: find resources of another type that reference the primary results
        if _revinclude and results:
            rev_info = _INCLUDE_REFERENCE_MAP.get(_revinclude)
            if rev_info:
                _, sql_path = rev_info
                rev_type = _revinclude.split(":")[0]
                primary_refs = [f"{rt}/{r['id']}" for r in results if r.get("id")]
                if primary_refs:
                    rev_condition = sql_path if "??" in sql_path else f"{sql_path} = ANY(??)"
                    _, rev_results = await state.db.search_resources_ex(
                        rev_type, {}, [(rev_condition, primary_refs)],
                        limit=min(_count * 10, 1000), offset=0
                    )
                    seen_rev: set = set()
                    for r in rev_results:
                        rid = r.get("id")
                        if rid and rid not in seen_rev:
                            seen_rev.add(rid)
                            entries.append({"search": {"mode": "include"}, "resource": r})

        return {
            "resourceType": "Bundle", "type": "searchset",
            "total": total,
            "link": _bundle_links(request, total, _count, _offset),
            "entry": entries,
        }

    # ------------------------------------------------------------------
    # Search by POST (FHIR spec §3.2.2 — POST /{type}/_search)
    # ------------------------------------------------------------------

    async def _search_post(request: Request):
        """FHIR search-by-POST: params in application/x-www-form-urlencoded body."""
        form = await request.form()
        # Merge URL query params (rare but allowed) with body params; body takes precedence.
        merged = dict(request.query_params)
        merged.update({k: v for k, v in form.multi_items()})

        base_params: Dict[str, Any] = {}
        extra_pairs: List[Tuple[str, Any]] = []
        if search_hook:
            base_params, extra_pairs = search_hook(merged)
        extra_pairs = list(extra_pairs) + _build_has_conditions(rt, merged) + _build_chained_conditions(rt, merged)

        _count = int(merged.get("_count", 20))
        _offset = int(merged.get("_offset", 0))
        _sort = merged.get("_sort")
        _revinclude = merged.get("_revinclude")

        patient_id = getattr(request.state, "fhir_patient_id", None)
        if patient_id and rt in _PATIENT_COMPARTMENT:
            sql_path, _ = _PATIENT_COMPARTMENT[rt]
            if sql_path is None:
                extra_pairs = [("data->>'id' = ??", patient_id)] + list(extra_pairs)
            else:
                extra_pairs = [(f"{sql_path} = ??", f"Patient/{patient_id}")] + list(extra_pairs)

        clinician_id = getattr(request.state, "fhir_clinician_id", None)
        if clinician_id and rt in _PATIENT_COMPARTMENT and not patient_id:
            if rt == "Patient":
                gp_ref = json.dumps([{"reference": f"Practitioner/{clinician_id}"}])
                extra_pairs = [("data->'generalPractitioner' @> ??::jsonb", gp_ref)] + list(extra_pairs)
            else:
                sql_path, _ = _PATIENT_COMPARTMENT[rt]
                if sql_path:
                    panel_refs = await _get_panel_patient_refs(clinician_id)
                    if not panel_refs:
                        return {"resourceType": "Bundle", "type": "searchset", "total": 0,
                                "link": _bundle_links(request, 0, _count, _offset), "entry": []}
                    extra_pairs = [(f"{sql_path} = ANY(??)", panel_refs)] + list(extra_pairs)

        total, results = await state.db.search_resources_ex(
            rt, base_params, extra_pairs, limit=_count, offset=_offset, sort=_sort
        )
        entries: List[Dict[str, Any]] = [{"resource": r} for r in results]

        if _revinclude and results:
            rev_info = _INCLUDE_REFERENCE_MAP.get(_revinclude)
            if rev_info:
                _, sql_path = rev_info
                rev_type = _revinclude.split(":")[0]
                primary_refs = [f"{rt}/{r['id']}" for r in results if r.get("id")]
                if primary_refs:
                    rev_condition = sql_path if "??" in sql_path else f"{sql_path} = ANY(??)"
                    _, rev_results = await state.db.search_resources_ex(
                        rev_type, {}, [(rev_condition, primary_refs)],
                        limit=min(_count * 10, 1000), offset=0
                    )
                    seen_rev: set = set()
                    for r in rev_results:
                        rid = r.get("id")
                        if rid and rid not in seen_rev:
                            seen_rev.add(rid)
                            entries.append({"search": {"mode": "include"}, "resource": r})

        return {"resourceType": "Bundle", "type": "searchset", "total": total,
                "link": _bundle_links(request, total, _count, _offset), "entry": entries}

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def _type_history(
        request: Request,
        _since: Optional[str] = Query(None, alias="_since"),
        _count: int = Query(20, alias="_count", ge=1, le=1000),
        _offset: int = Query(0, alias="_offset", ge=0),
    ):
        total, entries = await state.db.get_type_history(rt, since=_since, limit=_count, offset=_offset)
        return {
            "resourceType": "Bundle",
            "type": "history",
            "total": total,
            "link": _bundle_links(request, total, _count, _offset),
            "entry": entries,
        }

    async def _history(resource_id: str):
        h = await state.db.get_version_history(resource_id)
        if not h:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        return {"resourceType": "Bundle", "type": "history", "total": len(h), "entry": h}

    async def _versioned_read(resource_id: str, vid: int):
        resource = await state.db.get_resource(resource_id, version=vid)
        if not resource:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id}/_history/{vid} not found")
        return _fhir_response(resource)

    # ------------------------------------------------------------------
    # P2.5 — $validate
    # ------------------------------------------------------------------

    async def _validate(
        body: Dict[str, Any] = Body(...),
        profile: Optional[str] = Query(None),
    ):
        # Local structural validation via Pydantic
        local_issues: List[Dict[str, Any]] = []
        try:
            model_class(**body)
        except ValidationError as exc:
            local_issues = [
                {
                    "severity": "error",
                    "code": "invalid",
                    "details": {"text": err["msg"]},
                    "expression": [".".join(str(loc) for loc in err["loc"])],
                }
                for err in exc.errors()
            ]

        # US Core must-support checks (local, fast — only for known US Core profiles)
        us_core_issues: List[Dict[str, Any]] = []
        if profile and profile in _US_CORE_MUST_SUPPORT:
            for element_expr, check_fn in _US_CORE_MUST_SUPPORT[profile]:
                if not check_fn(body):
                    us_core_issues.append({
                        "severity": "warning",
                        "code": "required",
                        "details": {"text": f"US Core must-support element missing or incomplete: {element_expr}"},
                        "expression": [element_expr],
                    })

        # Profile validation via tx.fhir.org (only when ?profile= is provided)
        profile_issues: List[Dict[str, Any]] = []
        if profile:
            body_json = json.dumps(body, sort_keys=True)
            cache_key = f"validate:{rt}:{profile}:{hashlib.sha256(body_json.encode()).hexdigest()}"
            cached = await state.cache.get(cache_key)
            if cached is not None:
                profile_issues = cached
            else:
                try:
                    timeout = aiohttp.ClientTimeout(total=15)
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"https://tx.fhir.org/r4/{rt}/$validate",
                            json=body,
                            params={"profile": profile},
                            headers={
                                "Content-Type": "application/fhir+json",
                                "Accept": "application/fhir+json",
                            },
                            timeout=timeout,
                        ) as resp:
                            outcome = await resp.json(content_type=None)
                    profile_issues = [
                        i for i in outcome.get("issue", [])
                        if i.get("severity") in ("error", "warning")
                    ]
                    await state.cache.set(cache_key, profile_issues, ttl=3600)
                except Exception as e:
                    logger.warning("tx.fhir.org profile validation failed: %s", e)
                    profile_issues = [{
                        "severity": "warning",
                        "code": "not-supported",
                        "details": {"text": f"Profile validation against tx.fhir.org unavailable: {e}"},
                    }]

        all_issues = local_issues + us_core_issues + profile_issues
        if not all_issues:
            all_issues = [{"severity": "information", "code": "informational",
                           "details": {"text": f"{rt} resource is valid"}}]
        return {"resourceType": "OperationOutcome", "issue": all_issues}

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    async def _audit(resource_id: str):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        entries = await state.db.get_audit_log(resource_id)
        return {"resourceId": resource_id, "total": len(entries), "entries": entries}

    # ------------------------------------------------------------------
    # Name all handlers (required for unique OpenAPI operation IDs)
    # ------------------------------------------------------------------

    rt_lower = rt.lower()
    _create.__name__ = f"create_{rt_lower}"
    _search_post.__name__ = f"search_post_{rt_lower}"
    _read.__name__ = f"read_{rt_lower}"
    _update.__name__ = f"update_{rt_lower}"
    _delete.__name__ = f"delete_{rt_lower}"
    _patch.__name__ = f"patch_{rt_lower}"
    _conditional_update.__name__ = f"conditional_update_{rt_lower}"
    _conditional_delete.__name__ = f"conditional_delete_{rt_lower}"
    _search.__name__ = f"search_{rt_lower}"
    _type_history.__name__ = f"type_history_{rt_lower}"
    _history.__name__ = f"history_{rt_lower}"
    _versioned_read.__name__ = f"versioned_read_{rt_lower}"
    _validate.__name__ = f"validate_{rt_lower}"
    _audit.__name__ = f"audit_{rt_lower}"

    # ------------------------------------------------------------------
    # Route registration order matters: literals before parameters
    # ------------------------------------------------------------------

    router.post(f"/{rt}", status_code=201)(_create)
    router.post(f"/{rt}/_search")(_search_post)
    router.post(f"/{rt}/$validate")(_validate)
    # Type-level history MUST be registered before /{rt}/{resource_id} to take priority
    router.get(f"/{rt}/_history")(_type_history)
    router.get(f"/{rt}/{{resource_id}}")(_read)
    router.put(f"/{rt}/{{resource_id}}")(_update)
    router.patch(f"/{rt}/{{resource_id}}")(_patch)
    router.delete(f"/{rt}/{{resource_id}}", status_code=204)(_delete)
    # Conditional update/delete (no resource_id in path)
    router.put(f"/{rt}")(_conditional_update)
    router.delete(f"/{rt}", status_code=204)(_conditional_delete)
    router.get(f"/{rt}")(_search)
    router.get(f"/{rt}/{{resource_id}}/_history")(_history)
    router.get(f"/{rt}/{{resource_id}}/_history/{{vid}}")(_versioned_read)
    router.get(f"/{rt}/{{resource_id}}/$audit")(_audit)

    if allow_archive:
        async def _archive(resource_id: str, restore: bool = Query(False)):
            existing = await state.db.get_resource(resource_id)
            if not existing:
                raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
            success = await state.db.archive_resource(resource_id, archived=not restore)
            if not success:
                raise HTTPException(status_code=500, detail="Archive operation failed")
            await state.cache.invalidate_pattern(f"{rt}:{resource_id}:*")
            await state.cache.invalidate_pattern(f"{rt}:*")
            return {"resourceId": resource_id, "archived": not restore}
        _archive.__name__ = f"archive_{rt_lower}"
        router.patch(f"/{rt}/{{resource_id}}/$archive", status_code=200)(_archive)

    return router
