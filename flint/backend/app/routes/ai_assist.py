"""
AI-assisted vocabulary tools — multi-provider support.

Provider is selected via AI_PROVIDER env var:
  anthropic  (default) — requires ANTHROPIC_API_KEY
  openai               — requires OPENAI_API_KEY
  gemini               — requires GEMINI_API_KEY

POST /ai/suggest    — search SDOs and rank best matching codes
POST /ai/describe   — generate ValueSet metadata from selected codes
POST /ai/map        — suggest cross-system code mappings

Returns HTTP 503 if the configured provider's API key is missing.
"""

import os
import re
import json
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import external_cs
from app import state
from app.auth import require_access

router = APIRouter(prefix="/ai", tags=["AI Assistant"], dependencies=[Depends(require_access)])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------

def _provider() -> str:
    return os.getenv("AI_PROVIDER", "anthropic").lower()


def _complete(prompt: str, max_tokens: int = 2048) -> str:
    """
    Send a prompt to the configured AI provider and return the response text.
    Raises HTTPException(503) if the provider key is not configured.
    Raises HTTPException(400) if the provider name is unknown.
    """
    provider = _provider()

    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise HTTPException(
                status_code=503,
                detail="AI provider 'anthropic' requires ANTHROPIC_API_KEY in your .env file.",
            )
        import anthropic
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        client = anthropic.Anthropic(api_key=key)
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        except anthropic.APIError as e:
            raise HTTPException(status_code=502, detail=f"Anthropic API error: {e.message}") from e

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise HTTPException(
                status_code=503,
                detail="AI provider 'openai' requires OPENAI_API_KEY in your .env file.",
            )
        from openai import OpenAI
        import openai as _openai
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        client = OpenAI(api_key=key)
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content or ""
        except _openai.APIError as e:
            raise HTTPException(status_code=502, detail=f"OpenAI API error: {e.message}") from e

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise HTTPException(
                status_code=503,
                detail="AI provider 'gemini' requires GEMINI_API_KEY in your .env file.",
            )
        from google import genai
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        client = genai.Client(api_key=key)
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            return resp.text
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Gemini API error: {e}") from e

    raise HTTPException(
        status_code=400,
        detail=f"Unknown AI_PROVIDER '{provider}'. Valid values: anthropic, openai, gemini.",
    )


def _complete_chat(system: str, messages: list[dict], max_tokens: int = 2048) -> str:
    """
    Multi-turn chat completion with a system prompt.
    messages: list of {"role": "user"|"assistant", "content": str}
    """
    provider = _provider()

    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise HTTPException(status_code=503, detail="AI provider 'anthropic' requires ANTHROPIC_API_KEY in your .env file.")
        import anthropic
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        client = anthropic.Anthropic(api_key=key)
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return msg.content[0].text
        except anthropic.APIError as e:
            raise HTTPException(status_code=502, detail=f"Anthropic API error: {e.message}") from e

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise HTTPException(status_code=503, detail="AI provider 'openai' requires OPENAI_API_KEY in your .env file.")
        from openai import OpenAI
        import openai as _openai
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        client = OpenAI(api_key=key)
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}] + messages,
            )
            return resp.choices[0].message.content or ""
        except _openai.APIError as e:
            raise HTTPException(status_code=502, detail=f"OpenAI API error: {e.message}") from e

    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise HTTPException(status_code=503, detail="AI provider 'gemini' requires GEMINI_API_KEY in your .env file.")
        from google import genai
        from google.genai import types as gtypes
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        client = genai.Client(api_key=key)
        try:
            # Gemini uses "model" instead of "assistant" for the role
            gemini_contents = [
                gtypes.Content(
                    role="model" if m["role"] == "assistant" else "user",
                    parts=[gtypes.Part(text=m["content"])],
                )
                for m in messages
            ]
            resp = client.models.generate_content(
                model=model,
                contents=gemini_contents,
                config=gtypes.GenerateContentConfig(system_instruction=system),
            )
            return resp.text
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Gemini API error: {e}") from e

    raise HTTPException(status_code=400, detail=f"Unknown AI_PROVIDER '{provider}'. Valid values: anthropic, openai, gemini.")


