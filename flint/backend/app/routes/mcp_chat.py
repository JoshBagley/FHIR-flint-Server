"""
MCP-style FHIR chat — AI with tool-calling backed by Flint-FHIR endpoints.

Exposes the same six operations defined in xSoVx/fhir-mcp (Option 1):
  fhir_capabilities, fhir_search, fhir_read,
  terminology_lookup, terminology_expand, terminology_translate

The AI provider (anthropic | openai | gemini) is selected via AI_PROVIDER env var,
same as the rest of the ai_assist routes.  Each provider's native tool-calling /
function-calling API is used so the model can autonomously decide which tools to
invoke and chain multiple calls before giving a final answer.

POST /mcp-chat/chat   — agentic chat with tool use
GET  /mcp-chat/tools  — list available tools (no auth required)
"""

import os
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/mcp-chat", tags=["MCP Chat"])
logger = logging.getLogger(__name__)

# Within the Docker container the FastAPI app is reachable on localhost:8000.
_FHIR_BASE = "http://localhost:8000"
_MAX_TOOL_ROUNDS = 6        # guard against infinite loops
_TOOL_TIMEOUT = 30.0        # seconds per HTTP tool call


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic / JSON Schema format — converted per provider)
# ---------------------------------------------------------------------------

MCP_TOOLS: list[dict] = [
    {
        "name": "fhir_capabilities",
        "description": (
            "Retrieve the FHIR server capability statement.  "
            "Use this to discover what resource types and operations the server supports."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "fhir_search",
        "description": (
            "Search for FHIR resources (ValueSet, CodeSystem, or ConceptMap).  "
            "Returns a summary list with id, name, title, status, and canonical URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "enum": ["ValueSet", "CodeSystem", "ConceptMap"],
                    "description": "The FHIR resource type to search.",
                },
                "name": {
                    "type": "string",
                    "description": "Filter by resource name or title (partial match).",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: active | draft | retired.",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum results to return (1–20, default 10).",
                },
            },
            "required": ["resource_type"],
        },
    },
    {
        "name": "fhir_read",
        "description": (
            "Read a specific FHIR resource by type and ID.  "
            "Returns metadata without the full concept/compose arrays (too large); "
            "use terminology_expand to retrieve the codes of a ValueSet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "enum": ["ValueSet", "CodeSystem", "ConceptMap"],
                },
                "resource_id": {
                    "type": "string",
                    "description": "The FHIR resource id (UUID or slug).",
                },
            },
            "required": ["resource_type", "resource_id"],
        },
    },
    {
        "name": "terminology_lookup",
        "description": (
            "Look up a specific code in a FHIR CodeSystem to retrieve its display "
            "name and properties."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "system": {
                    "type": "string",
                    "description": "Canonical CodeSystem URL (e.g. http://snomed.info/sct).",
                },
                "code": {"type": "string", "description": "The code to look up."},
            },
            "required": ["system", "code"],
        },
    },
    {
        "name": "terminology_expand",
        "description": (
            "Expand a ValueSet to retrieve its list of codes.  "
            "Pass a text filter to narrow results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Canonical ValueSet URL.",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum codes to return (1–100, default 20).",
                },
                "filter": {
                    "type": "string",
                    "description": "Optional text filter to narrow returned codes.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "terminology_translate",
        "description": (
            "Translate a code from one code system to another using a stored ConceptMap."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "system": {
                    "type": "string",
                    "description": "Source code system URL.",
                },
                "target_system": {
                    "type": "string",
                    "description": "Target code system URL.",
                },
            },
            "required": ["code", "system", "target_system"],
        },
    },
]

_SYSTEM_PROMPT = """\
You are a FHIR R4 terminology assistant connected to Flint-FHIR — a general-purpose
FHIR R4 terminology server containing value sets, code systems, and concept maps.

You have access to six tools that mirror the operations exposed by the
xSoVx/fhir-mcp MCP server:
  • fhir_capabilities   — what the server supports
  • fhir_search         — search ValueSets, CodeSystems, or ConceptMaps
  • fhir_read           — read a resource by ID
  • terminology_lookup  — look up a code in a code system
  • terminology_expand  — expand a ValueSet to see its codes
  • terminology_translate — translate codes between systems via a ConceptMap

Use tools to answer the user's questions accurately.  When listing codes always
show the code and its display name.  Keep responses concise and well-structured.
"""


# ---------------------------------------------------------------------------
# Tool execution — self-HTTP calls back into the running Flint-FHIR API
# ---------------------------------------------------------------------------

