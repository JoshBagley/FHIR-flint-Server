"""
Shared application state — holds global service instances
so both main.py and routers can import without circular deps.
"""

from typing import Any

db: Any = None
search_engine: Any = None
cache: Any = None