def _parse_json_response(raw: str) -> dict:
    """Strip markdown fences if present, then parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SuggestRequest(BaseModel):
    description: str
    systems: list[str] = ["snomed", "icd10cm", "loinc"]
    limit: int = 10


class DescribeRequest(BaseModel):
    codes: list[dict]
    context: Optional[str] = None


class MapRequest(BaseModel):
    codes: list[dict]
    source_system: str
    target_system: str


class MapSaveRequest(BaseModel):
    mappings: list[dict]
    source_system_url: str   # canonical system URL (from selected codes' .system field)
    target_system: str       # SDO id e.g. "icd10cm", "snomed", "rxnorm"
    name: str                # machine-readable UpperCamelCase name
    title: str               # human-readable title
    description: Optional[str] = None
    purpose: Optional[str] = None
    status: str = "draft"


def _sdo_id_to_url(sdo_id: str) -> str:
    """Resolve an SDO short-id to its canonical FHIR system URL."""
    info = next((s for s in external_cs.list_systems() if s["id"] == sdo_id), {})
    return info.get("url", sdo_id)


class ValidateValueSetRequest(BaseModel):
    codes: list[dict] = []          # inline code list: [{code, system, display?, systemName?}]
    valueset_id: Optional[str] = None  # pull codes from a stored ValueSet instead
    context: Optional[str] = None   # optional free-text context for the AI narrative


class ChatTurn(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatTurn]
    valueset_context: Optional[dict] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/provider")
def get_provider():
    """Return the currently configured AI provider and model."""
    provider = _provider()
    model_env = {
        "anthropic": ("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "openai":    ("OPENAI_MODEL",    "gpt-4o"),
        "gemini":    ("GEMINI_MODEL",    "gemini-2.0-flash"),
    }
    key_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai":    "OPENAI_API_KEY",
        "gemini":    "GEMINI_API_KEY",
    }
    env_var, default = model_env.get(provider, ("", ""))
    model = os.getenv(env_var, default) if env_var else "unknown"
    configured = bool(os.getenv(key_env.get(provider, ""), ""))
    return {"provider": provider, "model": model, "configured": configured}


@router.post("/suggest")
async def suggest_codes(req: SuggestRequest):
    """
    Search across one or more external code systems for a concept described in
    plain language, then use the configured AI provider to rank and explain the
    best matches with confidence ratings and clinical rationale.
    """
    async def _safe_search(sys_id: str) -> list:
        try:
            return await asyncio.wait_for(
                external_cs.search(sys_id, req.description, req.limit),
                timeout=8.0,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("SDO search timed out / failed [%s]: %s", sys_id, e)
            return []

    all_results = await asyncio.gather(*[_safe_search(s) for s in req.systems])
    candidates = [item for sublist in all_results for item in sublist]

    if not candidates:
        return {
            "suggestions": [],
            "additional_search_terms": [],
            "notes": "No results found from the selected code systems. Try broader search terms or different systems.",
        }

    candidates_trimmed = candidates[:60]

    prompt = f"""You are a clinical terminology expert helping a public health vocabulary specialist \
build a FHIR ValueSet.

The specialist needs codes that represent this clinical concept:
"{req.description}"

Here are candidate codes retrieved from standard code systems:
{json.dumps(candidates_trimmed, indent=2)}

Your task:
1. Select the most clinically relevant codes (up to {req.limit}) that best represent the described concept.
2. Assign a confidence level: "high" (direct match), "medium" (related), or "low" (possible but indirect).
3. Write a concise clinical rationale (1-2 sentences) for each selected code.
4. If a code is close but has an important caveat (too broad, retired, wrong context), note it in "caveats".
5. Suggest 2-3 additional search terms the specialist could use to find better candidates.

CRITICAL: You MUST copy the "code", "display", "system", and "systemName" values EXACTLY as they \
appear in the candidate list above. Do NOT paraphrase, translate, or rewrite display names — \
the authoritative display from the source system must be preserved verbatim.

