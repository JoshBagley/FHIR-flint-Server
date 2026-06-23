from typing import Dict, List, Any

RESOURCE_REGISTRY: List[Dict[str, Any]] = []


def register_resource(entry: Dict[str, Any]) -> None:
    RESOURCE_REGISTRY.append(entry)
