"""
FHIR Terminology Operations
============================
Implements FHIR R4 terminology operations:
- $expand: Expand a ValueSet
- $validate-code: Validate a code
- $lookup: Look up a concept
- Version history and diff operations
- Analytics
"""

from fastapi import APIRouter, Query, HTTPException, Body
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import asyncio
import hashlib
import json

from app import state
from app.services import external_cs

router = APIRouter(tags=["FHIR Operations"])

# Maps FHIR system URLs to the SDO connector IDs in external_cs.py.
# Used to delegate $expand/$lookup to external services when a locally
# registered CodeSystem has content="not-present" or content="fragment".
# OID aliases handle ValueSets imported from PHIN VADS where the migration
# script could not normalise a system reference (e.g. unknown OIDs).
# Human-readable display names for well-known code systems.
# Used to enrich expansion.contains with a systemName field.
_SYSTEM_DISPLAY_NAMES: Dict[str, str] = {
    "http://snomed.info/sct":                      "SNOMED CT",
    "http://loinc.org":                            "LOINC",
    "http://hl7.org/fhir/sid/icd-10-cm":           "ICD-10-CM",
    "http://hl7.org/fhir/sid/icd-9-cm":            "ICD-9-CM",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
    "https://cts.nlm.nih.gov/fhir":                "VSAC",
    "urn:oid:2.16.840.1.113883.6.1":               "LOINC",
    "urn:oid:2.16.840.1.113883.6.96":              "SNOMED CT",
    "urn:oid:2.16.840.1.113883.6.90":              "ICD-10-CM",
    "urn:oid:2.16.840.1.113883.6.103":             "ICD-9-CM",
    "urn:oid:2.16.840.1.113883.6.88":              "RxNorm",
}

_SYSTEM_URL_TO_SDO: Dict[str, str] = {
    # Canonical FHIR URLs
    "http://snomed.info/sct":                      "snomed",
    "http://loinc.org":                            "loinc",
    "http://hl7.org/fhir/sid/icd-10-cm":           "icd10cm",
    "http://hl7.org/fhir/sid/icd-9-cm":            "icd9cm",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "rxnorm",
    "https://cts.nlm.nih.gov/fhir":                "vsac",
    # OID aliases — produced by PHIN VADS imports where normalisation did not apply
    "urn:oid:2.16.840.1.113883.6.1":               "loinc",
    "urn:oid:2.16.840.1.113883.6.96":              "snomed",
    "urn:oid:2.16.840.1.113883.6.90":              "icd10cm",
    "urn:oid:2.16.840.1.113883.6.103":             "icd9cm",
    "urn:oid:2.16.840.1.113883.6.88":              "rxnorm",
}

# CodeSystem content values that indicate concepts are NOT stored locally.
_STUB_CONTENT = {"not-present", "fragment"}

# Base URL prefix for all HL7-owned terminology CodeSystems (v2 tables, v3 code systems).
_HL7_TERMINOLOGY_BASE = "http://terminology.hl7.org/CodeSystem/"


def _is_hl7_terminology_url(system: str) -> bool:
    """Return True for any HL7-owned terminology CodeSystem URL (v2 tables, v3 systems)."""
    return system.startswith(_HL7_TERMINOLOGY_BASE)


def _hl7_system_display_name(system: str) -> str:
    """Generate a human-readable name for HL7 v2/v3 terminology URLs."""
    local = system[len(_HL7_TERMINOLOGY_BASE):]   # e.g., "v2-0001", "v3-AdministrativeGender"
    if local.startswith("v2-"):
        return f"HL7 Table {local[3:]}"
    if local.startswith("v3-"):
        return f"HL7 v3 {local[3:]}"
    return f"HL7 {local}"


# ============================================================================
# ValueSet $expand Operation
# ============================================================================

