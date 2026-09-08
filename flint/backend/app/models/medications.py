from typing import Any, Literal

from pydantic import BaseModel

from app.main import CodeableConcept, Identifier, Meta
from app.models.clinical import Reference


class MedicationRequest(BaseModel):
    resourceType: Literal["MedicationRequest"] = "MedicationRequest"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    statusReason: CodeableConcept | None = None
    intent: str | None = None
    category: list[CodeableConcept] | None = None
    priority: str | None = None
    doNotPerform: bool | None = None
    medicationCodeableConcept: CodeableConcept | None = None
    medicationReference: Reference | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    supportingInformation: list[Reference] | None = None
    authoredOn: str | None = None
    requester: Reference | None = None
    performer: Reference | None = None
    performerType: CodeableConcept | None = None
    recorder: Reference | None = None
    reasonCode: list[CodeableConcept] | None = None
    reasonReference: list[Reference] | None = None
    instantiatesCanonical: list[str] | None = None
    instantiatesUri: list[str] | None = None
    basedOn: list[Reference] | None = None
    groupIdentifier: Identifier | None = None
    courseOfTherapyType: CodeableConcept | None = None
    insurance: list[Reference] | None = None
    note: list[dict[str, Any]] | None = None
    dosageInstruction: list[dict[str, Any]] | None = None
    dispenseRequest: dict[str, Any] | None = None
    substitution: dict[str, Any] | None = None
    priorPrescription: Reference | None = None
    detectedIssue: list[Reference] | None = None
    eventHistory: list[Reference] | None = None


class Procedure(BaseModel):
    resourceType: Literal["Procedure"] = "Procedure"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    instantiatesCanonical: list[str] | None = None
    instantiatesUri: list[str] | None = None
    basedOn: list[Reference] | None = None
    partOf: list[Reference] | None = None
    status: str | None = None
    statusReason: CodeableConcept | None = None
    category: CodeableConcept | None = None
    code: CodeableConcept | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    performedDateTime: str | None = None
    performedPeriod: dict[str, Any] | None = None
    performedString: str | None = None
    performedAge: dict[str, Any] | None = None
    performedRange: dict[str, Any] | None = None
    recorder: Reference | None = None
    asserter: Reference | None = None
    performer: list[dict[str, Any]] | None = None
    location: Reference | None = None
    reasonCode: list[CodeableConcept] | None = None
    reasonReference: list[Reference] | None = None
    bodySite: list[CodeableConcept] | None = None
    outcome: CodeableConcept | None = None
    report: list[Reference] | None = None
    complication: list[CodeableConcept] | None = None
    complicationDetail: list[Reference] | None = None
    followUp: list[CodeableConcept] | None = None
    note: list[dict[str, Any]] | None = None
    focalDevice: list[dict[str, Any]] | None = None
    usedReference: list[Reference] | None = None
    usedCode: list[CodeableConcept] | None = None


class MedicationDispense(BaseModel):
    resourceType: Literal["MedicationDispense"] = "MedicationDispense"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    statusReasonCodeableConcept: CodeableConcept | None = None
    statusReasonReference: Reference | None = None
    category: CodeableConcept | None = None
    medicationCodeableConcept: CodeableConcept | None = None
    medicationReference: Reference | None = None
    subject: Reference | None = None
    context: Reference | None = None
    performer: list[dict[str, Any]] | None = None
    location: Reference | None = None
    authorizingPrescription: list[Reference] | None = None
    type: CodeableConcept | None = None
    quantity: dict[str, Any] | None = None
    daysSupply: dict[str, Any] | None = None
    whenPrepared: str | None = None
    whenHandedOver: str | None = None
    destination: Reference | None = None
    receiver: list[Reference] | None = None
    note: list[dict[str, Any]] | None = None
    dosageInstruction: list[dict[str, Any]] | None = None
    substitution: dict[str, Any] | None = None
    extension: list[dict[str, Any]] | None = None


class DiagnosticReport(BaseModel):
    resourceType: Literal["DiagnosticReport"] = "DiagnosticReport"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    basedOn: list[Reference] | None = None
    status: str | None = None
    category: list[CodeableConcept] | None = None
    code: CodeableConcept | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    effectiveDateTime: str | None = None
    effectivePeriod: dict[str, Any] | None = None
    issued: str | None = None
    performer: list[Reference] | None = None
    resultsInterpreter: list[Reference] | None = None
    specimen: list[Reference] | None = None
    result: list[Reference] | None = None
    imagingStudy: list[Reference] | None = None
    media: list[dict[str, Any]] | None = None
    conclusion: str | None = None
    conclusionCode: list[CodeableConcept] | None = None
    presentedForm: list[dict[str, Any]] | None = None
