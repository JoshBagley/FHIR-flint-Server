from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.main import Coding, CodeableConcept, Identifier, Meta, ContactPoint


class HumanName(BaseModel):
    use: Optional[str] = None
    text: Optional[str] = None
    family: Optional[str] = None
    given: Optional[List[str]] = None
    prefix: Optional[List[str]] = None
    suffix: Optional[List[str]] = None


class Address(BaseModel):
    use: Optional[str] = None
    type: Optional[str] = None
    text: Optional[str] = None
    line: Optional[List[str]] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postalCode: Optional[str] = None
    country: Optional[str] = None


class Reference(BaseModel):
    reference: Optional[str] = None
    display: Optional[str] = None
    type: Optional[str] = None
    identifier: Optional[Identifier] = None


class Patient(BaseModel):
    resourceType: Literal["Patient"] = "Patient"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    active: Optional[bool] = None
    name: Optional[List[HumanName]] = None
    telecom: Optional[List[ContactPoint]] = None
    gender: Optional[str] = None
    birthDate: Optional[str] = None
    deceasedBoolean: Optional[bool] = None
    deceasedDateTime: Optional[str] = None
    address: Optional[List[Address]] = None
    maritalStatus: Optional[CodeableConcept] = None
    multipleBirthBoolean: Optional[bool] = None
    multipleBirthInteger: Optional[int] = None
    generalPractitioner: Optional[List[Reference]] = None
    managingOrganization: Optional[Reference] = None
    communication: Optional[List[Dict[str, Any]]] = None
    link: Optional[List[Dict[str, Any]]] = None
    extension: Optional[List[Dict[str, Any]]] = None


class Observation(BaseModel):
    resourceType: Literal["Observation"] = "Observation"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    category: Optional[List[CodeableConcept]] = None
    code: Optional[CodeableConcept] = None
    subject: Optional[Reference] = None
    focus: Optional[List[Reference]] = None
    encounter: Optional[Reference] = None
    effectiveDateTime: Optional[str] = None
    effectivePeriod: Optional[Dict[str, Any]] = None
    issued: Optional[str] = None
    performer: Optional[List[Reference]] = None
    valueQuantity: Optional[Dict[str, Any]] = None
    valueCodeableConcept: Optional[CodeableConcept] = None
    valueString: Optional[str] = None
    valueBoolean: Optional[bool] = None
    valueInteger: Optional[int] = None
    valueSampledData: Optional[Dict[str, Any]] = None
    valueTime: Optional[str] = None
    valueDateTime: Optional[str] = None
    valuePeriod: Optional[Dict[str, Any]] = None
    dataAbsentReason: Optional[CodeableConcept] = None
    interpretation: Optional[List[CodeableConcept]] = None
    note: Optional[List[Dict[str, Any]]] = None
    bodySite: Optional[CodeableConcept] = None
    method: Optional[CodeableConcept] = None
    specimen: Optional[Reference] = None
    device: Optional[Reference] = None
    referenceRange: Optional[List[Dict[str, Any]]] = None
    hasMember: Optional[List[Reference]] = None
    derivedFrom: Optional[List[Reference]] = None
    component: Optional[List[Dict[str, Any]]] = None


class Condition(BaseModel):
    resourceType: Literal["Condition"] = "Condition"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    clinicalStatus: Optional[CodeableConcept] = None
    verificationStatus: Optional[CodeableConcept] = None
    category: Optional[List[CodeableConcept]] = None
    severity: Optional[CodeableConcept] = None
    code: Optional[CodeableConcept] = None
    bodySite: Optional[List[CodeableConcept]] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    onsetDateTime: Optional[str] = None
    onsetAge: Optional[Dict[str, Any]] = None
    onsetPeriod: Optional[Dict[str, Any]] = None
    onsetRange: Optional[Dict[str, Any]] = None
    onsetString: Optional[str] = None
    abatementDateTime: Optional[str] = None
    abatementAge: Optional[Dict[str, Any]] = None
    abatementPeriod: Optional[Dict[str, Any]] = None
    abatementRange: Optional[Dict[str, Any]] = None
    abatementString: Optional[str] = None
    recordedDate: Optional[str] = None
    recorder: Optional[Reference] = None
    asserter: Optional[Reference] = None
    stage: Optional[List[Dict[str, Any]]] = None
    evidence: Optional[List[Dict[str, Any]]] = None
    note: Optional[List[Dict[str, Any]]] = None


