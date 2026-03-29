"""
External Code System connector service.

Provides unified search and lookup across standard SDOs:
  - SNOMED CT    (HL7 tx.fhir.org public FHIR — no key required)
  - ICD-10-CM    (NLM ClinicalTables API — no key required)
  - LOINC        (fhir.loinc.org FHIR server when LOINC_USERNAME+LOINC_PASSWORD set,
                  falls back to NLM ClinicalTables if credentials absent)
  - RxNorm       (NLM RxNav REST API — no key required)
  - VSAC         (NLM VSAC FHIR — UMLS_API_KEY)
"""

import os
import base64  # still used by _vsac_auth_header
import logging
import asyncio
from typing import Optional

import aiohttp
import yarl

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System registry
# ---------------------------------------------------------------------------

SYSTEMS: dict = {
    "snomed": {
        "id": "snomed",
        "name": "SNOMED CT",
        "url": "http://snomed.info/sct",
        "publisher": "SNOMED International",
        "description": "Systematized Nomenclature of Medicine — Clinical Terms. Comprehensive clinical terminology. Delegated to HL7 tx.fhir.org.",
        "requires_key": False,
        "category": "clinical",
    },
    "loinc": {
        "id": "loinc",
        "name": "LOINC",
        "url": "http://loinc.org",
        "publisher": "Regenstrief Institute",
        "description": "Logical Observation Identifiers Names and Codes. Lab tests, clinical measurements, and observations. Uses fhir.loinc.org when LOINC_USERNAME/LOINC_PASSWORD are set.",
        "requires_key": False,
        "category": "laboratory",
    },
    "icd10cm": {
        "id": "icd10cm",
        "name": "ICD-10-CM",
        "url": "http://hl7.org/fhir/sid/icd-10-cm",
        "publisher": "CDC / CMS",
        "description": "International Classification of Diseases, 10th Revision, Clinical Modification. Diagnoses and conditions.",
        "requires_key": False,
        "category": "diagnosis",
    },
    "rxnorm": {
        "id": "rxnorm",
        "name": "RxNorm",
        "url": "http://www.nlm.nih.gov/research/umls/rxnorm",
        "publisher": "NLM",
        "description": "Normalized names for clinical drugs. Medications and drug products.",
        "requires_key": False,
        "category": "medication",
    },
    "vsac": {
        "id": "vsac",
        "name": "VSAC / NLM",
        "url": "https://cts.nlm.nih.gov/fhir",
        "publisher": "NLM / VSAC",
        "description": "Value Set Authority Center — access to LOINC, SNOMED, RxNorm, ICD-10 via UMLS credentials.",
        "requires_key": True,
        "key_vars": ["UMLS_API_KEY"],
        "category": "multi",
    },
    "hl7v2": {
        "id": "hl7v2",
        "name": "HL7 v2 Tables",
        "url": "http://terminology.hl7.org/CodeSystem/v2-",
        "publisher": "HL7 International",
        "description": "HL7 Version 2.x code tables (e.g., Table 0001 Administrative Sex, Table 0076 Message Type). Delegated to tx.fhir.org when not stored locally.",
        "requires_key": False,
        "category": "hl7",
    },
}


def list_systems() -> list:
    """Return all systems with availability flag based on configured env vars."""
    result = []
    for sys_id, info in SYSTEMS.items():
        available = True
        if info.get("requires_key"):
            available = all(os.getenv(var, "") for var in info.get("key_vars", []))
        result.append({**info, "available": available})
    return result


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _get(session: aiohttp.ClientSession, url: str, **kwargs) -> dict | list:
    async with session.get(url, timeout=_TIMEOUT, **kwargs) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


# ---------------------------------------------------------------------------
# SNOMED CT (HL7 tx.fhir.org public FHIR server — no auth)
# ---------------------------------------------------------------------------

_TX_FHIR = "https://tx.fhir.org/r4"


async def search_snomed(query: str, limit: int) -> list:
    url = f"{_TX_FHIR}/ValueSet/$expand"
    params = {
        "url": "http://snomed.info/sct?fhir_vs",
        "filter": query,
        "count": limit,
        "_format": "json",
    }
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    results = []
    for item in data.get("expansion", {}).get("contains", []):
        code = item.get("code", "")
        results.append({
            "code": code,
            "display": item.get("display", ""),
            "system": "http://snomed.info/sct",
            "systemName": "SNOMED CT",
            "sourceUrl": f"https://browser.ihtsdotools.org/?perspective=full&conceptId1={code}",
        })
    return results


