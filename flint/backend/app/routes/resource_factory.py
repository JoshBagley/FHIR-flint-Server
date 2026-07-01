"""
Generic FHIR resource router factory.
Generates standard CRUD + history + versioned read + audit routes for any resource type.
"""
from typing import Callable, Dict, List, Optional, Any, Tuple, Type
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
}


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

    async def _read(resource_id: str):
        cache_key = f"{rt}:{resource_id}:latest"
        cached = await state.cache.get(cache_key)
        if cached:
            return _fhir_response(cached)
        resource = await state.db.get_resource(resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        await state.cache.set(cache_key, resource)
        return _fhir_response(resource)

    async def _update(request: Request, resource_id: str, resource: model_class):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
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

    async def _delete(resource_id: str):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
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
                    _, rev_results = await state.db.search_resources_ex(
                        rev_type, {}, [(f"{sql_path} = ANY(??)", primary_refs)],
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

        all_issues = local_issues + profile_issues
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