class Encounter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resourceType: Literal["Encounter"] = "Encounter"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    class_: Optional[Coding] = Field(None, alias="class")
    type: Optional[List[CodeableConcept]] = None
    serviceType: Optional[CodeableConcept] = None
    priority: Optional[CodeableConcept] = None
    subject: Optional[Reference] = None
    episodeOfCare: Optional[List[Reference]] = None
    basedOn: Optional[List[Reference]] = None
    participant: Optional[List[Dict[str, Any]]] = None
    appointment: Optional[List[Reference]] = None
    period: Optional[Dict[str, Any]] = None
    length: Optional[Dict[str, Any]] = None
    reasonCode: Optional[List[CodeableConcept]] = None
    reasonReference: Optional[List[Reference]] = None
    diagnosis: Optional[List[Dict[str, Any]]] = None
    account: Optional[List[Reference]] = None
    hospitalization: Optional[Dict[str, Any]] = None
    location: Optional[List[Dict[str, Any]]] = None
    serviceProvider: Optional[Reference] = None
    partOf: Optional[Reference] = None


class AllergyIntolerance(BaseModel):
    resourceType: Literal["AllergyIntolerance"] = "AllergyIntolerance"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    clinicalStatus: Optional[CodeableConcept] = None
    verificationStatus: Optional[CodeableConcept] = None
    type: Optional[str] = None
    category: Optional[List[str]] = None
    criticality: Optional[str] = None
    code: Optional[CodeableConcept] = None
    patient: Optional[Reference] = None
    encounter: Optional[Reference] = None
    onsetDateTime: Optional[str] = None
    onsetAge: Optional[Dict[str, Any]] = None
    onsetPeriod: Optional[Dict[str, Any]] = None
    onsetRange: Optional[Dict[str, Any]] = None
    onsetString: Optional[str] = None
    recordedDate: Optional[str] = None
    recorder: Optional[Reference] = None
    asserter: Optional[Reference] = None
    lastOccurrence: Optional[str] = None
    note: Optional[List[Dict[str, Any]]] = None
    reaction: Optional[List[Dict[str, Any]]] = None


class CareTeam(BaseModel):
    resourceType: Literal["CareTeam"] = "CareTeam"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    name: Optional[str] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    period: Optional[Dict[str, Any]] = None
    participant: Optional[List[Dict[str, Any]]] = None
    reasonCode: Optional[List[CodeableConcept]] = None
    reasonReference: Optional[List[Reference]] = None
    managingOrganization: Optional[List[Reference]] = None
    note: Optional[List[Dict[str, Any]]] = None
    extension: Optional[List[Dict[str, Any]]] = None


class CarePlan(BaseModel):
    resourceType: Literal["CarePlan"] = "CarePlan"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    text: Optional[Dict[str, Any]] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    intent: Optional[str] = None
    category: Optional[List[CodeableConcept]] = None
    title: Optional[str] = None
    description: Optional[str] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    period: Optional[Dict[str, Any]] = None
    created: Optional[str] = None
    author: Optional[Reference] = None
    contributor: Optional[List[Reference]] = None
    careTeam: Optional[List[Reference]] = None
    addresses: Optional[List[Reference]] = None
    supportingInfo: Optional[List[Reference]] = None
    goal: Optional[List[Reference]] = None
    activity: Optional[List[Dict[str, Any]]] = None
    note: Optional[List[Dict[str, Any]]] = None
    extension: Optional[List[Dict[str, Any]]] = None


class Immunization(BaseModel):
    resourceType: Literal["Immunization"] = "Immunization"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    statusReason: Optional[CodeableConcept] = None
    vaccineCode: Optional[CodeableConcept] = None
    patient: Optional[Reference] = None
    encounter: Optional[Reference] = None
    occurrenceDateTime: Optional[str] = None
    occurrenceString: Optional[str] = None
    recorded: Optional[str] = None
    primarySource: Optional[bool] = None
    reportOrigin: Optional[CodeableConcept] = None
    location: Optional[Reference] = None
    manufacturer: Optional[Reference] = None
    lotNumber: Optional[str] = None
    expirationDate: Optional[str] = None
    site: Optional[CodeableConcept] = None
    route: Optional[CodeableConcept] = None
    doseQuantity: Optional[Dict[str, Any]] = None
    performer: Optional[List[Dict[str, Any]]] = None
    note: Optional[List[Dict[str, Any]]] = None
    reasonCode: Optional[List[CodeableConcept]] = None
    reasonReference: Optional[List[Reference]] = None
    isSubpotent: Optional[bool] = None
    subpotentReason: Optional[List[CodeableConcept]] = None
    education: Optional[List[Dict[str, Any]]] = None
    programEligibility: Optional[List[CodeableConcept]] = None
    fundingSource: Optional[CodeableConcept] = None
    reaction: Optional[List[Dict[str, Any]]] = None
    protocolApplied: Optional[List[Dict[str, Any]]] = None


