# Legacy Link Continuity — Demo Presentation
## PH-TS: PHIN VADS URL Preservation

**Audience:** Public health informatics stakeholders, vocabulary teams, IT leadership  
**Date:** 2026-04-14  
**Feature:** Mock PHIN VADS Legacy URL Redirect

---

## 1. The Problem

PHIN VADS has been the CDC's primary public health vocabulary repository for over a decade. Across the public health community, legacy links to PHIN VADS value sets are embedded in:

- Data dictionaries and data standards documentation
- Case report forms (CRFs) and implementation guides
- Email threads, internal wikis, and SOPs
- Surveillance system configurations and ETL pipelines

A link like:

```
http://phinvads.cdc.gov/vads/ViewValueSet.action?oid=2.16.840.1.114222.4.11.1038
```

…carries institutional meaning. If PHIN VADS becomes unavailable or is deprecated, every one of these links breaks — silently sending users to a dead page with no indication of where the resource has moved.

**The goal:** When PH-TS serves as the replacement vocabulary service, legacy PHIN VADS links should continue to work — transparently routing users to the equivalent resource in PH-TS, with no manual lookup required.

---

## 2. The Solution: Transparent URL Redirect + OID Deep-Link

PH-TS implements a two-layer redirect chain that transforms a legacy PHIN VADS URL into a fully-resolved resource view in the PH-TS UI.

### Layer 1 — DNS + Nginx: Domain Intercept

The `phinvads.test` hostname (or, in a real deployment, the actual PHIN VADS domain) is mapped to the PH-TS server via a hosts file or DNS entry. Nginx intercepts the legacy URL and issues an HTTP 302 redirect:

```
GET http://phinvads.test/vads/ViewValueSet.action?oid=2.16.840.1.114222.4.11.1038

→ 302 Redirect →

http://localhost/?phts_oid=2.16.840.1.114222.4.11.1038&phts_type=ValueSet
```

Both `ValueSet` and `CodeSystem` path patterns are handled:

| Legacy Path | Redirects To |
|---|---|
| `/vads/ViewValueSet.action?oid={oid}` | `/?phts_oid={oid}&phts_type=ValueSet` |
| `/vads/ViewCodeSystem.action?id={oid}` | `/?phts_oid={oid}&phts_type=CodeSystem` |

> **Note:** Real PHIN VADS uses `?oid=` for ValueSet URLs and `?id=` for CodeSystem URLs. Nginx handles both parameter names — `?oid=` is also accepted for local test URLs.

The `.test` TLD is IANA-reserved (never publicly resolvable), which avoids browser HSTS preloading issues that would affect anything under `*.cdc.gov`.

### Layer 2 — React Deep-Link Handler: OID Lookup + Auto-Open

