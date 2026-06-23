"""FHIR R4 Bundle processor — batch and transaction support.

POST / accepts a Bundle with type "batch" or "transaction".
  batch:       each entry is processed independently; per-entry errors don't fail others.
  transaction: all entries execute on one DB connection under a single asyncpg transaction;
               any entry error rolls back the whole bundle and returns an OperationOutcome.

Internal urn:uuid: references are resolved via a pre-pass that assigns IDs to all POST
entries up-front, so later entries can reference earlier creates before they're committed.
"""
import json
import uuid as _uuid_mod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from app import state
from app.fhir_utils import RESOURCE_COUNT

router = APIRouter(tags=["Bundle"])


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_url(url: str) -> Tuple[str, Optional[str]]:
    """(resource_type, resource_id_or_None) — strips ?query and _history suffix."""
    path = url.split('?')[0].strip('/')
    parts = path.split('/')
    rt = parts[0] if parts else ''
    rid = parts[1] if len(parts) > 1 else None
    return rt, rid


def _parse_qs(qs: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for kv in (qs or '').split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            out[k] = v
    return out


def _resolve_refs(obj: Any, id_map: Dict[str, str]) -> Any:
    """Replace urn:uuid:... placeholders with ResourceType/id strings."""
    if not id_map:
        return obj
    if isinstance(obj, dict):
        return {k: _resolve_refs(v, id_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_refs(i, id_map) for i in obj]
    if isinstance(obj, str) and obj in id_map:
        return id_map[obj]
    return obj


def _ok(status: str, location: str = None, etag: str = None, resource: Dict = None) -> Dict:
    entry: Dict[str, Any] = {"response": {"status": status}}
    if location:
        entry["response"]["location"] = location
    if etag:
        entry["response"]["etag"] = etag
    if resource is not None:
        entry["resource"] = resource
    return entry


def _err(status: str, diag: str) -> Dict:
    return {
        "response": {"status": status},
        "resource": {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "processing", "diagnostics": diag}],
        },
    }


# ---------------------------------------------------------------------------
# Raw DB helpers (use a provided asyncpg connection — for transaction mode)
# ---------------------------------------------------------------------------

