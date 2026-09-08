from typing import Any

RESOURCE_REGISTRY: list[dict[str, Any]] = []


def register_resource(entry: dict[str, Any]) -> None:
    RESOURCE_REGISTRY.append(entry)
