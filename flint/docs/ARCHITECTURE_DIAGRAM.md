# Flint Technical Architecture

```mermaid
graph TB
    %% ── User / Client ──────────────────────────────────────────────
    User(["Browser / API Client"])

    %% ── Entry Point ────────────────────────────────────────────────
    subgraph nginx_layer["Nginx  :80"]
        NGINX["Reverse Proxy\nnginx.conf\n\n/ai/  →  backend :8000\n/ValueSet|CodeSystem|...  →  backend :8000\n/  →  frontend :5173"]
    end

    %% ── Frontend ────────────────────────────────────────────────────
    subgraph frontend_layer["Frontend  :5173"]
        VITE["React + Vite (HMR)\nApp.tsx\nValueSetBuilder.tsx\n└─ 3-panel VS editor\n└─ Vocabulary AI Assistant chat"]
    end

    %% ── Backend ─────────────────────────────────────────────────────
    subgraph backend_layer["Backend  :8000  (FastAPI)"]
        MAIN["main.py\nrouter registration\nPrometheus /metrics"]

        subgraph routes["Routes"]
            FHIR["fhir_operations.py\nValueSet CRUD / $expand\nCodeSystem $lookup / $validate\nConceptMap $translate\n$subsumes · $diff · _history\nPOST $validate-batch (200 codes)"]
            SDO_RT["sdo_search.py\nGET /sdo/systems\nGET /sdo/search\nGET /sdo/lookup"]
            AI_RT["ai_assist.py\nPOST /ai/suggest\nPOST /ai/describe\nPOST /ai/map\nGET  /ai/provider"]
        end

        subgraph services["Services"]
            EXT_CS["external_cs.py\nSDO Connector\naiohttp · timeout 15 s\nasyncio.gather fan-out"]
            AI_SVC["_complete(prompt)\nAI provider abstraction\ndispatch via AI_PROVIDER env var"]
        end

        MAIN --> FHIR
        MAIN --> SDO_RT
        MAIN --> AI_RT
        FHIR --> EXT_CS
        SDO_RT --> EXT_CS
        AI_RT --> AI_SVC
        AI_RT --> EXT_CS
    end

    %% ── Storage ──────────────────────────────────────────────────────
    subgraph storage_layer["Storage"]
        PG[("PostgreSQL  :5432\nDB: flint\n\nfhir_resources\nresource_versions\nidx_unique_resource_url_version\n\n2,017 ValueSets\n1,176 CodeSystems\n1 ConceptMap")]
        ES[("Elasticsearch  :9200\nIndex: fhir_resources\nnested objects limit: 50,000\nFull-text + concept search")]
        REDIS[("Redis  :6379\nSession / cache")]
    end

    %% ── Observability ────────────────────────────────────────────────
    subgraph obs_layer["Observability"]
        PROM["Prometheus  :9090\nscrapes /metrics every 15 s"]
        LOKI["Loki  :3100\nLog aggregation"]
        PROMTAIL["Promtail\nDocker SD → Loki\nmounts docker.sock"]
        GRAFANA["Grafana  :3001\nFlint Server Overview (metrics)\nFlint Logs (LogQL)"]
    end

    %% ── Dev / Admin UIs ──────────────────────────────────────────────
    subgraph admin_layer["Admin Tools"]
        ADMINER["Adminer  :8181\nPostgreSQL browser"]
        KIBANA["Kibana  :5601\nElasticsearch browser"]
    end

    %% ── External SDO APIs ────────────────────────────────────────────
    subgraph external_sdo["External SDO APIs"]
        SNOMED["SNOMED CT\nSnowstorm public FHIR\n(no auth)"]
        ICD10["ICD-10-CM\nNLM ClinicalTables\n(no auth)"]
        LOINC_EXT["LOINC\nNLM ClinicalTables\n(no auth)"]
        RXNORM["RxNorm\nNLM RxNav REST\n(no auth)"]
        VSAC["VSAC\ncts.nlm.nih.gov/fhir\n(UMLS API key)"]
        HL7TX["HL7 v2 Tables\ntx.fhir.org\n(fallback only)"]
    end

    %% ── External AI APIs ─────────────────────────────────────────────
    subgraph external_ai["External AI APIs  (active: Gemini)"]
        GEMINI["Google Gemini\ngemini-2.0-flash"]
        ANTHROPIC["Anthropic\nclaude-sonnet-4-6"]
        OPENAI["OpenAI\ngpt-4o"]
    end

    %% ── Migration Tools ──────────────────────────────────────────────
    subgraph migration["Migration / Import Scripts"]
        MIG1["import_hl7_core.py\n~981 HL7 R4 CodeSystems"]
        MIG2["import_hl7_v2_tables.py\n~200 v2 table CodeSystems"]
        MIG3["import_icd9cm.py\n~14 k ICD-9-CM codes"]
        MIG4["import_phinvads_txt.py\n1,994 PHIN VADS ValueSets"]
        MIG5["phinvads_migrate.py\nPHIN VADS STU3 API\nSTU3→R4 conversion"]
    end

    %% ── Connections ──────────────────────────────────────────────────
    User -->|HTTP| nginx_layer
    nginx_layer -->|proxy| frontend_layer
    nginx_layer -->|proxy| backend_layer

    FHIR <-->|read/write| PG
    FHIR <-->|index/search| ES
    AI_RT <-->|cache| REDIS
    SDO_RT <-->|cache| REDIS

    EXT_CS -->|delegate $expand/$lookup| SNOMED
    EXT_CS -->|delegate $expand/$lookup| ICD10
    EXT_CS -->|delegate $expand/$lookup| LOINC_EXT
    EXT_CS -->|delegate $expand/$lookup| RXNORM
    EXT_CS -->|delegate $expand/$lookup| VSAC
    EXT_CS -->|fallback v2 tables| HL7TX

    AI_SVC -->|AI_PROVIDER=gemini| GEMINI
    AI_SVC -.->|AI_PROVIDER=anthropic| ANTHROPIC
    AI_SVC -.->|AI_PROVIDER=openai| OPENAI

    PROM -->|scrape /metrics| MAIN
    PROMTAIL -->|ship logs| LOKI
    LOKI --> GRAFANA
    PROM --> GRAFANA

    ADMINER <-->|SQL| PG
    KIBANA <-->|REST| ES

    migration_layer -->|POST FHIR R4| nginx_layer

    subgraph migration_layer[""]
        MIG1
        MIG2
        MIG3
        MIG4
        MIG5
    end

    %% ── Code System Storage Tiers (annotation) ───────────────────────
    %% complete  → HL7 core, ICD-9-CM, ICD-10-CM  (stored in PG)
    %% not-present → SNOMED CT, CPT               (delegate only)
    %% fragment  → LOINC                           (partial PG + delegate)
```