async def lookup_snomed(code: str) -> Optional[dict]:
    url = f"{_TX_FHIR}/CodeSystem/$lookup"
    params = {"system": "http://snomed.info/sct", "code": code, "_format": "json"}
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    if not data:
        return None
    display = next(
        (p.get("valueString", "") for p in data.get("parameter", []) if p.get("name") == "display"),
        "",
    )
    return {
        "code": code,
        "display": display,
        "system": "http://snomed.info/sct",
        "systemName": "SNOMED CT",
        "active": True,
    }


# ---------------------------------------------------------------------------
# ICD-10-CM (NLM ClinicalTables — no auth)
# ---------------------------------------------------------------------------

async def search_icd10cm(query: str, limit: int) -> list:
    url = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
    params = {"sf": "code,name", "terms": query, "maxList": limit}
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    # Response format: [total, [codes], null, [[code, name], ...]]
    results = []
    for pair in (data[3] if len(data) > 3 and data[3] else []):
        code = pair[0]
        results.append({
            "code": code,
            "display": pair[1],
            "system": "http://hl7.org/fhir/sid/icd-10-cm",
            "systemName": "ICD-10-CM",
            "sourceUrl": f"https://www.icd10data.com/ICD10CM/Codes/{code}",
        })
    return results


async def lookup_icd10cm(code: str) -> Optional[dict]:
    url = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
    params = {"sf": "code,name", "terms": code, "maxList": 5}
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    for pair in (data[3] if len(data) > 3 and data[3] else []):
        if pair[0].upper() == code.upper():
            return {
                "code": pair[0],
                "display": pair[1],
                "system": "http://hl7.org/fhir/sid/icd-10-cm",
                "systemName": "ICD-10-CM",
            }
    return None


# ---------------------------------------------------------------------------
# RxNorm (NLM RxNav REST — no auth)
# ---------------------------------------------------------------------------

async def search_rxnorm(query: str, limit: int) -> list:
    url = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
    params = {"term": query, "maxEntries": limit}
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    results = []
    seen: set = set()
    for candidate in data.get("approximateGroup", {}).get("candidate", []):
        rxcui = candidate.get("rxcui")
        name = candidate.get("name", "")
        if rxcui and rxcui not in seen:
            seen.add(rxcui)
            results.append({
                "code": rxcui,
                "display": name,
                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "systemName": "RxNorm",
                "sourceUrl": f"https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm={rxcui}",
            })
    return results[:limit]


# ---------------------------------------------------------------------------
# LOINC (fhir.loinc.org with Basic auth when credentials set,
#         NLM ClinicalTables as no-auth fallback)
# ---------------------------------------------------------------------------

_LOINC_FHIR = "https://fhir.loinc.org"
_NLM_LOINC = "https://clinicaltables.nlm.nih.gov/api/loinc_items/v3/search"


def _loinc_auth_header() -> Optional[str]:
    u = os.getenv("LOINC_USERNAME", "")
    p = os.getenv("LOINC_PASSWORD", "")
    if u and p:
        return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()
    return None


async def search_loinc(query: str, limit: int) -> list:
    auth = _loinc_auth_header()
    if auth:
        # fhir.loinc.org $expand — richer FHIR results
        headers = {"Authorization": auth, "Accept": "application/fhir+json"}
        url = f"{_LOINC_FHIR}/ValueSet/$expand"
        params = {"url": "http://loinc.org/vs", "filter": query, "count": limit, "_format": "json"}
        async with aiohttp.ClientSession() as session:
            data = await _get(session, url, headers=headers, params=params)
        return [
            {
                "code": item.get("code", ""),
                "display": item.get("display", ""),
                "system": "http://loinc.org",
                "systemName": "LOINC",
                "sourceUrl": f"https://loinc.org/{item.get('code', '')}",
            }
            for item in data.get("expansion", {}).get("contains", [])
        ]
    else:
        # Fallback: NLM ClinicalTables (no auth)
        params = {"terms": query, "maxList": limit, "df": "LOINC_NUM,LONG_COMMON_NAME"}
        async with aiohttp.ClientSession() as session:
            data = await _get(session, _NLM_LOINC, params=params)
        return [
            {
                "code": pair[0],
                "display": pair[1],
                "system": "http://loinc.org",
                "systemName": "LOINC",
                "sourceUrl": f"https://loinc.org/{pair[0]}",
            }
            for pair in (data[3] if len(data) > 3 and data[3] else [])
        ]


