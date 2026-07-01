# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Repository Layout

All application code lives in `flint/`. There is no other code at the repository root.

```
FHIR-Server/
└── flint/          ← entire project lives here
    ├── backend/    ← FastAPI app (Python)
    ├── frontend/   ← React/Vite app (TypeScript)
    ├── migration/  ← terminology import scripts
    ├── infrastructure/docker/nginx/
    ├── docs/
    ├── Makefile
    └── docker-compose.yml + override + prod
```

A detailed `flint/CLAUDE.md` covers architecture, backend/frontend conventions, SDO integrations, deployment, and known issues.

---

## Common Commands

All commands run from `flint/`.

```bash
# Start core services (postgres, elasticsearch, redis, backend, frontend, nginx)
make start
# or
docker compose up -d

# Start with observability (Prometheus, Grafana, Loki)
make start-obs

# Rebuild a single service
docker compose up -d --build backend
docker compose up -d --build frontend   # required after vite.config.ts changes

# Run backend tests
docker compose exec backend pytest

# Run frontend lint
cd frontend && npm run lint

# Run frontend tests
cd frontend && npm test

# Reload nginx config (no restart)
docker compose exec nginx nginx -s reload

# Tail logs
docker compose logs backend -f

# Stop everything
make stop
```

---

## Stack at a Glance

**Flint** is a general-purpose FHIR R4 server — custom-built in Python, not HAPI FHIR or any Java-based framework.

| Layer | Technology |
|---|---|
| Backend | FastAPI + asyncpg (PostgreSQL 15) |
| Search | Elasticsearch 8.11 |
| Cache | Redis 7 |
| Frontend | React 18 + TypeScript + Vite + Tailwind |
| Proxy | Nginx |
| Observability | Prometheus + Grafana + Loki + Promtail |
| AI | Anthropic / OpenAI / Gemini (switchable via `AI_PROVIDER` env var) |

Services run on: Nginx `localhost:80`, API `localhost:8000`, Vite `localhost:5173`, Grafana `localhost:3001`.

---

## Key Architecture Notes

- **FHIR models** are hand-rolled Pydantic classes — no fhir.resources library. Terminology models (`ValueSet`, `CodeSystem`, `ConceptMap`) live in `main.py`; clinical/admin models are in `app/models/` (`clinical.py`, `administrative.py`, `medications.py`).
- **Route split:**
  - `main.py` — CRUD + search for `ValueSet` / `CodeSystem` / `ConceptMap`; `DatabaseManager`; app startup
  - `routes/fhir_operations.py` — All FHIR operations: `$expand`, `$validate-code`, `$lookup`, `$translate`, `$subsumes`, `$validate-batch`, `$diff`
  - `routes/resource_factory.py` — Generic factory that generates 9 standard FHIR handlers per resource type
  - `routes/clinical.py` / `administrative.py` / `medications.py` — Search hooks + CapabilityStatement registration for 13 clinical/admin resource types
  - `routes/bundle.py` — `POST /` Bundle processor (batch + transaction with atomic rollback)
  - `routes/sdo_search.py` — SDO connector search; `routes/ai_assist.py` — AI endpoints
- **Shared utilities:** `app/fhir_utils.py` — Prometheus metrics, `_fhir_response`, `_check_etag`, `_bundle_links`; `app/capability.py` — `RESOURCE_REGISTRY` populated at import time, consumed by `/metadata`.
- **Code system storage tiers:** `content = "complete"` → serve from Postgres; `content = "not-present"` or `"fragment"` → delegate to external SDO connectors in `services/external_cs.py`.
- **Dev vs prod:** `docker-compose.override.yml` auto-loads in dev (hot-reload, src mounts). For prod/demo, explicitly pass `-f docker-compose.prod.yml --env-file .env.prod`.
- **vite.config.ts** is baked into the Docker image, not volume-mounted — changes require `--build frontend`.
- **Nginx route order matters:** `/ai/` block before FHIR regex block; `location = /` (exact) before `location /` (prefix) to route `POST /` to the Bundle endpoint while `GET /` goes to the frontend.