@router.get("/ValueSet/$expand")
async def expand_valueset_get(
    url: Optional[str] = Query(None),
    valueSetVersion: Optional[str] = Query(None),
    filter: Optional[str] = Query(None),
    offset: int = Query(0),
    count: int = Query(100)
):
    return await _perform_expansion(url, valueSetVersion, filter, offset, count)


@router.post("/ValueSet/$expand")
async def expand_valueset_post(body: Dict[str, Any] = Body(...)):
    params = body.get('parameter', [])
    url = next((p['valueUri'] for p in params if p.get('name') == 'url'), None)
    version = next((p['valueString'] for p in params if p.get('name') == 'valueSetVersion'), None)
    filter_text = next((p['valueString'] for p in params if p.get('name') == 'filter'), None)
    offset = next((p['valueInteger'] for p in params if p.get('name') == 'offset'), 0)
    count = next((p['valueInteger'] for p in params if p.get('name') == 'count'), 100)
    return await _perform_expansion(url, version, filter_text, offset, count)


async def _get_system_name(
    system: Optional[str],
    cache: Dict[str, str],
    cs: Optional[Dict] = None,
) -> Optional[str]:
    """Resolve a system URI to a human-readable display name.

    Resolution order:
      1. Per-request cache (avoid duplicate DB hits)
      2. Static well-known map (_SYSTEM_DISPLAY_NAMES)
      3. title / name from a CodeSystem record already fetched by the caller
      4. DB lookup as a last resort
    Falls back to the raw URI if nothing is found.
    """
    if not system:
        return None
    if system in cache:
        return cache[system]
    if system in _SYSTEM_DISPLAY_NAMES:
        cache[system] = _SYSTEM_DISPLAY_NAMES[system]
        return cache[system]
    if _is_hl7_terminology_url(system):
        name = _hl7_system_display_name(system)
        cache[system] = name
        return name
    if cs:
        name = cs.get('title') or cs.get('name') or system
        cache[system] = name
        return name
    cs_results = await state.db.search_resources('CodeSystem', {'url': system})
    if cs_results:
        name = cs_results[0].get('title') or cs_results[0].get('name') or system
    else:
        name = system
    cache[system] = name
    return name


