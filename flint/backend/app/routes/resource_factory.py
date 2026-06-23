"""
Generic FHIR resource router factory.
Generates standard CRUD + history + versioned read + audit routes for any resource type.
"""
from typing import Callable, Dict, List, Optional, Any, Tuple, Type
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app import state
from app.fhir_utils import _check_etag, _bundle_links, _fhir_response, RESOURCE_COUNT

# SearchHook signature: (query_params_dict) -> (base_params, extra_condition_pairs)
# base_params: dict with keys "name", "status", "url", "identifier" (handled by search_resources_ex)
# extra_condition_pairs: list of (sql_fragment_with_one_??_placeholder, value)
SearchHook = Callable[
    [Dict[str, str]],
    Tuple[Dict[str, Any], List[Tuple[str, Any]]]
]


def create_resource_router(
    resource_type: str,
    model_class: Type[BaseModel],
    search_hook: Optional[SearchHook] = None,
    allow_archive: bool = False,
) -> APIRouter:
    router = APIRouter(tags=[resource_type])
    rt = resource_type

    async def _create(resource: model_class):
        data = resource.model_dump(exclude_none=True, by_alias=True)
        data['resourceType'] = rt
        resource_id = await state.db.create_resource(rt, data)
        await state.search_engine.index_resource(data)
        await state.cache.invalidate_pattern(f"{rt}:*")
        RESOURCE_COUNT.labels(resource_type=rt, operation="create").inc()
        created = await state.db.get_resource(resource_id)
        return _fhir_response(created, status_code=201, extra_headers={"Location": f"/{rt}/{resource_id}/_history/1"})

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
        await state.db.update_resource(resource_id, data)
        await state.search_engine.index_resource(data)
        await state.cache.invalidate_pattern(f"{rt}:{resource_id}:*")
        RESOURCE_COUNT.labels(resource_type=rt, operation="update").inc()
        return _fhir_response(await state.db.get_resource(resource_id))

    async def _delete(resource_id: str):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        await state.db.delete_resource(resource_id)
        await state.search_engine.delete_resource(resource_id)
        await state.cache.invalidate_pattern(f"{rt}:{resource_id}:*")
        await state.cache.invalidate_pattern(f"{rt}:*")

    async def _search(
        request: Request,
        _count: int = Query(20, alias="_count", ge=1, le=1000),
        _offset: int = Query(0, alias="_offset", ge=0),
        _sort: Optional[str] = Query(None, alias="_sort"),
    ):
        base_params: Dict[str, Any] = {}
        extra_pairs: List[Tuple[str, Any]] = []
        if search_hook:
            base_params, extra_pairs = search_hook(dict(request.query_params))
        total, results = await state.db.search_resources_ex(
            rt, base_params, extra_pairs,
            limit=_count, offset=_offset, sort=_sort
        )
        return {
            "resourceType": "Bundle", "type": "searchset",
            "total": total,
            "link": _bundle_links(request, total, _count, _offset),
            "entry": [{"resource": r} for r in results],
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

    async def _audit(resource_id: str):
        existing = await state.db.get_resource(resource_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"{rt}/{resource_id} not found")
        entries = await state.db.get_audit_log(resource_id)
        return {"resourceId": resource_id, "total": len(entries), "entries": entries}

    rt_lower = rt.lower()
    _create.__name__ = f"create_{rt_lower}"
    _read.__name__ = f"read_{rt_lower}"
    _update.__name__ = f"update_{rt_lower}"
    _delete.__name__ = f"delete_{rt_lower}"
    _search.__name__ = f"search_{rt_lower}"
    _history.__name__ = f"history_{rt_lower}"
    _versioned_read.__name__ = f"versioned_read_{rt_lower}"
    _audit.__name__ = f"audit_{rt_lower}"

    router.post(f"/{rt}", status_code=201)(_create)
    router.get(f"/{rt}/{{resource_id}}")(_read)
    router.put(f"/{rt}/{{resource_id}}")(_update)
    router.delete(f"/{rt}/{{resource_id}}", status_code=204)(_delete)
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
