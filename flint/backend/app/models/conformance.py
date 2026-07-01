from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel

from app.main import Meta, Identifier, ContactPoint, CodeableConcept


class StructureDefinition(BaseModel):
    """Minimal StructureDefinition model for storing US Core and other profiles.

    Uses extra='allow' so the full IG snapshot/differential JSON is accepted
    without modelling every nested element.
    """
    resourceType: Literal["StructureDefinition"] = "StructureDefinition"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    url: Optional[str] = None
    identifier: Optional[List[Identifier]] = None
    version: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    experimental: Optional[bool] = None
    date: Optional[str] = None
    publisher: Optional[str] = None
    description: Optional[str] = None
    purpose: Optional[str] = None
    kind: Optional[str] = None       # resource | complex-type | primitive-type | logical
    abstract: Optional[bool] = None
    type: Optional[str] = None       # FHIR resource type this profile constrains
    baseDefinition: Optional[str] = None
    derivation: Optional[str] = None # constraint | specialization
    snapshot: Optional[Dict[str, Any]] = None
    differential: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}
