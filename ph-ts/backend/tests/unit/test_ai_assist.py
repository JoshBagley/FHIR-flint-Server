"""
Tests for AI-enhanced vocabulary endpoints (/ai/*).

All external calls are mocked:
  - app.routes.ai_assist._complete      — synchronous AI provider call
  - app.routes.ai_assist._complete_chat — multi-turn AI chat call
  - app.services.external_cs.search     — SDO concept search

This lets us verify that the routes correctly:
  1. Pass candidates to the AI prompt
  2. Parse the AI JSON response into the expected shape
  3. Persist ConceptMaps from /ai/map-save
  4. Extract <suggested_codes> blocks from /ai/chat replies
  5. Return 503 when no API key is configured
"""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fake SDO search results — realistic SNOMED + LOINC candidates
# ---------------------------------------------------------------------------

SNOMED_DIABETES_CANDIDATES = [
    {
        "code": "73211009",
        "display": "Diabetes mellitus",
        "system": "http://snomed.info/sct",
        "systemName": "SNOMED CT",
    },
    {
        "code": "44054006",
        "display": "Diabetes mellitus type 2",
        "system": "http://snomed.info/sct",
        "systemName": "SNOMED CT",
    },
]

LOINC_GLUCOSE_CANDIDATES = [
    {
        "code": "2339-0",
        "display": "Glucose [Mass/volume] in Blood",
        "system": "http://loinc.org",
        "systemName": "LOINC",
    },
    {
        "code": "4548-4",
        "display": "Hemoglobin A1c/Hemoglobin.total in Blood",
        "system": "http://loinc.org",
        "systemName": "LOINC",
    },
]

ICD10_DIABETES_CANDIDATES = [
    {
        "code": "E11",
        "display": "Type 2 diabetes mellitus",
        "system": "http://hl7.org/fhir/sid/icd-10-cm",
        "systemName": "ICD-10-CM",
    },
    {
        "code": "E11.9",
        "display": "Type 2 diabetes mellitus without complications",
        "system": "http://hl7.org/fhir/sid/icd-10-cm",
        "systemName": "ICD-10-CM",
    },
]


# ---------------------------------------------------------------------------
# Canned AI responses (realistic JSON the model would return)
# ---------------------------------------------------------------------------

AI_SUGGEST_RESPONSE = json.dumps(
    {
        "suggestions": [
            {
                "code": "73211009",
                "display": "Diabetes mellitus",
                "system": "http://snomed.info/sct",
                "systemName": "SNOMED CT",
                "rationale": "Broadest SNOMED concept for diabetes; use as parent for hierarchical inclusion.",
                "confidence": "high",
                "caveats": None,
            },
            {
                "code": "44054006",
                "display": "Diabetes mellitus type 2",
                "system": "http://snomed.info/sct",
                "systemName": "SNOMED CT",
                "rationale": "Specific concept for T2DM; preferred for most PH surveillance ValueSets.",
                "confidence": "high",
                "caveats": None,
            },
            {
                "code": "E11.9",
                "display": "Type 2 diabetes mellitus without complications",
                "system": "http://hl7.org/fhir/sid/icd-10-cm",
                "systemName": "ICD-10-CM",
                "rationale": "ICD-10-CM equivalent for administrative billing; wider than SNOMED equivalent.",
                "confidence": "medium",
                "caveats": "Unspecified complication status — consider E11.* range for completeness.",
            },
        ],
        "additional_search_terms": ["hyperglycemia", "insulin resistance", "T2DM"],
        "notes": "Consider combining SNOMED ECL <<73211009 with ICD-10-CM E11.* for complete coverage.",
    }
)

AI_DESCRIBE_RESPONSE = json.dumps(
    {
        "name": "DiabetesMellitusSurveillanceCodes",
        "title": "Diabetes Mellitus Surveillance Codes",
        "description": "Codes representing diabetes mellitus diagnoses for public health surveillance, including SNOMED CT clinical concepts and ICD-10-CM administrative codes.",
        "purpose": "Use in case notification and chronic disease surveillance reporting where both clinical and administrative coding is required.",
        "suggested_url": "http://terminology.example.org/ValueSet/diabetes-mellitus-surveillance-codes",
        "notes": "SNOMED CT requires an affiliate license; ICD-10-CM is public domain.",
    }
)