async def _get_raw(conn, resource_id: str) -> Optional[Dict]:
    """Read resource with meta computed from resource_versions — mirrors DatabaseManager.get_resource."""
    row = await conn.fetchrow("""
        SELECT fr.data, fr.updated_at,
               (SELECT MAX(version_number) FROM resource_versions WHERE resource_id = $1) AS version
        FROM fhir_resources fr WHERE fr.id = $1
    """, resource_id)
    if not row:
        return None
    data = json.loads(row['data'])
    data['meta'] = {
        'versionId': str(row['version'] or 1),
        'lastUpdated': row['updated_at'].strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    return data


async def _create_raw(conn, rt: str, data: Dict) -> Tuple[str, str]:
    """Insert resource; mutates data to add meta. Returns (resource_id, versionId)."""
    rid = data.get('id') or str(_uuid_mod.uuid4())
    data['id'] = rid
    now = _now()
    data.setdefault('meta', {})
    data['meta'].update({'versionId': '1', 'lastUpdated': now})
    name_val = data.get('name') if isinstance(data.get('name'), str) else None
    await conn.execute(
        """INSERT INTO fhir_resources
           (id, resource_type, url, version, status, name, title, data, source, created_by, updated_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'internal','system','system')""",
        rid, rt, data.get('url'), data.get('version'), data.get('status'),
        name_val, data.get('title'), json.dumps(data),
    )
    await conn.execute(
        "INSERT INTO resource_versions (resource_id, version_number, data, created_by) VALUES ($1,1,$2,'system')",
        rid, json.dumps(data),
    )
    await conn.execute(
        "INSERT INTO audit_log (resource_id, resource_type, action, actor, summary) VALUES ($1,$2,'create','system',$3)",
        rid, rt, f"Bundle create {rt}/{rid}",
    )
    return rid, '1'


async def _update_raw(conn, rid: str, data: Dict) -> str:
    """Update resource; mutates data to add meta. Returns new versionId string."""
    row = await conn.fetchrow(
        "SELECT MAX(version_number) AS v FROM resource_versions WHERE resource_id = $1", rid
    )
    next_v = (row['v'] or 0) + 1
    now = _now()
    data.setdefault('meta', {})
    data['meta'].update({'versionId': str(next_v), 'lastUpdated': now})
    name_val = data.get('name') if isinstance(data.get('name'), str) else None
    rt = data.get('resourceType', 'Unknown')
    await conn.execute(
        """UPDATE fhir_resources
           SET data=$1, url=$2, version=$3, status=$4, name=$5, title=$6,
               updated_at=NOW(), updated_by='system'
           WHERE id=$7""",
        json.dumps(data), data.get('url'), data.get('version'), data.get('status'),
        name_val, data.get('title'), rid,
    )
    await conn.execute(
        "INSERT INTO resource_versions (resource_id, version_number, data, created_by) VALUES ($1,$2,$3,'system')",
        rid, next_v, json.dumps(data),
    )
    await conn.execute(
        "INSERT INTO audit_log (resource_id, resource_type, action, actor, summary) VALUES ($1,$2,'update','system',$3)",
        rid, rt, f"Bundle update to version {next_v}",
    )
    return str(next_v)


# ---------------------------------------------------------------------------
# Core entry dispatcher
# ---------------------------------------------------------------------------

async def _do_entry(
    full_url: str,
    resource: Dict,
    req: Dict,
    id_map: Dict[str, str],
    conn=None,          # asyncpg connection for transaction mode; None = auto-acquire
) -> Tuple[Dict, Optional[Tuple]]:
    """
    Process one bundle entry.
    Returns (response_entry_dict, post_action_or_None).
    post_action = ('create' | 'update' | 'delete', rt, rid, data_or_None)
    """
    if not req:
        return _err("400 Bad Request", "Bundle entry missing request"), None

    method = req.get('method', '').upper()
    url = req.get('url', '')
    rt, rid = _parse_url(url)

    resource = _resolve_refs(dict(resource or {}), id_map)
    resource['resourceType'] = rt

    # --- POST (create) ---
    if method == 'POST':
        if req.get('ifNoneExist'):
            qp = _parse_qs(req['ifNoneExist'])
            _, matches = await state.db.search_resources_ex(rt, qp, [], limit=2, offset=0)
            if len(matches) == 1:
                m = matches[0]
                vid = m.get('meta', {}).get('versionId', '1')
                return _ok("200 OK", f"{rt}/{m['id']}/_history/{vid}", f'W/"{vid}"', m), None
            if len(matches) > 1:
                return _err("412 Precondition Failed",
                            f"ifNoneExist matched {len(matches)} {rt} resources"), None

        if 'id' not in resource:
            resource['id'] = str(_uuid_mod.uuid4())

        if full_url.startswith('urn:uuid:'):
            id_map[full_url] = f"{rt}/{resource['id']}"

        if conn:
            rid_out, vid = await _create_raw(conn, rt, resource)
        else:
            rid_out = await state.db.create_resource(rt, resource)
            fetched = await state.db.get_resource(rid_out)
            vid = fetched.get('meta', {}).get('versionId', '1')
            resource = fetched

        RESOURCE_COUNT.labels(resource_type=rt, operation='create').inc()
        return (
            _ok("201 Created", f"{rt}/{rid_out}/_history/{vid}", f'W/"{vid}"', resource),
            ('create', rt, rid_out, resource),
        )

    # --- PUT (update) ---
    if method == 'PUT':
        if not rid:
            return _err("400 Bad Request", "PUT URL must include resource ID"), None

        existing = await _get_raw(conn, rid) if conn else await state.db.get_resource(rid)
        if not existing:
            return _err("404 Not Found", f"{rt}/{rid} not found"), None

        if req.get('ifMatch'):
            cur_vid = existing.get('meta', {}).get('versionId', '')
            cli_vid = req['ifMatch'].strip().strip('"').lstrip('W/').strip('"')
            if cli_vid != str(cur_vid):
                return _err("412 Precondition Failed",
                            f"Version conflict: server={cur_vid}, client sent {req['ifMatch']}"), None

        resource['id'] = rid
        if conn:
            new_vid = await _update_raw(conn, rid, resource)
        else:
            await state.db.update_resource(rid, resource)
            updated = await state.db.get_resource(rid)
            new_vid = str(updated.get('meta', {}).get('versionId', '?'))
            resource = updated

        RESOURCE_COUNT.labels(resource_type=rt, operation='update').inc()
        return (
            _ok("200 OK", f"{rt}/{rid}/_history/{new_vid}", f'W/"{new_vid}"', resource),
            ('update', rt, rid, resource),
        )

    # --- GET (read) ---
    if method == 'GET':
        if not rid:
            return _err("400 Bad Request", "GET URL must include resource ID"), None
        res = await _get_raw(conn, rid) if conn else await state.db.get_resource(rid)
        if not res:
            return _err("404 Not Found", f"{rt}/{rid} not found"), None
        vid = res.get('meta', {}).get('versionId', '1')
        return _ok("200 OK", etag=f'W/"{vid}"', resource=res), None

    # --- DELETE ---
    if method == 'DELETE':
        if not rid:
            return _err("400 Bad Request", "DELETE URL must include resource ID"), None
        if conn:
            await conn.execute("DELETE FROM resource_versions WHERE resource_id = $1", rid)
            await conn.execute("DELETE FROM fhir_resources WHERE id = $1", rid)
        else:
            await state.db.delete_resource(rid)
        return _ok("204 No Content"), ('delete', rt, rid, None)

    return _err("405 Method Not Allowed", f"Unsupported method: {method}"), None


# ---------------------------------------------------------------------------
# Post-commit side effects (ES index + cache invalidation)
# ---------------------------------------------------------------------------

async def _after_write(post_actions: List[Tuple]) -> None:
    for action, rt, rid, data in post_actions:
        try:
            if action in ('create', 'update') and data:
                await state.search_engine.index_resource(data)
                await state.cache.invalidate_pattern(f"{rt}:{rid}:*")
                await state.cache.invalidate_pattern(f"{rt}:*")
            elif action == 'delete':
                await state.search_engine.delete_resource(rid)
                await state.cache.invalidate_pattern(f"{rt}:{rid}:*")
                await state.cache.invalidate_pattern(f"{rt}:*")
        except Exception:
            pass  # ES/cache failures don't fail the committed write


# ---------------------------------------------------------------------------
# ID pre-pass for urn:uuid: reference resolution
# ---------------------------------------------------------------------------

def _pre_assign_ids(entries: List[Dict]) -> Dict[str, str]:
    """
    For every POST entry with a urn:uuid: fullUrl, ensure the resource has an 'id'
    and map fullUrl → ResourceType/id in id_map so later entries can reference it.
    """
    id_map: Dict[str, str] = {}
    for entry in entries:
        req = entry.get('request', {})
        full_url = entry.get('fullUrl', '')
        if req.get('method', '').upper() == 'POST' and full_url.startswith('urn:uuid:'):
            resource = entry.get('resource') or {}
            if 'id' not in resource:
                resource['id'] = str(_uuid_mod.uuid4())
                entry['resource'] = resource
            rt, _ = _parse_url(req.get('url', ''))
            id_map[full_url] = f"{rt}/{resource['id']}"
    return id_map


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

@router.post("/")
async def process_bundle(bundle: Dict[str, Any] = Body(...)):
    if bundle.get('resourceType') != 'Bundle':
        return JSONResponse(status_code=400, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "invalid",
                       "diagnostics": "Expected resourceType Bundle"}],
        })

    bundle_type = bundle.get('type', '')
    if bundle_type not in ('batch', 'transaction'):
        return JSONResponse(status_code=400, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "invalid",
                       "diagnostics": f"Unsupported Bundle.type '{bundle_type}'. Use 'batch' or 'transaction'."}],
        })

    entries: List[Dict] = bundle.get('entry') or []
    id_map = _pre_assign_ids(entries)

    # ------------------------------------------------------------------ batch
    if bundle_type == 'batch':
        response_entries: List[Dict] = []
        post_actions: List[Tuple] = []
        for entry in entries:
            try:
                result, action = await _do_entry(
                    entry.get('fullUrl', ''),
                    entry.get('resource') or {},
                    entry.get('request') or {},
                    id_map,
                )
                response_entries.append(result)
                if action:
                    post_actions.append(action)
            except Exception as exc:
                response_entries.append(_err("500 Internal Server Error", str(exc)))

        await _after_write(post_actions)
        return JSONResponse(content={
            "resourceType": "Bundle", "type": "batch-response",
            "total": len(response_entries), "entry": response_entries,
        })

    # -------------------------------------------------------------- transaction
    response_entries = []
    post_actions = []
    try:
        async with state.db.pool.acquire() as conn:
            async with conn.transaction():
                for entry in entries:
                    result, action = await _do_entry(
                        entry.get('fullUrl', ''),
                        entry.get('resource') or {},
                        entry.get('request') or {},
                        id_map,
                        conn=conn,
                    )
                    status_code = int(
                        (result.get('response', {}).get('status') or '500').split()[0]
                    )
                    if status_code >= 400:
                        diag = (
                            result.get('resource', {})
                            .get('issue', [{}])[0]
                            .get('diagnostics', 'entry failed')
                        )
                        raise ValueError(f"{result['response']['status']}: {diag}")
                    response_entries.append(result)
                    if action:
                        post_actions.append(action)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "processing", "diagnostics": str(exc)}],
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "fatal", "code": "exception", "diagnostics": str(exc)}],
        })

    await _after_write(post_actions)
    return JSONResponse(content={
        "resourceType": "Bundle", "type": "transaction-response",
        "total": len(response_entries), "entry": response_entries,
    })