async def _perform_expansion(
    url: Optional[str],
    version: Optional[str],
    filter_text: Optional[str],
    offset: int,
    count: int
) -> Dict[str, Any]:
    if not url:
        raise HTTPException(status_code=400, detail="url parameter is required")

    search_results = await state.db.search_resources('ValueSet', {'url': url})
    if not search_results:
        raise HTTPException(status_code=404, detail=f"ValueSet with url {url} not found")

    valueset = search_results[0]
    all_concepts: List[Dict[str, Any]] = []
    system_name_cache: Dict[str, str] = {}
    compose = valueset.get('compose', {})

    for include in compose.get('include', []):
        system = include.get('system')

        if 'concept' in include:
            system_name = await _get_system_name(system, system_name_cache)
            for concept in include['concept']:
                c: Dict[str, Any] = {
                    'system': system,
                    'code': concept['code'],
                    'display': concept.get('display', concept['code']),
                }
                if system_name:
                    c['systemName'] = system_name
                all_concepts.append(c)
        elif system:
            cs_results = await state.db.search_resources('CodeSystem', {'url': system})
            if cs_results:
                cs = cs_results[0]
                cs_content = cs.get('content', 'complete')
                local_concepts = cs.get('concept', [])
                system_name = await _get_system_name(system, system_name_cache, cs)

                if cs_content in _STUB_CONTENT or not local_concepts:
                    # Stub/fragment — delegate to external SDO connector
                    sdo_id = _SYSTEM_URL_TO_SDO.get(system)
                    if sdo_id:
                        term = filter_text or ''
                        external = await external_cs.search(sdo_id, term, limit=count)
                        for item in external:
                            c = {
                                'system': system,
                                'code': item['code'],
                                'display': item.get('display', item['code']),
                            }
                            if system_name:
                                c['systemName'] = system_name
                            all_concepts.append(c)
                else:
                    for concept in local_concepts:
                        c = {
                            'system': system,
                            'code': concept['code'],
                            'display': concept.get('display', concept['code']),
                        }
                        if system_name:
                            c['systemName'] = system_name
                        all_concepts.append(c)
            else:
                # No local CodeSystem — try external connector directly
                system_name = await _get_system_name(system, system_name_cache)
                sdo_id = _SYSTEM_URL_TO_SDO.get(system)
                if sdo_id:
                    term = filter_text or ''
                    external = await external_cs.search(sdo_id, term, limit=count)
                    for item in external:
                        c = {
                            'system': system,
                            'code': item['code'],
                            'display': item.get('display', item['code']),
                        }
                        if system_name:
                            c['systemName'] = system_name
                        all_concepts.append(c)
                elif _is_hl7_terminology_url(system):
                    # HL7 v2/v3 table not stored locally — delegate expansion to tx.fhir.org
                    term = filter_text or ''
                    try:
                        external = await external_cs.search_hl7v2(system, term, limit=count)
                        for item in external:
                            c = {
                                'system': system,
                                'code': item['code'],
                                'display': item.get('display', item['code']),
                            }
                            if system_name:
                                c['systemName'] = system_name
                            all_concepts.append(c)
                    except Exception:
                        pass  # tx.fhir.org unavailable — return empty for this system

    if filter_text:
        filter_lower = filter_text.lower()
        all_concepts = [
            c for c in all_concepts
            if filter_lower in c['code'].lower() or filter_lower in (c.get('display') or '').lower()
        ]

    total = len(all_concepts)
    paginated = all_concepts[offset:offset + count]

    return {
        'resourceType': 'ValueSet',
        'id': valueset.get('id'),
        'url': url,
        'version': version or valueset.get('version'),
        'name': valueset.get('name'),
        'title': valueset.get('title'),
        'status': valueset.get('status'),
        'expansion': {
            'identifier': hashlib.md5(f"{url}{version or ''}".encode()).hexdigest(),
            'timestamp': datetime.now().isoformat(),
            'total': total,
            'offset': offset,
            'contains': paginated
        }
    }


# ============================================================================
# ValueSet $concept-search Operation
# ============================================================================

@router.get("/ValueSet/$concept-search")
async def concept_search(
    q: str = Query(..., description="Term to search in concept codes and displays"),
    limit: int = Query(20, ge=1, le=100),
    ids: Optional[str] = Query(None, description="Comma-separated ValueSet IDs to restrict search to"),
):
    """
    Search across stored ValueSets for concepts matching the query term.
    Optionally restrict to a specific set of ValueSet IDs via the `ids` parameter.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="q parameter is required")

    term = q.strip().lower()
    id_list = [i.strip() for i in ids.split(",") if i.strip()] if ids else []

    async with state.db.pool.acquire() as conn:
        if id_list:
            rows = await conn.fetch(
                """
                SELECT id, url, name, title, status, version, data
                FROM fhir_resources
                WHERE resource_type = 'ValueSet'
                  AND lower(data::text) LIKE $1
                  AND id = ANY($3::text[])
                ORDER BY title NULLS LAST
                LIMIT $2
                """,
                f"%{term}%",
                limit * 5,
                id_list,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, url, name, title, status, version, data
                FROM fhir_resources
                WHERE resource_type = 'ValueSet'
                  AND lower(data::text) LIKE $1
                ORDER BY title NULLS LAST
                LIMIT $2
                """,
                f"%{term}%",
                limit * 5,
            )

    entries = []
    for row in rows:
        raw = row["data"]
        data = raw if isinstance(raw, dict) else json.loads(raw)
        matched: List[Dict[str, Any]] = []

        for include in data.get("compose", {}).get("include", []):
            system = include.get("system", "")
            for concept in include.get("concept", []):
                code = concept.get("code", "")
                display = concept.get("display", "")
                if term in code.lower() or term in display.lower():
                    matched.append({"code": code, "display": display, "system": system})

        for concept in data.get("expansion", {}).get("contains", []):
            code = concept.get("code", "")
            display = concept.get("display", "")
            system = concept.get("system", "")
            if term in code.lower() or term in display.lower():
                if not any(m["code"] == code for m in matched):
                    matched.append({"code": code, "display": display, "system": system})

        if not matched:
            continue

        entries.append({
            "resource": {
                "resourceType": "ValueSet",
                "id": row["id"],
                "url": row["url"],
                "name": row["name"],
                "title": row["title"],
                "status": row["status"],
                "version": row["version"],
            },
            "search": {
                "matchedConcepts": matched[:20],
                "totalMatched": len(matched),
            },
        })

        if len(entries) >= limit:
            break

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(entries),
        "query": q,
        "entry": entries,
    }