AI_MAP_RESPONSE = json.dumps(
    {
        "mappings": [
            {
                "source_code": "73211009",
                "source_display": "Diabetes mellitus",
                "target_code": "E11",
                "target_display": "Type 2 diabetes mellitus",
                "target_system": "http://hl7.org/fhir/sid/icd-10-cm",
                "equivalence": "wider",
                "rationale": "SNOMED 'Diabetes mellitus' is broader than ICD-10-CM E11 which specifies Type 2.",
            },
            {
                "source_code": "44054006",
                "source_display": "Diabetes mellitus type 2",
                "target_code": "E11.9",
                "target_display": "Type 2 diabetes mellitus without complications",
                "target_system": "http://hl7.org/fhir/sid/icd-10-cm",
                "equivalence": "equivalent",
                "rationale": "Direct semantic equivalent for uncomplicated T2DM.",
            },
        ],
        "notes": "Review E11.* subcategories for cases with specific complications.",
    }
)

AI_CHAT_REPLY_WITH_CODES = """
The standard SNOMED CT code for COVID-19 is 840539006.

<suggested_codes>
[{"code": "840539006", "display": "Disease caused by severe acute respiratory syndrome coronavirus 2", "system": "http://snomed.info/sct", "systemName": "SNOMED CT"}]
</suggested_codes>

For laboratory confirmation, use LOINC 94500-6.

<suggested_codes>
[{"code": "94500-6", "display": "SARS-CoV-2 (COVID-19) RNA [Presence] in Respiratory specimen by NAA with probe detection", "system": "http://loinc.org", "systemName": "LOINC"}]
</suggested_codes>
"""


# ===========================================================================
# /ai/provider
# ===========================================================================

async def test_ai_provider_returns_configured_info(client: AsyncClient):
    """GET /ai/provider must return provider, model, and configured fields."""
    resp = await client.get("/ai/provider")
    assert resp.status_code == 200
    body = resp.json()
    assert "provider" in body
    assert "model" in body
    assert "configured" in body
    assert body["provider"] in ("anthropic", "openai", "gemini")


# ===========================================================================
# /ai/suggest
# ===========================================================================

async def test_suggest_returns_ranked_snomed_and_icd10_codes(client: AsyncClient):
    """
    POST /ai/suggest must search SDOs in parallel, pass candidates to the AI,
    and return ranked suggestions with the expected shape.
    """
    all_candidates = SNOMED_DIABETES_CANDIDATES + ICD10_DIABETES_CANDIDATES

    async def _mock_search(sys_id: str, query: str, limit: int = 10):
        if sys_id == "snomed":
            return SNOMED_DIABETES_CANDIDATES
        if sys_id == "icd10cm":
            return ICD10_DIABETES_CANDIDATES
        return []

    with patch("app.services.external_cs.search", side_effect=_mock_search), \
         patch("app.routes.ai_assist._complete", return_value=AI_SUGGEST_RESPONSE):
        resp = await client.post(
            "/ai/suggest",
            json={
                "description": "Type 2 diabetes mellitus for public health surveillance",
                "systems": ["snomed", "icd10cm"],
                "limit": 5,
            },
        )

    assert resp.status_code == 200
    body = resp.json()

    # Shape checks
    assert "suggestions" in body
    assert "additional_search_terms" in body
    assert len(body["suggestions"]) >= 2

    # Code correctness
    codes = {s["code"] for s in body["suggestions"]}
    assert "73211009" in codes   # SNOMED Diabetes mellitus
    assert "E11.9" in codes      # ICD-10-CM T2DM

    # Each suggestion must have required fields
    for suggestion in body["suggestions"]:
        assert "code" in suggestion
        assert "display" in suggestion
        assert "system" in suggestion
        assert "confidence" in suggestion
        assert suggestion["confidence"] in ("high", "medium", "low")


