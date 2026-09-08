from typing import Any, Literal

from pydantic import BaseModel

from app.main import CodeableConcept, Coding, ContactPoint, Identifier, Meta
from app.models.clinical import Address, HumanName, Reference


class Organization(BaseModel):
    resourceType: Literal["Organization"] = "Organization"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    active: bool | None = None
    type: list[CodeableConcept] | None = None
    name: str | None = None
    alias: list[str] | None = None
    telecom: list[ContactPoint] | None = None
    address: list[Address] | None = None
    partOf: Reference | None = None
    contact: list[dict[str, Any]] | None = None
    endpoint: list[Reference] | None = None


class Practitioner(BaseModel):
    resourceType: Literal["Practitioner"] = "Practitioner"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    active: bool | None = None
    name: list[HumanName] | None = None
    telecom: list[ContactPoint] | None = None
    address: list[Address] | None = None
    gender: str | None = None
    birthDate: str | None = None
    photo: list[dict[str, Any]] | None = None
    qualification: list[dict[str, Any]] | None = None
    communication: list[CodeableConcept] | None = None


class PractitionerRole(BaseModel):
    resourceType: Literal["PractitionerRole"] = "PractitionerRole"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    active: bool | None = None
    period: dict[str, Any] | None = None
    practitioner: Reference | None = None
    organization: Reference | None = None
    code: list[CodeableConcept] | None = None
    specialty: list[CodeableConcept] | None = None
    location: list[Reference] | None = None
    healthcareService: list[Reference] | None = None
    telecom: list[ContactPoint] | None = None
    availableTime: list[dict[str, Any]] | None = None
    notAvailable: list[dict[str, Any]] | None = None
    availabilityExceptions: str | None = None
    endpoint: list[Reference] | None = None


class Endpoint(BaseModel):
    resourceType: Literal["Endpoint"] = "Endpoint"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    connectionType: Coding | None = None
    name: str | None = None
    managingOrganization: Reference | None = None
    contact: list[ContactPoint] | None = None
    period: dict[str, Any] | None = None
    payloadType: list[CodeableConcept] | None = None
    payloadMimeType: list[str] | None = None
    address: str | None = None
    header: list[str] | None = None


class Location(BaseModel):
    resourceType: Literal["Location"] = "Location"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    operationalStatus: Coding | None = None
    name: str | None = None
    alias: list[str] | None = None
    description: str | None = None
    mode: str | None = None
    type: list[CodeableConcept] | None = None
    telecom: list[ContactPoint] | None = None
    address: Address | None = None
    physicalType: CodeableConcept | None = None
    position: dict[str, Any] | None = None
    managingOrganization: Reference | None = None
    partOf: Reference | None = None
    hoursOfOperation: list[dict[str, Any]] | None = None
    availabilityExceptions: str | None = None
    endpoint: list[Reference] | None = None