## Code System Storage Tiers

| Tier | `content` value | Concepts stored | Examples |
|---|---|---|---|
| Complete | `complete` | PostgreSQL | HL7 FHIR core, ICD-9-CM, ICD-10-CM, HL7 v2 tables |
| Stub | `not-present` | None (delegate only) | SNOMED CT, CPT |
| Fragment | `fragment` | Partial subset | LOINC |

`$expand` / `$lookup` check `CodeSystem.content` → local concepts first, then fall through to `external_cs.py` connectors.

## Request Routing Summary

| Path pattern | Handler |
|---|---|
| `/ai/*` | `ai_assist.py` — fan-out to SDOs + AI model |
| `/sdo/*` | `sdo_search.py` → `external_cs.py` |
| `/ValueSet`, `/CodeSystem`, `/ConceptMap` CRUD | `fhir_operations.py` → PostgreSQL + ES |
| `/$expand`, `/$lookup`, `/$validate*`, `/$translate`, `/$subsumes` | `fhir_operations.py` → local or delegate |
| `/metrics` | Prometheus scrape endpoint (Starlette middleware) |

## Port Reference

| Service | Port |
|---|---|
| Nginx (entry point) | 80 |
| Vite dev server | 5173 |
| FastAPI backend | 8000 |
| PostgreSQL | 5432 |
| Elasticsearch | 9200 |
| Redis | 6379 |
| Grafana | 3001 |
| Prometheus | 9090 |
| Loki | 3100 |
| Adminer | 8181 |
| Kibana | 5601 |