async def test_suggest_high_confidence_for_direct_snomed_match(client: AsyncClient):
    """The closest SNOMED match should have high confidence."""
    async def _mock_search(sys_id, query, limit=10):
        return SNOMED_DIABETES_CANDIDATES if sys_id == "snomed" else []

    with patch("app.services.external_cs.search", side_effect=_mock_search), \
         patch("app.routes.ai_assist._complete", return_value=AI_SUGGEST_RESPONSE):
        resp = await client.post(
            "/ai/suggest",
            json={"description": "diabetes mellitus", "systems": ["snomed"]},
        )

    assert resp.status_code == 200
    high_confidence = [s for s in resp.json()["suggestions"] if s["confidence"] == "high"]
    assert len(high_confidence) >= 1
    high_codes = {s["code"] for s in high_confidence}
    # At least one direct SNOMED diabetes code must be high-confidence
    assert high_codes & {"73211009", "44054006"}


async def test_suggest_no_candidates_returns_empty(client: AsyncClient):
    """When all SDO searches return empty, the endpoint returns [] without calling AI."""
    async def _mock_search(sys_id, query, limit=10):
        return []

    with patch("app.services.external_cs.search", side_effect=_mock_search):
        resp = await client.post(
            "/ai/suggest",
            json={"description": "some obscure concept", "systems": ["snomed", "loinc"]},
        )

    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []


async def test_suggest_returns_additional_search_terms(client: AsyncClient):
    """Response must include additional_search_terms list from AI."""
    async def _mock_search(sys_id, query, limit=10):
        return SNOMED_DIABETES_CANDIDATES

    with patch("app.services.external_cs.search", side_effect=_mock_search), \
         patch("app.routes.ai_assist._complete", return_value=AI_SUGGEST_RESPONSE):
        resp = await client.post(
            "/ai/suggest",
            json={"description": "diabetes", "systems": ["snomed"]},
        )

    assert resp.status_code == 200
    terms = resp.json().get("additional_search_terms", [])
    assert isinstance(terms, list)
    assert len(terms) > 0


async def test_suggest_503_when_no_api_key(client: AsyncClient):
    """If no API key is set, the endpoint must return 503."""
    async def _mock_search(sys_id, query, limit=10):
        return SNOMED_DIABETES_CANDIDATES

    import os
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    original_provider = os.environ.get("AI_PROVIDER", "anthropic")
    os.environ["AI_PROVIDER"] = "anthropic"

    try:
        with patch("app.services.external_cs.search", side_effect=_mock_search):
            resp = await client.post(
                "/ai/suggest",
                json={"description": "diabetes", "systems": ["snomed"]},
            )
        assert resp.status_code == 503
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original
        os.environ["AI_PROVIDER"] = original_provider


# ===========================================================================
# /ai/describe
# ===========================================================================

async def test_describe_returns_fhir_metadata_shape(client: AsyncClient):
    """POST /ai/describe must return all required FHIR ValueSet metadata fields."""
    codes = [
        {"code": "73211009", "display": "Diabetes mellitus", "system": "http://snomed.info/sct", "systemName": "SNOMED CT"},
        {"code": "E11.9",    "display": "Type 2 diabetes mellitus without complications", "system": "http://hl7.org/fhir/sid/icd-10-cm", "systemName": "ICD-10-CM"},
    ]
    with patch("app.routes.ai_assist._complete", return_value=AI_DESCRIBE_RESPONSE):
        resp = await client.post("/ai/describe", json={"codes": codes})

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "DiabetesMellitusSurveillanceCodes"
    assert body["title"] == "Diabetes Mellitus Surveillance Codes"
    assert "description" in body and len(body["description"]) > 10
    assert "purpose" in body
    assert "suggested_url" in body
    assert body["suggested_url"].startswith("http")


async def test_describe_with_context_string(client: AsyncClient):
    """An optional context string should be accepted without error."""
    codes = [{"code": "94500-6", "display": "SARS-CoV-2 PCR", "system": "http://loinc.org"}]
    with patch("app.routes.ai_assist._complete", return_value=AI_DESCRIBE_RESPONSE):
        resp = await client.post(
            "/ai/describe",
            json={"codes": codes, "context": "Used for COVID-19 case notification reporting"},
        )
    assert resp.status_code == 200


# ===========================================================================
# /ai/map
# ===========================================================================

