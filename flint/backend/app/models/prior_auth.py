from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field, ConfigDict

from app.main import CodeableConcept, Identifier, Meta
from app.models.clinical import Reference


class QuestionnaireItem(BaseModel):
    linkId: str
    definition: Optional[str] = None
    code: Optional[List[Dict[str, Any]]] = None
    prefix: Optional[str] = None
    text: Optional[str] = None
    type: Optional[str] = None
    enableWhen: Optional[List[Dict[str, Any]]] = None
    enableBehavior: Optional[str] = None
    required: Optional[bool] = None
    repeats: Optional[bool] = None
    readOnly: Optional[bool] = None
    maxLength: Optional[int] = None
    answerValueSet: Optional[str] = None
    answerOption: Optional[List[Dict[str, Any]]] = None
    initial: Optional[List[Dict[str, Any]]] = None
    item: Optional[List["QuestionnaireItem"]] = None


QuestionnaireItem.model_rebuild()


class Questionnaire(BaseModel):
    resourceType: Literal["Questionnaire"] = "Questionnaire"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    url: Optional[str] = None
    identifier: Optional[List[Identifier]] = None
    version: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    derivedFrom: Optional[List[str]] = None
    status: Optional[str] = None
    experimental: Optional[bool] = None
    subjectType: Optional[List[str]] = None
    date: Optional[str] = None
    publisher: Optional[str] = None
    contact: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None
    useContext: Optional[List[Dict[str, Any]]] = None
    jurisdiction: Optional[List[CodeableConcept]] = None
    purpose: Optional[str] = None
    copyright: Optional[str] = None
    approvalDate: Optional[str] = None
    lastReviewDate: Optional[str] = None
    effectivePeriod: Optional[Dict[str, Any]] = None
    code: Optional[List[Dict[str, Any]]] = None
    item: Optional[List[QuestionnaireItem]] = None


class QuestionnaireResponseItem(BaseModel):
    linkId: str
    definition: Optional[str] = None
    text: Optional[str] = None
    answer: Optional[List[Dict[str, Any]]] = None
    item: Optional[List["QuestionnaireResponseItem"]] = None


QuestionnaireResponseItem.model_rebuild()


class QuestionnaireResponse(BaseModel):
    resourceType: Literal["QuestionnaireResponse"] = "QuestionnaireResponse"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[Identifier] = None
    basedOn: Optional[List[Reference]] = None
    partOf: Optional[List[Reference]] = None
    questionnaire: Optional[str] = None
    status: Optional[str] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    authored: Optional[str] = None
    author: Optional[Reference] = None
    source: Optional[Reference] = None
    item: Optional[List[QuestionnaireResponseItem]] = None


class ClaimCareTeam(BaseModel):
    sequence: int
    provider: Reference
    responsible: Optional[bool] = None
    role: Optional[CodeableConcept] = None
    qualification: Optional[CodeableConcept] = None


class ClaimSupportingInfo(BaseModel):
    sequence: int
    category: CodeableConcept
    code: Optional[CodeableConcept] = None
    timingDate: Optional[str] = None
    timingPeriod: Optional[Dict[str, Any]] = None
    valueBoolean: Optional[bool] = None
    valueString: Optional[str] = None
    valueQuantity: Optional[Dict[str, Any]] = None
    valueAttachment: Optional[Dict[str, Any]] = None
    valueReference: Optional[Reference] = None
    reason: Optional[CodeableConcept] = None


class ClaimDiagnosis(BaseModel):
    sequence: int
    diagnosisCodeableConcept: Optional[CodeableConcept] = None
    diagnosisReference: Optional[Reference] = None
    type: Optional[List[CodeableConcept]] = None
    onAdmission: Optional[CodeableConcept] = None
    packageCode: Optional[CodeableConcept] = None


class ClaimProcedure(BaseModel):
    sequence: int
    type: Optional[List[CodeableConcept]] = None
    date: Optional[str] = None
    procedureCodeableConcept: Optional[CodeableConcept] = None
    procedureReference: Optional[Reference] = None
    udi: Optional[List[Reference]] = None


class ClaimInsurance(BaseModel):
    sequence: int
    focal: bool
    identifier: Optional[Identifier] = None
    coverage: Reference
    businessArrangement: Optional[str] = None
    preAuthRef: Optional[List[str]] = None
    claimResponse: Optional[Reference] = None


