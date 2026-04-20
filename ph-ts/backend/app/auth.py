import os
from fastapi import Header, HTTPException

_API_KEY = os.environ.get("ADMIN_API_KEY", "")


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Require X-API-Key header when ADMIN_API_KEY env var is set.
    When ADMIN_API_KEY is unset (local dev), the check is skipped."""
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
