from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel

from app.main import Coding, CodeableConcept, Identifier, Meta, ContactPoint
from app.models.clinical import HumanName, Address, Reference


class Organization(BaseModel):
    resourceType: Literal["Organization"] = "Organization"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    active: Optional[bool] = None
    type: Optional[List[CodeableConcept]] = None
    name: Optional[str] = None
    alias: Optional[List[str]] = None
    telecom: Optional[List[ContactPoint]] = None
    address: Optional[List[Address]] = None
    partOf: Optional[Reference] = None
    contact: Optional[List[Dict[str, Any]]] = None
    endpoint: Optional[List[Reference]] = None


class Practitioner(BaseModel):
    resourceType: Literal["Practitioner"] = "Practitioner"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    active: Optional[bool] = None
    name: Optional[List[HumanName]] = None
    telecom: Optional[List[ContactPoint]] = None
    address: Optional[List[Address]] = None
    gender: Optional[str] = None
    birthDate: Optional[str] = None
    photo: Optional[List[Dict[str, Any]]] = None
    qualification: Optional[List[Dict[str, Any]]] = None
    communication: Optional[List[CodeableConcept]] = None


class PractitionerRole(BaseModel):
    resourceType: Literal["PractitionerRole"] = "PractitionerRole"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    active: Optional[bool] = None
    period: Optional[Dict[str, Any]] = None
    practitioner: Optional[Reference] = None
    organization: Optional[Reference] = None
    code: Optional[List[CodeableConcept]] = None
    specialty: Optional[List[CodeableConcept]] = None
    location: Optional[List[Reference]] = None
    healthcareService: Optional[List[Reference]] = None
    telecom: Optional[List[ContactPoint]] = None
    availableTime: Optional[List[Dict[str, Any]]] = None
    notAvailable: Optional[List[Dict[str, Any]]] = None
    availabilityExceptions: Optional[str] = None
    endpoint: Optional[List[Reference]] = None


class Location(BaseModel):
    resourceType: Literal["Location"] = "Location"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    operationalStatus: Optional[Coding] = None
    name: Optional[str] = None
    alias: Optional[List[str]] = None
    description: Optional[str] = None
    mode: Optional[str] = None
    type: Optional[List[CodeableConcept]] = None
    telecom: Optional[List[ContactPoint]] = None
    address: Optional[Address] = None
    physicalType: Optional[CodeableConcept] = None
    position: Optional[Dict[str, Any]] = None
    managingOrganization: Optional[Reference] = None
    partOf: Optional[Reference] = None
    hoursOfOperation: Optional[List[Dict[str, Any]]] = None
    availabilityExceptions: Optional[str] = None
    endpoint: Optional[List[Reference]] = None
