from typing import Any, Literal

from pydantic import BaseModel

from app.main import Identifier, Meta


class StructureDefinition(BaseModel):
    """Minimal StructureDefinition model for storing US Core and other profiles.

    Uses extra='allow' so the full IG snapshot/differential JSON is accepted
    without modelling every nested element.
    """
    resourceType: Literal["StructureDefinition"] = "StructureDefinition"
    id: str | None = None
    meta: Meta | None = None
    url: str | None = None
    identifier: list[Identifier] | None = None
    version: str | None = None
    name: str | None = None
    title: str | None = None
    status: str | None = None
    experimental: bool | None = None
    date: str | None = None
    publisher: str | None = None
    description: str | None = None
    purpose: str | None = None
    kind: str | None = None       # resource | complex-type | primitive-type | logical
    abstract: bool | None = None
    type: str | None = None       # FHIR resource type this profile constrains
    baseDefinition: str | None = None
    derivation: str | None = None # constraint | specialization
    snapshot: dict[str, Any] | None = None
    differential: dict[str, Any] | None = None

    model_config = {"extra": "allow"}
