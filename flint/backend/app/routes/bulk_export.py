"""
FHIR Bulk Data Export (FHIR Bulk Data IG v2)

Endpoints:
  GET  /$export              — system-level kick-off (all resource types)
  GET  /Patient/$export      — patient-compartment kick-off
  GET  /jobs/{id}            — status poll (202 in-progress, 200 complete)
  GET  /bulk/{job_id}/{file} — NDJSON file download
  DELETE /jobs/{id}          — cancel in-progress export
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app import state

router = APIRouter(tags=["Bulk Export"])

_EXPORT_DIR = Path(os.getenv("BULK_EXPORT_DIR", "/tmp/bulk-export"))
_EXPORT_TTL = 86400  # job state + files expire after 24h

_ALL_TYPES = [
    "ValueSet", "CodeSystem", "ConceptMap",
    "Patient", "Observation", "Condition", "Encounter",
    "AllergyIntolerance", "Immunization",
    "Organization", "Practitioner", "PractitionerRole", "Location",
    "MedicationRequest", "Procedure", "DiagnosticReport",
    "StructureDefinition",
]
_PATIENT_COMPARTMENT = [
    "Patient", "Observation", "Condition", "Encounter",
    "AllergyIntolerance", "Immunization",
    "MedicationRequest", "Procedure", "DiagnosticReport",
]

# job_id → asyncio.Task (in-memory, for cancellation)
_tasks: Dict[str, asyncio.Task] = {}


async def _run_export(job_id: str, types: List[str], since: Optional[str], base_url: str) -> None:
    job_dir = _EXPORT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    output: List[Dict] = []

    try:
        extra = []
        if since:
            extra = [("data->'meta'->>'lastUpdated' >= ??", since)]

        for rt in types:
            count = 0
            offset = 0
            file_path = job_dir / f"{rt}.ndjson"

            with open(file_path, "w") as f:
                while True:
                    total, results = await state.db.search_resources_ex(
                        rt, {}, extra, limit=500, offset=offset
                    )
                    for r in results:
                        f.write(json.dumps(r) + "\n")
                        count += 1
                    offset += 500
                    if offset >= total:
                        break

            if count > 0:
                output.append({
                    "type": rt,
                    "url": f"{base_url}/bulk/{job_id}/{rt}.ndjson",
                    "count": count,
                })
            else:
                file_path.unlink(missing_ok=True)

        update: Dict = {
            "status": "complete",
            "output": output,
            "transactionTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except asyncio.CancelledError:
        update = {"status": "cancelled", "output": output}
    except Exception as e:
        update = {"status": "failed", "error": [{"type": "OperationOutcome", "url": str(e)}]}

    job = await state.cache.get(f"bulk:job:{job_id}") or {}
    job.update(update)
    await state.cache.set(f"bulk:job:{job_id}", job, ttl=_EXPORT_TTL)
    _tasks.pop(job_id, None)


async def _kickoff(request: Request, types: List[str], since: Optional[str]) -> Response:
    job_id = str(uuid.uuid4())
    base_url = str(request.base_url).rstrip("/")

    job = {
        "status": "in-progress",
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request": str(request.url),
        "requiresAccessToken": False,
        "output": [],
        "error": [],
    }
    await state.cache.set(f"bulk:job:{job_id}", job, ttl=_EXPORT_TTL)

    task = asyncio.create_task(_run_export(job_id, types, since, base_url))
    _tasks[job_id] = task

    return Response(
        status_code=202,
        headers={"Content-Location": f"{base_url}/jobs/{job_id}"},
    )


@router.get("/$export")
async def system_export(
    request: Request,
    _type: Optional[str] = Query(None, alias="_type"),
    _since: Optional[str] = Query(None, alias="_since"),
    _outputFormat: Optional[str] = Query(None, alias="_outputFormat"),
):
    if _outputFormat and "ndjson" not in _outputFormat.lower() and "json" not in _outputFormat.lower():
        raise HTTPException(status_code=400, detail=f"Unsupported _outputFormat: {_outputFormat}")
    types = [t.strip() for t in _type.split(",")] if _type else list(_ALL_TYPES)
    invalid = [t for t in types if t not in _ALL_TYPES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown resource types: {', '.join(invalid)}")
    return await _kickoff(request, types, _since)


@router.get("/Patient/$export")
async def patient_export(
    request: Request,
    _type: Optional[str] = Query(None, alias="_type"),
    _since: Optional[str] = Query(None, alias="_since"),
    _outputFormat: Optional[str] = Query(None, alias="_outputFormat"),
):
    if _outputFormat and "ndjson" not in _outputFormat.lower() and "json" not in _outputFormat.lower():
        raise HTTPException(status_code=400, detail=f"Unsupported _outputFormat: {_outputFormat}")
    types = [t.strip() for t in _type.split(",")] if _type else list(_PATIENT_COMPARTMENT)
    invalid = [t for t in types if t not in _PATIENT_COMPARTMENT]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Type not in Patient compartment: {', '.join(invalid)}")
    return await _kickoff(request, types, _since)


@router.get("/jobs/{job_id}")
async def export_status(job_id: str):
    job = await state.cache.get(f"bulk:job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail=f"Export job {job_id} not found or expired")

    if job["status"] == "in-progress":
        return Response(status_code=202, headers={"X-Progress": "in-progress"})

    if job["status"] == "complete":
        return JSONResponse(content=job)

    raise HTTPException(status_code=500, detail=f"Export job {job['status']}: {job.get('error', [])}")


@router.get("/bulk/{job_id}/{filename}")
async def download_export_file(job_id: str, filename: str):
    if "/" in filename or ".." in filename or not filename.endswith(".ndjson"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = _EXPORT_DIR / job_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found or expired")
    return FileResponse(path=str(file_path), media_type="application/ndjson", filename=filename)


@router.delete("/jobs/{job_id}")
async def cancel_export(job_id: str):
    job = await state.cache.get(f"bulk:job:{job_id}")
    if not job:
        raise HTTPException(status_code=404, detail=f"Export job {job_id} not found or expired")
    if job["status"] != "in-progress":
        raise HTTPException(status_code=409, detail=f"Job is already {job['status']}")

    task = _tasks.get(job_id)
    if task and not task.done():
        task.cancel()

    job["status"] = "cancelled"
    await state.cache.set(f"bulk:job:{job_id}", job, ttl=_EXPORT_TTL)
    return Response(status_code=202)
