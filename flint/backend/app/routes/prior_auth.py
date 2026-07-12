"""Prior Authorization routes — Da Vinci PAS resources and $submit operation.

Resources: Questionnaire, QuestionnaireResponse, Claim, Coverage, ClaimResponse, ServiceRequest
Operation: POST /Claim/$submit  (PASRequestBundle → PASResponseBundle)
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import state
from app.capability import register_resource
from app.fhir_utils import _date_condition, _patient_ref
from app.models.prior_auth import (
    Claim, ClaimResponse, Coverage, Questionnaire, QuestionnaireResponse, ServiceRequest,
)
from app.routes.bundle import _after_write, _create_raw
from app.routes.resource_factory import create_resource_router


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
# Search hooks
# ---------------------------------------------------------------------------

def _questionnaire_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if "url" in qp:
        base["url"] = qp["url"]
    if "status" in qp:
        base["status"] = qp["status"]
    if "name" in qp:
        base["name"] = qp["name"]
    if "title" in qp:
        extra.append(("data->>'title' ILIKE ??", f"%{qp['title']}%"))
    if "version" in qp:
        extra.append(("data->>'version' = ??", qp["version"]))
    if "date" in qp:
        extra.append(_date_condition("data->>'date'", qp["date"]))
    return base, extra


def _questionnaire_response_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if "status" in qp:
        base["status"] = qp["status"]
    if "questionnaire" in qp:
        extra.append(("data->>'questionnaire' = ??", qp["questionnaire"]))
    if "patient" in qp:
        extra.append(("data->'subject'->>'reference' = ??", qp["patient"]))
    if "subject" in qp:
        extra.append(("data->'subject'->>'reference' = ??", qp["subject"]))
    if "encounter" in qp:
        extra.append(("data->'encounter'->>'reference' = ??", qp["encounter"]))
    if "author" in qp:
        extra.append(("data->'author'->>'reference' = ??", qp["author"]))
    if "authored" in qp:
        extra.append(_date_condition("data->>'authored'", qp["authored"]))
    return base, extra


def _claim_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if "status" in qp:
        base["status"] = qp["status"]
    if "identifier" in qp:
        base["identifier"] = qp["identifier"]
    if "patient" in qp:
        extra.append(("data->'patient'->>'reference' = ??", qp["patient"]))
    if "use" in qp:
        extra.append(("data->>'use' = ??", qp["use"]))
    if "created" in qp:
        extra.append(_date_condition("data->>'created'", qp["created"]))
    if "provider" in qp:
        extra.append(("data->'provider'->>'reference' = ??", qp["provider"]))
    if "insurer" in qp:
        extra.append(("data->'insurer'->>'reference' = ??", qp["insurer"]))
    if "encounter" in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'item', '[]'::jsonb)) it, "
            "jsonb_array_elements(COALESCE(it->'encounter', '[]'::jsonb)) enc "
            "WHERE enc->>'reference' = ??)",
            qp["encounter"],
        ))
    return base, extra


def _coverage_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if "status" in qp:
        base["status"] = qp["status"]
    if "identifier" in qp:
        base["identifier"] = qp["identifier"]
    if "patient" in qp or "beneficiary" in qp:
        val = qp.get("patient") or qp.get("beneficiary")
        extra.append(("data->'beneficiary'->>'reference' = ??", _patient_ref(val)))
    if "subscriber" in qp:
        extra.append(("data->'subscriber'->>'reference' = ??", qp["subscriber"]))
    if "payor" in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'payor', '[]'::jsonb)) p "
            "WHERE p->>'reference' = ??)",
            qp["payor"],
        ))
    if "type" in qp:
        extra.append(("data->'type'->>'text' ILIKE ??", f"%{qp['type']}%"))
    return base, extra


def _claim_response_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if "status" in qp:
        base["status"] = qp["status"]
    if "identifier" in qp:
        base["identifier"] = qp["identifier"]
    if "patient" in qp:
        extra.append(("data->'patient'->>'reference' = ??", qp["patient"]))
    if "use" in qp:
        extra.append(("data->>'use' = ??", qp["use"]))
    if "outcome" in qp:
        extra.append(("data->>'outcome' = ??", qp["outcome"]))
    if "request" in qp:
        extra.append(("data->'request'->>'reference' = ??", qp["request"]))
    if "insurer" in qp:
        extra.append(("data->'insurer'->>'reference' = ??", qp["insurer"]))
    if "created" in qp:
        extra.append(_date_condition("data->>'created'", qp["created"]))
    return base, extra


def _service_request_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if "status" in qp:
        base["status"] = qp["status"]
    if "identifier" in qp:
        base["identifier"] = qp["identifier"]
    if "patient" in qp or "subject" in qp:
        val = qp.get("patient") or qp.get("subject")
        extra.append(("data->'subject'->>'reference' = ??", val))
    if "encounter" in qp:
        extra.append(("data->'encounter'->>'reference' = ??", qp["encounter"]))
    if "requester" in qp:
        extra.append(("data->'requester'->>'reference' = ??", qp["requester"]))
    if "performer" in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'performer', '[]'::jsonb)) p "
            "WHERE p->>'reference' = ??)",
            qp["performer"],
        ))
    if "intent" in qp:
        extra.append(("data->>'intent' = ??", qp["intent"]))
    if "category" in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'category', '[]'::jsonb)) c "
            "WHERE c->>'text' = ??)",
            qp["category"],
        ))
    if "authored" in qp:
        extra.append(_date_condition("data->>'authoredOn'", qp["authored"]))
    return base, extra


# ---------------------------------------------------------------------------
# CRUD routers (factory-generated)
# ---------------------------------------------------------------------------

questionnaire_router = create_resource_router(
    "Questionnaire", Questionnaire, _questionnaire_search_hook
)
questionnaire_response_router = create_resource_router(
    "QuestionnaireResponse", QuestionnaireResponse, _questionnaire_response_search_hook
)
claim_router = create_resource_router("Claim", Claim, _claim_search_hook)
coverage_router = create_resource_router("Coverage", Coverage, _coverage_search_hook)
claim_response_router = create_resource_router(
    "ClaimResponse", ClaimResponse, _claim_response_search_hook
)
service_request_router = create_resource_router(
    "ServiceRequest", ServiceRequest, _service_request_search_hook
)

# ---------------------------------------------------------------------------
# Claim/$submit  — Da Vinci PAS prior authorization submission
# ---------------------------------------------------------------------------
#
# REAL PAYER INTEGRATION NOTE (future work):
#
# The current implementation stores all bundle resources and generates a synthetic
# ClaimResponse with outcome="queued". A production payer integration would:
#
#   1. Validate the PASRequestBundle against Da Vinci PAS profiles (HL7 FHIR IG):
#      https://hl7.org/fhir/us/davinci-pas/
#
#   2. Translate the FHIR Bundle → X12 278 prior-authorization-request transaction
#      using a mapping engine (e.g., Availity, Change Healthcare, or Edifecs).
#      The X12N TR3 278 Implementation Guide specifies the field mapping.
#
#   3. Submit the X12 278 to the payer's clearinghouse / trading-partner endpoint.
#
#   4. Await the 278A acknowledgment response (synchronous) or use async polling /
#      FHIR Subscriptions (R5-style topic-based) if the payer supports it.
#
#   5. Translate the X12 278A response → PASResponseBundle (ClaimResponse):
#        278A Approved → outcome="complete", preAuthRef="<auth number>",
#                         item[].adjudication with approved quantities/amounts
#        278A Denied   → outcome="complete", item[].adjudication with denied
#                         reason codes (X12 AAA segments → FHIR error.code)
#        278A Pended   → outcome="queued",
#                         communicationRequest=[ref to Questionnaire for ADI]
#
#   6. Store the ClaimResponse and return the PASResponseBundle to the provider.
#
#   For FHIR-native payers (rare today, growing under CMS-0057-F mandates), the
#   PASRequestBundle can be forwarded directly without X12 translation.
#
# ---------------------------------------------------------------------------

submit_router = APIRouter(tags=["Prior Authorization"])


@submit_router.post("/Claim/$submit")
async def claim_submit(request: Request):
    """PAS prior authorization submission — accepts PASRequestBundle, returns PASResponseBundle."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "invalid", "diagnostics": "Invalid JSON body"}],
        })

    if body.get("resourceType") != "Bundle":
        return JSONResponse(status_code=400, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "invalid",
                       "diagnostics": "Request body must be a Bundle (PASRequestBundle)"}],
        })

    entries: List[Dict[str, Any]] = body.get("entry", [])

    # Locate the Claim resource within the bundle
    claim_resource: Dict[str, Any] = {}
    for entry in entries:
        r = entry.get("resource", {})
        if r.get("resourceType") == "Claim":
            claim_resource = r
            break

    if not claim_resource:
        return JSONResponse(status_code=422, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "required",
                       "diagnostics": "Bundle must contain a Claim resource"}],
        })

    if claim_resource.get("use") != "preauthorization":
        return JSONResponse(status_code=422, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "value",
                       "diagnostics": "Claim.use must be 'preauthorization' for prior authorization requests"}],
        })

    # Store all bundle resources atomically, then generate a ClaimResponse
    now = _now()
    post_actions: List[Tuple] = []
    claim_id: str = ""
    cr_data: Dict[str, Any] = {}

    async with state.db.pool.acquire() as conn:
        async with conn.transaction():
            for entry in entries:
                resource = dict(entry.get("resource", {}))
                rt = resource.get("resourceType")
                if not rt:
                    continue
                rid, _ = await _create_raw(conn, rt, resource)
                if rt == "Claim":
                    claim_id = rid
                post_actions.append(("create", rt, rid, resource))

            cr_data = {
                "resourceType": "ClaimResponse",
                "id": str(uuid.uuid4()),
                "status": "active",
                "use": "preauthorization",
                "type": claim_resource.get("type"),
                "patient": claim_resource.get("patient"),
                "created": now,
                "insurer": claim_resource.get("insurer"),
                "requestor": claim_resource.get("provider"),
                "request": {"reference": f"Claim/{claim_id}"},
                "outcome": "queued",
                "disposition": "Prior authorization request received and is pending review.",
            }
            cr_id, _ = await _create_raw(conn, "ClaimResponse", cr_data)
            post_actions.append(("create", "ClaimResponse", cr_id, cr_data))

    await _after_write(post_actions)

    return JSONResponse(status_code=201, content={
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "collection",
        "timestamp": now,
        "entry": [{"fullUrl": f"/ClaimResponse/{cr_id}", "resource": cr_data}],
    })