Respond ONLY with valid JSON in this exact structure (no markdown, no explanation outside the JSON):
{{
  "suggestions": [
    {{
      "code": "string",
      "display": "string",
      "system": "string",
      "systemName": "string",
      "rationale": "string",
      "confidence": "high|medium|low",
      "caveats": "string or null"
    }}
  ],
  "additional_search_terms": ["string"],
  "notes": "string"
}}"""

    try:
        raw = _complete(prompt, max_tokens=2048)
        parsed = _parse_json_response(raw)
    except HTTPException:
        raise
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Failed to parse AI suggest response: %s", e)
        return {
            "suggestions": candidates_trimmed[: req.limit],
            "additional_search_terms": [],
            "notes": "AI response parse error — returning raw search results.",
        }
    except Exception as e:
        logger.error("Unexpected error in /ai/suggest: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}") from e

    # Validate every suggestion against the live terminology server.
    # Sets validated=True (confirmed), False (not found), or None (system not connected).
    suggestions = parsed.get("suggestions", [])
    if suggestions:
        suggestions = list(
            await asyncio.gather(*[_validate_suggested_code(s) for s in suggestions])
        )
        parsed["suggestions"] = suggestions

    return parsed


@router.post("/describe")
async def describe_valueset(req: DescribeRequest):
    """
    Given a list of selected codes, use the configured AI provider to generate
    professional FHIR ValueSet metadata: name, title, description, purpose, URL.
    """
    context_note = f"\nAdditional context: {req.context}" if req.context else ""

    prompt = f"""You are a clinical terminology expert.

A public health vocabulary specialist has selected these codes for a new FHIR ValueSet:
{json.dumps(req.codes, indent=2)}
{context_note}

Generate professional FHIR ValueSet metadata. Requirements:
- name: UpperCamelCase, no spaces, descriptive (e.g. "BloodPressureObservationCodes")
- title: Human-readable sentence case (e.g. "Blood Pressure Observation Codes")
- description: 1-3 sentences describing what this ValueSet contains and its clinical purpose
- purpose: When/why this ValueSet should be used
- suggested_url: A canonical URL following the pattern http://terminology.example.org/ValueSet/<kebab-case-name>

Respond ONLY with valid JSON (no markdown, no explanation outside the JSON):
{{
  "name": "string",
  "title": "string",
  "description": "string",
  "purpose": "string",
  "suggested_url": "string",
  "notes": "string"
}}"""

    try:
        raw = _complete(prompt, max_tokens=1024)
        return _parse_json_response(raw)
    except HTTPException:
        raise
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Failed to parse AI describe response: %s", e)
        return {"notes": "AI response parse error."}
    except Exception as e:
        logger.error("Unexpected error in /ai/describe: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}") from e


@router.post("/map")
async def map_codes(req: MapRequest):
    """
    Given a list of codes from one system, use the configured AI provider to
    suggest equivalent codes in a target system with FHIR equivalence values.
    """
    target_searches = [
        external_cs.search(req.target_system, c.get("display", c.get("code", "")), 5)
        for c in req.codes[:10]
    ]
    target_results_list = await asyncio.gather(*target_searches, return_exceptions=True)

    target_candidates = []
    for r in target_results_list:
        if isinstance(r, list):
            target_candidates.extend(r)

    sys_info = next(
        (s for s in external_cs.list_systems() if s["id"] == req.target_system), {}
    )
    target_name = sys_info.get("name", req.target_system)

    prompt = f"""You are a clinical terminology expert specializing in cross-terminology code mapping.

Source codes to map:
{json.dumps(req.codes, indent=2)}

Target system: {target_name}

Candidate codes found in {target_name}:
{json.dumps(target_candidates[:50], indent=2)}

For each source code, identify the best equivalent in {target_name}.

FHIR equivalence values (use exactly one):
- "equivalent"  — exactly the same clinical meaning
- "wider"        — the target concept is broader than the source
- "narrower"     — the target concept is more specific than the source
- "inexact"      — overlapping but not equivalent in all contexts
- "unmatched"    — no suitable equivalent exists in the target system

