# Troubleshooting Guide

## Quick Diagnostic

```bash
# 1. Are all containers running?
docker compose ps

# 2. Is the stack healthy?
curl http://localhost/health

# 3. Any recent errors?
docker compose logs --tail=50 backend
docker compose logs --tail=50 nginx
```

---

## Common Issues

### Docker Desktop not running

**Symptom:**
```
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

**Fix:** Start Docker Desktop and wait ~30 seconds before retrying.

---

### 502 Bad Gateway

**Symptoms:** Browser shows `502 Bad Gateway` when accessing http://localhost.

**Diagnose:**
```bash
docker compose ps
# Look for any service not in "Up (healthy)" state

docker compose logs backend --tail=30
docker compose logs nginx --tail=20
```

**Most common causes:**

1. **Backend still starting** — wait 30–60 s after `docker compose up`. The backend waits for Postgres, Elasticsearch, and Redis to be healthy before starting.
2. **Elasticsearch out of memory** — increase Docker Desktop memory allocation to 4 GB+ (Settings → Resources → Memory).
3. **Backend crashed** — check `docker compose logs backend` for Python tracebacks.

```bash
# Force restart
docker compose restart backend
```

---

### Postgres authentication failed

**Symptom:**
```
FATAL: password authentication failed for user "phts"
```

**Fix:** Check the actual password in `.env`:
```bash
cat .env | grep POSTGRES_PASSWORD
```

Use that value (not a hardcoded default) when connecting via Adminer or psql.

**Adminer connection details:**
| Field | Value |
|-------|-------|
| Server | `postgres` |
| Username | `phts` |
| Password | _(value from `.env`)_ |
| Database | `phts` |

If the password in `.env` was changed after the volume was first created, the volume still holds the old credentials. Reset:
```bash
docker compose down -v   # deletes all data
docker compose up -d --build
```

---

### Frontend shows stale code / HMR not working

**Cause A — Vite HMR polling not active:**

Check whether the container has the current `vite.config.ts`:
```bash
docker compose exec frontend cat vite.config.ts
```

It should contain `usePolling: true`. If not, the image needs a rebuild (the config is baked in, not volume-mounted):
```bash
docker compose up -d --build frontend
```

Then do a hard browser refresh: `Ctrl+Shift+R`.

**Cause B — Change was made outside `frontend/src/`:**

Files outside `src/` (e.g., `vite.config.ts`, `package.json`, `tailwind.config.js`) are not volume-mounted. Any change to them requires a rebuild:
```bash
docker compose up -d --build frontend
```

---

### Port already in use

**Symptom:**
```
Bind for 0.0.0.0:XXXX failed: port is already allocated
```

**Find the conflicting process:**
```bash
# Windows
netstat -ano | findstr :8181

# macOS/Linux
lsof -i :8181
```

Then either kill the process or change the host-side port in `docker-compose.yml`:
```yaml
ports:
  - "8282:8080"   # change 8181 to any free port
```

---

### Migration script — HTML response / WAF block

**Symptom:**
```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
# or
Received HTML response from PHIN VADS — WAF may be blocking
```

**Fix:** The PHIN VADS WAF blocks requests with non-standard User-Agent or Accept headers. Ensure the migration script is using the corrected headers (no custom User-Agent, `Accept: application/json, */*`).

Run with debug logging to see raw responses:
```bash
python phinvads_migrate.py --oid <oid> --log-level DEBUG
```

---

### Migration script — HTTP 422 on import

**Symptom:** Resources fetch successfully but POST to the local server returns `422 Unprocessable Entity`.

**Fix:** Run a dry-run and inspect the generated JSON:
```bash
python phinvads_migrate.py --oid <oid> --dry-run --output-dir ./exported
```

Open the exported file and check for missing required fields. Common issues:
- `date` field is a FHIR `date` type (e.g., `"2019-02-23"`) — ensure the server model accepts `Optional[str]`, not `Optional[datetime]`.
- `status` not normalised — should be one of `active`, `draft`, `retired`, `unknown`.

---

### Migration script — Unicode error on Windows

**Symptom:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'
```

**Cause:** Windows console defaults to cp1252, which cannot encode the arrow/check characters used in log messages.

**Fix:** The script should already configure its stream handler with `encoding='utf-8'`. If you still see this, run:
```bash
set PYTHONIOENCODING=utf-8
python phinvads_migrate.py ...
```

---

### $expand returns empty or error

**Symptom:** Clicking "View Expansion" shows "This ValueSet has no concepts" or an error.

**Check:**
```bash
# Does the ValueSet exist?
curl "http://localhost/ValueSet?name=<name>"

# Does it expand?
curl "http://localhost/ValueSet/\$expand?url=<url>&count=10"
```

**Common causes:**
- The ValueSet uses `compose.include` with only a `system` reference and no inline `concept` list — expansion may not be fully supported for external code systems.
- The URL parameter must exactly match the `url` field stored in the resource (case-sensitive).

---

### Elasticsearch index out of sync

After a bulk import or crash, search results may not reflect the database contents.

```bash
# Check ES cluster health
curl http://localhost:9200/_cluster/health?pretty

# Check index stats
curl http://localhost:9200/_cat/indices?v
```

To rebuild the index, restart the backend (it re-indexes on startup if the index is missing):
```bash
docker compose restart backend
```

---

### Out of memory / Elasticsearch keeps crashing

**Symptom:** `docker compose ps` shows `phts-elasticsearch` restarting repeatedly.

**Fix:**

1. Increase Docker Desktop memory: Settings → Resources → Memory → set to **4 GB minimum, 8 GB recommended**
2. Reduce Elasticsearch heap in `docker-compose.yml`:
   ```yaml
   environment:
     - "ES_JAVA_OPTS=-Xms256m -Xmx256m"
   ```
3. Restart:
   ```bash
   docker compose up -d elasticsearch
   ```

---

## Health Check Checklist

```bash
# Containers running?
docker compose ps

# Nginx / load balancer
curl http://localhost/health
# Expected: healthy

# Backend API
curl http://localhost:8000/health
# Expected: {"status":"healthy","database":"connected","search":"connected","cache":"connected"}

# FHIR metadata
curl http://localhost/metadata
# Expected: {"resourceType":"CapabilityStatement",...}

# PostgreSQL
docker compose exec postgres psql -U phts -d phts -c "SELECT count(*) FROM resources;"

# Elasticsearch
curl http://localhost:9200/_cluster/health
# Expected: "status":"green" or "yellow"

# Redis
docker compose exec redis redis-cli ping
# Expected: PONG
```

---

## Nuclear Reset

If nothing else works, wipe all data and start fresh:

```bash
docker compose down -v           # stop containers + delete volumes
docker system prune -a -f        # remove all unused images (frees disk)
docker compose up -d --build     # rebuild from scratch
```

> This permanently deletes all imported terminology data. Re-run the migration tool to reload.