class DeviceUdiCarrier(BaseModel):
    deviceIdentifier: Optional[str] = None
    issuer: Optional[str] = None
    jurisdiction: Optional[str] = None
    carrierAIDC: Optional[str] = None
    carrierHRF: Optional[str] = None
    entryType: Optional[str] = None


class Device(BaseModel):
    resourceType: Literal["Device"] = "Device"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    udiCarrier: Optional[List[DeviceUdiCarrier]] = None
    status: Optional[str] = None
    distinctIdentifier: Optional[str] = None
    manufacturer: Optional[str] = None
    manufactureDate: Optional[str] = None
    expirationDate: Optional[str] = None
    lotNumber: Optional[str] = None
    serialNumber: Optional[str] = None
    deviceName: Optional[List[Dict[str, Any]]] = None
    modelNumber: Optional[str] = None
    type: Optional[CodeableConcept] = None
    patient: Optional[Reference] = None
    note: Optional[List[Dict[str, Any]]] = None
    extension: Optional[List[Dict[str, Any]]] = None
    text: Optional[Dict[str, Any]] = None


class GoalTarget(BaseModel):
    measure: Optional[CodeableConcept] = None
    detailQuantity: Optional[Dict[str, Any]] = None
    detailRange: Optional[Dict[str, Any]] = None
    detailCodeableConcept: Optional[CodeableConcept] = None
    detailString: Optional[str] = None
    detailBoolean: Optional[bool] = None
    detailInteger: Optional[int] = None
    detailRatio: Optional[Dict[str, Any]] = None
    dueDate: Optional[str] = None
    dueDuration: Optional[Dict[str, Any]] = None


class Goal(BaseModel):
    resourceType: Literal["Goal"] = "Goal"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    lifecycleStatus: Optional[str] = None
    achievementStatus: Optional[CodeableConcept] = None
    category: Optional[List[CodeableConcept]] = None
    priority: Optional[CodeableConcept] = None
    description: Optional[CodeableConcept] = None
    subject: Optional[Reference] = None
    startDate: Optional[str] = None
    startCodeableConcept: Optional[CodeableConcept] = None
    target: Optional[List[GoalTarget]] = None
    statusDate: Optional[str] = None
    statusReason: Optional[str] = None
    expressedBy: Optional[Reference] = None
    addresses: Optional[List[Reference]] = None
    note: Optional[List[Dict[str, Any]]] = None
    outcomeCode: Optional[List[CodeableConcept]] = None
    outcomeReference: Optional[List[Reference]] = None
    extension: Optional[List[Dict[str, Any]]] = None


class DocumentReferenceContent(BaseModel):
    attachment: Dict[str, Any]
    format: Optional[Coding] = None


class DocumentReference(BaseModel):
    resourceType: Literal["DocumentReference"] = "DocumentReference"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    masterIdentifier: Optional[Identifier] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    docStatus: Optional[str] = None
    type: Optional[CodeableConcept] = None
    category: Optional[List[CodeableConcept]] = None
    subject: Optional[Reference] = None
    date: Optional[str] = None
    author: Optional[List[Reference]] = None
    authenticator: Optional[Reference] = None
    custodian: Optional[Reference] = None
    relatesTo: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None
    securityLabel: Optional[List[CodeableConcept]] = None
    content: Optional[List[DocumentReferenceContent]] = None
    context: Optional[Dict[str, Any]] = None
    text: Optional[Dict[str, Any]] = None
    extension: Optional[List[Dict[str, Any]]] = None


class Specimen(BaseModel):
    resourceType: Literal["Specimen"] = "Specimen"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    accessionIdentifier: Optional[Identifier] = None
    status: Optional[str] = None
    type: Optional[CodeableConcept] = None
    subject: Optional[Reference] = None
    receivedTime: Optional[str] = None
    parent: Optional[List[Reference]] = None
    request: Optional[List[Reference]] = None
    collection: Optional[Dict[str, Any]] = None
    processing: Optional[List[Dict[str, Any]]] = None
    container: Optional[List[Dict[str, Any]]] = None
    condition: Optional[List[CodeableConcept]] = None
    note: Optional[List[Dict[str, Any]]] = None
