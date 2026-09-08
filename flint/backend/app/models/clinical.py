from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.main import CodeableConcept, Coding, ContactPoint, Identifier, Meta


class HumanName(BaseModel):
    use: str | None = None
    text: str | None = None
    family: str | None = None
    given: list[str] | None = None
    prefix: list[str] | None = None
    suffix: list[str] | None = None


class Address(BaseModel):
    use: str | None = None
    type: str | None = None
    text: str | None = None
    line: list[str] | None = None
    city: str | None = None
    state: str | None = None
    postalCode: str | None = None
    country: str | None = None


class Reference(BaseModel):
    reference: str | None = None
    display: str | None = None
    type: str | None = None
    identifier: Identifier | None = None


class Patient(BaseModel):
    resourceType: Literal["Patient"] = "Patient"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    active: bool | None = None
    name: list[HumanName] | None = None
    telecom: list[ContactPoint] | None = None
    gender: str | None = None
    birthDate: str | None = None
    deceasedBoolean: bool | None = None
    deceasedDateTime: str | None = None
    address: list[Address] | None = None
    maritalStatus: CodeableConcept | None = None
    multipleBirthBoolean: bool | None = None
    multipleBirthInteger: int | None = None
    generalPractitioner: list[Reference] | None = None
    managingOrganization: Reference | None = None
    communication: list[dict[str, Any]] | None = None
    link: list[dict[str, Any]] | None = None
    extension: list[dict[str, Any]] | None = None


class Observation(BaseModel):
    resourceType: Literal["Observation"] = "Observation"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    category: list[CodeableConcept] | None = None
    code: CodeableConcept | None = None
    subject: Reference | None = None
    focus: list[Reference] | None = None
    encounter: Reference | None = None
    effectiveDateTime: str | None = None
    effectivePeriod: dict[str, Any] | None = None
    issued: str | None = None
    performer: list[Reference] | None = None
    valueQuantity: dict[str, Any] | None = None
    valueCodeableConcept: CodeableConcept | None = None
    valueString: str | None = None
    valueBoolean: bool | None = None
    valueInteger: int | None = None
    valueSampledData: dict[str, Any] | None = None
    valueTime: str | None = None
    valueDateTime: str | None = None
    valuePeriod: dict[str, Any] | None = None
    dataAbsentReason: CodeableConcept | None = None
    interpretation: list[CodeableConcept] | None = None
    note: list[dict[str, Any]] | None = None
    bodySite: CodeableConcept | None = None
    method: CodeableConcept | None = None
    specimen: Reference | None = None
    device: Reference | None = None
    referenceRange: list[dict[str, Any]] | None = None
    hasMember: list[Reference] | None = None
    derivedFrom: list[Reference] | None = None
    component: list[dict[str, Any]] | None = None


class Condition(BaseModel):
    resourceType: Literal["Condition"] = "Condition"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    clinicalStatus: CodeableConcept | None = None
    verificationStatus: CodeableConcept | None = None
    category: list[CodeableConcept] | None = None
    severity: CodeableConcept | None = None
    code: CodeableConcept | None = None
    bodySite: list[CodeableConcept] | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    onsetDateTime: str | None = None
    onsetAge: dict[str, Any] | None = None
    onsetPeriod: dict[str, Any] | None = None
    onsetRange: dict[str, Any] | None = None
    onsetString: str | None = None
    abatementDateTime: str | None = None
    abatementAge: dict[str, Any] | None = None
    abatementPeriod: dict[str, Any] | None = None
    abatementRange: dict[str, Any] | None = None
    abatementString: str | None = None
    recordedDate: str | None = None
    recorder: Reference | None = None
    asserter: Reference | None = None
    stage: list[dict[str, Any]] | None = None
    evidence: list[dict[str, Any]] | None = None
    note: list[dict[str, Any]] | None = None


class Encounter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resourceType: Literal["Encounter"] = "Encounter"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    class_: Coding | None = Field(None, alias="class")
    type: list[CodeableConcept] | None = None
    serviceType: CodeableConcept | None = None
    priority: CodeableConcept | None = None
    subject: Reference | None = None
    episodeOfCare: list[Reference] | None = None
    basedOn: list[Reference] | None = None
    participant: list[dict[str, Any]] | None = None
    appointment: list[Reference] | None = None
    period: dict[str, Any] | None = None
    length: dict[str, Any] | None = None
    reasonCode: list[CodeableConcept] | None = None
    reasonReference: list[Reference] | None = None
    diagnosis: list[dict[str, Any]] | None = None
    account: list[Reference] | None = None
    hospitalization: dict[str, Any] | None = None
    location: list[dict[str, Any]] | None = None
    serviceProvider: Reference | None = None
    partOf: Reference | None = None


