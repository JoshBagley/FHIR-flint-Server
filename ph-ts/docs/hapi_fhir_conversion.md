# HAPI FHIR Conversion Review

**Date:** 2026-04-14  
**Question:** What would it look like to replace the custom FastAPI FHIR core with HAPI FHIR Server?

---

## What HAPI Gives You For Free

| Feature | Current (custom) | HAPI |
|---|---|---|
| FHIR R4 conformance | Hand-rolled Pydantic | Fully conformant, certified |
| `$expand`, `$validate-code`, `$lookup` | Custom implementations | Built-in, spec-compliant |
| Search parameters | Custom SQL | Auto-generated from StructureDefinitions |
| Capability Statement | Manually maintained | Auto-generated |
| Resource versioning | Custom `resource_versions` table | Built-in `_history` |
| FHIR subscriptions | Not present | Built-in |
| Terminology loader | Custom SDO connectors | Native SNOMED CT/LOINC loaders (via NPM/ZIP artifacts) |

---

## What You'd Lose or Have to Rebuild

### 1. SDO Connectors
HAPI's built-in terminology support requires loading artifacts (e.g. a SNOMED CT RF2 release zip, a LOINC distribution). The current connectors do live query against NLM ClinicalTables, VSAC API, and tx.fhir.org instead of holding local copies. That logic doesn't translate — you'd either:
- Keep a Python sidecar service for live SDO search (`/sdo/*` routes), or
- Load full artifact snapshots into HAPI's database (large, slow to update)

### 2. Custom Operations
`$views`, `$tag-view`, `$diff`, `$stats` are PH-TS-specific. In HAPI, custom operations require writing Java `IResourceProvider` or `IOperationProvider` interceptors. These aren't trivial — you'd write Java code for each.

### 3. AI + MCP Endpoints
These can't live in HAPI at all. They'd become a separate Python service (`/ai/*`, `/mcp-chat/*`). Nginx would proxy `/ai` and `/mcp-chat` to the Python sidecar, and FHIR operations to HAPI. Architecturally sound but adds a service boundary.

### 4. Disease Views / Source Extension
The `useContext`-based views system is stored as JSONB extensions. HAPI stores resources in its own normalized JPA schema — the custom source extension would survive (it's valid FHIR), but the `sync_log` table, tagging logic, and admin sync endpoints would all need to move to the sidecar.

### 5. Data Migration
~1,998 ValueSets + 1,176 CodeSystems + ConceptMaps currently in PostgreSQL JSONB. Migration to HAPI would mean `PUT`-ing every resource via FHIR REST to populate HAPI's JPA schema. Technically straightforward (a migration script), but HAPI's schema is completely different — no JSONB, normalized relational tables.

---

## What the New Architecture Would Look Like

```
Nginx
├── /fhir/*          → HAPI FHIR (Java, port 8080)
│                        └── PostgreSQL (HAPI's schema)
├── /sdo/*           → Python sidecar (FastAPI, port 8001)
├── /ai/*            → Python sidecar
├── /mcp-chat/*      → Python sidecar
├── /admin/*         → Python sidecar
└── /                → React frontend (unchanged)
```

The sidecar essentially becomes the non-FHIR half of the current `main.py` + all route modules. HAPI handles the FHIR REST layer.

---

## Key Costs

| Item | Effort |
|---|---|
| HAPI setup + Postgres config | Low (Docker image, config yaml) |
| Data migration script | Medium (bulk PUT via FHIR REST) |
| Custom operation interceptors (Java) | High ($views, $tag-view, $diff, $stats) |
| Sidecar refactor (SDO, AI, admin, MCP) | Medium (extract from current main.py) |
| Memory: HAPI JVM | ~1–2 GB RAM minimum vs ~200–300 MB for FastAPI |
| Conformance testing | Lower risk (HAPI is Touchstone-tested) |

---

## Verdict

For a **vanilla terminology server** (search CodeSystems, expand ValueSets, validate codes against SDO content), HAPI is a strong default — certification-grade FHIR conformance for free.

For **PH-TS specifically**, the custom operations, AI layer, live SDO connectors, and disease views system mean maintaining a Python sidecar that does most of the interesting work anyway. HAPI would handle CRUD and standard operations, which the custom stack already handles correctly.

**Genuine wins from HAPI:**
- Better FHIR search parameter support (no hand-rolled SQL for every filter)
- Automatic `_history` without maintaining `resource_versions`
- Interoperability — external clients expecting strict FHIR conformance have fewer surprises

**Recommendation:** If CDC interoperability or Touchstone certification ever becomes a requirement, HAPI is the right move. If PH-TS stays an internal PH tool, the migration cost likely doesn't pay off.