async def test_map_returns_snomed_to_icd10_mappings(client: AsyncClient):
    """
    POST /ai/map must return mappings with FHIR equivalence values for
    each source SNOMED code.
    """
    source_codes = [
        {"code": "73211009", "display": "Diabetes mellitus", "system": "http://snomed.info/sct"},
        {"code": "44054006", "display": "Diabetes mellitus type 2", "system": "http://snomed.info/sct"},
    ]

    async def _mock_search(sys_id, query, limit=5):
        return ICD10_DIABETES_CANDIDATES

    with patch("app.services.external_cs.search", side_effect=_mock_search), \
         patch("app.routes.ai_assist._complete", return_value=AI_MAP_RESPONSE):
        resp = await client.post(
            "/ai/map",
            json={
                "codes": source_codes,
                "source_system": "snomed",
                "target_system": "icd10cm",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "mappings" in body
    assert len(body["mappings"]) == 2

    # Check specific mapping equivalences
    mappings_by_src = {m["source_code"]: m for m in body["mappings"]}
    assert mappings_by_src["73211009"]["equivalence"] == "wider"
    assert mappings_by_src["44054006"]["equivalence"] == "equivalent"
    assert mappings_by_src["44054006"]["target_code"] == "E11.9"


async def test_map_equivalence_values_are_valid_fhir(client: AsyncClient):
    """All returned equivalence values must be valid FHIR R4 values."""
    valid_equivalences = {"equivalent", "wider", "narrower", "inexact", "unmatched"}
    source_codes = [
        {"code": "73211009", "display": "Diabetes mellitus", "system": "http://snomed.info/sct"},
    ]

    async def _mock_search(sys_id, query, limit=5):
        return ICD10_DIABETES_CANDIDATES

    with patch("app.services.external_cs.search", side_effect=_mock_search), \
         patch("app.routes.ai_assist._complete", return_value=AI_MAP_RESPONSE):
        resp = await client.post(
            "/ai/map",
            json={"codes": source_codes, "source_system": "snomed", "target_system": "icd10cm"},
        )

    assert resp.status_code == 200
    for mapping in resp.json()["mappings"]:
        assert mapping["equivalence"] in valid_equivalences


# ===========================================================================
# /ai/map-save
# ===========================================================================

async def test_map_save_persists_conceptmap(client: AsyncClient):
    """
    POST /ai/map-save must create a ConceptMap resource with the correct
    source/target systems, elements, and equivalence values.
    """
    payload = {
        "mappings": [
            {
                "source_code": "73211009",
                "source_display": "Diabetes mellitus",
                "target_code": "E11",
                "target_display": "Type 2 diabetes mellitus",
                "target_system": "http://hl7.org/fhir/sid/icd-10-cm",
                "equivalence": "wider",
                "rationale": "SNOMED concept is broader than ICD-10-CM E11.",
            },
            {
                "source_code": "44054006",
                "source_display": "Diabetes mellitus type 2",
                "target_code": "E11.9",
                "target_display": "Type 2 diabetes mellitus without complications",
                "target_system": "http://hl7.org/fhir/sid/icd-10-cm",
                "equivalence": "equivalent",
                "rationale": "Semantic equivalent for uncomplicated T2DM.",
            },
        ],
        "source_system_url": "http://snomed.info/sct",
        "target_system": "icd10cm",
        "name": "SnomedToDiabetesICD10Map",
        "title": "SNOMED to ICD-10-CM Diabetes Mapping",
        "description": "AI-assisted mapping of SNOMED diabetes concepts to ICD-10-CM.",
        "status": "draft",
    }
    resp = await client.post("/ai/map-save", json=payload)
    assert resp.status_code == 201
    body = resp.json()

    # Shape checks
    assert body["resourceType"] == "ConceptMap"
    assert body["name"] == "SnomedToDiabetesICD10Map"
    assert body["status"] == "draft"
    assert "id" in body

    # Verify group structure
    group = body["group"][0]
    assert group["source"] == "http://snomed.info/sct"
    # target should be the canonical URL for icd10cm
    assert "icd-10-cm" in group["target"] or "icd10cm" in group["target"]

    # Element correctness
    elements_by_src = {e["code"]: e for e in group["element"]}
    assert "73211009" in elements_by_src
    assert "44054006" in elements_by_src
    assert elements_by_src["44054006"]["target"][0]["equivalence"] == "equivalent"
    assert elements_by_src["73211009"]["target"][0]["equivalence"] == "wider"


async def test_map_save_unmatched_codes_stored_correctly(client: AsyncClient):
    """
    When target_code is absent, the element must use equivalence='unmatched'.
    """
    payload = {
        "mappings": [
            {
                "source_code": "263495000",
                "source_display": "Gender",
                "target_code": None,
                "target_display": None,
                "target_system": "http://hl7.org/fhir/sid/icd-10-cm",
                "equivalence": "unmatched",
                "rationale": "No ICD-10-CM equivalent for SNOMED 'Gender' concept.",
            },
        ],
        "source_system_url": "http://snomed.info/sct",
        "target_system": "icd10cm",
        "name": "TestUnmatchedMap",
        "title": "Test Unmatched Map",
        "status": "draft",
    }
    resp = await client.post("/ai/map-save", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    element = body["group"][0]["element"][0]
    assert element["code"] == "263495000"
    assert element["target"][0]["equivalence"] == "unmatched"


# ===========================================================================
# /ai/chat
# ===========================================================================

async def test_chat_returns_reply_and_extracts_suggested_codes(client: AsyncClient):
    """
    POST /ai/chat must strip <suggested_codes> blocks from the reply text
    and return them as structured data.
    """
    with patch("app.routes.ai_assist._complete_chat", return_value=AI_CHAT_REPLY_WITH_CODES):
        resp = await client.post(
            "/ai/chat",
            json={
                "messages": [
                    {"role": "user", "content": "What SNOMED and LOINC codes should I use for COVID-19?"}
                ]
            },
        )

    assert resp.status_code == 200
    body = resp.json()

    # Structured codes extracted
    codes_by_code = {c["code"]: c for c in body["suggested_codes"]}
    assert "840539006" in codes_by_code
    assert codes_by_code["840539006"]["system"] == "http://snomed.info/sct"
    assert codes_by_code["840539006"]["systemName"] == "SNOMED CT"
    assert "94500-6" in codes_by_code
    assert codes_by_code["94500-6"]["system"] == "http://loinc.org"

    # Tags stripped from reply text
    assert "<suggested_codes>" not in body["reply"]
    assert "</suggested_codes>" not in body["reply"]
    # Core message preserved
    assert "840539006" in body["reply"] or "COVID-19" in body["reply"]


async def test_chat_reply_without_suggested_codes(client: AsyncClient):
    """A reply with no <suggested_codes> block must return empty list."""
    plain_reply = "Use SNOMED ECL <<73211009 to capture all diabetes descendants."
    with patch("app.routes.ai_assist._complete_chat", return_value=plain_reply):
        resp = await client.post(
            "/ai/chat",
            json={"messages": [{"role": "user", "content": "How do I capture all diabetes codes?"}]},
        )

    assert resp.status_code == 200
    assert resp.json()["suggested_codes"] == []
    assert "SNOMED ECL" in resp.json()["reply"]


async def test_chat_with_valueset_context(client: AsyncClient):
    """ValueSet context should be accepted and forwarded without error."""
    plain_reply = "Your COVID-19 ValueSet looks good."
    with patch("app.routes.ai_assist._complete_chat", return_value=plain_reply):
        resp = await client.post(
            "/ai/chat",
            json={
                "messages": [{"role": "user", "content": "Does this look complete?"}],
                "valueset_context": {
                    "title": "COVID-19 Case Notification",
                    "description": "Codes for COVID-19 case notification.",
                    "codes": [
                        {"code": "840539006", "display": "COVID-19", "system": "http://snomed.info/sct", "systemName": "SNOMED CT"},
                    ],
                },
            },
        )

    assert resp.status_code == 200
    assert "reply" in resp.json()


async def test_chat_multi_turn_conversation(client: AsyncClient):
    """Multi-turn messages list should be passed through without error."""
    with patch("app.routes.ai_assist._complete_chat", return_value="Use 840539006 for COVID-19."):
        resp = await client.post(
            "/ai/chat",
            json={
                "messages": [
                    {"role": "user",      "content": "I need codes for COVID-19 surveillance."},
                    {"role": "assistant", "content": "I recommend starting with SNOMED CT."},
                    {"role": "user",      "content": "Which specific SNOMED code?"},
                ],
            },
        )

    assert resp.status_code == 200
    assert resp.json()["reply"]
