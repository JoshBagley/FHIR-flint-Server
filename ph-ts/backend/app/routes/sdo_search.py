"""
SDO (Standard Development Organization) search routes.

GET /sdo/systems          — list configured code systems and their availability
GET /sdo/search           — search concepts in a specific code system
GET /sdo/lookup           — look up a single code
"""

from fastapi import APIRouter, HTTPException, Query
from app.services import external_cs

router = APIRouter(prefix="/sdo", tags=["SDO Search"])


@router.get("/systems")
async def list_systems():
    """List all configured external code systems and whether they are available."""
    return {"systems": external_cs.list_systems()}


@router.get("/search")
async def search_concepts(
    system: str = Query(..., description="System ID: snomed | loinc | icd10cm | rxnorm | vsac"),
    q: str = Query(..., description="Search term or phrase"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """
    Search for concepts in an external code system.

    Returns a list of matching codes with their display names and system URL.
    The `system` parameter must be one of the IDs returned by `GET /sdo/systems`.
    """
    if system not in external_cs._SEARCH_FNS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown system '{system}'. Valid values: {list(external_cs._SEARCH_FNS.keys())}",
        )
    results = await external_cs.search(system, q, limit)
    return {
        "system": system,
        "query": q,
        "count": len(results),
        "results": results,
    }


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