class AllergyIntolerance(BaseModel):
    resourceType: Literal["AllergyIntolerance"] = "AllergyIntolerance"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    clinicalStatus: CodeableConcept | None = None
    verificationStatus: CodeableConcept | None = None
    type: str | None = None
    category: list[str] | None = None
    criticality: str | None = None
    code: CodeableConcept | None = None
    patient: Reference | None = None
    encounter: Reference | None = None
    onsetDateTime: str | None = None
    onsetAge: dict[str, Any] | None = None
    onsetPeriod: dict[str, Any] | None = None
    onsetRange: dict[str, Any] | None = None
    onsetString: str | None = None
    recordedDate: str | None = None
    recorder: Reference | None = None
    asserter: Reference | None = None
    lastOccurrence: str | None = None
    note: list[dict[str, Any]] | None = None
    reaction: list[dict[str, Any]] | None = None


class CareTeam(BaseModel):
    resourceType: Literal["CareTeam"] = "CareTeam"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    name: str | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    period: dict[str, Any] | None = None
    participant: list[dict[str, Any]] | None = None
    reasonCode: list[CodeableConcept] | None = None
    reasonReference: list[Reference] | None = None
    managingOrganization: list[Reference] | None = None
    note: list[dict[str, Any]] | None = None
    extension: list[dict[str, Any]] | None = None


class CarePlan(BaseModel):
    resourceType: Literal["CarePlan"] = "CarePlan"
    id: str | None = None
    meta: Meta | None = None
    text: dict[str, Any] | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    intent: str | None = None
    category: list[CodeableConcept] | None = None
    title: str | None = None
    description: str | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    period: dict[str, Any] | None = None
    created: str | None = None
    author: Reference | None = None
    contributor: list[Reference] | None = None
    careTeam: list[Reference] | None = None
    addresses: list[Reference] | None = None
    supportingInfo: list[Reference] | None = None
    goal: list[Reference] | None = None
    activity: list[dict[str, Any]] | None = None
    note: list[dict[str, Any]] | None = None
    extension: list[dict[str, Any]] | None = None


class Immunization(BaseModel):
    resourceType: Literal["Immunization"] = "Immunization"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    statusReason: CodeableConcept | None = None
    vaccineCode: CodeableConcept | None = None
    patient: Reference | None = None
    encounter: Reference | None = None
    occurrenceDateTime: str | None = None
    occurrenceString: str | None = None
    recorded: str | None = None
    primarySource: bool | None = None
    reportOrigin: CodeableConcept | None = None
    location: Reference | None = None
    manufacturer: Reference | None = None
    lotNumber: str | None = None
    expirationDate: str | None = None
    site: CodeableConcept | None = None
    route: CodeableConcept | None = None
    doseQuantity: dict[str, Any] | None = None
    performer: list[dict[str, Any]] | None = None
    note: list[dict[str, Any]] | None = None
    reasonCode: list[CodeableConcept] | None = None
    reasonReference: list[Reference] | None = None
    isSubpotent: bool | None = None
    subpotentReason: list[CodeableConcept] | None = None
    education: list[dict[str, Any]] | None = None
    programEligibility: list[CodeableConcept] | None = None
    fundingSource: CodeableConcept | None = None
    reaction: list[dict[str, Any]] | None = None
    protocolApplied: list[dict[str, Any]] | None = None


class DeviceUdiCarrier(BaseModel):
    deviceIdentifier: str | None = None
    issuer: str | None = None
    jurisdiction: str | None = None
    carrierAIDC: str | None = None
    carrierHRF: str | None = None
    entryType: str | None = None


class Device(BaseModel):
    resourceType: Literal["Device"] = "Device"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    udiCarrier: list[DeviceUdiCarrier] | None = None
    status: str | None = None
    distinctIdentifier: str | None = None
    manufacturer: str | None = None
    manufactureDate: str | None = None
    expirationDate: str | None = None
    lotNumber: str | None = None
    serialNumber: str | None = None
    deviceName: list[dict[str, Any]] | None = None
    modelNumber: str | None = None
    type: CodeableConcept | None = None
    patient: Reference | None = None
    note: list[dict[str, Any]] | None = None
    extension: list[dict[str, Any]] | None = None
    text: dict[str, Any] | None = None