Respond ONLY with valid JSON (no markdown, no explanation outside the JSON):
{{
  "mappings": [
    {{
      "source_code": "string",
      "source_display": "string",
      "target_code": "string or null",
      "target_display": "string or null",
      "target_system": "string",
      "equivalence": "equivalent|wider|narrower|inexact|unmatched",
      "rationale": "string"
    }}
  ],
  "notes": "string"
}}"""

    try:
        raw = _complete(prompt, max_tokens=2048)
        return _parse_json_response(raw)
    except HTTPException:
        raise
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Failed to parse AI map response: %s", e)
        return {"mappings": [], "notes": "AI response parse error."}
    except Exception as e:
        logger.error("Unexpected error in /ai/map: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}") from e


@router.post("/map-save", status_code=201)
async def save_map_as_concept_map(req: MapSaveRequest):
    """
    Persist AI mapping results as a FHIR R4 ConceptMap resource.

    Transforms AiMapResponse.mappings[] into a ConceptMap group, storing
    each mapping's rationale as a target.comment and the AI equivalence value
    directly as the FHIR equivalence code.
    """
    source_url = req.source_system_url
    target_url = _sdo_id_to_url(req.target_system)

    elements = []
    for m in req.mappings:
        if m.get("target_code"):
            target_entry: dict = {
                "code": m["target_code"],
                "display": m.get("target_display") or "",
                "equivalence": m.get("equivalence", "inexact"),
            }
            if m.get("rationale"):
                target_entry["comment"] = m["rationale"]
            targets = [target_entry]
        else:
            targets = [{"equivalence": "unmatched"}]

        elements.append({
            "code": m.get("source_code", ""),
            "display": m.get("source_display", ""),
            "target": targets,
        })

    concept_map: dict = {
        "resourceType": "ConceptMap",
        "name": req.name,
        "title": req.title,
        "status": req.status,
        "group": [{
            "source": source_url,
            "target": target_url,
            "element": elements,
        }],
    }
    if req.description:
        concept_map["description"] = req.description
    if req.purpose:
        concept_map["purpose"] = req.purpose

    resource_id = await state.db.create_resource("ConceptMap", concept_map)
    await state.search_engine.index_resource(concept_map)
    await state.cache.invalidate_pattern("ConceptMap:*")
    saved = await state.db.get_resource(resource_id)
    return JSONResponse(content=saved, status_code=201)


async def _find_alternative_codes(entry: dict) -> dict:
    """For a code that failed validation, search the same system for close matches."""
    sdo_id = _URL_TO_SDO_ID.get(entry.get("system", ""))
    if not sdo_id:
        return {**entry, "alternatives": []}
    query = entry.get("display") or entry.get("code", "")
    try:
        results = await asyncio.wait_for(
            external_cs.search(sdo_id, query, 3), timeout=5.0
        )
        return {**entry, "alternatives": results[:3]}
    except Exception:
        return {**entry, "alternatives": []}


_URL_TO_SDO_ID = {
    "http://snomed.info/sct":                       "snomed",
    "http://loinc.org":                             "loinc",
    "http://hl7.org/fhir/sid/icd-10-cm":           "icd10cm",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "rxnorm",
}

_URL_TO_SYSTEM_NAME = {
    "http://snomed.info/sct":                       "SNOMED CT",
    "http://loinc.org":                             "LOINC",
    "http://hl7.org/fhir/sid/icd-10-cm":           "ICD-10-CM",
    "http://hl7.org/fhir/sid/icd-9-cm":            "ICD-9-CM",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
    "http://hl7.org/fhir/sid/cvx":                 "CVX",
}

# Regex patterns for detecting codes mentioned in free-text conversation.
# Only match formats that are unambiguous enough to be worth a live lookup.
_CODE_PATTERNS = [
    # SNOMED CT: 6–12 digit plain integer
    ("snomed", "http://snomed.info/sct", "SNOMED CT",
     re.compile(r'(?<!\d)(\d{6,12})(?!\d)')),
    # LOINC: digits-check-digit, e.g. 94500-6
    ("loinc", "http://loinc.org", "LOINC",
     re.compile(r'(?<!\d)(\d{1,5}-\d)(?!\d)')),
    # ICD-10-CM: letter + 2 digits + optional .chars, e.g. J12.82
    ("icd10cm", "http://hl7.org/fhir/sid/icd-10-cm", "ICD-10-CM",
     re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,4})?)\b')),
]


async def _lookup_codes_in_text(text: str) -> list[dict]:
    """
    Scan free text for recognisable code patterns, look each up against the live
    terminology server, and return authoritative {code, system, systemName, display}
    records.  Only codes that resolve successfully are included.
    """
    seen: set[tuple[str, str]] = set()
    tasks: list[tuple[str, str, str, str]] = []  # (sdo_id, url, system_name, code)

    for sdo_id, url, system_name, pattern in _CODE_PATTERNS:
        for m in pattern.finditer(text):
            code = m.group(1)
            key = (sdo_id, code)
            if key not in seen:
                seen.add(key)
                tasks.append((sdo_id, url, system_name, code))

    if not tasks:
        return []

    async def _do_lookup(sdo_id, url, system_name, code):
        try:
            result = await asyncio.wait_for(
                external_cs.lookup(sdo_id, code), timeout=5.0
            )
            if result and result.get("display"):
                return {"code": code, "system": url,
                        "systemName": system_name, "display": result["display"]}
        except Exception:
            pass
        return None

    results = await asyncio.gather(*[_do_lookup(*t) for t in tasks])
    return [r for r in results if r is not None]


async def _validate_suggested_code(entry: dict) -> dict:
    """
    Replace AI-generated display with the authoritative live-lookup value.
    Adds 'validated' field: True = confirmed, False = not found, None = system not connected.
    """
    system = entry.get("system", "")
    code = entry.get("code", "")
    if not system or not code:
        return {**entry, "validated": None}
    sdo_id = _URL_TO_SDO_ID.get(system)
    if not sdo_id:
        return {**entry, "validated": None}
    try:
        result = await asyncio.wait_for(
            external_cs.lookup(sdo_id, code), timeout=5.0
        )
        if result and result.get("display"):
            return {**entry, "display": result["display"], "validated": True}
        if result is None:
            return {
                **entry,
                "caveats": "Code not found in live terminology server — verify before use.",
                "validated": False,
            }
    except Exception:
        pass
    return {**entry, "validated": None}


@router.post("/validate-valueset")
async def validate_valueset(req: ValidateValueSetRequest):
    """
    Agentic ValueSet validation. Two-phase:

    Phase 1 — mechanical: run live $lookup on every code, categorise as
      valid / invalid / unvalidatable (system not connected).
      For invalid codes, search the same system for close alternatives.

    Phase 2 — AI narrative: feed the full validation report to the AI,
      which explains each failure, recommends specific replacements, flags
      overall quality concerns, and returns a ready_to_save verdict.

    Accepts either an inline code list or a valueset_id to pull from the DB.
    """
    # ── 1. Resolve codes ──────────────────────────────────────────────────────
    codes: list[dict] = list(req.codes)

    if req.valueset_id and not codes:
        resource = await state.db.get_resource(req.valueset_id)
        if not resource:
            raise HTTPException(status_code=404, detail=f"ValueSet {req.valueset_id} not found")
        for include in resource.get("compose", {}).get("include", []):
            system = include.get("system", "")
            system_name = _URL_TO_SYSTEM_NAME.get(system, system)
            for concept in include.get("concept", []):
                codes.append({
                    "code": concept.get("code", ""),
                    "display": concept.get("display", ""),
                    "system": system,
                    "systemName": system_name,
                })
        if not codes:
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "unvalidatable": 0,
                "results": {"valid": [], "invalid": [], "unvalidatable": []},
                "ai_review": {
                    "summary": "ValueSet has no explicit concepts (intensional definition). Use $expand to preview codes before validating.",
                    "issues": [],
                    "overall_concerns": ["Intensional ValueSets cannot be validated without expansion."],
                    "ready_to_save": None,
                },
            }

    if not codes:
        raise HTTPException(status_code=400, detail="Provide codes[] or a valueset_id with stored concepts.")

    # Attach systemName where missing
    for c in codes:
        if not c.get("systemName"):
            c["systemName"] = _URL_TO_SYSTEM_NAME.get(c.get("system", ""), c.get("system", ""))

    # ── 2. Live validation — concurrent $lookup for every code ────────────────
    validated = list(await asyncio.gather(*[_validate_suggested_code(c) for c in codes]))

    passed = [c for c in validated if c.get("validated") is True]
    failed = [c for c in validated if c.get("validated") is False]
    unvalidatable = [c for c in validated if c.get("validated") is None]

    # ── 3. Find alternatives for failed codes ─────────────────────────────────
    if failed:
        failed = list(await asyncio.gather(*[_find_alternative_codes(c) for c in failed]))

    # ── 4. AI narrative ───────────────────────────────────────────────────────
    def _slim(codes_list: list, include_alts: bool = False) -> list:
        out = []
        for c in codes_list:
            entry = {"code": c["code"], "display": c.get("display", ""), "system": c.get("systemName", c.get("system", ""))}
            if include_alts and c.get("alternatives"):
                entry["alternatives"] = [{"code": a["code"], "display": a.get("display", "")} for a in c["alternatives"]]
            out.append(entry)
        return out

    context_note = f"\nAdditional context: {req.context}" if req.context else ""
    prompt = f"""You are a clinical terminology expert reviewing a FHIR ValueSet for quality.{context_note}