async def _execute_tool(name: str, args: dict) -> Any:
    """Call a Flint-FHIR endpoint and return a JSON-serialisable result."""
    headers = {"Accept": "application/fhir+json"}
    try:
        async with httpx.AsyncClient(timeout=_TOOL_TIMEOUT) as client:

            if name == "fhir_capabilities":
                resp = await client.get(f"{_FHIR_BASE}/metadata", headers=headers)
                data = resp.json()
                resources = [
                    r.get("type")
                    for r in (data.get("rest", [{}])[0].get("resource", []))
                ]
                return {
                    "fhirVersion": data.get("fhirVersion"),
                    "status": data.get("status"),
                    "resourceTypes": resources,
                }

            elif name == "fhir_search":
                rt = args.get("resource_type", "ValueSet")
                params: dict[str, str] = {
                    "_summary": "true",
                    "_count": str(min(int(args.get("count", 10)), 20)),
                }
                if args.get("name"):
                    params["name"] = args["name"]
                if args.get("status"):
                    params["status"] = args["status"]
                resp = await client.get(
                    f"{_FHIR_BASE}/{rt}", params=params, headers=headers
                )
                data = resp.json()
                entries = data.get("entry", [])
                resources = [
                    {
                        "id": e["resource"].get("id"),
                        "name": e["resource"].get("name"),
                        "title": e["resource"].get("title"),
                        "status": e["resource"].get("status"),
                        "url": e["resource"].get("url"),
                        "conceptCount": e["resource"].get("_conceptCount"),
                    }
                    for e in entries
                    if "resource" in e
                ]
                return {"total": data.get("total", len(resources)), "resources": resources}

            elif name == "fhir_read":
                rt = args.get("resource_type", "ValueSet")
                rid = args.get("resource_id", "")
                resp = await client.get(
                    f"{_FHIR_BASE}/{rt}/{rid}", headers=headers
                )
                if resp.status_code == 404:
                    return {"error": f"{rt}/{rid} not found"}
                data = resp.json()
                # Strip large arrays — use terminology_expand for codes
                trimmed = {
                    k: v
                    for k, v in data.items()
                    if k not in ("concept", "compose", "expansion", "group")
                }
                return trimmed

            elif name == "terminology_lookup":
                resp = await client.get(
                    f"{_FHIR_BASE}/CodeSystem/$lookup",
                    params={"system": args.get("system", ""), "code": args.get("code", "")},
                    headers=headers,
                )
                return resp.json()

            elif name == "terminology_expand":
                url = args.get("url", "")
                count = min(int(args.get("count", 20)), 100)
                params = {"url": url, "count": str(count)}
                if args.get("filter"):
                    params["filter"] = args["filter"]
                resp = await client.get(
                    f"{_FHIR_BASE}/ValueSet/$expand", params=params, headers=headers
                )
                data = resp.json()
                contains = data.get("expansion", {}).get("contains", [])
                return {
                    "total": data.get("expansion", {}).get("total", len(contains)),
                    "codes": contains[:100],
                }

            elif name == "terminology_translate":
                resp = await client.get(
                    f"{_FHIR_BASE}/ConceptMap/$translate",
                    params={
                        "code": args.get("code", ""),
                        "system": args.get("system", ""),
                        "target": args.get("target_system", ""),
                    },
                    headers=headers,
                )
                return resp.json()

            else:
                return {"error": f"Unknown tool: {name}"}

    except httpx.RequestError as exc:
        logger.warning("Tool %s HTTP error: %s", name, exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Per-provider schema conversion helpers
# ---------------------------------------------------------------------------

def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def _schema_to_gemini(schema: dict) -> dict:
    """Recursively convert JSON Schema (lowercase types) to Gemini format (UPPER)."""
    _map = {
        "object": "OBJECT",
        "string": "STRING",
        "integer": "INTEGER",
        "number": "NUMBER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
    }
    result: dict = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            result[k] = _map.get(v, v.upper())
        elif k == "properties" and isinstance(v, dict):
            result[k] = {pk: _schema_to_gemini(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            result[k] = _schema_to_gemini(v)
        elif k == "enum":
            # Gemini doesn't support enum in function schemas — skip
            pass
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Provider-specific agentic loops
# ---------------------------------------------------------------------------

async def _run_anthropic(messages: list[dict], tool_calls_out: list[dict]) -> str:
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="AI provider 'anthropic' requires ANTHROPIC_API_KEY.",
        )
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=key)

    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in MCP_TOOLS
    ]

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        for _ in range(_MAX_TOOL_ROUNDS):
            if resp.stop_reason != "tool_use":
                break

            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = await _execute_tool(block.name, block.input)
                    tool_calls_out.append(
                        {"tool": block.name, "args": block.input, "result": result}
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )

            # Serialize content blocks to dicts for the next request
            messages = messages + [
                {
                    "role": "assistant",
                    "content": [
                        (
                            {"type": "text", "text": b.text}
                            if b.type == "text"
                            else {
                                "type": "tool_use",
                                "id": b.id,
                                "name": b.name,
                                "input": b.input,
                            }
                        )
                        for b in resp.content
                    ],
                },
                {"role": "user", "content": tool_results},
            ]

            resp = client.messages.create(
                model=model,
                max_tokens=2048,
                system=_SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

        return next(
            (b.text for b in resp.content if hasattr(b, "text") and b.text),
            "(no response)",
        )

    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {exc.message}") from exc


async def _run_openai(messages: list[dict], tool_calls_out: list[dict]) -> str:
    from openai import OpenAI
    import openai as _openai

    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="AI provider 'openai' requires OPENAI_API_KEY.",
        )
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=key)
    oai_tools = _to_openai_tools(MCP_TOOLS)
    oai_messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + messages

    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=2048,
            tools=oai_tools,
            messages=oai_messages,
        )

        for _ in range(_MAX_TOOL_ROUNDS):
            choice = resp.choices[0]
            if choice.finish_reason != "tool_calls":
                break

            msg = choice.message
            oai_messages.append(msg)

            for tc in msg.tool_calls or []:
                args = json.loads(tc.function.arguments)
                result = await _execute_tool(tc.function.name, args)
                tool_calls_out.append(
                    {"tool": tc.function.name, "args": args, "result": result}
                )
                oai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            resp = client.chat.completions.create(
                model=model,
                max_tokens=2048,
                tools=oai_tools,
                messages=oai_messages,
            )

        return resp.choices[0].message.content or "(no response)"

    except _openai.APIError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {exc.message}") from exc