async def lookup_loinc(code: str) -> Optional[dict]:
    auth = _loinc_auth_header()
    if auth:
        # fhir.loinc.org $lookup
        headers = {"Authorization": auth, "Accept": "application/fhir+json"}
        url = f"{_LOINC_FHIR}/CodeSystem/$lookup"
        params = {"system": "http://loinc.org", "code": code, "_format": "json"}
        async with aiohttp.ClientSession() as session:
            data = await _get(session, url, headers=headers, params=params)
        # $lookup returns a Parameters resource
        display = next(
            (p.get("valueString", "") for p in data.get("parameter", []) if p.get("name") == "display"),
            "",
        )
        if display:
            return {"code": code, "display": display, "system": "http://loinc.org", "systemName": "LOINC"}
        return None
    else:
        # Fallback: NLM ClinicalTables
        params = {"terms": code, "maxList": 5, "df": "LOINC_NUM,LONG_COMMON_NAME"}
        async with aiohttp.ClientSession() as session:
            data = await _get(session, _NLM_LOINC, params=params)
        for pair in (data[3] if len(data) > 3 and data[3] else []):
            if pair[0].upper() == code.upper():
                return {"code": pair[0], "display": pair[1], "system": "http://loinc.org", "systemName": "LOINC"}
        return None


# ---------------------------------------------------------------------------
# VSAC (NLM VSAC FHIR — Basic auth: apikey:<UMLS_API_KEY>)
# ---------------------------------------------------------------------------

def _vsac_auth_header() -> str:
    api_key = os.getenv("UMLS_API_KEY", "")
    return "Basic " + base64.b64encode(f"apikey:{api_key}".encode()).decode()


async def search_vsac(query: str, limit: int) -> list:
    if not os.getenv("UMLS_API_KEY", ""):
        return []
    headers = {
        "Authorization": _vsac_auth_header(),
        "Accept": "application/fhir+json",
    }
    url = "https://cts.nlm.nih.gov/fhir/ValueSet"
    params = {"name": query, "_count": limit}
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, headers=headers, params=params)
    results = []
    for entry in data.get("entry", []):
        r = entry.get("resource", {})
        vs_id = r.get("id", "")
        results.append({
            "code": vs_id,
            "display": r.get("title") or r.get("name", ""),
            "description": r.get("description", ""),
            "system": r.get("url", "https://cts.nlm.nih.gov/fhir"),
            "systemName": "VSAC",
            "sourceUrl": f"https://vsac.nlm.nih.gov/valueset/{vs_id}/expansion" if vs_id else "",
        })
    return results


# ---------------------------------------------------------------------------
# HL7 v2 Tables (tx.fhir.org public FHIR server — no auth)
# Used as fallback when v2 table concepts are not stored locally after running
# migration/import_hl7_v2_tables.py.
# ---------------------------------------------------------------------------

def _v2_system_name(system_url: str) -> str:
    """Derive a human-readable name from an HL7 v2 table URL."""
    if "v2-" in system_url:
        table_num = system_url.rsplit("v2-", 1)[-1]
        return f"HL7 Table {table_num}"
    return "HL7 v2 Table"


async def search_hl7v2(system_url: str, query: str, limit: int) -> list:
    """Expand an HL7 v2 table CodeSystem via tx.fhir.org and optionally filter."""
    # Convert CodeSystem URL to implicit ValueSet URL for $expand
    vs_url = system_url.replace(
        "http://terminology.hl7.org/CodeSystem/v2-",
        "http://terminology.hl7.org/ValueSet/v2-",
    )
    url = f"{_TX_FHIR}/ValueSet/$expand"
    params: dict = {"url": vs_url, "count": limit, "_format": "json"}
    if query:
        params["filter"] = query
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    system_name = _v2_system_name(system_url)
    results = []
    for item in data.get("expansion", {}).get("contains", []):
        results.append({
            "code": item.get("code", ""),
            "display": item.get("display", ""),
            "system": system_url,
            "systemName": system_name,
        })
    return results


async def lookup_hl7v2(system_url: str, code: str) -> Optional[dict]:
    """Lookup a single code in an HL7 v2 table via tx.fhir.org $lookup."""
    url = f"{_TX_FHIR}/CodeSystem/$lookup"
    params = {"system": system_url, "code": code, "_format": "json"}
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    display = next(
        (p.get("valueString", "") for p in data.get("parameter", []) if p.get("name") == "display"),
        "",
    )
    if not display:
        return None
    return {
        "code": code,
        "display": display,
        "system": system_url,
        "systemName": _v2_system_name(system_url),
        "active": True,
    }


