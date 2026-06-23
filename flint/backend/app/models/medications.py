from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel

from app.main import CodeableConcept, Identifier, Meta
from app.models.clinical import Reference


class MedicationRequest(BaseModel):
    resourceType: Literal["MedicationRequest"] = "MedicationRequest"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    statusReason: Optional[CodeableConcept] = None
    intent: Optional[str] = None
    category: Optional[List[CodeableConcept]] = None
    priority: Optional[str] = None
    doNotPerform: Optional[bool] = None
    medicationCodeableConcept: Optional[CodeableConcept] = None
    medicationReference: Optional[Reference] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    supportingInformation: Optional[List[Reference]] = None
    authoredOn: Optional[str] = None
    requester: Optional[Reference] = None
    performer: Optional[Reference] = None
    performerType: Optional[CodeableConcept] = None
    recorder: Optional[Reference] = None
    reasonCode: Optional[List[CodeableConcept]] = None
    reasonReference: Optional[List[Reference]] = None
    instantiatesCanonical: Optional[List[str]] = None
    instantiatesUri: Optional[List[str]] = None
    basedOn: Optional[List[Reference]] = None
    groupIdentifier: Optional[Identifier] = None
    courseOfTherapyType: Optional[CodeableConcept] = None
    insurance: Optional[List[Reference]] = None
    note: Optional[List[Dict[str, Any]]] = None
    dosageInstruction: Optional[List[Dict[str, Any]]] = None
    dispenseRequest: Optional[Dict[str, Any]] = None
    substitution: Optional[Dict[str, Any]] = None
    priorPrescription: Optional[Reference] = None
    detectedIssue: Optional[List[Reference]] = None
    eventHistory: Optional[List[Reference]] = None


class Procedure(BaseModel):
    resourceType: Literal["Procedure"] = "Procedure"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    instantiatesCanonical: Optional[List[str]] = None
    instantiatesUri: Optional[List[str]] = None
    basedOn: Optional[List[Reference]] = None
    partOf: Optional[List[Reference]] = None
    status: Optional[str] = None
    statusReason: Optional[CodeableConcept] = None
    category: Optional[CodeableConcept] = None
    code: Optional[CodeableConcept] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    performedDateTime: Optional[str] = None
    performedPeriod: Optional[Dict[str, Any]] = None
    performedString: Optional[str] = None
    performedAge: Optional[Dict[str, Any]] = None
    performedRange: Optional[Dict[str, Any]] = None
    recorder: Optional[Reference] = None
    asserter: Optional[Reference] = None
    performer: Optional[List[Dict[str, Any]]] = None
    location: Optional[Reference] = None
    reasonCode: Optional[List[CodeableConcept]] = None
    reasonReference: Optional[List[Reference]] = None
    bodySite: Optional[List[CodeableConcept]] = None
    outcome: Optional[CodeableConcept] = None
    report: Optional[List[Reference]] = None
    complication: Optional[List[CodeableConcept]] = None
    complicationDetail: Optional[List[Reference]] = None
    followUp: Optional[List[CodeableConcept]] = None
    note: Optional[List[Dict[str, Any]]] = None
    focalDevice: Optional[List[Dict[str, Any]]] = None
    usedReference: Optional[List[Reference]] = None
    usedCode: Optional[List[CodeableConcept]] = None


class DiagnosticReport(BaseModel):
    resourceType: Literal["DiagnosticReport"] = "DiagnosticReport"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    basedOn: Optional[List[Reference]] = None
    status: Optional[str] = None
    category: Optional[List[CodeableConcept]] = None
    code: Optional[CodeableConcept] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    effectiveDateTime: Optional[str] = None
    effectivePeriod: Optional[Dict[str, Any]] = None
    issued: Optional[str] = None
    performer: Optional[List[Reference]] = None
    resultsInterpreter: Optional[List[Reference]] = None
    specimen: Optional[List[Reference]] = None
    result: Optional[List[Reference]] = None
    imagingStudy: Optional[List[Reference]] = None
    media: Optional[List[Dict[str, Any]]] = None
    conclusion: Optional[str] = None
    conclusionCode: Optional[List[CodeableConcept]] = None
    presentedForm: Optional[List[Dict[str, Any]]] = None
