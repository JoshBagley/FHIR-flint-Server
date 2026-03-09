"""
Shared application state — holds global service instances
so both main.py and routers can import without circular deps.
"""
from typing import Optional

db = None
search_engine = None
cache = None