async def subsumes_snomed(codeA: str, codeB: str) -> str:
    """
    Check subsumption between two SNOMED CT concepts via tx.fhir.org.

    Returns one of: 'equivalent' | 'subsumes' | 'subsumed-by' | 'not-subsumed'
    """
    url = f"{_TX_FHIR}/CodeSystem/$subsumes"
    params = {
        "system": "http://snomed.info/sct",
        "codeA": codeA,
        "codeB": codeB,
        "_format": "json",
    }
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, params=params)
    outcome = next(
        (p.get("valueCode", "") for p in data.get("parameter", []) if p.get("name") == "outcome"),
        "not-subsumed",
    )
    return outcome


async def subsumes_loinc(codeA: str, codeB: str) -> Optional[str]:
    """
    Check subsumption between two LOINC codes via fhir.loinc.org.

    Returns outcome string or None if credentials are not configured.
    """
    auth = _loinc_auth_header()
    if not auth:
        return None
    headers = {"Authorization": auth, "Accept": "application/fhir+json"}
    url = f"{_LOINC_FHIR}/CodeSystem/$subsumes"
    params = {
        "system": "http://loinc.org",
        "codeA": codeA,
        "codeB": codeB,
        "_format": "json",
    }
    async with aiohttp.ClientSession() as session:
        data = await _get(session, url, headers=headers, params=params)
    return next(
        (p.get("valueCode", "") for p in data.get("parameter", []) if p.get("name") == "outcome"),
        "not-subsumed",
    )


async def expand_snomed_ecl(ecl: str, filter_text: str, count: int) -> list:
    """
    Expand a SNOMED CT ECL expression via tx.fhir.org.

    ECL examples:
      <<73211009   — Diabetes mellitus and all descendants (self + descendants)
      <73211009    — Proper descendants only
      ^447562003   — Reference set members
      73211009     — Single concept

    tx.fhir.org uses FHIR implicit ValueSet URL formats rather than raw ECL:
      isa/{id}      — concept + all descendants (equivalent to <<{id})
      refset/{id}   — reference set members (equivalent to ^{id})
    Simple single-concept and ECL expressions are translated automatically.
    """
    import re

    ecl = ecl.strip()

    # <<{id} or <{id}  → isa/{id}  (self+descendants or descendants-only, both
    # map to isa/ since tx.fhir.org doesn't distinguish; callers needing strict
    # proper-descendants can post-filter the root concept themselves)
    m = re.match(r'^<{1,2}(\d+)\s*$', ecl)
    if m:
        vs_url = f"http://snomed.info/sct?fhir_vs=isa/{m.group(1)}"
    # ^{refsetId}  → refset/{id}
    elif re.match(r'^\^(\d+)\s*$', ecl):
        refset_id = re.match(r'^\^(\d+)\s*$', ecl).group(1)
        vs_url = f"http://snomed.info/sct?fhir_vs=refset/{refset_id}"
    # Plain concept ID — single concept
    elif re.match(r'^\d+\s*$', ecl):
        vs_url = f"http://snomed.info/sct?fhir_vs=isa/{ecl}"
    else:
        # Complex ECL not reducible to a simple URL — not supported via tx.fhir.org
        raise ValueError(
            f"Complex ECL expressions are not supported via tx.fhir.org: {ecl!r}. "
            "Use simple is-a filters (<<conceptId) or reference set filters (^refsetId)."
        )

    from urllib.parse import urlencode
    qs_params: list = [("url", vs_url), ("count", count), ("_format", "json")]
    if filter_text:
        qs_params.append(("filter", filter_text))
    # urlencode encodes '?' as '%3F' and '=' as '%3D' in param values.
    # Pass as yarl.URL(..., encoded=True) so yarl does not re-normalize and
    # decode '%3F' back to '?' — which would cause tx.fhir.org to misparse the
    # SNOMED implicit ValueSet URL (splitting the query string at the second '?').
    request_url = f"{_TX_FHIR}/ValueSet/$expand?{urlencode(qs_params)}"
    async with aiohttp.ClientSession() as session:
        async with session.get(yarl.URL(request_url, encoded=True), timeout=_TIMEOUT) as resp:
            if not resp.ok:
                body = await resp.text()
                # Extract diagnostics from OperationOutcome if present
                try:
                    import json as _json
                    oo = _json.loads(body)
                    diag = oo.get("issue", [{}])[0].get("diagnostics", body[:300])
                except Exception:
                    diag = body[:300]
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history,
                    status=resp.status, message=diag,
                )
            data = await resp.json(content_type=None)
    results = []
    for item in data.get("expansion", {}).get("contains", []):
        code = item.get("code", "")
        results.append({
            "code": code,
            "display": item.get("display", ""),
            "system": "http://snomed.info/sct",
            "systemName": "SNOMED CT",
            "sourceUrl": f"https://browser.ihtsdotools.org/?perspective=full&conceptId1={code}",
        })
    return results


