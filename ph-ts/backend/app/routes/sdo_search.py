"""
SDO (Standard Development Organization) search routes.

GET /sdo/systems          — list configured code systems and their availability
GET /sdo/search           — search concepts in a specific code system
GET /sdo/lookup           — look up a single code
"""

from fastapi import APIRouter, HTTPException, Query
from app.services import external_cs
from app import state

router = APIRouter(prefix="/sdo", tags=["SDO Search"])

_HL7_V2_URL_PREFIX = "http://terminology.hl7.org/CodeSystem/v2-"


@router.get("/systems")
async def list_systems():
    """List all configured external code systems and whether they are available."""
    return {"systems": external_cs.list_systems()}


async def _search_hl7v2_local(query: str, limit: int) -> list:
    """Search concepts across locally-imported HL7 v2 table CodeSystems.

    Requires that HL7 v2 tables have been imported via migration/import_hl7_v2_tables.py.
    Returns an empty list if no local tables are found.
    """
    safe_q = f"%{query.lower()}%"
    async with state.db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                concept->>'code'    AS code,
                concept->>'display' AS display,
                data->>'url'        AS system_url,
                COALESCE(data->>'title', data->>'name') AS system_title
            FROM fhir_resources,
                 jsonb_array_elements(data->'concept') AS concept
            WHERE resource_type = 'CodeSystem'
              AND archived = FALSE
              AND url LIKE $1
              AND (
                  lower(concept->>'code')    LIKE $2
               OR lower(concept->>'display') LIKE $2
              )
            LIMIT $3
            """,
            f"{_HL7_V2_URL_PREFIX}%",
            safe_q,
            limit,
        )
    results = []
    for row in rows:
        system_url = row["system_url"] or ""
        if "v2-" in system_url:
            table_num = system_url.rsplit("v2-", 1)[-1]
            system_name = f"HL7 Table {table_num}"
        else:
            system_name = row["system_title"] or "HL7 v2"
        results.append({
            "code": row["code"] or "",
            "display": row["display"] or "",
            "system": system_url,
            "systemName": system_name,
        })
    return results


@router.get("/search")
async def search_concepts(
    system: str = Query(..., description="System ID: snomed | loinc | icd10cm | rxnorm | vsac | hl7v2"),
    q: str = Query(..., description="Search term or phrase"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """
    Search for concepts in an external code system.

    Returns a list of matching codes with their display names and system URL.
    The `system` parameter must be one of the IDs returned by `GET /sdo/systems`.

    For `hl7v2`, searches locally-imported HL7 v2 table CodeSystems (requires
    migration/import_hl7_v2_tables.py to have been run).
    """
    if system == "hl7v2":
        results = await _search_hl7v2_local(q, limit)
        return {
            "system": system,
            "query": q,
            "count": len(results),
            "results": results,
            **({"note": "No HL7 v2 tables found locally. Run migration/import_hl7_v2_tables.py to enable this search."} if not results else {}),
        }

    if system not in external_cs._SEARCH_FNS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown system '{system}'. Valid values: {list(external_cs._SEARCH_FNS.keys()) + ['hl7v2']}",
        )
    results = await external_cs.search(system, q, limit)
    return {
        "system": system,
        "query": q,
        "count": len(results),
        "results": results,
    }


@router.get("/snomed/children/{concept_id}")
async def snomed_children(
    concept_id: str,
    edition: str = Query("international", description="international | us"),
):
    """
    Return direct children (and parent) of a SNOMED CT concept for lazy tree navigation.

    Delegates to tx.fhir.org CodeSystem/$lookup with property=child/parent.
    Falls back to International Edition when the US Edition module is unavailable.
    """
    try:
        result = await external_cs.get_snomed_children(concept_id, edition)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SNOMED hierarchy lookup failed: {e}")
    return result


@router.get("/lookup")
async def lookup_code(
    system: str = Query(..., description="System ID: snomed | loinc | icd10cm"),
    code: str = Query(..., description="Code to look up"),
):
    """
    Look up a single code in an external code system.

    Returns code details (display, system URL, active status) or 404 if not found.
    """
    result = await external_cs.lookup(system, code)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Code '{code}' not found in system '{system}'",
        )
    return result
