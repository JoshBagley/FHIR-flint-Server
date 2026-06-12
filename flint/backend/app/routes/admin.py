"""
Admin endpoints — import sync status.

GET  /admin/sync/status            List recent sync runs
GET  /admin/sync/status/{run_id}   Status of a specific run

Sync runs are inserted into sync_log by the migration scripts in migration/.
These endpoints expose their status for monitoring.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query

from app import state
from app.auth import require_access

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_access)])
logger = logging.getLogger(__name__)


@router.get("/sync/status")
async def list_sync_status(
    limit: int = Query(10, ge=1, le=50, description="Number of recent runs to return"),
):
    """Return the most recent import sync runs with counts and status.

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