# ---------------------------------------------------------------------------
# CapabilityStatement registrations
# ---------------------------------------------------------------------------

register_resource({
    "type": "Questionnaire",
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
    "searchParam": [
        {"name": "url", "type": "uri"},
        {"name": "status", "type": "token"},
        {"name": "name", "type": "string"},
        {"name": "title", "type": "string"},
        {"name": "version", "type": "token"},
        {"name": "date", "type": "date"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

register_resource({
    "type": "QuestionnaireResponse",
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
    "searchInclude": [
        "QuestionnaireResponse:questionnaire",
        "QuestionnaireResponse:subject",
        "QuestionnaireResponse:encounter",
    ],
    "searchParam": [
        {"name": "questionnaire", "type": "reference"},
        {"name": "patient", "type": "reference"},
        {"name": "subject", "type": "reference"},
        {"name": "encounter", "type": "reference"},
        {"name": "author", "type": "reference"},
        {"name": "authored", "type": "date"},
        {"name": "status", "type": "token"},
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
    "type": "Claim",
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
    "searchInclude": ["Claim:patient", "Claim:provider", "Claim:insurer"],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "use", "type": "token"},
        {"name": "created", "type": "date"},
        {"name": "provider", "type": "reference"},
        {"name": "insurer", "type": "reference"},
        {"name": "encounter", "type": "reference"},
        {"name": "identifier", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
        {"name": "submit", "definition": "http://hl7.org/fhir/us/davinci-pas/OperationDefinition/Claim-submit"},
    ],
})

register_resource({
    "type": "Coverage",
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
    "searchInclude": [
        "Coverage:beneficiary",
        "Coverage:subscriber",
        "Coverage:payor",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "beneficiary", "type": "reference"},
        {"name": "subscriber", "type": "reference"},
        {"name": "payor", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "type", "type": "token"},
        {"name": "identifier", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
})

register_resource({
    "type": "ClaimResponse",
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
    "searchInclude": [
        "ClaimResponse:patient",
        "ClaimResponse:request",
        "ClaimResponse:insurer",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "request", "type": "reference"},
        {"name": "insurer", "type": "reference"},
        {"name": "use", "type": "token"},
        {"name": "outcome", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "created", "type": "date"},
        {"name": "identifier", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
})

register_resource({
    "type": "ServiceRequest",
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
    "searchInclude": [
        "ServiceRequest:subject",
        "ServiceRequest:encounter",
        "ServiceRequest:requester",
        "ServiceRequest:performer",
    ],
    "searchParam": [
        {"name": "patient", "type": "reference"},
        {"name": "subject", "type": "reference"},
        {"name": "encounter", "type": "reference"},
        {"name": "requester", "type": "reference"},
        {"name": "performer", "type": "reference"},
        {"name": "status", "type": "token"},
        {"name": "intent", "type": "token"},
        {"name": "category", "type": "token"},
        {"name": "authored", "type": "date"},
        {"name": "identifier", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_include", "type": "string"},
    ],
})

routers = [
    questionnaire_router,
    questionnaire_response_router,
    claim_router,
    coverage_router,
    claim_response_router,
    service_request_router,
    submit_router,
]