Live terminology server validation results:

PASSED — {len(passed)} codes confirmed valid in the live server:
{json.dumps(_slim(passed), indent=2)}

FAILED — {len(failed)} codes NOT found in the live server (with search candidates for replacement):
{json.dumps(_slim(failed, include_alts=True), indent=2)}

UNVALIDATABLE — {len(unvalidatable)} codes whose system is not connected to this server:
{json.dumps(_slim(unvalidatable), indent=2)}

Tasks:
1. Write a 2-3 sentence quality summary.
2. For each FAILED code: explain the likely reason (retired code, wrong system, typo, version mismatch) and pick the best replacement from the alternatives provided.
3. Note any overall concerns: duplicate concepts, inconsistent specificity, missing coverage gaps, licensing issues.
4. Set ready_to_save to true only if all validatable codes passed.

Respond ONLY with valid JSON — no markdown, no text outside the JSON:
{{
  "summary": "string",
  "issues": [
    {{
      "code": "string",
      "display": "string",
      "issue": "string",
      "recommendation": "string",
      "suggested_replacement": {{"code": "string", "display": "string", "system": "string"}} | null
    }}
  ],
  "overall_concerns": ["string"],
  "ready_to_save": true | false | null
}}"""

    try:
        raw = _complete(prompt, max_tokens=2048)
        ai_review = _parse_json_response(raw)
    except Exception as e:
        logger.warning("AI narrative failed in /ai/validate-valueset: %s", e)
        ai_review = {
            "summary": f"{len(passed)} of {len(codes)} codes confirmed valid. {len(failed)} not found. {len(unvalidatable)} could not be checked (system not connected).",
            "issues": [],
            "overall_concerns": [],
            "ready_to_save": len(failed) == 0 or None,
        }

    return {
        "total": len(codes),
        "passed": len(passed),
        "failed": len(failed),
        "unvalidatable": len(unvalidatable),
        "results": {
            "valid": passed,
            "invalid": failed,
            "unvalidatable": unvalidatable,
        },
        "ai_review": ai_review,
    }


@router.post("/chat")
async def chat_sme(req: ChatRequest):
    """
    Free-form multi-turn conversation with an AI Assistant acting as an expert vocabulary specialist.
    Maintains full conversation history. ValueSet context (description, purpose,
    selected codes) is injected into the system prompt so the AI can give
    contextually relevant guidance.

    When the AI recommends specific codes it wraps them in <suggested_codes>[...]
    </suggested_codes> — these are parsed out and returned as structured data
    so the frontend can render them as addable code cards.
    """
    # Build context block from the current ValueSet state
    ctx = req.valueset_context or {}
    context_lines = []
    if ctx.get("title") or ctx.get("name"):
        context_lines.append(f"Name/title: {ctx.get('title') or ctx.get('name')}")
    if ctx.get("description"):
        context_lines.append(f"Description: {ctx['description']}")
    if ctx.get("purpose"):
        context_lines.append(f"Purpose: {ctx['purpose']}")
    codes = ctx.get("codes", [])
    if codes:
        summary = ", ".join(
            f"{c.get('display') or c.get('code', '')} [{c.get('systemName') or c.get('system', '')}]"
            for c in codes[:20]
        )
        context_lines.append(f"Codes selected so far ({len(codes)}): {summary}")

    context_block = "\n".join(context_lines) if context_lines else "No ValueSet context provided yet."

    # Pre-lookup: scan the latest user message for code patterns and inject
    # authoritative results into the system prompt BEFORE the AI responds.
    # This eliminates hallucinated code meanings — the AI is given ground-truth
    # data and forbidden from substituting its own training-data memory.
    latest_user_text = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )
    live_lookups = await _lookup_codes_in_text(latest_user_text)

    if live_lookups:
        lookup_lines = "\n".join(
            f"  {r['systemName']} {r['code']} = \"{r['display']}\""
            for r in live_lookups
        )
        live_lookup_block = (
            f"\n\nAuthoritative code lookups from the live terminology server "
            f"(verified — use these exact values):\n{lookup_lines}"
        )
    else:
        live_lookup_block = ""

    system_prompt = f"""You are an AI Assistant with deep expertise in FHIR R4 terminology and vocabulary, \