_VSAC_FHIR = "https://cts.nlm.nih.gov/fhir"
_SNOMED_US_MODULE = "731000124108"


async def expand_snomed_ecl_us(ecl: str, filter_text: str, count: int) -> list:
    """
    Expand a SNOMED CT ECL expression, preferring the US Edition.

    Attempts the US Edition first using the module-qualified URL on tx.fhir.org
    (http://snomed.info/sct/731000124108?fhir_vs=...). If tx.fhir.org does not
    have that module loaded (404/422), falls back transparently to the
    International Edition. Concepts are labelled with the edition that was
    actually served so the caller can tell which path was taken.

    VSAC is intentionally not used here — it does not support arbitrary implicit
    SNOMED ValueSet expansion (only its own curated ValueSets by OID).
    """
    import re
    from urllib.parse import urlencode

    ecl = ecl.strip()
    m = re.match(r'^<{1,2}(\d+)\s*$', ecl)
    if m:
        vs_url_us = f"http://snomed.info/sct/{_SNOMED_US_MODULE}?fhir_vs=isa/{m.group(1)}"
    elif re.match(r'^\^(\d+)\s*$', ecl):
        refset_id = re.match(r'^\^(\d+)\s*$', ecl).group(1)
        vs_url_us = f"http://snomed.info/sct/{_SNOMED_US_MODULE}?fhir_vs=refset/{refset_id}"
    elif re.match(r'^\d+\s*$', ecl):
        vs_url_us = f"http://snomed.info/sct/{_SNOMED_US_MODULE}?fhir_vs=isa/{ecl}"
    else:
        raise ValueError(
            f"Complex ECL expressions are not supported: {ecl!r}. "
            "Use simple is-a filters (<<conceptId) or reference set filters (^refsetId)."
        )

    async def _try_expand(vs_url: str) -> tuple[list, bool]:
        """Returns (contains_list, ok). ok=False means server returned 404/422."""
        qs_params: list = [("url", vs_url), ("count", count), ("_format", "json")]
        if filter_text:
            qs_params.append(("filter", filter_text))
        request_url = f"{_TX_FHIR}/ValueSet/$expand?{urlencode(qs_params)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                yarl.URL(request_url, encoded=True), timeout=_TIMEOUT
            ) as resp:
                if resp.status in (404, 422):
                    return [], False
                if not resp.ok:
                    body = await resp.text()
                    try:
                        import json as _json
                        oo = _json.loads(body)
                        diag = oo.get("issue", [{}])[0].get("diagnostics", body[:300])
                    except Exception:
                        diag = body[:300]
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history,
                        status=resp.status, message=diag,
                    )
                data = await resp.json(content_type=None)
                return data.get("expansion", {}).get("contains", []), True

    # Try US Edition first; fall back to International if module not available.
    contains, us_available = await _try_expand(vs_url_us)
    if not us_available:
        logger.info("SNOMED US Edition not available on tx.fhir.org; falling back to International Edition")
        intl_url = vs_url_us.replace(f"/sct/{_SNOMED_US_MODULE}?", "/sct?")
        contains, _ = await _try_expand(intl_url)

    system_name = "SNOMED CT US Edition" if us_available else "SNOMED CT"
    results = []
    for item in contains:
        code = item.get("code", "")
        results.append({
            "code": code,
            "display": item.get("display", ""),
            "system": "http://snomed.info/sct",
            "systemName": system_name,
            "sourceUrl": f"https://browser.ihtsdotools.org/?perspective=full&conceptId1={code}",
        })
    return results