# ============================================================================
# ValueSet $validate-code Operation
# ============================================================================

@router.get("/ValueSet/$validate-code")
async def validate_code_get(
    url: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    system: Optional[str] = Query(None),
    display: Optional[str] = Query(None)
):
    return await _perform_validation(url, code, system, display)


@router.post("/ValueSet/$validate-code")
async def validate_code_post(body: Dict[str, Any] = Body(...)):
    params = body.get('parameter', [])
    url = next((p['valueUri'] for p in params if p.get('name') == 'url'), None)
    code = next((p['valueCode'] for p in params if p.get('name') == 'code'), None)
    system = next((p['valueUri'] for p in params if p.get('name') == 'system'), None)
    display = next((p['valueString'] for p in params if p.get('name') == 'display'), None)
    return await _perform_validation(url, code, system, display)


async def _perform_validation(
    url: Optional[str],
    code: Optional[str],
    system: Optional[str],
    display: Optional[str]
) -> Dict[str, Any]:
    if not url or not code:
        raise HTTPException(status_code=400, detail="url and code parameters are required")

    expansion = await _perform_expansion(url, None, None, 0, 10000)
    contains = expansion.get('expansion', {}).get('contains', [])

    for concept in contains:
        if concept['code'] == code:
            if system and concept.get('system') != system:
                continue

            parameters = [
                {'name': 'result', 'valueBoolean': True},
                {'name': 'display', 'valueString': concept.get('display')}
            ]

            if display and concept.get('display') != display:
                parameters.append({
                    'name': 'message',
                    'valueString': f"Display '{display}' does not match expected '{concept.get('display')}'"
                })
            else:
                parameters.append({'name': 'message', 'valueString': 'Code is valid'})

            return {'resourceType': 'Parameters', 'parameter': parameters}

    return {
        'resourceType': 'Parameters',
        'parameter': [
            {'name': 'result', 'valueBoolean': False},
            {'name': 'message', 'valueString': 'Code not found in ValueSet'}
        ]
    }


# ============================================================================
# CodeSystem $lookup Operation
# ============================================================================

@router.get("/CodeSystem/$lookup")
async def lookup_code_get(
    system: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    version: Optional[str] = Query(None)
):
    return await _perform_lookup(system, code, version)


@router.post("/CodeSystem/$lookup")
async def lookup_code_post(body: Dict[str, Any] = Body(...)):
    params = body.get('parameter', [])
    system = next((p['valueUri'] for p in params if p.get('name') == 'system'), None)
    code = next((p['valueCode'] for p in params if p.get('name') == 'code'), None)
    version = next((p['valueString'] for p in params if p.get('name') == 'version'), None)
    return await _perform_lookup(system, code, version)