embedded in a public health FHIR Terminology Server. You are assisting a public health informaticist \
who is building FHIR R4 ValueSets.

Your expertise covers:
- SNOMED CT: clinical concept hierarchies, pre/post-coordinated expressions, ECL queries, \
  US Edition vs International, preferred terms vs synonyms
- LOINC: lab tests, clinical observations, panels, surveys, radiology, LOINC parts and hierarchy
- ICD-10-CM / ICD-9-CM: diagnosis coding, HCC risk adjustment, public health surveillance, \
  code specificity and laterality
- RxNorm: normalized drug names, clinical drug components, prescribable drugs, ingredient/product distinction
- HL7 v2/v3 code systems: administrative gender, race/ethnicity, marital status, observation status
- CDC vocabularies: CVX, MVX, notifiable conditions, syndromic surveillance
- CVX/MVX: immunization vaccine and manufacturer codes
- CPT / HCPCS: procedure coding (license-aware — advise on usage without reproducing code lists)
- NDC: National Drug Codes
- ISO 3166: country/territory codes
- FHIR R4 ValueSet design: intensional vs extensional definitions, use of filters and \
  hierarchy operators, versioning strategy, canonical URL conventions

CRITICAL — Code accuracy rules (follow these without exception):
1. NEVER state what a specific code number means from your training data memory alone.
2. If authoritative lookup results are provided below, use ONLY those values when \
   discussing those codes. Do not contradict or supplement them.