class ClaimItem(BaseModel):
    sequence: int
    careTeamSequence: Optional[List[int]] = None
    diagnosisSequence: Optional[List[int]] = None
    procedureSequence: Optional[List[int]] = None
    informationSequence: Optional[List[int]] = None
    revenue: Optional[CodeableConcept] = None
    category: Optional[CodeableConcept] = None
    productOrService: CodeableConcept
    modifier: Optional[List[CodeableConcept]] = None
    programCode: Optional[List[CodeableConcept]] = None
    servicedDate: Optional[str] = None
    servicedPeriod: Optional[Dict[str, Any]] = None
    locationCodeableConcept: Optional[CodeableConcept] = None
    locationAddress: Optional[Dict[str, Any]] = None
    locationReference: Optional[Reference] = None
    quantity: Optional[Dict[str, Any]] = None
    unitPrice: Optional[Dict[str, Any]] = None
    factor: Optional[float] = None
    net: Optional[Dict[str, Any]] = None
    udi: Optional[List[Reference]] = None
    bodySite: Optional[CodeableConcept] = None
    subSite: Optional[List[CodeableConcept]] = None
    encounter: Optional[List[Reference]] = None
    detail: Optional[List[Dict[str, Any]]] = None


class Claim(BaseModel):
    resourceType: Literal["Claim"] = "Claim"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    type: Optional[CodeableConcept] = None
    subType: Optional[CodeableConcept] = None
    use: Optional[str] = None
    patient: Optional[Reference] = None
    billablePeriod: Optional[Dict[str, Any]] = None
    created: Optional[str] = None
    enterer: Optional[Reference] = None
    insurer: Optional[Reference] = None
    provider: Optional[Reference] = None
    priority: Optional[CodeableConcept] = None
    fundsReserve: Optional[CodeableConcept] = None
    related: Optional[List[Dict[str, Any]]] = None
    prescription: Optional[Reference] = None
    originalPrescription: Optional[Reference] = None
    payee: Optional[Dict[str, Any]] = None
    referral: Optional[Reference] = None
    facility: Optional[Reference] = None
    careTeam: Optional[List[ClaimCareTeam]] = None
    supportingInfo: Optional[List[ClaimSupportingInfo]] = None
    diagnosis: Optional[List[ClaimDiagnosis]] = None
    procedure: Optional[List[ClaimProcedure]] = None
    insurance: Optional[List[ClaimInsurance]] = None
    accident: Optional[Dict[str, Any]] = None
    item: Optional[List[ClaimItem]] = None
    total: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

class CoverageClass(BaseModel):
    type: CodeableConcept
    value: str
    name: Optional[str] = None


class Coverage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resourceType: Literal["Coverage"] = "Coverage"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    type: Optional[CodeableConcept] = None
    policyHolder: Optional[Reference] = None
    subscriber: Optional[Reference] = None
    subscriberId: Optional[str] = None
    beneficiary: Optional[Reference] = None
    dependent: Optional[str] = None
    relationship: Optional[CodeableConcept] = None
    period: Optional[Dict[str, Any]] = None
    payor: Optional[List[Reference]] = None
    # "class" is a reserved word in Python — alias required
    class_: Optional[List[CoverageClass]] = Field(None, alias="class")
    order: Optional[int] = None
    network: Optional[str] = None
    costToBeneficiary: Optional[List[Dict[str, Any]]] = None
    subrogation: Optional[bool] = None
    contract: Optional[List[Reference]] = None


# ---------------------------------------------------------------------------
# ClaimResponse
# ---------------------------------------------------------------------------

class ClaimResponseItem(BaseModel):
    itemSequence: int
    noteNumber: Optional[List[int]] = None
    adjudication: Optional[List[Dict[str, Any]]] = None
    detail: Optional[List[Dict[str, Any]]] = None


class ClaimResponseAddItem(BaseModel):
    itemSequence: Optional[List[int]] = None
    productOrService: Optional[CodeableConcept] = None
    modifier: Optional[List[CodeableConcept]] = None
    quantity: Optional[Dict[str, Any]] = None
    unitPrice: Optional[Dict[str, Any]] = None
    net: Optional[Dict[str, Any]] = None
    adjudication: Optional[List[Dict[str, Any]]] = None
    detail: Optional[List[Dict[str, Any]]] = None