async def _perform_lookup(
    system: Optional[str],
    code: Optional[str],
    version: Optional[str]
) -> Dict[str, Any]:
    if not system or not code:
        raise HTTPException(status_code=400, detail="system and code parameters are required")

    cs_results = await state.db.search_resources('CodeSystem', {'url': system})

    def find_concept(concepts, target_code):
        for concept in concepts:
            if concept.get('code') == target_code:
                return concept
            if 'concept' in concept:
                nested = find_concept(concept['concept'], target_code)
                if nested:
                    return nested
        return None

    if cs_results:
        codesystem = cs_results[0]
        cs_content = codesystem.get('content', 'complete')
        concept = find_concept(codesystem.get('concept', []), code)

        if concept:
            return {
                'resourceType': 'Parameters',
                'parameter': [
                    {'name': 'name', 'valueString': codesystem.get('name')},
                    {'name': 'version', 'valueString': codesystem.get('version')},
                    {'name': 'display', 'valueString': concept.get('display')},
                    {'name': 'definition', 'valueString': concept.get('definition', '')}
                ]
            }

        # Concept not found locally — fall through to external if stub/fragment
        if cs_content not in _STUB_CONTENT:
            return {
                'resourceType': 'Parameters',
                'parameter': [
                    {'name': 'result', 'valueBoolean': False},
                    {'name': 'message', 'valueString': 'Code not found'}
                ]
            }
    else:
        codesystem = None

    # No local CodeSystem, or it's a stub — try external SDO connector
    sdo_id = _SYSTEM_URL_TO_SDO.get(system)
    if sdo_id:
        ext = await external_cs.lookup(sdo_id, code)
        if ext:
            return {
                'resourceType': 'Parameters',
                'parameter': [
                    {'name': 'name', 'valueString': ext.get('systemName', system)},
                    {'name': 'version', 'valueString': codesystem.get('version') if codesystem else None},
                    {'name': 'display', 'valueString': ext.get('display')},
                    {'name': 'definition', 'valueString': ''}
                ]
            }

    # HL7 v2/v3 terminology tables — delegate to tx.fhir.org when not in _SYSTEM_URL_TO_SDO
    if not sdo_id and _is_hl7_terminology_url(system):
        ext = await external_cs.lookup_by_system_url(system, code)
        if ext:
            return {
                'resourceType': 'Parameters',
                'parameter': [
                    {'name': 'name', 'valueString': ext.get('systemName', system)},
                    {'name': 'version', 'valueString': codesystem.get('version') if codesystem else None},
                    {'name': 'display', 'valueString': ext.get('display')},
                    {'name': 'definition', 'valueString': ''}
                ]
            }

    if not cs_results:
        raise HTTPException(status_code=404, detail=f"CodeSystem with url {system} not found")

    return {
        'resourceType': 'Parameters',
        'parameter': [
            {'name': 'result', 'valueBoolean': False},
            {'name': 'message', 'valueString': 'Code not found'}
        ]
    }


# ============================================================================
# ValueSet $validate-batch Operation
# ============================================================================

