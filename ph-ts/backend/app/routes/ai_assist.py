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
import json
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import external_cs

router = APIRouter(prefix="/ai", tags=["AI Assistant"])
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
        return _parse_json_response(raw)
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

    context_block = "\n".join(context_lines) if context_lines else "No ValueSet context provided yet — the user has not filled in details or selected codes."

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
- PHIN VADS / CDC public health vocabularies: PHIN, PHVS, notifiable conditions, syndromic surveillance
- CVX/MVX: immunization vaccine and manufacturer codes
- CPT / HCPCS: procedure coding (license-aware — advise on usage without reproducing code lists)
- NDC: National Drug Codes
- ISO 3166: country/territory codes
- FHIR R4 ValueSet design: intensional vs extensional definitions, use of filters and \
  hierarchy operators, versioning strategy, canonical URL conventions

When you recommend specific codes and are confident in them, emit them in a structured block \
so the user can add them to the ValueSet with one click:

<suggested_codes>
[{{"code": "263495000", "display": "Gender", "system": "http://snomed.info/sct", "systemName": "SNOMED CT"}}]
</suggested_codes>

Only use this format when you are confident in the specific code values. For exploratory \
suggestions where the user should verify, describe them in prose and recommend they search manually.

Be concise and practical. Cite specific codes, systems, and hierarchy paths where helpful. \
Flag licensing constraints (SNOMED affiliate license, LOINC free account, CPT AMA license) \
when the user is asking about restricted systems. When there are multiple valid options, \
explain the trade-offs so the user can make an informed choice.

Current ValueSet being built:
{context_block}"""

    conversation = [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        raw = _complete_chat(system_prompt, conversation, max_tokens=2048)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in /ai/chat: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}") from e

    # Extract and strip <suggested_codes> blocks
    import re
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

    return {"reply": reply_text, "suggested_codes": suggested_codes}