async def _run_gemini(messages: list[dict], tool_calls_out: list[dict]) -> str:
    from google import genai
    from google.genai import types as gtypes

    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="AI provider 'gemini' requires GEMINI_API_KEY.",
        )
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = genai.Client(api_key=key)

    gemini_tools = gtypes.Tool(
        function_declarations=[
            gtypes.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=_schema_to_gemini(t["input_schema"]),
            )
            for t in MCP_TOOLS
        ]
    )

    def _to_contents(msgs: list[dict]) -> list[gtypes.Content]:
        return [
            gtypes.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[gtypes.Part(text=m["content"])],
            )
            for m in msgs
        ]

    contents = _to_contents(messages)
    cfg = gtypes.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        tools=[gemini_tools],
    )

    try:
        for _ in range(_MAX_TOOL_ROUNDS):
            resp = client.models.generate_content(
                model=model, contents=contents, config=cfg
            )

            # Check for function calls in any part
            fc_parts = [
                p for p in resp.candidates[0].content.parts if p.function_call
            ]
            if not fc_parts:
                break

            # Append the model's response to contents
            contents.append(resp.candidates[0].content)

            # Execute each function call and append results
            result_parts = []
            for part in fc_parts:
                fc = part.function_call
                args = dict(fc.args)
                result = await _execute_tool(fc.name, args)
                tool_calls_out.append({"tool": fc.name, "args": args, "result": result})
                result_parts.append(
                    gtypes.Part(
                        function_response=gtypes.FunctionResponse(
                            name=fc.name,
                            response={"result": json.dumps(result, default=str)},
                        )
                    )
                )
            contents.append(gtypes.Content(role="user", parts=result_parts))

        return resp.text or "(no response)"

    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class McpMessage(BaseModel):
    role: str    # "user" | "assistant"
    content: str


class McpChatRequest(BaseModel):
    messages: list[McpMessage]


class ToolCallRecord(BaseModel):
    tool: str
    args: dict
    result: Any


class McpChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallRecord] = []
    provider: str = ""
    model: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/tools")
def list_tools():
    """Return the list of available MCP-style tools and their descriptions."""
    return {
        "tools": [
            {"name": t["name"], "description": t["description"]}
            for t in MCP_TOOLS
        ]
    }


@router.post("/chat", response_model=McpChatResponse)
async def mcp_chat(req: McpChatRequest):
    """
    Chat endpoint with AI tool-calling backed by Flint-FHIR FHIR endpoints.
    The AI autonomously decides which tools to invoke to answer the question.
    """
    provider = os.getenv("AI_PROVIDER", "anthropic").lower()
    model_env = {
        "anthropic": ("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "openai":    ("OPENAI_MODEL",    "gpt-4o"),
        "gemini":    ("GEMINI_MODEL",    "gemini-2.0-flash"),
    }
    env_var, default_model = model_env.get(provider, ("", "unknown"))
    active_model = os.getenv(env_var, default_model) if env_var else default_model

    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    tool_calls_out: list[dict] = []

    if provider == "anthropic":
        reply = await _run_anthropic(messages, tool_calls_out)
    elif provider == "openai":
        reply = await _run_openai(messages, tool_calls_out)
    elif provider == "gemini":
        reply = await _run_gemini(messages, tool_calls_out)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown AI_PROVIDER '{provider}'. Valid values: anthropic, openai, gemini.",
        )

    return McpChatResponse(
        reply=reply,
        tool_calls=[ToolCallRecord(**tc) for tc in tool_calls_out],
        provider=provider,
        model=active_model,
    )
