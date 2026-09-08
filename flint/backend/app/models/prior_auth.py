from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.main import CodeableConcept, Identifier, Meta
from app.models.clinical import Reference


class QuestionnaireItem(BaseModel):
    linkId: str
    definition: str | None = None
    code: list[dict[str, Any]] | None = None
    prefix: str | None = None
    text: str | None = None
    type: str | None = None
    enableWhen: list[dict[str, Any]] | None = None
    enableBehavior: str | None = None
    required: bool | None = None
    repeats: bool | None = None
    readOnly: bool | None = None
    maxLength: int | None = None
    answerValueSet: str | None = None
    answerOption: list[dict[str, Any]] | None = None
    initial: list[dict[str, Any]] | None = None
    item: list["QuestionnaireItem"] | None = None


QuestionnaireItem.model_rebuild()


class Questionnaire(BaseModel):
    resourceType: Literal["Questionnaire"] = "Questionnaire"
    id: str | None = None
    meta: Meta | None = None
    url: str | None = None
    identifier: list[Identifier] | None = None
    version: str | None = None
    name: str | None = None
    title: str | None = None
    derivedFrom: list[str] | None = None
    status: str | None = None
    experimental: bool | None = None
    subjectType: list[str] | None = None
    date: str | None = None
    publisher: str | None = None
    contact: list[dict[str, Any]] | None = None
    description: str | None = None
    useContext: list[dict[str, Any]] | None = None
    jurisdiction: list[CodeableConcept] | None = None
    purpose: str | None = None
    copyright: str | None = None
    approvalDate: str | None = None
    lastReviewDate: str | None = None
    effectivePeriod: dict[str, Any] | None = None
    code: list[dict[str, Any]] | None = None
    item: list[QuestionnaireItem] | None = None


class QuestionnaireResponseItem(BaseModel):
    linkId: str
    definition: str | None = None
    text: str | None = None
    answer: list[dict[str, Any]] | None = None
    item: list["QuestionnaireResponseItem"] | None = None


QuestionnaireResponseItem.model_rebuild()


class QuestionnaireResponse(BaseModel):
    resourceType: Literal["QuestionnaireResponse"] = "QuestionnaireResponse"
    id: str | None = None
    meta: Meta | None = None
    identifier: Identifier | None = None
    basedOn: list[Reference] | None = None
    partOf: list[Reference] | None = None
    questionnaire: str | None = None
    status: str | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    authored: str | None = None
    author: Reference | None = None
    source: Reference | None = None
    item: list[QuestionnaireResponseItem] | None = None


class ClaimCareTeam(BaseModel):
    sequence: int
    provider: Reference
    responsible: bool | None = None
    role: CodeableConcept | None = None
    qualification: CodeableConcept | None = None


class ClaimSupportingInfo(BaseModel):
    sequence: int
    category: CodeableConcept
    code: CodeableConcept | None = None
    timingDate: str | None = None
    timingPeriod: dict[str, Any] | None = None
    valueBoolean: bool | None = None
    valueString: str | None = None
    valueQuantity: dict[str, Any] | None = None
    valueAttachment: dict[str, Any] | None = None
    valueReference: Reference | None = None
    reason: CodeableConcept | None = None


class ClaimDiagnosis(BaseModel):
    sequence: int
    diagnosisCodeableConcept: CodeableConcept | None = None
    diagnosisReference: Reference | None = None
    type: list[CodeableConcept] | None = None
    onAdmission: CodeableConcept | None = None
    packageCode: CodeableConcept | None = None


class ClaimProcedure(BaseModel):
    sequence: int
    type: list[CodeableConcept] | None = None
    date: str | None = None
    procedureCodeableConcept: CodeableConcept | None = None
    procedureReference: Reference | None = None
    udi: list[Reference] | None = None


class ClaimInsurance(BaseModel):
    sequence: int
    focal: bool
    identifier: Identifier | None = None
    coverage: Reference
    businessArrangement: str | None = None
    preAuthRef: list[str] | None = None
    claimResponse: Reference | None = None


class ClaimItem(BaseModel):
    sequence: int
    careTeamSequence: list[int] | None = None
    diagnosisSequence: list[int] | None = None
    procedureSequence: list[int] | None = None
    informationSequence: list[int] | None = None
    revenue: CodeableConcept | None = None
    category: CodeableConcept | None = None
    productOrService: CodeableConcept
    modifier: list[CodeableConcept] | None = None
    programCode: list[CodeableConcept] | None = None
    servicedDate: str | None = None
    servicedPeriod: dict[str, Any] | None = None
    locationCodeableConcept: CodeableConcept | None = None
    locationAddress: dict[str, Any] | None = None
    locationReference: Reference | None = None
    quantity: dict[str, Any] | None = None
    unitPrice: dict[str, Any] | None = None
    factor: float | None = None
    net: dict[str, Any] | None = None
    udi: list[Reference] | None = None
    bodySite: CodeableConcept | None = None
    subSite: list[CodeableConcept] | None = None
    encounter: list[Reference] | None = None
    detail: list[dict[str, Any]] | None = None


class Claim(BaseModel):
    resourceType: Literal["Claim"] = "Claim"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    type: CodeableConcept | None = None
    subType: CodeableConcept | None = None
    use: str | None = None
    patient: Reference | None = None
    billablePeriod: dict[str, Any] | None = None
    created: str | None = None
    enterer: Reference | None = None
    insurer: Reference | None = None
    provider: Reference | None = None
    priority: CodeableConcept | None = None
    fundsReserve: CodeableConcept | None = None
    related: list[dict[str, Any]] | None = None
    prescription: Reference | None = None
    originalPrescription: Reference | None = None
    payee: dict[str, Any] | None = None
    referral: Reference | None = None
    facility: Reference | None = None
    careTeam: list[ClaimCareTeam] | None = None
    supportingInfo: list[ClaimSupportingInfo] | None = None
    diagnosis: list[ClaimDiagnosis] | None = None
    procedure: list[ClaimProcedure] | None = None
    insurance: list[ClaimInsurance] | None = None
    accident: dict[str, Any] | None = None
    item: list[ClaimItem] | None = None
    total: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