When the PH-TS frontend loads with `?phts_oid=` in the URL, a `useEffect` hook fires after the initial resource list has loaded (to avoid a race condition with the list's own drawer reset):

1. Reads `phts_oid` and `phts_type` from `window.location.search`
2. Calls `GET /{type}?identifier={oid}&_summary=true` against the PH-TS API
3. If a match is found, switches to the correct tab (ValueSet or CodeSystem) and opens the resource detail drawer automatically
4. Cleans the URL with `history.replaceState` so the query params don't persist on refresh

The OID lookup is resilient: the identifier search strips `urn:oid:` prefixes automatically and queries the stored `identifier[].value` JSONB array, matching the bare OID regardless of how it was originally imported.

---

## 3. Demo Flow

**Setup (one-time, local demo):**
```
# Windows hosts file (run Notepad as Administrator):
# C:\Windows\System32\drivers\etc\hosts
127.0.0.1   phinvads.test
```

**Live demo URLs:**
```
# ValueSet (Condition — COVID-19)
http://phinvads.test/vads/ViewValueSet.action?oid=2.16.840.1.114222.4.11.1038

# CodeSystem (HL7 table 0323 — Action Code)
http://phinvads.test/vads/ViewCodeSystem.action?id=2.16.840.1.113883.12.323
```

**What the audience sees:**
1. Browser navigates to a URL that looks exactly like a PHIN VADS link
2. Without any user action, the page lands on the PH-TS home screen
3. The matching resource detail drawer opens automatically — title, OID, concepts, metadata all visible
4. The URL bar is clean (`http://localhost/`) — no query parameters persisted

---

## 4. Technical Architecture Summary

```
User clicks legacy PHIN VADS link
        │
        ▼
[DNS / hosts file]
phinvads.test → 127.0.0.1 (PH-TS server)
        │
        ▼
[Nginx — phinvads.test server block]
/vads/ViewValueSet.action?oid={oid}
        │  HTTP 302
        ▼
http://localhost/?phts_oid={oid}&phts_type=ValueSet
        │
        ▼
[React — App.tsx deepLink useEffect]
Waits for loadingResources = false
        │
        ▼
GET /ValueSet?identifier={oid}&_summary=true
        │
        ▼
[FastAPI — search_resources()]
Strips urn:oid: prefix if present
Queries identifier[].value in JSONB
        │
        ▼
Returns matching ValueSet (summary)
        │
        ▼
setActiveTab('ValueSet')
setSelectedResource(first match)
→ Detail drawer opens automatically
        │
        ▼
history.replaceState → URL cleaned
```

---

## 5. Key Technical Points for Stakeholders

| Concern | Answer |
|---|---|
| **Does this require changes to existing links?** | No. Links work as-is; only DNS/hosts routing changes. |
| **Does it work for CodeSystems too?** | Yes. `/vads/ViewCodeSystem.action?oid=` is handled identically. |
| **What if the OID isn't in PH-TS?** | The drawer simply doesn't open; the user lands on the normal home screen. No error displayed. |
| **Is HSTS / browser security an issue?** | No. The `.test` TLD is IANA-reserved and never HSTS-preloaded. CDC domains with HSTS would require additional cert configuration in production. |
| **Production deployment path** | Replace `phinvads.test` with the real PHIN VADS hostname in nginx + DNS. No code changes needed. |
| **Does it break when PHIN VADS is live?** | Only when DNS or hosts routing is active. In production this is a deliberate cutover, not an accidental intercept. |

---

## 6. What's in PH-TS That Makes This Meaningful

The redirect is only useful because PH-TS holds a comprehensive import of PHIN VADS content:

- **1,998 ValueSets** imported from PHIN VADS exports
- **1,176 CodeSystems** (including SDO-backed: SNOMED CT, LOINC, ICD-10-CM, RxNorm)
- **988 ValueSets** tagged to PHIN VADS disease/condition program views (2,750 tags)
- Full OID preservation in the `identifier` field of every imported resource
- Source provenance tracked (`phinvads` badge displayed per resource)

Every resource retains its original PHIN VADS OID, which is what the legacy URL carries — making the lookup deterministic and reliable.

---

## 7. Scope and Limitations

**In scope (current):**
- `ViewValueSet.action?oid=` and `ViewCodeSystem.action?id=` URL patterns (real PHIN VADS parameter names)
- `?oid=` also accepted for CodeSystem URLs (local test convenience)
- OID-based lookup (the primary PHIN VADS identifier)
- Local demo via `phinvads.test` and hosts file

**Not in scope (future work if needed):**
- Version-specific PHIN VADS links (e.g. `version=` query params — PH-TS would open the current version)
- Redirecting PHIN VADS API calls (not just UI links)
- Full production DNS cutover (requires infrastructure coordination)
- Handling OIDs that were never imported into PH-TS (graceful 404 messaging could be added)

---

## 8. Summary

PH-TS implements a transparent, zero-code-change path for legacy PHIN VADS URL continuity. A link written years ago, embedded in a data dictionary or an email, continues to resolve — landing the user directly on the correct resource in the new system. The mechanism is lightweight (nginx redirect + a 20-line React effect), reliable (OID is the durable identifier), and production-ready with only a DNS change required.
