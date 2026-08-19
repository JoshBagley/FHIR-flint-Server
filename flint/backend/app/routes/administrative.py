from typing import Dict, List, Any, Tuple

from app.capability import register_resource
from app.models.administrative import Organization, Practitioner, PractitionerRole, Location
from app.routes.resource_factory import create_resource_router


def _organization_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if 'name' in qp:
        # FHIR string search is prefix (starts-with), not contains — prevents cross-matches
        # like "General Hospital" matching "MASSACHUSETTS GENERAL HOSPITAL"
        extra.append(("data->>'name' ILIKE ??", f"{qp['name']}%"))
    if 'identifier' in qp:
        base['identifier'] = qp['identifier']
    if 'type' in qp:
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'type', '[]'::jsonb)) t, jsonb_array_elements(COALESCE(t->'coding', '[]'::jsonb)) c WHERE c->>'code' = ??)",
            qp['type']
        ))
    if 'active' in qp:
        extra.append(("data->>'active' = ??", qp['active']))
    if 'address' in qp:
        # FHIR string search is prefix (starts-with) per field, not contains on full text.
        # Checking each field separately avoids "WEST SPRINGFIELD" matching "Springfield"
        # (concatenated it contains the term, but city doesn't start with it).
        # Excludes 'line' so street names like "75 SPRINGFIELD RD" don't create false matches.
        addr_val = f"{qp['address'].lower()}%"
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'address', '[]'::jsonb)) a "
            "WHERE lower(COALESCE(a->>'city','')) LIKE ?? "
            "OR lower(COALESCE(a->>'state','')) LIKE ?? "
            "OR lower(COALESCE(a->>'postalCode','')) LIKE ?? "
            "OR lower(COALESCE(a->>'country','')) LIKE ?? "
            "OR lower(COALESCE(a->>'district','')) LIKE ?? "
            "OR lower(COALESCE(a->>'text','')) LIKE ??)",
            [addr_val] * 6,
        ))
    return base, extra


def _practitioner_search_hook(qp: Dict[str, str]) -> Tuple[Dict[str, Any], List[Tuple[str, Any]]]:
    base: Dict[str, Any] = {}
    extra: List[Tuple[str, Any]] = []
    if '_id' in qp:
        extra.append(("data->>'id' = ??", qp['_id']))
    if 'name' in qp:
        # FHIR name search: prefix match on family, given, or text — searches JSONB array directly
        # (the name DB column is not populated for Practitioners seeded via direct SQL)
        name_val = f"{qp['name'].lower()}%"
        extra.append((
            "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'name', '[]'::jsonb)) n "
            "WHERE lower(COALESCE(n->>'family','')) LIKE ?? "
            "OR lower(COALESCE(n->>'text','')) LIKE ?? "
            "OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(COALESCE(n->'given', '[]'::jsonb)) g WHERE lower(g) LIKE ??))",
            [name_val] * 3,
        ))
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
        ident = qp['identifier']
        if '|' in ident:
            sys_part, _, val_part = ident.partition('|')
            extra.append((
                "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'identifier', '[]'::jsonb)) ident "
                "WHERE ident->>'system' = ?? AND ident->>'value' = ??)",
                [sys_part, val_part],
            ))
        else:
            extra.append((
                "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(data->'identifier', '[]'::jsonb)) ident WHERE ident->>'value' = ??)",
                ident,
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
    if 'address' in qp:
        extra.append((
            "lower((data->'address')::text) LIKE ??",
            f"%{qp['address'].lower()}%"
        ))
    if 'address-city' in qp:
        extra.append(("data->'address'->>'city' ILIKE ??", f"%{qp['address-city']}%"))
    if 'address-postalcode' in qp:
        extra.append(("data->'address'->>'postalCode' = ??", qp['address-postalcode']))
    if 'address-state' in qp:
        extra.append(("data->'address'->>'state' ILIKE ??", f"%{qp['address-state']}%"))
    if 'organization' in qp:
        extra.append(("data->'managingOrganization'->>'reference' = ??", qp['organization']))
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
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-organization",
    ],
    "searchParam": [
        {"name": "name", "type": "string"},
        {"name": "identifier", "type": "token"},
        {"name": "type", "type": "token"},
        {"name": "active", "type": "token"},
        {"name": "address", "type": "string"},
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
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitioner",
    ],
    "searchParam": [
        {"name": "_id", "type": "token"},
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
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-practitionerrole",
    ],
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
    "supportedProfile": [
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-location",
    ],
    "searchParam": [
        {"name": "name", "type": "string"},
        {"name": "identifier", "type": "token"},
        {"name": "status", "type": "token"},
        {"name": "type", "type": "token"},
        {"name": "address", "type": "string"},
        {"name": "address-city", "type": "string"},
        {"name": "address-postalcode", "type": "string"},
        {"name": "address-state", "type": "string"},
        {"name": "organization", "type": "reference"},
        {"name": "_count", "type": "number"},
        {"name": "_offset", "type": "number"},
        {"name": "_sort", "type": "string"},
    ],
    "operation": [
        {"name": "validate", "definition": "http://hl7.org/fhir/OperationDefinition/Resource-validate"},
    ],
})

routers = [organization_router, practitioner_router, practitioner_role_router, location_router]