class CoverageClass(BaseModel):
    type: CodeableConcept
    value: str
    name: str | None = None


class Coverage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resourceType: Literal["Coverage"] = "Coverage"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    type: CodeableConcept | None = None
    policyHolder: Reference | None = None
    subscriber: Reference | None = None
    subscriberId: str | None = None
    beneficiary: Reference | None = None
    dependent: str | None = None
    relationship: CodeableConcept | None = None
    period: dict[str, Any] | None = None
    payor: list[Reference] | None = None
    # "class" is a reserved word in Python — alias required
    class_: list[CoverageClass] | None = Field(None, alias="class")
    order: int | None = None
    network: str | None = None
    costToBeneficiary: list[dict[str, Any]] | None = None
    subrogation: bool | None = None
    contract: list[Reference] | None = None


# ---------------------------------------------------------------------------
# ClaimResponse
# ---------------------------------------------------------------------------

class ClaimResponseItem(BaseModel):
    itemSequence: int
    noteNumber: list[int] | None = None
    adjudication: list[dict[str, Any]] | None = None
    detail: list[dict[str, Any]] | None = None


class ClaimResponseAddItem(BaseModel):
    itemSequence: list[int] | None = None
    productOrService: CodeableConcept | None = None
    modifier: list[CodeableConcept] | None = None
    quantity: dict[str, Any] | None = None
    unitPrice: dict[str, Any] | None = None
    net: dict[str, Any] | None = None
    adjudication: list[dict[str, Any]] | None = None
    detail: list[dict[str, Any]] | None = None


class ClaimResponseError(BaseModel):
    itemSequence: int | None = None
    detailSequence: int | None = None
    subDetailSequence: int | None = None
    code: CodeableConcept


class ClaimResponseProcessNote(BaseModel):
    number: int | None = None
    type: str | None = None
    text: str
    language: CodeableConcept | None = None


class ClaimResponseInsurance(BaseModel):
    sequence: int
    focal: bool
    coverage: Reference
    businessArrangement: str | None = None
    claimResponse: Reference | None = None


class ClaimResponse(BaseModel):
    resourceType: Literal["ClaimResponse"] = "ClaimResponse"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    status: str | None = None
    type: CodeableConcept | None = None
    subType: CodeableConcept | None = None
    use: str | None = None          # claim | preauthorization | predetermination
    patient: Reference | None = None
    created: str | None = None
    insurer: Reference | None = None
    requestor: Reference | None = None
    request: Reference | None = None
    outcome: str | None = None      # queued | complete | error | partial
    disposition: str | None = None
    preAuthRef: str | None = None   # authorization number if approved
    preAuthPeriod: dict[str, Any] | None = None
    payeeType: CodeableConcept | None = None
    item: list[ClaimResponseItem] | None = None
    addItem: list[ClaimResponseAddItem] | None = None
    adjudication: list[dict[str, Any]] | None = None
    total: list[dict[str, Any]] | None = None
    payment: dict[str, Any] | None = None
    fundsReserve: CodeableConcept | None = None
    formCode: CodeableConcept | None = None
    form: dict[str, Any] | None = None
    processNote: list[ClaimResponseProcessNote] | None = None
    communicationRequest: list[Reference] | None = None
    insurance: list[ClaimResponseInsurance] | None = None
    error: list[ClaimResponseError] | None = None


# ---------------------------------------------------------------------------
# ServiceRequest
# ---------------------------------------------------------------------------

class ServiceRequest(BaseModel):
    resourceType: Literal["ServiceRequest"] = "ServiceRequest"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    instantiatesCanonical: list[str] | None = None
    instantiatesUri: list[str] | None = None
    basedOn: list[Reference] | None = None
    replaces: list[Reference] | None = None
    requisition: Identifier | None = None
    status: str | None = None      # draft | active | on-hold | revoked | completed | entered-in-error | unknown
    intent: str | None = None      # proposal | plan | directive | order | ...
    category: list[CodeableConcept] | None = None
    priority: str | None = None    # routine | urgent | asap | stat
    doNotPerform: bool | None = None
    code: CodeableConcept | None = None
    orderDetail: list[CodeableConcept] | None = None
    quantityQuantity: dict[str, Any] | None = None
    quantityRatio: dict[str, Any] | None = None
    quantityRange: dict[str, Any] | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    occurrenceDateTime: str | None = None
    occurrencePeriod: dict[str, Any] | None = None
    occurrenceTiming: dict[str, Any] | None = None
    asNeededBoolean: bool | None = None
    asNeededCodeableConcept: CodeableConcept | None = None
    authoredOn: str | None = None
    requester: Reference | None = None
    performerType: CodeableConcept | None = None
    performer: list[Reference] | None = None
    locationCode: list[CodeableConcept] | None = None
    locationReference: list[Reference] | None = None
    reasonCode: list[CodeableConcept] | None = None
    reasonReference: list[Reference] | None = None
    insurance: list[Reference] | None = None
    supportingInfo: list[Reference] | None = None
    specimen: list[Reference] | None = None
    bodySite: list[CodeableConcept] | None = None
    note: list[dict[str, Any]] | None = None
    patientInstruction: str | None = None
    relevantHistory: list[Reference] | None = None
