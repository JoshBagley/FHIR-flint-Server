"""
Admin endpoints — PHIN VADS sync management.

POST /admin/sync/phinvads          Trigger a sync in the background
GET  /admin/sync/status            List recent sync runs
GET  /admin/sync/status/{run_id}   Status of a specific run

The sync runs migration/phinvads_migrate.py as a subprocess so the full
PHIN VADS migration logic (STU3→R4 conversion, dedup, retries, etc.) is
reused without code duplication.  Results are stored in the sync_log table.

Terminal alternative — identical result without the UI:
    docker compose exec backend python /app/migration/phinvads_migrate.py \\
        --target-url http://localhost:8000 --resource valueset
"""

import asyncio
import logging
import re
import sys
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app import state

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = logging.getLogger(__name__)

# Path inside the container (./migration is mounted at /app/migration)
_MIGRATION_SCRIPT = "/app/migration/phinvads_migrate.py"
# Call ourselves — subprocess POSTs resources back through the REST API
_TARGET_URL = "http://localhost:8000"

# Patterns for parsing the migration summary block printed at the end
_IMPORTED_RE = re.compile(r"Imported\s*:\s*(\d+)")
_SKIPPED_RE  = re.compile(r"Skipped\s*:\s*(\d+)")
_ERRORS_RE   = re.compile(r"Errors\s*:\s*(\d+)")


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_sync(run_id: int, resource_type: str, preview: bool = False) -> None:
    """
    Execute the migration script as an asyncio subprocess and write results
    back to sync_log when it completes.

    preview=True  → passes --preview to the script: existence-checked but no POST.
                    Imported count = genuinely new resources not yet in PH-TS.
    """
    cmd = [
        sys.executable,          # same Python interpreter as the backend
        _MIGRATION_SCRIPT,
        "--target-url", _TARGET_URL,
        "--resource", resource_type,
        "--log-level", "INFO",
    ]
    if preview:
        cmd.append("--preview")

    output_lines: list[str] = []
    exit_code = -1

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            output_lines.append(line)
            # Keep a rolling window so we don't accumulate unbounded memory
            if len(output_lines) > 300:
                output_lines.pop(0)

        exit_code = await proc.wait()
        output = "\n".join(output_lines)

        # Parse counts from the summary block at the end of the script output
        imported = sum(int(m) for m in _IMPORTED_RE.findall(output))
        skipped  = sum(int(m) for m in _SKIPPED_RE.findall(output))
        errors   = sum(int(m) for m in _ERRORS_RE.findall(output))
        status   = "success" if exit_code == 0 else "error"

        logger.info(
            "PHIN VADS sync run_id=%d finished: status=%s imported=%d skipped=%d errors=%d",
            run_id, status, imported, skipped, errors,
        )

    except Exception as exc:
        logger.error("Sync run_id=%d failed with exception: %s", run_id, exc, exc_info=True)
        output   = str(exc)
        imported = skipped = errors = 0
        status   = "error"

    # Write result to sync_log
    try:
        async with state.db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sync_log
                SET completed_at  = NOW(),
                    status        = $1,
                    new_count     = $2,
                    skipped_count = $3,
                    error_count   = $4,
                    output_tail   = $5
                WHERE id = $6
                """,
                status,
                imported,
                skipped,
                errors,
                output[-4000:],   # keep the last ~4 KB for display
                run_id,
            )
    except Exception as exc:
        logger.error("Could not update sync_log run_id=%d: %s", run_id, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/sync/phinvads", status_code=202)
async def trigger_phinvads_sync(
    background_tasks: BackgroundTasks,
    resource: str = Query(
        "all",
        description="What to sync: valueset | codesystem | all",
    ),
    preview: bool = Query(
        False,
        description=(
            "Preview mode — checks what WOULD be imported without actually posting anything. "
            "Imported count = genuinely new resources; Skipped = already present in PH-TS."
        ),
    ),
):
    """
    Trigger a PHIN VADS synchronisation in the background.

    Returns immediately with `run_id` and `status: started`.
    Poll **GET /admin/sync/status** to track progress.

    Set `preview=true` to see what would be imported before committing.

    Only one sync may run at a time — returns **409** if one is already
    in progress.

    Equivalent terminal commands:
        # Preview
        docker compose exec backend python /app/migration/phinvads_migrate.py \\
            --target-url http://localhost:8000 --resource <valueset|codesystem|all> --preview
        # Live import
        docker compose exec backend python /app/migration/phinvads_migrate.py \\
            --target-url http://localhost:8000 --resource <valueset|codesystem|all>
    """
    if resource not in ("valueset", "codesystem", "all"):
        raise HTTPException(
            status_code=400,
            detail="resource must be one of: valueset, codesystem, all",
        )

    async with state.db.pool.acquire() as conn:
        running = await conn.fetchval(
            "SELECT COUNT(*) FROM sync_log WHERE status = 'running'"
        )
        if running:
            raise HTTPException(
                status_code=409,
                detail="A sync is already in progress. Check GET /admin/sync/status for details.",
            )

        run_id: int = await conn.fetchval(
            """
            INSERT INTO sync_log (source, resource_type, triggered_by, status, started_at, dry_run)
            VALUES ('phinvads', $1, 'ui', 'running', NOW(), $2)
            RETURNING id
            """,
            resource,
            preview,
        )

    background_tasks.add_task(_run_sync, run_id, resource, preview)

    logger.info(
        "PHIN VADS sync started: run_id=%d resource=%s preview=%s",
        run_id, resource, preview,
    )
    return {"run_id": run_id, "status": "started", "resource": resource, "preview": preview}


@router.get("/sync/status")
async def list_sync_status(
    limit: int = Query(10, ge=1, le=50, description="Number of recent runs to return"),
):
    """
    Return the most recent PHIN VADS sync runs with counts and status.

    `status` values: **running** | **success** | **error**
    """
    async with state.db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source, resource_type, started_at, completed_at,
                   status, new_count, skipped_count, error_count,
                   output_tail, triggered_by, dry_run
            FROM sync_log
            ORDER BY started_at DESC
            LIMIT $1
            """,
            limit,
        )

    return {
        "runs": [
            {
                "run_id":        row["id"],
                "source":        row["source"],
                "resource_type": row["resource_type"],
                "started_at":    row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at":  row["completed_at"].isoformat() if row["completed_at"] else None,
                "status":        row["status"],
                "new_count":     row["new_count"] or 0,
                "skipped_count": row["skipped_count"] or 0,
                "error_count":   row["error_count"] or 0,
                "output_tail":   row["output_tail"],
                "triggered_by":  row["triggered_by"],
                "preview":       row["dry_run"] or False,
            }
            for row in rows
        ]
    }


@router.get("/sync/status/{run_id}")
async def get_sync_run(run_id: int):
    """Return the status and output for a single sync run."""
    async with state.db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, source, resource_type, started_at, completed_at,
                   status, new_count, skipped_count, error_count,
                   output_tail, triggered_by, dry_run
            FROM sync_log WHERE id = $1
            """,
            run_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail=f"Sync run {run_id} not found")

    return {
        "run_id":        row["id"],
        "source":        row["source"],
        "resource_type": row["resource_type"],
        "started_at":    row["started_at"].isoformat() if row["started_at"] else None,
        "completed_at":  row["completed_at"].isoformat() if row["completed_at"] else None,
        "status":        row["status"],
        "new_count":     row["new_count"] or 0,
        "skipped_count": row["skipped_count"] or 0,
        "error_count":   row["error_count"] or 0,
        "output_tail":   row["output_tail"],
        "triggered_by":  row["triggered_by"],
    }