class GoalTarget(BaseModel):
    measure: CodeableConcept | None = None
    detailQuantity: dict[str, Any] | None = None
    detailRange: dict[str, Any] | None = None
    detailCodeableConcept: CodeableConcept | None = None
    detailString: str | None = None
    detailBoolean: bool | None = None
    detailInteger: int | None = None
    detailRatio: dict[str, Any] | None = None
    dueDate: str | None = None
    dueDuration: dict[str, Any] | None = None


class Goal(BaseModel):
    resourceType: Literal["Goal"] = "Goal"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    lifecycleStatus: str | None = None
    achievementStatus: CodeableConcept | None = None
    category: list[CodeableConcept] | None = None
    priority: CodeableConcept | None = None
    description: CodeableConcept | None = None
    subject: Reference | None = None
    startDate: str | None = None
    startCodeableConcept: CodeableConcept | None = None
    target: list[GoalTarget] | None = None
    statusDate: str | None = None
    statusReason: str | None = None
    expressedBy: Reference | None = None
    addresses: list[Reference] | None = None
    note: list[dict[str, Any]] | None = None
    outcomeCode: list[CodeableConcept] | None = None
    outcomeReference: list[Reference] | None = None
    extension: list[dict[str, Any]] | None = None


class DocumentReferenceContent(BaseModel):
    attachment: dict[str, Any]
    format: Coding | None = None


class DocumentReference(BaseModel):
    resourceType: Literal["DocumentReference"] = "DocumentReference"
    id: str | None = None
    meta: Meta | None = None
    masterIdentifier: Identifier | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    docStatus: str | None = None
    type: CodeableConcept | None = None
    category: list[CodeableConcept] | None = None
    subject: Reference | None = None
    date: str | None = None
    author: list[Reference] | None = None
    authenticator: Reference | None = None
    custodian: Reference | None = None
    relatesTo: list[dict[str, Any]] | None = None
    description: str | None = None
    securityLabel: list[CodeableConcept] | None = None
    content: list[DocumentReferenceContent] | None = None
    context: dict[str, Any] | None = None
    text: dict[str, Any] | None = None
    extension: list[dict[str, Any]] | None = None


class Specimen(BaseModel):
    resourceType: Literal["Specimen"] = "Specimen"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    accessionIdentifier: Identifier | None = None
    status: str | None = None
    type: CodeableConcept | None = None
    subject: Reference | None = None
    receivedTime: str | None = None
    parent: list[Reference] | None = None
    request: list[Reference] | None = None
    collection: dict[str, Any] | None = None
    processing: list[dict[str, Any]] | None = None
    container: list[dict[str, Any]] | None = None
    condition: list[CodeableConcept] | None = None
    note: list[dict[str, Any]] | None = None


class RelatedPerson(BaseModel):
    resourceType: Literal["RelatedPerson"] = "RelatedPerson"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    active: bool | None = None
    patient: Reference | None = None
    relationship: list[CodeableConcept] | None = None
    name: list[HumanName] | None = None
    telecom: list[ContactPoint] | None = None
    gender: str | None = None
    birthDate: str | None = None
    address: list[Address] | None = None
    photo: list[dict[str, Any]] | None = None
    period: dict[str, Any] | None = None
    communication: list[dict[str, Any]] | None = None
    extension: list[dict[str, Any]] | None = None
    text: dict[str, Any] | None = None


class Provenance(BaseModel):
    resourceType: Literal["Provenance"] = "Provenance"
    id: str | None = None
    meta: Meta | None = None
    text: dict[str, Any] | None = None
    target: list[Reference] | None = None
    occurredPeriod: dict[str, Any] | None = None
    occurredDateTime: str | None = None
    recorded: str | None = None
    policy: list[str] | None = None
    location: Reference | None = None
    reason: list[dict[str, Any]] | None = None
    activity: dict[str, Any] | None = None
    agent: list[dict[str, Any]] | None = None
    entity: list[dict[str, Any]] | None = None
    signature: list[dict[str, Any]] | None = None
