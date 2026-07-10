# Flint Technical Architecture

```mermaid
graph TB
    %% ── User / Client ──────────────────────────────────────────────
    User(["Browser / API Client"])

    %% ── Auth ────────────────────────────────────────────────────────
    subgraph auth_layer["Keycloak  :8080"]
        KC["Keycloak 24\nRealm: fhir\nRoles: fhir-patient · fhir-clinician · fhir-admin\nClient: flint-app (PKCE)\nClient: flint-backend (client_credentials)\nTheme: keycloak/themes/flint/"]
    end

    %% ── Entry Point ────────────────────────────────────────────────
    subgraph nginx_layer["Nginx  :80"]
        NGINX["Reverse Proxy · nginx.conf\n\n/auth/  →  Keycloak :8080\n/ai/  →  backend :8000  (120s timeout)\n/mcp-chat/  →  backend :8000  (120s timeout)\n/admin/  →  backend :8000\n/Patient|Claim|Coverage|...  →  backend :8000\n/  →  frontend :5173"]
    end

    %% ── Frontend ────────────────────────────────────────────────────
    subgraph frontend_layer["Frontend  :5173"]
        VITE["React 18 + Vite (HMR)\nNo router — role-based app selection\n\nTerminologyApp  (all roles)\n  App.tsx · ValueSetBuilder.tsx\nClinicalApp  (fhir-clinician)\n  Patient panel · clinical tabs\n  Forms / Prior Auth tabs\nAdminApp  (fhir-admin)\n  FHIR resource CRUD · user mgmt\nSystemApp  (fhir-admin)\n  Bulk export · resource browser\nPatientPortalPage  (fhir-patient)\n  Read-only own record\nLoginGate → AuthCallback → JWT"]
    end

    %% ── Backend ─────────────────────────────────────────────────────
    subgraph backend_layer["Backend  :8000  (FastAPI)"]
        MAIN["main.py\nDatabaseManager · router registration\nSMART auth middleware\nPrometheus /metrics"]

        subgraph routes["Routes"]
            FHIR["fhir_operations.py\nValueSet / CodeSystem / ConceptMap CRUD\n$expand · $validate-code · $validate-batch\n$lookup · $translate · $subsumes · $diff"]
            FACTORY["resource_factory.py\ncreate_resource_router()\n13 clinical/admin types\nPOST · GET · PUT · DELETE\n_history · $audit · $validate\nclinician panel filter\npatient compartment filter"]
            PAS_RT["prior_auth.py\nQuestionnaire · QuestionnaireResponse\nClaim · Coverage · ClaimResponse\nServiceRequest\nPOST /Claim/$submit"]
            BUNDLE["bundle.py\nPOST / (batch/transaction)\nurn:uuid: reference resolution\natomic rollback"]
            SDO_RT["sdo_search.py\nGET /sdo/systems\nGET /sdo/search\nGET /sdo/lookup\nGET /sdo/snomed/children/{id}"]
            AI_RT["ai_assist.py\nPOST /ai/suggest\nPOST /ai/describe\nPOST /ai/map\nGET  /ai/provider\n\nmcp_chat.py\nPOST /mcp-chat/"]
            ADMIN_RT["admin_users.py\nGET /admin/users\nPOST /admin/users/clinician\nPOST /admin/users/patient\nPOST /admin/users/admin\nPATCH /admin/users/{id}/enable|disable"]
        end

        subgraph services["Services"]
            EXT_CS["external_cs.py\nSDO Connector\naiohttp · timeout 15 s\nasyncio.gather fan-out"]
            AI_SVC["_complete(prompt)\nAI provider abstraction\ndispatch via AI_PROVIDER env var"]
        end

        MAIN --> FHIR
        MAIN --> FACTORY
        MAIN --> PAS_RT
        MAIN --> BUNDLE
        MAIN --> SDO_RT
        MAIN --> AI_RT
        MAIN --> ADMIN_RT
        FHIR --> EXT_CS
        SDO_RT --> EXT_CS
        AI_RT --> AI_SVC
        AI_RT --> EXT_CS
    end

    %% ── Storage ──────────────────────────────────────────────────────
    subgraph storage_layer["Storage"]
        PG[("PostgreSQL  :5432\nDB: flint\n\nfhir_resources  (22 types, JSONB)\nresource_versions  (full snapshots)\naudit_log  (every write event)\n\n~2,000 ValueSets\n~1,200 CodeSystems\n21+ Patients · 6+ Practitioners\n...clinical, PAS resources")]
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
    nginx_layer -->|/auth/| auth_layer
    frontend_layer -->|PKCE login| auth_layer
    MAIN -->|JWT validation| auth_layer

    FHIR <-->|read/write| PG
    FACTORY <-->|read/write| PG
    PAS_RT <-->|read/write| PG
    BUNDLE <-->|read/write| PG
    ADMIN_RT -->|Keycloak Admin REST| auth_layer
    FHIR <-->|index/search| ES
    FACTORY <-->|index/search| ES
    AI_RT <-->|cache| REDIS
    SDO_RT <-->|cache| REDIS
    BUNDLE <-->|job state| REDIS

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
| `/auth/*` | Keycloak 24 (SMART on FHIR PKCE / token / discovery) |
| `/ai/*` | `ai_assist.py` — fan-out to SDOs + AI model |
| `/mcp-chat/*` | `mcp_chat.py` — tool-calling AI chat backed by FHIR endpoints |
| `/admin/*` | `admin_users.py` — Keycloak user management |
| `/sdo/*` | `sdo_search.py` → `external_cs.py` |
| `/ValueSet`, `/CodeSystem`, `/ConceptMap` CRUD | `fhir_operations.py` → PostgreSQL + ES |
| `/$expand`, `/$lookup`, `/$validate*`, `/$translate`, `/$subsumes` | `fhir_operations.py` → local or delegate |
| `/Patient`, `/Observation`, `/Condition`, `/Encounter`, ... (13 types) | `resource_factory.py` (generated routers) → PostgreSQL |
| `/Questionnaire`, `/QuestionnaireResponse`, `/Claim`, `/Coverage`, `/ClaimResponse`, `/ServiceRequest` | `prior_auth.py` (generated routers) → PostgreSQL |
| `POST /Claim/$submit` | `prior_auth.py` — PAS workflow |
| `POST /` (Bundle) | `bundle.py` — batch/transaction |
| `/jobs/*`, `/$export` | `bulk_export.py` — async NDJSON export |
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