@router.post("/ValueSet/$validate-batch")
async def validate_batch(body: Dict[str, Any] = Body(...)):
    """
    Validate multiple codes in a single request — optimised for HL7 v2 message validation.

    Accepts a plain JSON body with an `items` array. Each item must include `code`
    and either `system` (CodeSystem lookup) or `valueSetUrl` (ValueSet membership check):

        {
          "items": [
            {
              "code":        "M",
              "system":      "http://terminology.hl7.org/CodeSystem/v2-0001",
              "valueSetUrl": "http://hl7.org/fhir/ValueSet/administrative-gender",
              "display":     "Male"   // optional — triggers display mismatch check
            },
            {
              "code":   "94500-6",
              "system": "http://loinc.org"
            }
          ]
        }

    When `valueSetUrl` is present, validates via $validate-code (ValueSet membership).
    When only `system` is present, validates via $lookup (code existence in CodeSystem).
    All items are validated concurrently using asyncio.gather.

    Returns:
        {
          "results": [
            { "code": "M", "system": "...", "valueSetUrl": "...",
              "result": true, "display": "Male", "message": "Code is valid" },
            ...
          ],
          "summary": { "total": 2, "valid": 1, "invalid": 1 }
        }
    """
    items = body.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="items array is required and must not be empty")
    if len(items) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 items per batch request")

    async def _validate_item(item: Dict[str, Any]) -> Dict[str, Any]:
        code = item.get("code", "").strip()
        system = item.get("system", "").strip() or None
        vs_url = item.get("valueSetUrl", "").strip() or None
        display = item.get("display", "").strip() or None

        base = {"code": code, "system": system, "valueSetUrl": vs_url}

        if not code:
            return {**base, "result": False, "display": None, "message": "code is required"}

        try:
            if vs_url:
                # Validate against a ValueSet
                params_result = await _perform_validation(vs_url, code, system, display)
                params = {p["name"]: p for p in params_result.get("parameter", [])}
                return {
                    **base,
                    "result": params.get("result", {}).get("valueBoolean", False),
                    "display": params.get("display", {}).get("valueString"),
                    "message": params.get("message", {}).get("valueString", ""),
                }
            elif system:
                # Validate existence in a CodeSystem via $lookup
                lookup_result = await _perform_lookup(system, code, None)
                params = {p["name"]: p for p in lookup_result.get("parameter", [])}
                found_display = params.get("display", {}).get("valueString")
                if found_display is not None:
                    msg = "Code is valid"
                    if display and found_display and display != found_display:
                        msg = f"Display '{display}' does not match expected '{found_display}'"
                    return {**base, "result": True, "display": found_display, "message": msg}
                return {**base, "result": False, "display": None, "message": "Code not found in CodeSystem"}
            else:
                return {**base, "result": False, "display": None, "message": "system or valueSetUrl is required"}
        except HTTPException as e:
            return {**base, "result": False, "display": None, "message": e.detail}
        except Exception as e:
            return {**base, "result": False, "display": None, "message": f"Validation error: {str(e)}"}

    results = await asyncio.gather(*[_validate_item(item) for item in items])
    results = list(results)

    valid_count = sum(1 for r in results if r.get("result") is True)
    return {
        "results": results,
        "summary": {
            "total": len(results),
            "valid": valid_count,
            "invalid": len(results) - valid_count,
        },
    }


# ============================================================================
# Version History & Diff
# ============================================================================

@router.get("/ValueSet/{resource_id}/$diff")
async def diff_versions(resource_id: str, from_version: int, to_version: int):
    if from_version >= to_version:
        raise HTTPException(status_code=400, detail="from_version must be less than to_version")
    v1_data = await state.db.get_resource(resource_id, from_version)
    v2_data = await state.db.get_resource(resource_id, to_version)

    if not v1_data or not v2_data:
        raise HTTPException(status_code=404, detail="Version not found")

    def extract_concepts(vs):
        concepts = {}
        for include in vs.get('compose', {}).get('include', []):
            for concept in include.get('concept', []):
                concepts[concept['code']] = concept
        return concepts

    concepts_v1 = extract_concepts(v1_data)
    concepts_v2 = extract_concepts(v2_data)

    added = [c for code, c in concepts_v2.items() if code not in concepts_v1]
    removed = [c for code, c in concepts_v1.items() if code not in concepts_v2]
    modified = [
        {'code': code, 'old': concepts_v1[code], 'new': concepts_v2[code]}
        for code in set(concepts_v1.keys()) & set(concepts_v2.keys())
        if concepts_v1[code] != concepts_v2[code]
    ]

    return {
        'resourceType': 'Parameters',
        'parameter': [
            {'name': 'from_version', 'valueInteger': from_version},
            {'name': 'to_version', 'valueInteger': to_version},
            {'name': 'added', 'valueInteger': len(added)},
            {'name': 'removed', 'valueInteger': len(removed)},
            {'name': 'modified', 'valueInteger': len(modified)},
            {'name': 'changes', 'resource': {'added': added, 'removed': removed, 'modified': modified}}
        ]
    }


