from typing import Dict, List, Any, Tuple

from app.capability import register_resource
from app.models.administrative import Organization, Practitioner, PractitionerRole, Location
from app.routes.resource_factory import create_resource_router


def _organization_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'name' in qp:
        base['name'] = qp['name']
    if 'identifier' in qp:
        base['identifier'] = qp['identifier']
    if 'type' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'type', '[]'::jsonb)) t, jsonb_array_elements(COALESCE(t->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['type']
        ))
    if 'active' in qp:
        extra.append(("data->>'active' = ??", qp['active']))
    return base, extra


def _practitioner_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
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
    if 'identifier' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'identifier', '[]'::jsonb)) id WHERE id->>'value' = ??)",
            qp['identifier']
        ))
    if 'gender' in qp:
        extra.append(("data->>'gender' = ??", qp['gender']))
    return base, extra


def _practitioner_role_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'practitioner' in qp:
        extra.append(("data->'practitioner'->>'reference' = ??", qp['practitioner']))
    if 'organization' in qp:
        extra.append(("data->'organization'->>'reference' = ??", qp['organization']))
    if 'role' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'code', '[]'::jsonb)) t, jsonb_array_elements(COALESCE(t->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['role']
        ))
    if 'specialty' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'specialty', '[]'::jsonb)) t, jsonb_array_elements(COALESCE(t->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['specialty']
        ))
    return base, extra


def _location_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'name' in qp:
        base['name'] = qp['name']
    if 'identifier' in qp:
        base['identifier'] = qp['identifier']
    if 'status' in qp:
        base['status'] = qp['status']
    if 'type' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'type', '[]'::jsonb)) t, jsonb_array_elements(COALESCE(t->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['type']
        ))
    return base, extra


organization_router = create_resource_router("Organization", Organization, _organization_search_hook)
practitioner_router = create_resource_router("Practitioner", Practitioner, _practitioner_search_hook)
practitioner_role_router = create_resource_router("PractitionerRole", PractitionerRole, _practitioner_role_search_hook)
location_router = create_resource_router("Location", Location, _location_search_hook)

register_resource({
    "type": "Organization",
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
    "searchRevInclude": ["PractitionerRole:organization"],
    "searchParam": [
        {"name": "name", "type": "string"},
        {"name": "identifier", "type": "token"},
        {"name": "type", "type": "token"},
        {"name": "active", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_revinclude", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

register_resource({
    "type": "Practitioner",
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
    "searchRevInclude": ["PractitionerRole:practitioner"],
    "searchParam": [
        {"name": "family", "type": "string"},
        {"name": "given", "type": "string"},
        {"name": "name", "type": "string"},
        {"name": "identifier", "type": "token"},
        {"name": "gender", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
        {"name": "_revinclude", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

register_resource({
    "type": "PractitionerRole",
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
    "searchInclude": ["PractitionerRole:practitioner", "PractitionerRole:organization"],
    "searchParam": [
        {"name": "practitioner", "type": "reference"},
        {"name": "organization", "type": "reference"},
        {"name": "role", "type": "token"},
        {"name": "specialty", "type": "token"},
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
    "type": "Location",
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
        {"name": "name", "type": "string"},
        {"name": "identifier", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "type", "type": "token"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

routers = [organization_router, practitioner_router, practitioner_role_router, location_router]