3. If the user asks about a code that has NO lookup result below, say: \
   "I cannot confirm the meaning of [code] from my training data — please use the \
   Search or $lookup tool to get the authoritative display from the live system."
4. When emitting <suggested_codes> blocks, only include codes whose display you obtained \
   from live lookup results or from the /ai/suggest search results — never from memory.
5. It is better to say "I don't know the exact code" than to state a wrong one.

When you recommend specific codes that have been verified by live lookup, emit them so the \
user can add them to the ValueSet with one click:

<suggested_codes>
[{{"code": "119297000", "display": "Blood specimen", "system": "http://snomed.info/sct", "systemName": "SNOMED CT"}}]
</suggested_codes>

Be concise and practical. Explain terminology hierarchies, design trade-offs, and system \
differences in prose. For specific code values, always rely on live lookup results or \
direct the user to search.
Flag licensing constraints (SNOMED affiliate license, LOINC free account, CPT AMA license) \
when relevant.

Current ValueSet being built:
{context_block}{live_lookup_block}"""

    conversation = [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        raw = _complete_chat(system_prompt, conversation, max_tokens=2048)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in /ai/chat: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}") from e

    # Extract and strip <suggested_codes> blocks
    suggested_codes: list[dict] = []
    code_block_re = re.compile(r"<suggested_codes>\s*(.*?)\s*</suggested_codes>", re.DOTALL)
    for match in code_block_re.finditer(raw):
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, list):
                suggested_codes.extend(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    reply_text = code_block_re.sub("", raw).strip()

    # Post-validate: replace any AI-written displays in suggested_codes with
    # authoritative live-lookup values (second line of defence).
    if suggested_codes:
        suggested_codes = list(
            await asyncio.gather(*[_validate_suggested_code(c) for c in suggested_codes])
        )

    return {"reply": reply_text, "suggested_codes": suggested_codes}
