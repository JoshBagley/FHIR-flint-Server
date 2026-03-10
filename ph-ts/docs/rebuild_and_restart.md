# Rebuild & Restart Guide

All commands run from the `ph-ts` project directory:

```bash
cd ph-ts
```

---

## Quick Reference

| Change made | Command |
|-------------|---------|
| `App.tsx` / frontend code | `docker compose up -d --build frontend` |
| `main.py` / backend code | `docker compose up -d --build backend` |
| `nginx.conf` | `docker compose restart nginx` |
| `requirements.txt` | `docker compose up -d --build backend` |
| `docker-compose.yml` | `docker compose up -d` |
| Database schema change | `docker compose down -v && docker compose up -d --build` |

---

## Commands

### Restart everything (no rebuild)

Use when you only changed config files (`.env`, `nginx.conf`, etc.):

```bash
docker compose restart
```

### Rebuild only what changed

Rebuilds only the backend and frontend images, then restarts affected containers:

```bash
docker compose up -d --build backend frontend
```

### Rebuild everything and restart

```bash
docker compose up -d --build
```

### Full teardown and clean restart

Removes containers, networks, and named volumes (clears the database):

```bash
docker compose down -v
docker compose up -d --build
```

> **Warning:** `-v` deletes the PostgreSQL, Elasticsearch, and Redis data volumes. All imported terminology data will be lost.

---

## Watch Logs After Starting

```bash
# All services
docker compose logs -f

# Just backend and nginx
docker compose logs -f backend nginx

# Check which containers are running and healthy
docker compose ps
```

---

## Verify It's Working

```bash
# Health check — should return {"status":"healthy",...}
curl http://localhost/health

# Open the UI in a browser
start http://localhost
```

---

## Optional Admin Services

pgAdmin (database browser) and Kibana (Elasticsearch browser) are disabled by default. Start them with the `admin` profile:

```bash
docker compose --profile admin up -d
```

Access at:
- pgAdmin: http://localhost:5050
- Kibana: http://localhost:5601
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