# ============================================================================
# CodeSystem concept search (for the ValueSet Builder)
# ============================================================================

@router.get("/CodeSystem/$search-concepts")
async def search_codesystem_concepts(
    url: str = Query(..., description="Canonical URL of the CodeSystem to search"),
    q: str = Query("", description="Search term — matches code or display text"),
    count: int = Query(25, ge=1, le=200),
):
    """
    Full-text search within a locally stored CodeSystem's concept list.
    Returns results in the same {code, display, system, systemName} shape as
    /sdo/search so the ValueSet Builder can use a unified result format.
    """
    cs_results = await state.db.search_resources('CodeSystem', {'url': url})
    if not cs_results:
        raise HTTPException(status_code=404, detail=f"CodeSystem with url '{url}' not found")

    cs = cs_results[0]
    system_name = cs.get('title') or cs.get('name') or url

    if cs.get('content') == 'not-present':
        return {'results': [], 'systemName': system_name, 'total': 0}

    term = q.strip().lower()
    async with state.db.pool.acquire() as conn:
        if term:
            rows = await conn.fetch(
                """
                SELECT
                    concept->>'code'    AS code,
                    concept->>'display' AS display
                FROM fhir_resources,
                     jsonb_array_elements(data->'concept') AS concept
                WHERE resource_type = 'CodeSystem'
                  AND url = $1
                  AND archived = FALSE
                  AND (
                    lower(concept->>'code')    LIKE $2
                    OR lower(concept->>'display') LIKE $2
                  )
                ORDER BY
                    CASE WHEN lower(concept->>'display') LIKE $3 THEN 0 ELSE 1 END,
                    concept->>'display'
                LIMIT $4
                """,
                url, f"%{term}%", f"{term}%", count,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    concept->>'code'    AS code,
                    concept->>'display' AS display
                FROM fhir_resources,
                     jsonb_array_elements(data->'concept') AS concept
                WHERE resource_type = 'CodeSystem'
                  AND url = $1
                  AND archived = FALSE
                LIMIT $2
                """,
                url, count,
            )

    results = [
        {
            'code': row['code'],
            'display': row['display'] or row['code'],
            'system': url,
            'systemName': system_name,
        }
        for row in rows
        if row['code']
    ]
    return {'results': results, 'total': len(results), 'systemName': system_name}


@router.get("/CodeSystem/$search-all-concepts")
async def search_all_codesystem_concepts(
    q: str = Query("", description="Search term — matches code or display text"),
    count: int = Query(25, ge=1, le=200),
):
    """
    Full-text search across ALL locally stored CodeSystems that have concepts
    (content != 'not-present'). Returns results in the same shape as
    /CodeSystem/$search-concepts with system + systemName populated per row.
    """
    term = q.strip().lower()
    async with state.db.pool.acquire() as conn:
        if term:
            rows = await conn.fetch(
                """
                SELECT
                    concept->>'code'                        AS code,
                    concept->>'display'                     AS display,
                    data->>'url'                            AS system,
                    COALESCE(data->>'title', data->>'name', data->>'url') AS system_name
                FROM fhir_resources,
                     jsonb_array_elements(data->'concept') AS concept
                WHERE resource_type = 'CodeSystem'
                  AND archived = FALSE
                  AND COALESCE(data->>'content', 'complete') != 'not-present'
                  AND (
                    lower(concept->>'code')    LIKE $1
                    OR lower(concept->>'display') LIKE $1
                  )
                ORDER BY
                    CASE WHEN lower(concept->>'display') LIKE $2 THEN 0 ELSE 1 END,
                    concept->>'display'
                LIMIT $3
                """,
                f"%{term}%", f"{term}%", count,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    concept->>'code'                        AS code,
                    concept->>'display'                     AS display,
                    data->>'url'                            AS system,
                    COALESCE(data->>'title', data->>'name', data->>'url') AS system_name
                FROM fhir_resources,
                     jsonb_array_elements(data->'concept') AS concept
                WHERE resource_type = 'CodeSystem'
                  AND archived = FALSE
                  AND COALESCE(data->>'content', 'complete') != 'not-present'
                LIMIT $1
                """,
                count,
            )

    results = [
        {
            'code': row['code'],
            'display': row['display'] or row['code'],
            'system': row['system'] or '',
            'systemName': row['system_name'] or row['system'] or '',
        }
        for row in rows
        if row['code']
    ]
    return {'results': results, 'total': len(results)}