class ClaimResponseError(BaseModel):
    itemSequence: Optional[int] = None
    detailSequence: Optional[int] = None
    subDetailSequence: Optional[int] = None
    code: CodeableConcept


class ClaimResponseProcessNote(BaseModel):
    number: Optional[int] = None
    type: Optional[str] = None
    text: str
    language: Optional[CodeableConcept] = None


class ClaimResponseInsurance(BaseModel):
    sequence: int
    focal: bool
    coverage: Reference
    businessArrangement: Optional[str] = None
    claimResponse: Optional[Reference] = None


class ClaimResponse(BaseModel):
    resourceType: Literal["ClaimResponse"] = "ClaimResponse"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    status: Optional[str] = None
    type: Optional[CodeableConcept] = None
    subType: Optional[CodeableConcept] = None
    use: Optional[str] = None          # claim | preauthorization | predetermination
    patient: Optional[Reference] = None
    created: Optional[str] = None
    insurer: Optional[Reference] = None
    requestor: Optional[Reference] = None
    request: Optional[Reference] = None
    outcome: Optional[str] = None      # queued | complete | error | partial
    disposition: Optional[str] = None
    preAuthRef: Optional[str] = None   # authorization number if approved
    preAuthPeriod: Optional[Dict[str, Any]] = None
    payeeType: Optional[CodeableConcept] = None
    item: Optional[List[ClaimResponseItem]] = None
    addItem: Optional[List[ClaimResponseAddItem]] = None
    adjudication: Optional[List[Dict[str, Any]]] = None
    total: Optional[List[Dict[str, Any]]] = None
    payment: Optional[Dict[str, Any]] = None
    fundsReserve: Optional[CodeableConcept] = None
    formCode: Optional[CodeableConcept] = None
    form: Optional[Dict[str, Any]] = None
    processNote: Optional[List[ClaimResponseProcessNote]] = None
    communicationRequest: Optional[List[Reference]] = None
    insurance: Optional[List[ClaimResponseInsurance]] = None
    error: Optional[List[ClaimResponseError]] = None


# ---------------------------------------------------------------------------
# ServiceRequest
# ---------------------------------------------------------------------------

class ServiceRequest(BaseModel):
    resourceType: Literal["ServiceRequest"] = "ServiceRequest"
    id: Optional[str] = None
    meta: Optional[Meta] = None
    identifier: Optional[List[Identifier]] = None
    instantiatesCanonical: Optional[List[str]] = None
    instantiatesUri: Optional[List[str]] = None
    basedOn: Optional[List[Reference]] = None
    replaces: Optional[List[Reference]] = None
    requisition: Optional[Identifier] = None
    status: Optional[str] = None      # draft | active | on-hold | revoked | completed | entered-in-error | unknown
    intent: Optional[str] = None      # proposal | plan | directive | order | ...
    category: Optional[List[CodeableConcept]] = None
    priority: Optional[str] = None    # routine | urgent | asap | stat
    doNotPerform: Optional[bool] = None
    code: Optional[CodeableConcept] = None
    orderDetail: Optional[List[CodeableConcept]] = None
    quantityQuantity: Optional[Dict[str, Any]] = None
    quantityRatio: Optional[Dict[str, Any]] = None
    quantityRange: Optional[Dict[str, Any]] = None
    subject: Optional[Reference] = None
    encounter: Optional[Reference] = None
    occurrenceDateTime: Optional[str] = None
    occurrencePeriod: Optional[Dict[str, Any]] = None
    occurrenceTiming: Optional[Dict[str, Any]] = None
    asNeededBoolean: Optional[bool] = None
    asNeededCodeableConcept: Optional[CodeableConcept] = None
    authoredOn: Optional[str] = None
    requester: Optional[Reference] = None
    performerType: Optional[CodeableConcept] = None
    performer: Optional[List[Reference]] = None
    locationCode: Optional[List[CodeableConcept]] = None
    locationReference: Optional[List[Reference]] = None
    reasonCode: Optional[List[CodeableConcept]] = None
    reasonReference: Optional[List[Reference]] = None
    insurance: Optional[List[Reference]] = None
    supportingInfo: Optional[List[Reference]] = None
    specimen: Optional[List[Reference]] = None
    bodySite: Optional[List[CodeableConcept]] = None
    note: Optional[List[Dict[str, Any]]] = None
    patientInstruction: Optional[str] = None
    relevantHistory: Optional[List[Reference]] = None
