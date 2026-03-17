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
import hashlib
import json

from app import state

router = APIRouter(tags=["FHIR Operations"])


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
    all_concepts = []
    compose = valueset.get('compose', {})

    for include in compose.get('include', []):
        system = include.get('system')

        if 'concept' in include:
            for concept in include['concept']:
                all_concepts.append({
                    'system': system,
                    'code': concept['code'],
                    'display': concept.get('display', concept['code'])
                })
        elif system:
            cs_results = await state.db.search_resources('CodeSystem', {'url': system})
            if cs_results:
                cs = cs_results[0]
                for concept in cs.get('concept', []):
                    all_concepts.append({
                        'system': system,
                        'code': concept['code'],
                        'display': concept.get('display', concept['code'])
                    })

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
    if not cs_results:
        raise HTTPException(status_code=404, detail=f"CodeSystem with url {system} not found")

    codesystem = cs_results[0]

    def find_concept(concepts, target_code):
        for concept in concepts:
            if concept.get('code') == target_code:
                return concept
            if 'concept' in concept:
                nested = find_concept(concept['concept'], target_code)
                if nested:
                    return nested
        return None

    concept = find_concept(codesystem.get('concept', []), code)

    if not concept:
        return {
            'resourceType': 'Parameters',
            'parameter': [
                {'name': 'result', 'valueBoolean': False},
                {'name': 'message', 'valueString': 'Code not found'}
            ]
        }

    return {
        'resourceType': 'Parameters',
        'parameter': [
            {'name': 'name', 'valueString': codesystem.get('name')},
            {'name': 'version', 'valueString': codesystem.get('version')},
            {'name': 'display', 'valueString': concept.get('display')},
            {'name': 'definition', 'valueString': concept.get('definition', '')}
        ]
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
# Analytics
# ============================================================================

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