async def lookup_loinc_with_properties(code: str, properties: list) -> Optional[dict]:
    """
    Lookup a LOINC code and return requested properties (e.g. parent, child, COMPONENT).
    Uses fhir.loinc.org when credentials are configured (full hierarchy including parent/child).
    Falls back to NLM ClinicalTables for axis properties (COMPONENT, PROPERTY, SYSTEM, etc.)
    when credentials are absent — parent/child hierarchy requires credentials.
    """
    auth = _loinc_auth_header()
    if auth:
        param_list = [("system", "http://loinc.org"), ("code", code), ("_format", "json")]
        for prop in properties:
            param_list.append(("property", prop))
        headers = {"Authorization": auth, "Accept": "application/fhir+json"}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{_LOINC_FHIR}/CodeSystem/$lookup", headers=headers,
                                   params=param_list, timeout=_TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        result: dict = {"code": code, "system": "http://loinc.org", "systemName": "LOINC", "properties": []}
        for p in data.get("parameter", []):
            name = p.get("name", "")
            if name == "display":
                result["display"] = p.get("valueString", "")
            elif name == "property":
                parts = {part.get("name"): part for part in p.get("part", [])}
                prop_code = parts.get("code", {}).get("valueCode", "")
                prop_value = (
                    parts.get("value", {}).get("valueCode")
                    or parts.get("value", {}).get("valueString")
                    or parts.get("value", {}).get("valueCoding", {}).get("code")
                )
                if prop_code and prop_value:
                    result["properties"].append({"code": prop_code, "value": prop_value})
        return result

    # No credentials — NLM ClinicalTables fallback for axis properties.
    # parent/child hierarchy is not available without fhir.loinc.org credentials.
    _NLM_AXIS_FIELDS = "LOINC_NUM,LONG_COMMON_NAME,COMPONENT,PROPERTY,TIME_ASPCT,SYSTEM,SCALE_TYP,METHOD_TYP,STATUS,CLASS"
    _NLM_AXIS_IDX: dict = {
        "COMPONENT": 2, "PROPERTY": 3, "TIME_ASPCT": 4,
        "SYSTEM": 5, "SCALE_TYP": 6, "METHOD_TYP": 7,
        "STATUS": 8, "CLASS": 9,
    }
    params_nlm = {"terms": code, "maxList": 5, "df": _NLM_AXIS_FIELDS}
    async with aiohttp.ClientSession() as session:
        data = await _get(session, _NLM_LOINC, params=params_nlm)
    for row in (data[3] if len(data) > 3 and data[3] else []):
        if row[0].upper() == code.upper():
            result_props = []
            for prop in properties:
                idx = _NLM_AXIS_IDX.get(prop.upper())
                if idx is not None and len(row) > idx and row[idx]:
                    result_props.append({"code": prop, "value": row[idx]})
            return {
                "code": code,
                "system": "http://loinc.org",
                "systemName": "LOINC",
                "display": row[1] if len(row) > 1 else "",
                "properties": result_props,
            }
    return None


async def lookup_by_system_url(system_url: str, code: str) -> Optional[dict]:
    """
    Lookup a code using the full system URL.

    Used by fhir_operations for HL7 v2/v3 terminology table URLs that cannot
    be mapped to a fixed connector ID in _SYSTEM_URL_TO_SDO. Delegates to
    tx.fhir.org for any http://terminology.hl7.org/CodeSystem/* URL.
    """
    try:
        return await lookup_hl7v2(system_url, code)
    except Exception as e:
        logger.warning("HL7 terminology lookup failed [%s/%s]: %s", system_url, code, e)
        return None


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_SEARCH_FNS = {
    "snomed": search_snomed,
    "icd10cm": search_icd10cm,
    "rxnorm": search_rxnorm,
    "loinc": search_loinc,
    "vsac": search_vsac,
}

_LOOKUP_FNS = {
    "snomed": lookup_snomed,
    "icd10cm": lookup_icd10cm,
    "loinc": lookup_loinc,
}


async def search(system_id: str, query: str, limit: int = 20) -> list:
    fn = _SEARCH_FNS.get(system_id)
    if not fn:
        return []
    try:
        return await fn(query, limit)
    except Exception as e:
        logger.warning("SDO search failed [%s]: %s", system_id, e)
        return []


async def lookup(system_id: str, code: str) -> Optional[dict]:
    fn = _LOOKUP_FNS.get(system_id)
    if not fn:
        return None
    try:
        return await fn(code)
    except Exception as e:
        logger.warning("SDO lookup failed [%s/%s]: %s", system_id, code, e)
        return None