# ============================================================================
# Analytics
# ============================================================================

@router.get("/analytics/missing-codesystems")
async def missing_codesystems():
    """
    Return every system URI referenced in stored ValueSet compose.include blocks
    that has no corresponding CodeSystem record in the database.
    Includes a count of how many ValueSets reference each missing system and
    whether it is a known SDO that could be delegated to an external connector.
    """
    async with state.db.pool.acquire() as conn:
        # Count ValueSets that reference each distinct system URI
        rows = await conn.fetch("""
            SELECT system_url, COUNT(DISTINCT id) AS valueset_count
            FROM (
                SELECT id,
                       jsonb_array_elements(data->'compose'->'include')->>'system' AS system_url
                FROM fhir_resources
                WHERE resource_type = 'ValueSet'
                  AND archived = FALSE
            ) sub
            WHERE system_url IS NOT NULL
            GROUP BY system_url
            ORDER BY valueset_count DESC
        """)
        system_counts = {row['system_url']: row['valueset_count'] for row in rows}

        # Collect all CodeSystem URLs already registered
        cs_rows = await conn.fetch(
            "SELECT url, name, title FROM fhir_resources WHERE resource_type = 'CodeSystem' AND url IS NOT NULL AND archived = FALSE"
        )
        known_urls = {row['url'] for row in cs_rows}
        cs_info = {row['url']: {'name': row['name'], 'title': row['title']} for row in cs_rows}

    all_systems = set(system_counts.keys())
    missing_urls = all_systems - known_urls
    known_present = all_systems & known_urls

    missing = [
        {
            'url': url,
            'displayName': _SYSTEM_DISPLAY_NAMES.get(url) or (
                _hl7_system_display_name(url) if _is_hl7_terminology_url(url) else None
            ),
            'valueSetCount': system_counts[url],
            'knownSdo': url in _SYSTEM_URL_TO_SDO or _is_hl7_terminology_url(url),
        }
        for url in sorted(missing_urls, key=lambda u: -system_counts[u])
    ]

    present = [
        {
            'url': url,
            'name': cs_info[url]['name'],
            'title': cs_info[url]['title'],
            'valueSetCount': system_counts.get(url, 0),
        }
        for url in sorted(known_present, key=lambda u: -system_counts.get(u, 0))
    ]

    return {
        'totalSystemsReferenced': len(all_systems),
        'totalRegistered': len(known_present),
        'totalMissing': len(missing_urls),
        'missing': missing,
        'registered': present,
    }


@router.get("/$stats")
async def get_statistics():
    async with state.db.pool.acquire() as conn:
        vs_count = await conn.fetchval("SELECT COUNT(*) FROM fhir_resources WHERE resource_type = 'ValueSet'")
        cs_count = await conn.fetchval("SELECT COUNT(*) FROM fhir_resources WHERE resource_type = 'CodeSystem'")

    return {
        'resourceType': 'Parameters',
        'parameter': [
            {'name': 'total_valuesets', 'valueInteger': vs_count or 0},
            {'name': 'total_codesystems', 'valueInteger': cs_count or 0},
        ]
    }
