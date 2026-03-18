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
